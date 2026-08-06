# -*- coding: utf-8 -*-
"""
LOF 盘中估算净值引擎

背景：第三方盘中估值接口（天天基金 fundgz / fundmobapi）已失效，
     系统退化为用「滞后官方净值」计算盘中溢价率，导致溢价率系统性失真
     （QDII 净值滞后 1-2 个交易日，滞后期间的行情变动被误算为溢价）。

本引擎自建估算净值（业界做法，参考集思录"最新净值 × 挂钩标的涨跌"）：
  1. 港股（QDII港股 / 港股通LOF，匹配恒生/恒生科技/恒生国企）：
     估算净值 ≈ 最新官方净值 × (1 + 港股指数盘中涨跌 × 股票仓位)
     QDII港股再叠加当日美元兑人民币汇率变动。
  2. 海外QDII（纳指/标普/日经等，场内简称常无"QDII"字样，按指数secid识别）：
     估算净值 ≈ 最新官方净值 × (1 + 当日汇率变动) × (1 + 净值日之后最近的已收盘交易日涨跌 × 仓位)
     —— A股盘中美股未开盘，净值当日增量来自汇率与已收盘交易日。
  3. 境内指数 LOF（名称可匹配跟踪指数，或命中 lof_index_map.json）：
     估算净值 ≈ 最新官方净值 × (1 + 跟踪指数当日涨跌 × 股票仓位)
  4. 其他（主动型 / 商品 / 无匹配）：
     使用最新官方净值，标注滞后天数，不强行估算。

当官方净值已更新到最近交易日（盘后）时，回退使用正式净值。
"""
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import requests

