# -*- coding: utf-8 -*-
"""
主动型/FOF 基金持仓估值

数据源：
  1. 天天基金 f10 季报重仓股（FundArchivesDatas.aspx?type=jjcc，HTML 正则解析，
     每行含东财 secid 如 0.002353 / 1.688548 + 名称 + 占净值比例）。
  2. 东财 push2delay stock/get 抓重仓股当日涨跌幅（f170）。

估算净值 = 最新官方净值 × (1 + Σ(重仓股占净值比例 × 个股当日涨跌))
  未覆盖仓位（重仓股之外）视为当日涨跌为 0，属保守近似（集思录同法）。

季报数据按代码持久化缓存（约 90 天有效），避免每次启动重复抓取。
"""
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# 值得持仓估值的主动型/FOF 特征词（匹配到才尝试抓季报，控制请求量）
ACTIVE_HINTS = (
    "混合", "灵活", "精选", "优选", "成长", "价值", "优势", "回报", "策略",
    "主题", "产业", "新兴", "行业", "蓝筹", "龙头", "创新", "核心", "领先",
    "内需", "转型", "均衡", "质量", "品质", "配置", "FOF", "科创",
)

# 债券型特征词：名称命中则视为债基（无 A 股股票持仓，不参与持仓估值）
BOND_HINTS = (
    "债", "转债", "添利", "增利", "丰利", "丰润", "丰泽", "丰和", "丰锐",
    "同利", "金利", "聚利", "天盈", "天锋", "天丰", "永兴", "永旭", "通福",
    "惠裕", "强化收益", "四季", "岁丰", "汇利", "通利",
)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://fundf10.eastmoney.com/",
    "Accept": "*/*",
}
_QUOTE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "*/*",
}

_session: Optional[requests.Session] = None
_holdings_mem: Dict[str, Optional[dict]] = {}
_holdings_lock = threading.Lock()
_stock_lock = threading.Lock()
_stock_cache: Dict[str, object] = {}

_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "holdings_cache.json")
_CACHE_TTL = 90 * 86400  # 季报约 90 天


def _sess() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.trust_env = False
    return _session


def _load_file_cache() -> dict:
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_file_cache(cache: dict) -> None:
    try:
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception as e:
        logger.warning("Save holdings cache failed: %s", e)


def fetch_holdings(code: str, retries: int = 3) -> Optional[dict]:
    """抓取 f10 jjcc 重仓股。返回 {date, stocks:[{name,secid,weight_pct}]} 或 None（无股票持仓/数据过旧）。"""
    url = (f"https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
           f"?type=jjcc&code={code}&topline=10")
    for attempt in range(retries + 1):
        try:
            resp = _sess().get(url, headers=_HEADERS, timeout=8)
            resp.encoding = "utf-8"
            content = resp.text
            m_date = re.search(r"截止至：<font class='px12'>([\d-]+)</font>", content)
            if not m_date:
                # 限流时常返回空/错误页，重试；仍无日期才判定为无持仓
                if attempt < retries:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                return None
            # 持仓过旧（QDII 等长期未披露季报）不应用来估值
            try:
                report_date = datetime.strptime(m_date.group(1), "%Y-%m-%d")
                if (datetime.now() - report_date).days > 200:
                    logger.debug("jjcc stale for %s: %s", code, m_date.group(1))
                    return None
            except ValueError:
                return None
            stocks: List[dict] = []
            for row in re.findall(r"<tr>.*?</tr>", content, re.S):
                if "unify/r/" not in row:
                    continue
                secid_m = re.search(r"unify/r/([\d.]+)", row)
                name_m = re.search(r"class='tol'><a[^>]*>([^<]+)</a>", row)
                pct_m = re.search(r"<td class='tor'>([\d.]+)%</td>", row)
                if secid_m and name_m and pct_m:
                    stocks.append({
                        "name": name_m.group(1),
                        "secid": secid_m.group(1),
                        "weight_pct": float(pct_m.group(1)),
                    })
            if not stocks:
                return None  # 有日期但无 A股股票（FOF/债基/QDII海外）→ 真无持仓
            return {"date": m_date.group(1), "stocks": stocks}
        except Exception as e:
            logger.debug("jjcc fetch failed %s (attempt %d): %s", code, attempt + 1, e)
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))  # 递增退避
    return None