import holdings
from trading_calendar import is_trading_day, get_last_trading_date

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────
# 指数映射配置
# 名称关键词 → 东财指数 secid（全部经 push2delay stock/get 实测可用）
# 注意：匹配按顺序取第一个命中，父子级关键词需从长到短排列
#       （如"中证1000"在"中证100"前、"恒生科技/恒生国企"在"恒生"前）
# 已验证：1.000967 实为"基本600"（非煤炭）、1.000941 实为"新能源"（非有色）
#       —— 煤炭用 0.399998、有色用 0.399395（国证有色）
# ─────────────────────────────────────────────────────
INDEX_KEYWORDS: List[Tuple[str, str]] = [
    # 海外 / 港股
    ("纳斯达克", "100.NDX"),
    ("纳指", "100.NDX"),
    ("标普500", "100.SPX"),
    ("标普", "100.SPX"),
    ("日经", "100.N225"),
    ("德国DAX", "100.GDAXI"),
    # 美股行业基金（QDII）——必须早于 A股"消费"等裸词，避免张冠李戴
    ("美国消费", "100.SPX"),
    ("海外科技", "100.NDX"),
    ("海外互联网", "0.399970"),
    ("恒生科技", "124.HSTECH"),
    ("恒生国企", "100.HSCEI"),
    ("H股", "100.HSCEI"),
    ("香港大盘", "100.HSI"),
    ("香港银行", "100.HSI"),
    ("香港中小", "100.HSI"),
    ("港股高股息", "100.HSI"),
    ("港股通新经济", "100.HSI"),
    ("港股小盘", "100.HSI"),
    ("沪深港300", "1.000300"),
    ("50AH", "1.000016"),
    ("恒生", "100.HSI"),
    # A股宽基
    ("中证A100", "1.000903"),
    ("A100", "1.000903"),
    ("中证1000", "1.000852"),
    ("1000增强", "1.000852"),
    ("中证100", "0.399903"),
    ("中证800", "1.000906"),
    ("中证500", "1.000905"),
    ("500增强", "1.000905"),
    ("中小企业100", "0.399005"),
    ("中小企业综", "0.399005"),
    ("中小板", "0.399005"),
    ("深证100", "0.399004"),
    ("深证成指", "0.399001"),
    ("深成指", "0.399001"),
    ("深成", "0.399001"),
    ("沪深300", "1.000300"),
    ("上证50", "1.000016"),
    ("创业板", "0.399006"),
    ("创业板50", "0.399673"),
    ("创业50", "0.399673"),
    ("科创50", "1.000688"),
    ("中证红利", "1.000922"),
    ("红利ETF", "1.000922"),
    ("红利基金", "1.000922"),
    ("红利优选", "1.000922"),
    ("沪港深红利", "1.000922"),
    ("港股通红利", "1.000922"),
    ("国企红利", "1.000824"),
    ("基本面50", "1.000925"),
    ("巨潮100", "0.399004"),
    ("中证流通", "1.000902"),
    ("中证全指", "1.000985"),
    ("中证90", "0.399903"),
    # A股行业/主题
    ("煤炭等权", "0.399990"),
    ("中证煤炭", "0.399998"),
    ("煤炭", "0.399998"),
    ("国证有色", "0.399395"),
    ("有色金属", "0.399395"),
    ("能源金属", "0.399395"),
    ("有色", "0.399395"),
    ("国证钢铁", "0.399440"),
    ("钢铁", "0.399440"),
    ("国证油气", "0.399439"),
    ("石油", "0.399439"),
    # 注："原油"不移入指数映射——原油基金（161129/501018/160723）为商品期货基金，
    #     需走商品估值（COMMODITY_KEYWORDS），否则会被误当作油气股票指数
    ("中证银行", "0.399986"),
    ("银行", "0.399986"),
    ("证券公司", "0.399975"),
    ("券商", "0.399975"),
    ("证券龙头", "0.399437"),
    ("证券", "0.399975"),
    ("保险主题", "0.399809"),
    ("保险", "0.399809"),
    ("中证医疗", "0.399989"),
    ("医疗", "0.399989"),
    ("中证医药", "1.000933"),
    ("医药100", "1.000978"),
    ("生物医药", "0.399441"),
    ("生物科技", "0.399441"),
    ("医药", "1.000933"),
    ("中药", "0.399441"),
    ("中证白酒", "0.399997"),
    ("中证酒", "0.399987"),
    ("白酒", "0.399997"),
    ("食品饮料", "1.000807"),
    ("食品", "1.000807"),
    ("酒", "0.399987"),
    ("消费红利", "1.000990"),
    ("中证消费", "1.000932"),
    ("消费100", "0.399364"),
    ("消费50", "1.000126"),
    ("消费", "0.399932"),
    ("中证军工", "0.399967"),
    ("军工", "0.399967"),
    ("国防", "0.399973"),
    ("中证新能", "0.399808"),
    ("新能源车", "0.399417"),
    ("CS新能车", "0.399976"),
    ("新能源", "0.399808"),
    ("新能", "0.399808"),
    ("智能汽车", "0.399432"),
    ("芯片", "0.980017"),
    ("半导体", "0.980017"),
    ("电子50", "0.399281"),
    ("申万电子", "0.399281"),
    ("中证环保", "1.000827"),
    ("环保", "1.000827"),
    ("环境治理", "1.000827"),
    ("基建工程", "0.399995"),
    ("基建", "0.399995"),
    ("一带一路", "0.399991"),
    ("带路", "0.399991"),
    ("国企改革", "0.399974"),
    ("并购重组", "0.399992"),
    ("房地产", "0.399241"),
    ("地产", "0.399241"),
    ("中证体育", "0.399804"),
    ("体育", "0.399804"),
    ("高铁产业", "0.399807"),
    ("高铁", "0.399807"),
    ("养老产业", "0.399812"),
    ("养老", "0.399812"),
    ("中证农业", "1.000949"),
    ("农业", "1.000949"),
    ("中证能源", "1.000928"),
    ("资源", "0.399319"),
    ("中证上游", "1.000961"),
    ("大宗商品", "1.000979"),
    ("中证金融", "0.399934"),
    ("金融LOF", "0.399934"),
    ("金融科技", "0.399699"),
    ("科技100", "0.399608"),
    ("科创信息", "1.000682"),
    ("科创芯片", "1.000685"),
    ("中证信息", "1.000935"),
    ("信息", "1.000935"),
    ("计算机", "1.000935"),
    ("云计算", "0.399262"),
    ("数字经济", "0.399262"),
    ("大数据50", "0.399282"),
    ("大数据", "0.399282"),
    ("人工智能", "0.399262"),
    ("智能家居", "0.399996"),
    ("机器人", "0.399283"),
    ("TMT", "1.000998"),
    ("传媒", "0.399434"),
    ("数字传媒", "0.399434"),
    ("移动互联", "0.399970"),
    ("互联网", "0.399970"),
    ("互联", "0.399970"),
    ("中证央企", "1.000926"),
    ("央企", "1.000926"),
    ("国企指数", "100.HSCEI"),
    ("全球油气", "0.399439"),
    ("油气", "0.399439"),
]

# 港股指数 secid：盘中实时交易，可叠加当日涨跌（港股QDII 与 港股通LOF）
_HK_INDEX_SECIDS = {"100.HSI", "124.HSTECH", "100.HSCEI"}
# 海外指数 secid：A股盘中美股/日股等未开盘，当日涨跌反映"净值日之后最近的已收盘交易日"变动
_OVERSEAS_INDEX_SECIDS = {"100.NDX", "100.SPX", "100.N225", "100.GDAXI"}

# ─────────────────────────────────────────────────────
# 商品映射配置（商品期货基金估值源）
# 关键词 → (新浪 hq symbol, 显示名)。统一使用 hf_ 系列（格式：pos0=昨收, pos3=最新）
#   黄金 → hf_XAU 伦敦金现货（贴近国内 Au99.99，优于 COMEX 期货 hf_GC）
#   白银 → hf_SI  纽约白银期货
#   原油 → hf_OIL 布伦特原油（与国内 SC 原油相关性最高；国内期货 nf_SC0 格式复杂弃用）
# 商品基金（黄金/白银/原油）为商品期货基金，名称不含"QDII"字样但仍按全商品波动估算。
# ─────────────────────────────────────────────────────
COMMODITY_KEYWORDS: List[Tuple[str, str, str]] = [
    # 元组：关键词, 海外现货symbol(新浪hf_), 显示名, 国内期货主力symbol(新浪历史AU0/AG0/SC0)
    # 国内期货历史用于覆盖"净值日→最近交易日"的海外涨跌（海外历史接口不可用，大行情下二者同步）
    ("黄金", "hf_XAU", "伦敦金现货", "AU0"),
    ("白银", "hf_SI", "纽约白银", "AG0"),
    ("原油", "hf_OIL", "布伦特原油", "SC0"),
]

# 商品基金商品仓位（期货/ETF 满仓运作，留部分现金）
COMMODITY_POSITION = 0.9

# 兜底静态映射文件：{code: {"index": 名称, "secid": ..., "position": 股票仓位}}
_INDEX_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lof_index_map.json")

# 指数LOF股票仓位默认值（季报通常 90%-95%）
DEFAULT_POSITION = 0.95

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "*/*",
}
_FX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn/",
    "Accept": "*/*",
}

_session: Optional[requests.Session] = None


def _sess() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.trust_env = False
    return _session