def get_holdings_batch(codes: List[str], force: bool = False) -> Dict[str, dict]:
    """
    并发批量获取基金持仓（当日已缓存直接复用）。返回 {code: holdings}，仅含成功且有股票持仓的。
    无持仓的基金也记录缓存（None），避免反复抓取。
    """
    global _holdings_mem
    if not codes:
        return {}
    codes = list(dict.fromkeys(codes))
    with _holdings_lock:
        mem = dict(_holdings_mem)
    cache = _load_file_cache()

    result: Dict[str, dict] = {}
    todo: List[str] = []
    for c in codes:
        h = mem.get(c)
        if h is not None:
            if h:
                result[c] = h
            continue
        entry = cache.get(c)
        if entry and entry.get("ts"):
            age = datetime.now().timestamp() - entry["ts"]
            # 失败(None)缓存 5 分钟可重试；成功持仓缓存 90 天
            ttl = _CACHE_TTL if entry.get("data") else 300
            if age < ttl:
                h = entry.get("data")
                with _holdings_lock:
                    _holdings_mem[c] = h
                if h:
                    result[c] = h
                continue
        todo.append(c)

    if todo:
        with ThreadPoolExecutor(max_workers=3) as ex:  # 并发过高会触发 jjcc 限流
            futures = {ex.submit(fetch_holdings, c): c for c in todo}
            for fut, c in futures.items():
                h = fut.result()
                with _holdings_lock:
                    _holdings_mem[c] = h
                if h:
                    result[c] = h
                    cache[c] = {"ts": datetime.now().timestamp(), "data": h}
                else:
                    cache[c] = {"ts": datetime.now().timestamp(), "data": None}
        _save_file_cache(cache)
    return result


def fetch_stock_change(secid: str) -> Optional[float]:
    """单只个股当日涨跌幅（%）。东财 stock/get，f170。"""
    url = ("https://push2delay.eastmoney.com/api/qt/stock/get"
           f"?secid={secid}&ut=fa5fd1943c7b386f172d6893dbfba10b&fltt=2&invt=2"
           "&fields=f43,f58,f170")
    for attempt in range(2):
        try:
            resp = _sess().get(url, headers=_QUOTE_HEADERS, timeout=8)
            data = resp.json()
            chg = (data.get("data") or {}).get("f170")
            if chg == "-" or chg is None:
                return None
            return float(chg)
        except Exception as e:
            logger.debug("Stock fetch failed %s (attempt %d): %s", secid, attempt + 1, e)
            if attempt == 0:
                time.sleep(0.3)
    return None


def get_stock_changes(secids: List[str], force: bool = False) -> Dict[str, float]:
    """并发批量获取个股当日涨跌幅（%）。返回 {secid: change_pct}，当日缓存。"""
    global _stock_cache
    if not secids:
        return {}
    day = datetime.now().strftime("%Y%m%d")
    secids = list(dict.fromkeys(secids))
    with _stock_lock:
        if not force and _stock_cache.get("ts") == day:
            cached = {k: v for k, v in _stock_cache.get("data", {}).items() if k in secids}
            if cached:
                return cached
    result: Dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_stock_change, s): s for s in secids}
        for fut, s in futures.items():
            chg = fut.result()
            if chg is not None:
                result[s] = chg
    if result:
        with _stock_lock:
            merged = dict(_stock_cache.get("data", {}))
            merged.update(result)
            _stock_cache = {"ts": day, "data": merged}
    return result


def estimate_holdings_fund(nav: float, holdings: dict, changes: Dict[str, float]) -> Optional[float]:
    """按重仓股加权估算净值。changes: secid -> change_pct。未覆盖仓位视为涨跌 0。"""
    total = 0.0
    covered = 0
    for s in holdings["stocks"]:
        chg = changes.get(s["secid"])
        if chg is not None:
            total += s["weight_pct"] / 100.0 * chg / 100.0
            covered += 1
    if covered == 0:
        return None
    return nav * (1 + total)