def _safe_float(val, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# ─────────────────────────────────────────────────────
# 交易日 / 净值滞后判断
# ─────────────────────────────────────────────────────
_recent_trade_cache: Dict[str, object] = {}


def get_recent_trade_date() -> str:
    """
    最近交易日（YYYY-MM-DD）。
    今天为交易日则返回今天，否则返回上一个交易日（带缓存，避免频繁调用交易日历）。
    """
    day = datetime.now().strftime("%Y-%m-%d")
    if _recent_trade_cache.get("ts") == day:
        return _recent_trade_cache.get("date", day)
    try:
        if is_trading_day():
            recent = day
        else:
            recent = get_last_trading_date()
    except Exception:
        recent = day
    _recent_trade_cache["ts"] = day
    _recent_trade_cache["date"] = recent
    return recent


def calc_nav_lag_days(nav_date: Optional[str], recent_trade: Optional[str]) -> int:
    """净值日期滞后最近交易日多少天（自然日）。"""
    if not nav_date or not recent_trade:
        return 0
    try:
        d1 = datetime.strptime(str(nav_date)[:10], "%Y-%m-%d")
        d2 = datetime.strptime(str(recent_trade)[:10], "%Y-%m-%d")
        return max(0, (d2 - d1).days)
    except Exception:
        return 0


# ─────────────────────────────────────────────────────
# 汇率（当日美元兑人民币变动率）
# ─────────────────────────────────────────────────────
_fx_lock = threading.Lock()
_fx_cache: Dict[str, object] = {}


def get_fx_change_today(force: bool = False) -> float:
    """
    当日美元兑人民币汇率变动率（人民币口径，可正可负）。
    返回 0.0 表示获取失败（此时不做汇率修正，避免引入错误）。
    新浪 fx_susdcny 格式：时间,最新,买,卖,成交量,开,高,低,昨收,名称,涨跌幅?
    """
    global _fx_cache
    day = datetime.now().strftime("%Y%m%d")
    with _fx_lock:
        if not force and _fx_cache.get("ts") == day:
            return _safe_float(_fx_cache.get("value"), 0.0)

    for symbol in ("fx_susdcny", "USDCNY"):
        try:
            url = f"https://hq.sinajs.cn/list={symbol}"
            resp = _sess().get(url, headers=_FX_HEADERS, timeout=8)
            resp.encoding = "gbk"
            m = re.search(r'="([^"]+)"', resp.text)
            if not m:
                continue
            parts = m.group(1).split(",")
            if len(parts) < 9:
                continue
            latest = _safe_float(parts[1])
            prev_close = _safe_float(parts[8])
            if latest > 0 and prev_close > 0:
                change = (latest - prev_close) / prev_close
                with _fx_lock:
                    _fx_cache = {"ts": day, "value": change}
                logger.info("FX change today: %.4f%% (latest=%.4f prev=%.4f)",
                            change * 100, latest, prev_close)
                return change
        except Exception as e:
            logger.debug("FX fetch failed (%s): %s", symbol, e)
    return 0.0


# ─────────────────────────────────────────────────────
# 指数行情（当日涨跌幅 %）
# ─────────────────────────────────────────────────────
_index_lock = threading.Lock()
_index_cache: Dict[str, object] = {}


def fetch_index_change(secid: str) -> Optional[float]:
    """单只指数当日涨跌幅（%）。东财 stock/get 已验证可用。"""
    url = ("https://push2delay.eastmoney.com/api/qt/stock/get"
           f"?secid={secid}&ut=fa5fd1943c7b386f172d6893dbfba10b&fltt=2&invt=2"
           "&fields=f43,f58,f60,f170")
    for attempt in range(2):
        try:
            resp = _sess().get(url, headers=_HEADERS, timeout=8)
            data = resp.json()
            chg = ((data.get("data") or {}).get("f170"))
            if chg == "-" or chg is None:
                return None
            return _safe_float(chg)
        except Exception as e:
            logger.debug("Index fetch failed %s (attempt %d): %s", secid, attempt + 1, e)
            if attempt == 0:
                time.sleep(0.5)
    return None


def get_index_changes(secids: List[str], force: bool = False) -> Dict[str, float]:
    """批量获取指数当日涨跌幅（%）。返回 {secid: change_pct}。"""
    global _index_cache
    if not secids:
        return {}
    day = datetime.now().strftime("%Y%m%d")
    secids = list(dict.fromkeys(secids))  # 去重保序
    with _index_lock:
        if not force and _index_cache.get("ts") == day:
            cached = {k: v for k, v in _index_cache.get("data", {}).items() if k in secids}
            if cached:
                return cached

    result: Dict[str, float] = {}
    for secid in secids:
        chg = fetch_index_change(secid)
        if chg is not None:
            result[secid] = chg
        time.sleep(0.1)  # 限制频率

    if result:
        with _index_lock:
            merged = dict(_index_cache.get("data", {}))
            merged.update(result)
            _index_cache = {"ts": day, "data": merged}
    return result


# ─────────────────────────────────────────────────────
# 商品行情（当日涨跌幅 %）
# ─────────────────────────────────────────────────────
_commodity_lock = threading.Lock()
_commodity_cache: Dict[str, object] = {}


def fetch_commodity_change(symbol: str) -> Optional[float]:
    """单只商品（hf_ 系列）当日涨跌幅（%）。新浪 hq 接口，pos0=昨收, pos3=最新。"""
    url = f"https://hq.sinajs.cn/list={symbol}"
    try:
        resp = _sess().get(url, headers=_FX_HEADERS, timeout=8)
        resp.encoding = "gbk"
        m = re.search(r'="([^"]+)"', resp.text)
        if not m:
            return None
        parts = m.group(1).split(",")
        # 新浪 hf_ 外盘格式：pos3=最新价, pos7=昨收（已用东财 COMEX 昨收 4305.2 交叉验证；pos0 是开盘价，勿当昨收）
        if len(parts) < 8:
            return None
        latest = _safe_float(parts[3])
        prev_close = _safe_float(parts[7])
        if latest > 0 and prev_close > 0:
            return (latest - prev_close) / prev_close * 100.0
    except Exception as e:
        logger.debug("Commodity fetch failed %s: %s", symbol, e)
    return None


def get_commodity_changes(symbols: List[str], force: bool = False) -> Dict[str, float]:
    """批量获取商品当日涨跌幅（%）。返回 {symbol: change_pct}。"""
    global _commodity_cache
    if not symbols:
        return {}
    day = datetime.now().strftime("%Y%m%d")
    symbols = list(dict.fromkeys(symbols))  # 去重保序
    with _commodity_lock:
        if not force and _commodity_cache.get("ts") == day:
            cached = {k: v for k, v in _commodity_cache.get("data", {}).items() if k in symbols}
            if cached:
                return cached

    result: Dict[str, float] = {}
    for symbol in symbols:
        chg = fetch_commodity_change(symbol)
        if chg is not None:
            result[symbol] = chg
        time.sleep(0.1)  # 限制频率

    if result:
        with _commodity_lock:
            merged = dict(_commodity_cache.get("data", {}))
            merged.update(result)
            _commodity_cache = {"ts": day, "data": merged}
    return result


def match_commodity(name: str) -> Optional[Tuple[str, str, str]]:
    """匹配商品基金。返回 (海外symbol, 显示名, 国内期货symbol) 或 None。"""
    for kw, symbol, label, cn_symbol in COMMODITY_KEYWORDS:
        if kw in name:
            return symbol, label, cn_symbol
    return None


# ─────────────────────────────────────────────────────
# 商品累计涨跌：净值日→最近交易日（国内期货历史近似海外）
#   × 最近交易日→今日（海外现货当日）
# ─────────────────────────────────────────────────────
_cn_fut_lock = threading.Lock()
_cn_fut_cache: Dict[str, object] = {}


def fetch_cn_fut_hist(symbol: str) -> Optional[Dict[str, float]]:
    """新浪国内期货日K历史 {date: close}（InnerFuturesNewService，接口返回全量约500KB）。"""
    url = (f"https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
           f"var%20_=/InnerFuturesNewService.getDailyKLine?symbol={symbol}")
    try:
        resp = _sess().get(url, headers=_FX_HEADERS, timeout=12)
        m = re.search(r"\[.*\]", resp.text, re.S)
        if not m:
            return None
        rows = json.loads(m.group(0))
        hist = {}
        for row in rows:
            d = str(row.get("d") or "")
            c = _safe_float(row.get("c"))
            if len(d) == 10 and c > 0:
                hist[d] = c
        return hist or None
    except Exception as e:
        logger.debug("CN fut hist fetch failed %s: %s", symbol, e)
    return None


def get_cn_fut_hist(symbol: str, force: bool = False) -> Optional[Dict[str, float]]:
    """带当日缓存：历史日K每天拉一次（全量较大，不重复抓）。"""
    global _cn_fut_cache
    day = datetime.now().strftime("%Y%m%d")
    with _cn_fut_lock:
        if not force and _cn_fut_cache.get("ts") == day:
            data = _cn_fut_cache.get("data", {})
            if symbol in data:
                return data[symbol]
    hist = fetch_cn_fut_hist(symbol)
    if hist:
        with _cn_fut_lock:
            merged = dict(_cn_fut_cache.get("data", {}))
            merged[symbol] = hist
            _cn_fut_cache = {"ts": day, "data": merged}
    return hist


def commodity_cumulative_change(hist: Optional[Dict[str, float]], nav_date: str,
                                recent_trade: str, today_chg: float) -> float:
    """
    商品累计涨跌（小数，0.03=3%）。
    段1（净值日→最近已收盘交易日）：国内期货历史近似海外（大行情下同步，已验证 8/5 沪金+2.70%）
    段2（最近已收盘交易日→今日）：海外现货当日涨跌。
    历史/日期缺失时退回当日涨跌。
    注意：recent_trade 可能是今天盘中（日K未生成），段1终点须取 hist 中
    ≤ recent_trade 的最后一天，否则会漏掉净值日到昨日的整段涨跌。
    """
    seg2 = today_chg / 100.0
    if not hist:
        return seg2
    base = str(nav_date)[:10]
    end = str(recent_trade)[:10]
    d0 = sorted(d for d in hist if d <= base)
    d1 = sorted(d for d in hist if d <= end)
    if not d0 or not d1:
        return seg2
    c0 = hist[d0[-1]]
    c1 = hist[d1[-1]]
    if c0 <= 0 or c1 <= 0:
        return seg2
    seg1 = c1 / c0 - 1.0
    return (1 + seg1) * (1 + seg2) - 1.0


# ─────────────────────────────────────────────────────
# 海外指数累计涨跌（美股：净值日→最近已收盘交易日）
# 腾讯美股日K fqkline 已验证可用；替代东财 f170 单日涨跌，
# 避免 QDII 滞后多日时美股已收盘但 f170 只反映最近一天而漏天。
# ─────────────────────────────────────────────────────
_US_TENCENT_CODE = {"100.NDX": "us.NDX", "100.SPX": "us.INX"}
_us_hist_lock = threading.Lock()
_us_hist_cache: Dict[str, object] = {}


def fetch_us_hist(tencent_code: str) -> Optional[Dict[str, float]]:
    """腾讯美股日K {date: close}（近 45 天，字段: date,open,close,high,low,vol）。"""
    start = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={tencent_code},day,{start},{end},40,qfq")
    try:
        resp = _sess().get(url, headers=_HEADERS, timeout=10)
        data = (resp.json().get("data") or {})
        rows = (data.get(tencent_code) or {}).get("day") or []
        hist = {}
        for row in rows:
            if len(row) >= 3:
                d = str(row[0]); c = _safe_float(row[2])
                if len(d) == 10 and c > 0:
                    hist[d] = c
        return hist or None
    except Exception as e:
        logger.debug("US hist fetch failed %s: %s", tencent_code, e)
    return None


def get_us_hist(secid: str, force: bool = False) -> Optional[Dict[str, float]]:
    """按东财 secid 取美股日K，当日缓存。腾讯不支持的（N225/GDAXI）返回 None。"""
    global _us_hist_cache
    tc = _US_TENCENT_CODE.get(secid)
    if not tc:
        return None
    day = datetime.now().strftime("%Y%m%d")
    with _us_hist_lock:
        if not force and _us_hist_cache.get("ts") == day:
            data = _us_hist_cache.get("data", {})
            if tc in data:
                return data[tc]
    hist = fetch_us_hist(tc)
    if hist:
        with _us_hist_lock:
            merged = dict(_us_hist_cache.get("data", {}))
            merged[tc] = hist
            _us_hist_cache = {"ts": day, "data": merged}
    return hist


def us_cumulative_change(hist: Optional[Dict[str, float]], nav_date: str,
                         single_chg: float) -> float:
    """
    美股累计涨跌（小数，0.00825=0.825%）= 最近已收盘交易日 / 净值日基准日 - 1。
    覆盖 QDII 滞后多日时被 f170 漏掉的部分（如净值日 8/4、美股 8/6 已收盘，
    f170 只给 8/6 单日，而这里累计 8/6÷8/4 覆盖 8/5+8/6 两天）。
    历史缺失或净值日无数据时退回单日涨跌（现状 f170）。
    """
    if not hist:
        return single_chg / 100.0
    dates = sorted(hist)
    end_close = hist[dates[-1]]
    base = [d for d in dates if d <= str(nav_date)[:10]]
    if not base:
        return single_chg / 100.0
    base_close = hist[base[-1]]
    if end_close <= 0 or base_close <= 0:
        return single_chg / 100.0
    return end_close / base_close - 1.0


# ─────────────────────────────────────────────────────
# 基金 → 指数匹配
# ─────────────────────────────────────────────────────
_map_lock = threading.Lock()
_static_map: Optional[Dict[str, dict]] = None


def _load_static_map() -> Dict[str, dict]:
    if not os.path.exists(_INDEX_MAP_PATH):
        return {}
    try:
        with open(_INDEX_MAP_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load lof_index_map.json: %s", e)
        return {}


def get_static_map() -> Dict[str, dict]:
    global _static_map
    with _map_lock:
        if _static_map is None:
            _static_map = _load_static_map()
        return _static_map


def match_index(code: str, name: str) -> Optional[Tuple[str, float]]:
    """
    匹配基金跟踪指数。返回 (secid, 股票仓位) 或 None。
    优先静态映射，其次名称关键词。
    """
    static = get_static_map()
    entry = static.get(code)
    if entry and entry.get("secid"):
        return str(entry["secid"]), _safe_float(entry.get("position"), DEFAULT_POSITION)

    for kw, secid in INDEX_KEYWORDS:
        if kw in name:
            return secid, DEFAULT_POSITION
    return None


# ─────────────────────────────────────────────────────
# 估算主逻辑
# ─────────────────────────────────────────────────────
def estimate_funds(funds: List[Dict]) -> Dict[str, dict]:
    """
    批量估算净值。

    Args:
        funds: [{code, name, nav, nav_date, is_formal_nav, ...}, ...]

    Returns:
        {code: {
            est_nav: float|None,      # 用于盘中溢价率计算的净值
            est_source: str,          # formal / fx / fx+hk / fx+idx / index / commodity / holdings / formal_lag / none
            nav_lag_days: int,        # 净值滞后天数
            index_secid: str|None,    # 匹配到的指数/商品 symbol（若有）
        }}
    """
    recent_trade = get_recent_trade_date()
    fx_change = get_fx_change_today()

    # 收集需要抓取的指数
    need_index: Dict[str, List[str]] = {}  # code -> [secid]
    for f in funds:
        if not f.get("nav") or not f.get("name"):
            continue
        nav_date = str(f.get("nav_date") or "")[:10]
        if nav_date == recent_trade:
            continue  # 官方净值已更新到最近交易日，无需估算
        secid, _pos = match_index(f["code"], f["name"]) or (None, DEFAULT_POSITION)
        if secid:
            need_index[f["code"]] = secid

    index_changes = get_index_changes(list(set(need_index.values())))

    # 收集需要抓取的商品（未匹配指数的基金再尝试商品映射）
    need_commodity: Dict[str, str] = {}  # code -> symbol
    for f in funds:
        if not f.get("nav") or not f.get("name"):
            continue
        nav_date = str(f.get("nav_date") or "")[:10]
        if nav_date == recent_trade:
            continue
        if f["code"] in need_index:
            continue  # 已有指数匹配，无需商品估值
        comm = match_commodity(f["name"])
        if comm:
            need_commodity[f["code"]] = comm[0]

    commodity_changes = get_commodity_changes(list(set(need_commodity.values())))

    # 收集需要持仓估值的主动型/FOF（未匹配指数与商品的）
    # 判定：名称命中主动特征词，或 LOF/定开/封闭 结尾的主动型——
    #   场内简称常不含特征词（如"兴全合宜LOF"），须兜底纳入，否则漏判成 formal_lag
    need_holdings: List[str] = []
    for f in funds:
        if not f.get("nav") or not f.get("name"):
            continue
        nav_date = str(f.get("nav_date") or "")[:10]
        if nav_date == recent_trade:
            continue
        if f["code"] in need_index or f["code"] in need_commodity:
            continue
        name = f["name"]
        if name.startswith("184"):
            continue  # 老封基，无场内交易意义
        if "QDII" in name.upper():
            continue  # QDII 持仓海外，jjcc 无 A 股，不参与持仓估值
        is_bond = any(w in name for w in holdings.BOND_HINTS)
        if is_bond:
            continue  # 债基无 A 股股票持仓，排除避免无效抓取
        # 兜底：未匹配指数/商品的基金全部尝试持仓估值。
        # 深市老 LOF 等场内简称常无"LOF/定开/混合"等特征词（鹏华收益/中银持续增长/银华明择…），
        # 名称关键词枚举不完备，只能全量兜底；jjcc 无 A 股持仓的会失败缓存，无害。
        need_holdings.append(f["code"])

    holdings_map = holdings.get_holdings_batch(need_holdings)
    all_stock_secids: List[str] = []
    for h in holdings_map.values():
        for s in h["stocks"]:
            all_stock_secids.append(s["secid"])
    stock_changes = holdings.get_stock_changes(all_stock_secids)

    result: Dict[str, dict] = {}
    for f in funds:
        code = f["code"]
        nav = f.get("nav")
        name = f.get("name") or ""
        nav_date = str(f.get("nav_date") or "")[:10]
        lag = calc_nav_lag_days(nav_date, recent_trade)

        if not nav or nav <= 0:
            result[code] = {"est_nav": None, "est_source": "none", "nav_lag_days": lag, "index_secid": None}
            continue

        # 1) 官方净值已更新到最近交易日 → 用正式净值
        if nav_date == recent_trade:
            result[code] = {"est_nav": nav, "est_source": "formal", "nav_lag_days": 0, "index_secid": None}
            continue

        is_qdii = "QDII" in name.upper()
        secid, position = match_index(code, name) or (None, DEFAULT_POSITION)
        chg = index_changes.get(secid) if secid else None
        is_hk = secid in _HK_INDEX_SECIDS
        is_overseas = secid in _OVERSEAS_INDEX_SECIDS

        # 2) 港股（QDII港股 / 港股通LOF）：港股盘中实时涨跌修正；QDII额外叠加汇率
        if is_hk:
            est = nav * (1 + (fx_change if is_qdii else 0.0))
            if chg is not None:
                est *= (1 + chg / 100.0 * position)
            result[code] = {
                "est_nav": round(est, 4),
                "est_source": "fx+hk" if is_qdii else "index",
                "nav_lag_days": lag, "index_secid": secid,
            }
            continue

        # 3) 海外QDII（纳指/标普/日经等，场内简称常无"QDII"字样）：
        #    汇率修正 + 累计涨跌（净值日→最近已收盘交易日，腾讯美股日K，避免 f170 漏天）
        if is_overseas:
            est = nav * (1 + fx_change)
            if chg is not None:
                hist = get_us_hist(secid)
                cum = us_cumulative_change(hist, nav_date, chg)
                est *= (1 + cum * position)
            result[code] = {
                "est_nav": round(est, 4), "est_source": "fx+idx",
                "nav_lag_days": lag, "index_secid": secid,
            }
            continue

        # 4) 境内指数 LOF：指数当日涨跌修正
        if secid and chg is not None:
            est = nav * (1 + chg / 100.0 * position)
            result[code] = {
                "est_nav": round(est, 4), "est_source": "index",
                "nav_lag_days": lag, "index_secid": secid,
            }
            continue

        # 5) 商品基金（黄金/白银/原油，均为 QDII）：累计涨跌 × 汇率叠加
        if secid is None:
            comm = match_commodity(name)
            if comm:
                symbol, _label, cn_symbol = comm
                cchg = commodity_changes.get(symbol)
                if cchg is not None:
                    # 累计涨跌 = 净值日→最近交易日（国内期货历史近似海外）× 最近交易日→今日（海外现货当日）
                    hist = get_cn_fut_hist(cn_symbol)
                    cum = commodity_cumulative_change(hist, nav_date, recent_trade, cchg)
                    est = nav * (1 + fx_change) * (1 + cum * COMMODITY_POSITION)
                    result[code] = {
                        "est_nav": round(est, 4), "est_source": "commodity",
                        "nav_lag_days": lag, "index_secid": symbol,
                    }
                    continue

        # 6) 主动型/FOF：重仓股加权持仓估值
        if secid is None:
            h = holdings_map.get(code)
            if h:
                est = holdings.estimate_holdings_fund(nav, h, stock_changes)
                if est is not None:
                    result[code] = {
                        "est_nav": round(est, 4), "est_source": "holdings",
                        "nav_lag_days": lag, "index_secid": None,
                    }
                    continue

        # 7) 无匹配（主动型/商品等）：用最新官方净值，标注滞后
        result[code] = {
            "est_nav": nav, "est_source": "formal_lag",
            "nav_lag_days": lag, "index_secid": None,
        }

    return result
