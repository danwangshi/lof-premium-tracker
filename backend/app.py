# -*- coding: utf-8 -*-
"""
LOF基金数据服务 - RESTful API
场内LOF基金: 实时价格 + 净值/估值 + 溢价率 + 成交额

启动命令: python app.py
依赖: pip install flask requests flask-cors
"""
import sys
# Fix Windows console encoding before any print
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import logging
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler

from config import Config
from data_fetcher import get_fetcher
from history_db import get_history_db, filter_and_forward_fill
from chart_cache import get_chart_cache
from task_queue import get_task_queue

# ─────────────────────────────────────────────
# 日志配置
# ─────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("lof-api")

# 抑制 urllib3 和 charset_normalizer 的 DEBUG 日志，只显示 WARNING 及以上
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
logging.getLogger('charset_normalizer').setLevel(logging.WARNING)

# ─────────────────────────────────────────────
# Flask 应用
# ─────────────────────────────────────────────
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*", "methods": ["GET", "POST", "OPTIONS"], "allow_headers": ["Content-Type"]}})  # 允许跨域，支持预检请求


# ══════════════════════════════════════════════════════════════════
# 通用响应构建
# ══════════════════════════════════════════════════════════════════

def ok(data, meta=None, status=200):
    """成功响应: { code: 0, message, data, meta? }"""
    payload = {"code": 0, "message": "success", "data": data}
    if meta:
        payload["meta"] = meta
    return jsonify(payload), status


def err_resp(message, code=1, status=400, details=None):
    """错误响应: { code, message, details? }"""
    payload = {"code": code, "message": message}
    if details:
        payload["details"] = details
    return jsonify(payload), status


def error(message, status=400):
    """简化错误响应"""
    return err_resp(message, status=status)


# ══════════════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════════════

def _is_suspended(fund: dict) -> bool:
    """判断基金是否停牌或无成交"""
    vol = fund.get("volume")
    amt = fund.get("amount")
    # 成交量为0 → 停牌
    if vol is not None and vol == 0:
        return True
    # 成交额为0 → 停牌（SSE 数据有 amount）
    if amt is not None and amt == 0:
        return True
    # SZ 数据可能缺少 volume/amount，但 price≈1.0 且无波动 → 停牌基金典型特征
    # 使用 float() 兼容 PostgreSQL NUMERIC → Decimal 类型
    price = float(fund.get("price", 0) or 0)
    pct = float(fund.get("change_pct", 0) or 0)
    if abs(price - 1.0) < 0.001 and pct == 0 and (vol is None or vol == 0):
        return True
    return False


def _fmt(fund: dict, detail: bool = False) -> dict:
    """
    统一格式化输出字段
    所有溢价率/溢价状态已在 data_fetcher 中计算完毕
    """
    # float() 兼容 PostgreSQL NUMERIC → Python Decimal 类型
    premium = fund.get("premium_rate")
    nav = fund.get("nav")
    price = float(fund.get("price", 0) or 0)
    change_pct = float(fund.get("change_pct", 0) or 0)
    
    # 在 _fmt 内部计算 shares_incr，确保一定返回
    shares_incr_val = fund.get("shares_incr")
    if shares_incr_val is None:
        shares_incr_val = 0  # 强制默认为 0，防止被 JSON 过滤
    if fund.get("code") == "160644":
        import sys
        print(f"DEBUG: fund keys = {list(fund.keys())}", file=sys.stderr)
        print(f"DEBUG: shares_incr_val = {shares_incr_val}", file=sys.stderr)

    result = {
        # ── 基础信息 ──
        "code":       fund.get("code"),              # 6位基金代码
        "name":       fund.get("name"),              # 基金名称
        # ── 交易数据 ──
        "price":      fund.get("price"),             # 最新价（元）
        "change_pct": change_pct,                    # 涨跌幅（%）
        "volume":     fund.get("volume"),            # 成交量（股）
        "amount":     fund.get("amount"),            # 成交额（元）
        # ── 净值数据 ──
        "nav":        nav,                          # 当前净值/估算净值（元）
        "nav_date":   fund.get("nav_date"),         # 净值日期/估值时间
        "is_formal_nav": fund.get("is_formal_nav", False),  # 是否盘后正式净值
        # ── 溢价分析 ──
        "premium_rate":  premium,                   # 溢价率（%），正=溢价，负=折价
        "premium_status": fund.get("premium_status"),  # 溢价/折价/平价
        "avg_premium_3d": fund.get("avg_premium_3d"),  # 三日平均溢价率（%）
        # ── 费率数据 ──
        "purchase_fee_rate": fund.get("purchase_fee_rate"),  # 申购优惠费率（%）
        "redemption_fee_rate": fund.get("redemption_fee_rate"),  # 赎回费率最短档（%）
        "purchase_limit": fund.get("purchase_limit"),  # 日累计申购限额（元），None=无限额
        # ── 状态 ──
        "is_suspended": _is_suspended(fund),        # 是否停牌/无成交
        "can_purchase": fund.get("can_purchase"),  # 是否可申购（None=未知）
        "data_date": fund.get("_history_date"),     # 数据日期（历史回填时有值）
        # ── 场内份额 ──
        "shares": fund.get("shares"),               # 场内份额（股）
        "shares_date": fund.get("shares_date"),     # 份额日期
        "shares_source": fund.get("shares_source"), # 份额数据来源（SSE/SZSE）
        "shares_incr": shares_incr_val,     # 新增份额（股）
        # ── 推导字段 ──
        "change_amount": round(change_pct / 100 * price, 4) if (price and price > 0) else None,
    }
    
    # 调试：如果 code 是 160644，打印整个 result
    if fund.get("code") == "160644":
        print(f"DEBUG _fmt: shares_incr value = {result.get('shares_incr')}")

    if detail:
        volume = fund.get("volume") or 0
        amount = fund.get("amount") or 0
        result.update({
            "prev_nav": fund.get("prev_nav"),        # 昨日净值
            "volume_w": round(volume / 10000, 2),    # 成交量（万手）
            "amount_w": round(amount / 10000, 2),    # 成交额（万元）
        })

    return result


# ══════════════════════════════════════════════════════════════════
# Web 前端静态文件服务
# ══════════════════════════════════════════════════════════════════

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root (backend/../)

@app.route("/")
def index():
    """返回 Web 前端首页"""
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/css/<path:filename>")
def css_files(filename):
    return send_from_directory(os.path.join(BASE_DIR, "css"), filename)

@app.route("/js/<path:filename>")
def js_files(filename):
    return send_from_directory(os.path.join(BASE_DIR, "js"), filename)

@app.route("/assets/<path:filename>")
def assets_files(filename):
    return send_from_directory(os.path.join(BASE_DIR, "assets"), filename)

@app.route("/favicon.ico")
def favicon():
    """返回网站图标，避免 404 错误"""
    return send_from_directory(os.path.join(BASE_DIR, "assets"), "icon.jpg", mimetype="image/jpeg")


# ══════════════════════════════════════════════════════════════════
# 静态文件服务
# ══════════════════════════════════════════════════════════════════

import os

@app.route('/pages/<path:filename>')
def serve_pages(filename):
    """服务 pages 目录下的静态 HTML 文件"""
    pages_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pages')
    return send_from_directory(pages_dir, filename)

@app.route('/css/<path:filename>')
def serve_css(filename):
    """服务 css 目录下的样式文件"""
    css_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'css')
    return send_from_directory(css_dir, filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    """服务 js 目录下的脚本文件"""
    js_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'js')
    return send_from_directory(js_dir, filename)

# ══════════════════════════════════════════════════════════════════
# API 路由
# ══════════════════════════════════════════════════════════════════

# ── 健康检查 ──
@app.route("/health", methods=["GET"])
def health():
    """健康检查: 返回服务状态、缓存数量、最后更新时间"""
    f = get_fetcher()
    hdb = get_history_db()
    available_dates = hdb.get_available_dates()
    cache_count = len(f.get_all())
    return ok({
        "status": "running",
        "data_ready": cache_count > 0,
        "total": cache_count,
        "cache_count": cache_count,
        "last_fetch": f.last_fetch_time.isoformat() if f.last_fetch_time else None,
        "error": f.fetch_error,
        "refresh_interval_sec": Config.REFRESH_INTERVAL_SECONDS,
        "history_dates": available_dates,
        "history_days": len(available_dates),
        "chart_cache": get_chart_cache().get_stats(),
        "tasks": get_task_queue().get_stats(),
    })


# ── 手动刷新（仅返回当前缓存，不触发外部API调用） ──
# 外部API调用仅由中心服务器每5分钟自动发起的懒更新机制触发
@app.route("/refresh", methods=["POST"])
def refresh():
    """返回当前内存缓存状态，不触发新的数据抓取"""
    f = get_fetcher()
    return ok({
        "triggered": False,
        "note": "数据由服务端每5分钟自动刷新，此接口仅返回当前缓存",
        "count": len(f.get_all()),
        "last_fetch": f.last_fetch_time.isoformat() if f.last_fetch_time else None,
    })


# ── 手动补填历史数据 ──
@app.route("/init-history", methods=["POST"])
def init_history():
    """手动触发7天历史数据补填"""
    try:
        days = min(21, max(1, int(request.args.get("days", 7))))
    except ValueError:
        return err_resp("days 必须为正整数", code=10, status=400)
    try:
        from history_fetcher import fetch_historical_data
        rows = fetch_historical_data(days=days)
        hdb = get_history_db()
        # 重新加载缓存
        f = get_fetcher()
        f.load_from_history(hdb)
        # 注入三日均值
        avg_map = hdb.get_all_avg_premium_3d()
        with f._lock:
            for code, fund in f._cache.items():
                fund["avg_premium_3d"] = avg_map.get(code)
        return ok({"rows": rows, "dates": hdb.get_available_dates(), "cache_count": len(f.get_all())})
    except Exception as e:
        return err_resp(f"历史数据补填失败: {e}", code=11, status=500)


# ── 手动补填K线历史数据 ──
@app.route("/init-kline-history", methods=["POST"])
def init_kline_history():
    """手动触发365天K线历史数据补填（任务队列调度）"""
    tq = get_task_queue()

    def _do_kline_fetch():
        from history_fetcher import fetch_kline_historical_data
        return fetch_kline_historical_data()

    task = tq.submit("kline_backfill", "K线历史数据补填", _do_kline_fetch)
    if task.status.value == "running":
        return ok({"status": "already_running", "task": task.to_dict()})
    return ok({"status": "started", "task": task.to_dict()})


# ── 任务状态查询 ──
@app.route("/api/tasks", methods=["GET"])
def list_tasks():
    """查看后台任务状态"""
    tq = get_task_queue()
    return ok({"tasks": tq.get_stats()})


# ─────────────────────────────────────────────────────────────────
# 接口1: GET /api/funds
# 获取全量 LOF 基金列表（分页 + 排序 + 搜索 + 筛选）
# ─────────────────────────────────────────────────────────────────

@app.route("/api/funds", methods=["GET"])
def list_funds():
    # 懒更新：用户访问时检查数据是否陈旧，在后台触发刷新
    _trigger_lazy_refresh()
    f = get_fetcher()
    all_data = f.get_all()

    # 服务启动中，数据尚未加载
    if not all_data:
        return err_resp(
            "数据未就绪，服务正在初始化，请稍后重试",
            code=3,
            status=503,
            details={"tip": "首次启动约需 1-2 分钟加载全量数据"}
        )

    # ── 分页参数 ──
    try:
        page     = max(1, int(request.args.get("page", 1)))
        page_size = min(1000, max(1, int(request.args.get("page_size", 100))))
    except ValueError:
        return err_resp("page 和 page_size 必须为正整数", code=4, status=400)

    # ── 排序 ──
    sort_field = request.args.get("sort", "amount")
    sort_order = request.args.get("order", "desc")
    valid_sorts = {"amount", "change_pct", "premium_rate", "price", "code", "name", "avg_premium_3d"}
    if sort_field not in valid_sorts:
        return err_resp(f"sort 可选值: {','.join(valid_sorts)}", code=5, status=400)
    if sort_order not in {"asc", "desc"}:
        return err_resp("order 必须是 asc 或 desc", code=6, status=400)

    reverse = (sort_order == "desc")

    # ── 搜索（按代码或名称） ──
    search = (request.args.get("search") or "").strip()
    if search:
        s = search.upper()
        all_data = {k: v for k, v in all_data.items()
                    if s in k or s in v.get("name", "").upper()}

    # ── 溢价/折价筛选 ──
    filt = request.args.get("filter", "all")
    if filt == "premium":
        all_data = {k: v for k, v in all_data.items()
                    if (v.get("premium_rate") or 0) > 0}
    elif filt == "discount":
        all_data = {k: v for k, v in all_data.items()
                    if (v.get("premium_rate") or 0) < 0}

    # ── 停牌筛选（已移至前端处理，后端始终返回全部数据） ──
    # show_suspended = request.args.get("suspended", "0")
    # if show_suspended != "1":
    #     all_data = {k: v for k, v in all_data.items()
    #                 if not _is_suspended(v)}

    # ── 申购限额筛选（支持多选） ──
    purchase_limits = request.args.getlist("purchase_limit")
    if purchase_limits:
        # 分离特殊选项和数值选项
        special_filters = [p for p in purchase_limits if p in ['suspended', 'unlimited']]
        numeric_limits = [float(p) for p in purchase_limits if p not in ['suspended', 'unlimited']]
        
        def matches_filter(fund):
            can_purchase = fund.get("can_purchase")
            limit = fund.get("purchase_limit")
            
            # 检查是否匹配特殊选项
            if 'suspended' in special_filters and can_purchase is False:
                return True
            if 'unlimited' in special_filters and can_purchase is not False and limit is None:
                return True
            
            # 检查是否匹配数值选项
            if numeric_limits and limit in numeric_limits:
                return True
            
            return False
        
        all_data = {k: v for k, v in all_data.items() if matches_filter(v)}

    # ── 排序 ──
    items = list(all_data.values())
    
    # ── 补充份额数据并计算增量 ──
    hdb = get_history_db()
    shares_map = hdb.get_all_latest_shares()
    
    for item in items:
        code = item.get("code")
        if not code: continue
        
        # 1. 如果缓存中没有份额，从数据库补全
        if item.get("shares") is None and code in shares_map:
            share_info = shares_map[code]
            item["shares"] = share_info.get("shares")
            item["shares_date"] = share_info.get("date")
            item["shares_source"] = share_info.get("source")
        
        # 2. 统一计算新增份额（对比上一个不同日期的数据）
        try:
            # 获取最近 7 天的数据，确保能找到两个不同日期的记录
            prev_shares_info = hdb.get_shares_by_code(code, days=7)
            if len(prev_shares_info) >= 2:
                latest = prev_shares_info[0]
                # 找到第一个与最新日期不同的记录
                previous = None
                for record in prev_shares_info[1:]:
                    if record.get('date') != latest.get('date'):
                        previous = record
                        break
                
                if previous:
                    s1 = latest.get('shares', 0)
                    s2 = previous.get('shares', 0)
                    today_share = float(s1) if s1 is not None else 0.0
                    yesterday_share = float(s2) if s2 is not None else 0.0
                    incr_val = round(today_share - yesterday_share, 2)
                    item["shares_incr"] = incr_val
                else:
                    item["shares_incr"] = 0
            else:
                item["shares_incr"] = 0
        except Exception as e:
            item["shares_incr"] = 0
    
    if sort_field == "premium_rate":
        items.sort(key=lambda x: x.get("premium_rate") if x.get("premium_rate") is not None else -9999.0, reverse=reverse)
    elif sort_field == "change_pct":
        items.sort(key=lambda x: x.get("change_pct") if x.get("change_pct") is not None else 0, reverse=reverse)
    elif sort_field == "amount":
        items.sort(key=lambda x: x.get("amount") if x.get("amount") is not None else 0, reverse=reverse)
    elif sort_field == "price":
        items.sort(key=lambda x: x.get("price") if x.get("price") is not None else 0, reverse=reverse)
    elif sort_field == "code":
        items.sort(key=lambda x: x.get("code", ""), reverse=reverse)
    elif sort_field == "name":
        items.sort(key=lambda x: x.get("name", ""), reverse=reverse)
    elif sort_field == "avg_premium_3d":
        items.sort(key=lambda x: x.get("avg_premium_3d") if x.get("avg_premium_3d") is not None else -9999.0, reverse=reverse)

    total = len(items)
    start = (page - 1) * page_size
    
    page_items = [_fmt(f) for f in items[start: start + page_size]]

    return ok(
        page_items,
        meta={
            "page":        page,
            "page_size":   page_size,
            "total":       total,
            "total_pages": (total + page_size - 1) // page_size,
            "last_fetch":  f.last_fetch_time.isoformat() if f.last_fetch_time else None,
            "data_source": "东方财富 + 天天基金网",
        }
    )


@app.route("/api/purchase-limits", methods=["GET"])
def get_purchase_limits():
    """获取所有申购限额选项（用于下拉多选）"""
    f = get_fetcher()
    all_data = f.get_all()
    
    # 收集所有不同的申购限额值
    limits_set = set()
    has_suspended = False
    has_unlimited = False
    
    for fund in all_data.values():
        can_purchase = fund.get("can_purchase")
        limit = fund.get("purchase_limit")
        
        # 检查是否有暂停申购的基金
        if can_purchase is False:
            has_suspended = True
        # 检查是否有开放申购（无限额）的基金
        elif can_purchase is not False and limit is None:
            has_unlimited = True
        # 只有可申购且有具体限额的基金，才收集限额值
        elif can_purchase is not False and limit is not None:
            limits_set.add(limit)
    
    # 转换为列表并排序
    limits_list = sorted(list(limits_set))
    
    # 添加特殊选项：暂停申购和开放申购
    special_options = []
    if has_suspended:
        special_options.append({"value": "suspended", "label": "暂停申购"})
    if has_unlimited:
        special_options.append({"value": "unlimited", "label": "开放申购"})
    
    return ok({
        "limits": limits_list,
        "special_options": special_options,
        "count": len(limits_list) + len(special_options)
    })


@app.route("/api/debug/cache/<code>", methods=["GET"])
def debug_cache_raw(code: str):
    """临时调试端点：直接读原始cache，不走_fmt"""
    f = get_fetcher()
    fund = f.get_one(code)
    return ok({"raw": fund, "cache_count": len(f.get_all())})

# ─────────────────────────────────────────────────────────────────
# 接口2: GET /api/funds/<code>
# 获取单只 LOF 基金详情
# ─────────────────────────────────────────────────────────────────

@app.route("/api/funds/<code>", methods=["GET"])
def fund_detail(code: str):
    # 懒更新
    _trigger_lazy_refresh()
    f = get_fetcher()
    fund = f.get_one(code)
    if not fund:
        return err_resp(
            f"未找到基金: {code}",
            code=7,
            status=404,
            details={"code": code, "tip": "请确认基金代码为6位数字，如 166009"}
        )
    return ok(_fmt(fund, detail=True))


# ─────────────────────────────────────────────────────────────────

@app.route("/api/funds/<code>/chart", methods=["GET"])
def fund_chart(code: str):
    """获取基金历史价格/净值曲线数据，支持 7/30/365 日。热门基金优先从缓存读取"""
    f = get_fetcher()
    fund = f.get_one(code)
    if not fund:
        return err_resp(f"未找到基金: {code}", code=7, status=404)

    try:
        days = min(365, max(7, int(request.args.get("days", 7))))
    except ValueError:
        days = 7

    # 检查预渲染缓存
    cc = get_chart_cache()
    cached = cc.get(code)
    if cached and str(days) in cached.get("charts", {}):
        chart = cached["charts"][str(days)]
        if chart:
            return ok({
                "code": code,
                "name": fund.get("name"),
                "days": days,
                "chart": chart,
                "cached": True,
            })

    # 未缓存，实时查询
    hdb = get_history_db()
    raw = hdb.get_kline_history(code=code, days=days)
    filtered = filter_and_forward_fill(raw)

    return ok({
        "code": code,
        "name": fund.get("name"),
        "days": days,
        "chart": filtered,
    })

# ══════════════════════════════════════════════════════════════════
# 历史数据 API
# ══════════════════════════════════════════════════════════════════

@app.route("/api/history", methods=["GET"])
def history():
    """
    获取历史溢价率数据
    参数:
      code: 基金代码（可选，不传则返回概览）
      days: 查询天数（默认7，最大7）
    """
    _trigger_lazy_refresh()
    hdb = get_history_db()

    try:
        days = min(21, max(1, int(request.args.get("days", 7))))
    except ValueError:
        return err_resp("days 必须为正整数", code=9, status=400)

    code = request.args.get("code")
    code = code.strip().zfill(6) if code else None

    if code:
        # 单只基金历史
        fund = get_fetcher().get_one(code)
        if not fund:
            return err_resp(f"未找到基金: {code}", code=7, status=404)
        data = hdb.get_history(code=code, days=days)
        avg = hdb.get_avg_premium_3d(code)
        return ok({
            "code": code,
            "name": fund.get("name"),
            "avg_premium_3d": avg,
            "history": data,
        })
    else:
        # 全量概览：返回可用日期列表 + 所有基金的三日均溢
        avg_map = hdb.get_all_avg_premium_3d()
        dates = hdb.get_available_dates()
        return ok({
            "available_dates": dates,
            "avg_premium_3d": avg_map,
        }, meta={
            "history_days": len(dates),
        })


@app.route("/api/shares", methods=["GET"])
def get_shares():
    """
    获取基金份额数据
    参数:
      code: 基金代码（可选，不传则返回所有基金最新份额）
      days: 查询天数（默认30，仅当指定code时有效）
    """
    _trigger_lazy_refresh()
    hdb = get_history_db()

    code = request.args.get("code")
    code = code.strip().zfill(6) if code else None

    if code:
        # 单只基金份额历史
        days = min(90, max(1, int(request.args.get("days", 30))))
        data = hdb.get_shares_by_code(code=code, days=days)
        latest = hdb.get_latest_shares(code=code)
        
        fund = get_fetcher().get_one(code)
        fund_name = fund.get("name", code) if fund else code
        
        return ok({
            "code": code,
            "name": fund_name,
            "latest": latest,
            "history": data,
        })
    else:
        # 全量最新份额
        all_shares = hdb.get_all_latest_shares()
        return ok({
            "shares": all_shares,
            "count": len(all_shares),
        })


@app.route("/api/shares/fetch", methods=["POST"])
def fetch_shares_now():
    """
    立即触发份额数据抓取（后台执行）
    """
    try:
        from data_fetcher import get_fetcher
        fetcher = get_fetcher()
        # 异步获取份额数据
        fetcher._fetch_and_save_shares([])
        return ok({
            "message": "份额数据抓取任务已启动（后台执行）",
        })
    except Exception as e:
        return err_resp(f"启动失败: {str(e)}", code=10, status=500)


# ══════════════════════════════════════════════════════════════════
# 懒更新机制（替代 APScheduler，适用于 Railway 等休眠平台）
# ══════════════════════════════════════════════════════════════════

import threading

_lazy_refreshing = False   # 防止并发刷新
_lazy_lock = threading.Lock()


def _trigger_lazy_refresh():
    """
    检查数据是否陈旧，若是则在后台线程触发刷新。
    所有 API 请求入口调用此方法，确保数据常新。
    """
    global _lazy_refreshing
    f = get_fetcher()

    # 缓存为空时强制刷新（Railway重启后PostgreSQL丢失场景）
    cache_empty = len(f.get_all()) == 0

    # 检查是否需要刷新
    if not cache_empty and f.last_fetch_time is not None:
        age = (datetime.now(timezone.utc) - f.last_fetch_time).total_seconds()
        if age < Config.REFRESH_INTERVAL_SECONDS:
            return  # 数据还新鲜，不用刷新

    # 避免并发刷新
    if _lazy_refreshing:
        return

    with _lazy_lock:
        if _lazy_refreshing:
            return
        _lazy_refreshing = True

    def _do_refresh():
        nonlocal cache_empty
        try:
            logger.info("⏰ 懒更新触发，开始刷新...")
            ok_flag = f.fetch_all()
            if ok_flag:
                # 保存溢价率快照到历史数据库
                try:
                    hdb = get_history_db()
                    hdb.save_snapshot(f.get_all())
                    # 注入三日平均溢价率到缓存
                    avg_map = hdb.get_all_avg_premium_3d()
                    with f._lock:
                        for code, fund in f._cache.items():
                            fund["avg_premium_3d"] = avg_map.get(code)
                    # 刷新热门基金曲线图缓存
                    try:
                        cc = get_chart_cache()
                        cc.refresh(hdb, f.get_all())
                    except Exception as ex:
                        logger.debug(f"Chart cache refresh skipped: {ex}")
                except Exception as ex:
                    logger.warning(f"历史数据保存失败: {ex}")
                logger.info(f"✅ 懒更新完成，当前缓存 {len(f.get_all())} 只基金")
            else:
                # 实时抓取失败，尝试从历史数据降级
                if len(f.get_all()) == 0:
                    hdb = get_history_db()
                    hist_ok = f.load_from_history(hdb)
                    if hist_ok:
                        try:
                            avg_map = hdb.get_all_avg_premium_3d()
                            with f._lock:
                                for code, fund in f._cache.items():
                                    fund["avg_premium_3d"] = avg_map.get(code)
                        except Exception as ex:
                            logger.warning(f"历史三日均溢计算失败: {ex}")
                        logger.info(f"✅ 懒更新降级到历史数据，{len(f.get_all())} 只基金")
                    else:
                        logger.warning("⚠️ 懒更新失败且无历史数据可用，稍后重试")
                else:
                    logger.warning("⚠️ 懒更新失败，继续使用当前缓存")
        finally:
            global _lazy_refreshing
            _lazy_refreshing = False

    t = threading.Thread(target=_do_refresh, daemon=True)
    t.start()


# ══════════════════════════════════════════════════════════════════
# 启动初始化（gunicorn兼容 - 模块导入时执行后台初始化）
# ══════════════════════════════════════════════════════════════════

def _startup_init():
    """
    后台初始化线程，模块导入时启动。
    兼容 gunicorn：不依赖 __main__ 块。
    策略：seed文件 → history_db → 实时API（逐级降级）
    """
    f = get_fetcher()
    hdb = get_history_db()

    # ── 第一步：从种子文件加载数据（解决Railway重启PostgreSQL丢失问题）──
    available_dates = hdb.get_available_dates()
    cache_empty = len(f.get_all()) == 0

    if cache_empty and len(available_dates) < 3:
        logger.info("📦 缓存为空且历史数据不足，尝试从种子文件加载...")
        seed_ok = f.load_from_seed()
        if seed_ok:
            # 注入三日平均溢价率
            try:
                avg_map = hdb.get_all_avg_premium_3d()
                with f._lock:
                    for code, fund in f._cache.items():
                        fund["avg_premium_3d"] = avg_map.get(code)
            except Exception as ex:
                logger.warning(f"⚠️ 三日均溢计算失败: {ex}")
            cache_count = len(f.get_all())
            logger.info(f"✅ 种子数据加载完成，{cache_count} 只基金已就绪")
        else:
            logger.info("⚠️ 种子文件不可用，尝试从history_db降级...")
            hist_ok = f.load_from_history(hdb)
            if hist_ok:
                try:
                    avg_map = hdb.get_all_avg_premium_3d()
                    with f._lock:
                        for code, fund in f._cache.items():
                            fund["avg_premium_3d"] = avg_map.get(code)
                except Exception as ex:
                    logger.warning(f"⚠️ 三日均溢计算失败: {ex}")
                logger.info(f"✅ 历史数据降级加载完成，{len(f.get_all())} 只基金")
            else:
                # 尝试从API补填（可能因网络问题失败）
                logger.info("📦 尝试从API补填历史数据...")
                try:
                    from history_fetcher import fetch_historical_data
                    rows = fetch_historical_data(days=7)
                    logger.info(f"✅ 历史数据补填完成，共 {rows} 条记录")
                except Exception as ex:
                    logger.warning(f"⚠️ 历史数据补填失败: {ex}")
    elif cache_empty and len(available_dates) >= 3:
        # PostgreSQL有数据，直接加载
        logger.info(f"📦 从history_db加载（{len(available_dates)}天数据）...")
        hist_ok = f.load_from_history(hdb)
        if hist_ok:
            try:
                avg_map = hdb.get_all_avg_premium_3d()
                with f._lock:
                    for code, fund in f._cache.items():
                        fund["avg_premium_3d"] = avg_map.get(code)
            except Exception as ex:
                logger.warning(f"⚠️ 三日均溢计算失败: {ex}")
            logger.info(f"✅ 历史数据加载完成，{len(f.get_all())} 只基金已就绪")
    else:
        logger.info(f"📦 缓存已有 {len(f.get_all())} 只基金，跳过初始化")

    # ── 第二步：尝试实时数据抓取 ──
    logger.info("📡 正在尝试拉取实时数据...")
    ok_flag = f.fetch_all()
    if ok_flag:
        try:
            hdb.save_snapshot(f.get_all())
            avg_map = hdb.get_all_avg_premium_3d()
            with f._lock:
                for code, fund in f._cache.items():
                    fund["avg_premium_3d"] = avg_map.get(code)
            try:
                cc = get_chart_cache()
                cc.refresh(hdb, f.get_all())
            except Exception as ex:
                logger.debug(f"Chart cache refresh skipped: {ex}")
        except Exception as ex:
            logger.warning(f"历史数据保存失败: {ex}")
        logger.info(f"✅ 实时数据刷新完成，{len(f.get_all())} 只基金")
    else:
        logger.info("⚠️ 实时数据抓取失败，继续使用历史数据服务")


# 启动后台初始化线程（gunicorn导入模块时自动触发）
_init_thread = threading.Thread(target=_startup_init, daemon=True)
_init_thread.start()

# ══════════════════════════════════════════════════════════════════
# 定时任务：每天早上7点自动抓取份额数据
# ══════════════════════════════════════════════════════════════════

def _scheduled_fetch_shares():
    """定时任务：自动抓取前一天的份额数据（仅早上7点执行）"""
    try:
        from trading_calendar import is_trading_day, get_last_trading_date
        
        # 检查今天是否为交易日
        if not is_trading_day():
            logger.info("⏰ 定时任务：今天是非交易日，跳过份额数据抓取")
            return
        
        logger.info("⏰ 定时任务触发：开始抓取份额数据")
        
        # 获取上一个交易日的日期
        last_trading_date = get_last_trading_date()
        logger.info(f"将抓取 {last_trading_date} 的份额数据")
        
        # 从交易所 API 获取份额数据
        from datasource.share_source import ExchangeShareSource
        from history_db import get_history_db
        
        share_source = ExchangeShareSource()
        hdb = get_history_db()
        
        shares_data = share_source.fetch_all_shares(date=last_trading_date)
        
        if shares_data:
            saved_count = hdb.save_shares_batch(shares_data, date=last_trading_date)
            logger.info(f"✅ 定时任务：份额数据抓取成功，保存 {saved_count} 条记录")
        else:
            logger.warning("⚠️  定时任务：未获取到份额数据")
            
    except Exception as e:
        logger.error(f"❌ 定时任务：份额数据抓取失败: {e}")

# 初始化定时任务调度器
scheduler = BackgroundScheduler(timezone='Asia/Shanghai')
scheduler.start()
logger.info("⏰ 定时任务调度器已启动")


# K线数据播种已改为手动触发: POST /init-kline-history
# 避免部署时因长耗时健康检查超时导致失败


# ══════════════════════════════════════════════════════════════════
# 企业微信通知功能
# ══════════════════════════════════════════════════════════════════

# 全局变量：企业微信通知器实例
wework_notifier = None

def init_wework_notifier():
    """初始化企业微信通知器（从环境变量读取配置）"""
    global wework_notifier
    
    try:
        from wework_notifier import create_notifier_from_env
        wework_notifier = create_notifier_from_env()
        
        if wework_notifier:
            logger.info("✅ 企业微信通知器初始化成功")
        else:
            logger.info("ℹ️  未配置企业微信通知（WEWORK_CORPID等环境变量为空）")
    except Exception as e:
        logger.error(f"初始化企业微信通知器失败: {e}")


def send_shares_update_notification(shares_count: int, date: str):
    """
    发送份额更新通知
    
    Args:
        shares_count: 更新的基金数量
        date: 数据日期
    """
    if not wework_notifier:
        return
    
    try:
        # 使用新的通知格式（与 lof_project2 保持一致）
        wework_notifier.send_shares_update_notification(shares_count, date)
        logger.info("企业微信通知发送成功")
    except Exception as e:
        logger.error(f"发送企业微信通知失败: {e}")


# 初始化企业微信通知器
init_wework_notifier()

# 初始化定时任务（支持多个时间）
def init_wework_schedule():
    """初始化企业微信定时任务（从环境变量读取配置）"""
    import os
    
    # 检查定时任务是否启用
    schedule_enabled = os.getenv('WEWORK_SCHEDULE_ENABLED', 'true').strip().lower()
    if schedule_enabled not in ('true', '1', 'yes'):
        logger.info("ℹ️  企业微信定时任务未启用（WEWORK_SCHEDULE_ENABLED=false）")
        return
    
    # 1. 每天早上7点固定执行份额数据抓取
    scheduler.add_job(
        func=_scheduled_fetch_shares,
        trigger='cron',
        hour=7,
        minute=0,
        id='wework_shares_0700',
        name='每日份额数据抓取 (07:00)',
        replace_existing=True
    )
    logger.info("✅ 定时任务已添加: 每日 07:00 份额数据抓取")
    
    # 2. 根据 WEWORK_SCHEDULE_TIMES 配置发送基金溢价信息通知
    schedule_times_str = os.getenv('WEWORK_SCHEDULE_TIMES', '').strip()
    
    if not schedule_times_str:
        logger.info("ℹ️  未配置 WEWORK_SCHEDULE_TIMES，不发送定时溢价通知")
        return
    
    # 解析逗号分隔的时间列表
    schedule_times = [t.strip() for t in schedule_times_str.split(',')]
    logger.info(f"✅ 企业微信溢价通知时间配置: {', '.join(schedule_times)}")
    
    # 为每个时间添加定时通知任务
    for time_str in schedule_times:
        try:
            # 解析时间格式 HH:MM
            parts = time_str.split(':')
            if len(parts) != 2:
                logger.warning(f"⚠️  时间格式错误: {time_str}，跳过")
                continue
            
            hour = int(parts[0])
            minute = int(parts[1])
            
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                logger.warning(f"⚠️  时间超出范围: {time_str}，跳过")
                continue
            
            # 添加定时通知任务
            job_id = f'wework_notify_{hour:02d}{minute:02d}'
            scheduler.add_job(
                func=lambda: manual_wework_notify(),
                trigger='cron',
                hour=hour,
                minute=minute,
                id=job_id,
                name=f'企业微信溢价通知 ({time_str})',
                replace_existing=True
            )
            
            logger.info(f"✅ 定时任务已添加: {time_str} 溢价通知")
            
        except Exception as e:
            logger.error(f"❌ 添加定时任务失败 ({time_str}): {e}")

# 初始化定时任务
init_wework_schedule()


# ══════════════════════════════════════════════════════════════════
# API：手动触发企业微信通知
# ══════════════════════════════════════════════════════════════════

@app.route("/api/wework/notify", methods=["POST"])
def manual_wework_notify():
    """
    手动触发企业微信通知（发送基金日报）
    
    Returns:
        JSON响应
    """
    if not wework_notifier:
        return error("企业微信未配置", 400)
    
    try:
        # 先触发懒刷新，确保使用最新数据
        _trigger_lazy_refresh()
        
        # 等待一下让刷新完成（最多等待10秒）
        import time
        f = get_fetcher()
        wait_count = 0
        while wait_count < 20:  # 最多等待20*0.5=10秒
            # 检查最后更新时间，如果最近30秒内更新过，说明数据已就绪
            if f.last_fetch_time:
                from datetime import datetime, timezone
                age = (datetime.now(timezone.utc) - f.last_fetch_time).total_seconds()
                if age < 30:  # 数据在30秒内更新过
                    break
            time.sleep(0.5)
            wait_count += 1
        
        # 获取最新的基金数据
        all_data = f.get_all()
        
        # get_all() 返回的是 {code: fund_info, ...} 格式
        if isinstance(all_data, dict):
            realtime_data = list(all_data.values())
        else:
            realtime_data = all_data
        
        if not realtime_data:
            return error("无法获取基金数据", 500)
        
        # 确保所有基金都有 shares_incr 和 shares 字段
        # 从数据库中补全份额数据
        from history_db import HistoryDB
        hdb = HistoryDB()
        
        # 获取所有基金的份额数据（最近7天）
        shares_map = {}
        for fund in realtime_data:
            code = fund.get('code')
            if code:
                try:
                    shares_info = hdb.get_shares_by_code(code, days=7)
                    if shares_info:
                        latest = shares_info[0]
                        shares_map[code] = {
                            'shares': latest.get('shares'),
                            'date': latest.get('date'),
                            'source': latest.get('source')
                        }
                except Exception:
                    pass
        
        # 补全份额数据和计算新增份额
        for fund in realtime_data:
            code = fund.get('code')
            if not code:
                continue
            
            # 1. 如果缓存中没有份额，从数据库补全
            if fund.get('shares') is None and code in shares_map:
                share_info = shares_map[code]
                fund['shares'] = share_info.get('shares')
                fund['shares_date'] = share_info.get('date')
                fund['shares_source'] = share_info.get('source')
            
            # 2. 统一计算新增份额（对比上一个不同日期的数据）
            try:
                prev_shares_info = hdb.get_shares_by_code(code, days=30)
                if len(prev_shares_info) >= 2:
                    latest = prev_shares_info[0]
                    # 找到第一个与最新日期不同的记录
                    previous = None
                    for record in prev_shares_info[1:]:
                        if record.get('date') != latest.get('date'):
                            previous = record
                            break
                    
                    if previous:
                        s1 = latest.get('shares', 0)
                        s2 = previous.get('shares', 0)
                        today_share = float(s1) if s1 is not None else 0.0
                        yesterday_share = float(s2) if s2 is not None else 0.0
                        incr_val = round(today_share - yesterday_share, 2)
                        fund['shares_incr'] = incr_val
                    else:
                        fund['shares_incr'] = 0
                else:
                    fund['shares_incr'] = 0
            except Exception:
                fund['shares_incr'] = 0
        
        # 从环境变量读取阈值（默认值：溢价 5%，折价 3%）
        import os
        try:
            premium_threshold = float(os.getenv('WEWORK_PREMIUM_THRESHOLD', '5.0'))
        except ValueError:
            premium_threshold = 5.0
        
        try:
            discount_threshold = float(os.getenv('WEWORK_DISCOUNT_THRESHOLD', '3.0'))
        except ValueError:
            discount_threshold = 3.0
        
        logger.info(f"[企业微信] 使用阈值 - 溢价: ≥{premium_threshold}%, 折价: ≤-{discount_threshold}%")
        
        # 筛选溢价和折价基金
        premium_funds = []
        discount_funds = []
        skipped_count = 0
        
        for fund in realtime_data:
            # 调试日志
            if not isinstance(fund, dict):
                logger.error(f"基金数据格式错误: {type(fund)} = {fund}")
                continue
            
            fund_code = fund.get('code', '')
            fund_name = fund.get('name', '')
            
            # 获取申购状态
            can_purchase = fund.get('can_purchase')
            purchase_limit = fund.get('purchase_limit')
            
            # 如果 can_purchase 为 False，说明暂停申购
            if can_purchase is False:
                purchase_info = '暂停申购'
            elif purchase_limit is not None:
                purchase_info = str(purchase_limit)
            else:
                purchase_info = '开放申购'
            
            premium_rate = fund.get('premium_rate', 0)
            
            # 过滤停牌基金（与前端保持一致，使用 _is_suspended 函数判断）
            if _is_suspended(fund):
                continue
            
            if premium_rate is None:
                continue
            
            # premium_rate 已经是百分比值（如 5.0 表示 5%），不需要再乘以 100
            rate_percent = premium_rate
            
            # 溢价基金
            if rate_percent >= premium_threshold:
                # 过滤停牌基金
                if _is_suspended(fund):
                    continue
                
                if purchase_info and ('暂停' in purchase_info or '关闭' in purchase_info):
                    skipped_count += 1
                    continue
                
                premium_funds.append({
                    'code': fund_code,
                    'name': fund_name,
                    'rate': rate_percent,
                    'type': '溢价',
                    'purchaseInfo': purchase_info,
                    'sharesIncr': fund.get('shares_incr'),
                    'shares': fund.get('shares')
                })
                logger.info(f"[企业微信] 溢价基金 {fund_code}: shares_incr={fund.get('shares_incr')}, shares={fund.get('shares')}")
            # 折价基金
            elif rate_percent <= -discount_threshold:
                discount_funds.append({
                    'code': fund_code,
                    'name': fund_name,
                    'rate': rate_percent,
                    'type': '折价',
                    'purchaseInfo': purchase_info,
                    'sharesIncr': fund.get('shares_incr'),
                    'shares': fund.get('shares')
                })
                logger.info(f"[企业微信] 折价基金 {fund_code}: shares_incr={fund.get('shares_incr')}, shares={fund.get('shares')}")
        
        # 按绝对值排序
        premium_funds.sort(key=lambda x: x['rate'], reverse=True)
        discount_funds.sort(key=lambda x: abs(x['rate']), reverse=True)
        
        # 构建报告内容
        from datetime import datetime
        current_date = datetime.now().strftime('%Y-%m-%d')
        current_time = datetime.now().strftime('%H:%M')
        
        content = f"📊 LOF基金日报 ({current_date} {current_time})\n"
        content += "━━━━━━━━━━━━━━━━━━━━━━\n"
        content += f"溢价阈值: ≥{premium_threshold}% | 折价阈值: ≤-{discount_threshold}%\n"
        content += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # 溢价基金部分
        if premium_funds:
            content += f"🔺 溢价基金 ({len(premium_funds)}只)\n"
            content += "─" * 40 + "\n"
            for idx, fund in enumerate(premium_funds, 1):  # 显示所有溢价基金
                # 根据 purchaseInfo 显示不同的状态
                purchase_info = fund['purchaseInfo']
                if purchase_info == '暂停申购':
                    purchase_status = '❌暂停'
                elif purchase_info and purchase_info.replace('.', '').isdigit():
                    # 是数字，显示限购金额
                    limit_value = float(purchase_info)
                    if limit_value >= 10000:
                        purchase_status = f'限购{int(limit_value/10000)}万'
                    else:
                        purchase_status = f'限购{int(limit_value)}元'
                else:
                    purchase_status = '✅开放'
                
                # 格式化新增份额
                shares_incr = fund.get('sharesIncr')
                shares = fund.get('shares')
                shares_info = ''
                
                if shares_incr is not None and shares_incr != 0:
                    # 份额数据单位已经是万份，直接使用
                    incr_wan = shares_incr
                    # 计算百分比变化
                    incr_rate_text = ''
                    if shares is not None:
                        # 兼容 Decimal 类型
                        yesterday_shares = float(shares) - shares_incr  # 昨日份额 = 当前份额 - 新增份额
                        if yesterday_shares > 0:
                            rate = (shares_incr / yesterday_shares * 100)
                            if rate >= 0:
                                incr_rate_text = f'(+{rate:.0f}%)'
                            else:
                                incr_rate_text = f'({rate:.0f}%)'
                    
                    # 根据数值大小决定显示格式
                    if abs(incr_wan) >= 1:
                        # 大于等于1万，显示整数
                        if incr_wan >= 0:
                            shares_info = f' 📈+{incr_wan:.0f}万{incr_rate_text}'
                        else:
                            shares_info = f' 📉{incr_wan:.0f}万{incr_rate_text}'
                    else:
                        # 小于1万，显示一位小数
                        if incr_wan >= 0:
                            shares_info = f' 📈+{incr_wan:.1f}万{incr_rate_text}'
                        else:
                            shares_info = f' 📉{incr_wan:.1f}万{incr_rate_text}'
                
                content += f"{idx}. {fund['code']} {fund['name']}\n"
                content += f"   溢价 {fund['rate']:.2f}% {purchase_status}{shares_info}\n"
            content += "\n"
        else:
            content += f"🔺 溢价基金: 无\n\n"
        
        content += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # 折价基金部分
        if discount_funds:
            content += f"🔻 折价基金 ({len(discount_funds)}只)\n"
            content += "─" * 40 + "\n"
            for idx, fund in enumerate(discount_funds, 1):  # 显示所有折价基金
                # 根据 purchaseInfo 显示不同的状态
                purchase_info = fund['purchaseInfo']
                if purchase_info == '暂停申购':
                    purchase_status = '❌暂停'
                elif purchase_info and purchase_info.replace('.', '').isdigit():
                    # 是数字，显示限购金额
                    limit_value = float(purchase_info)
                    if limit_value >= 10000:
                        purchase_status = f'限购{int(limit_value/10000)}万'
                    else:
                        purchase_status = f'限购{int(limit_value)}元'
                else:
                    purchase_status = '✅开放'
                
                # 格式化新增份额
                shares_incr = fund.get('sharesIncr')
                shares = fund.get('shares')
                shares_info = ''
                
                if shares_incr is not None and shares_incr != 0:
                    # 份额数据单位已经是万份，直接使用
                    incr_wan = shares_incr
                    # 计算百分比变化
                    incr_rate_text = ''
                    if shares is not None:
                        # 兼容 Decimal 类型
                        yesterday_shares = float(shares) - shares_incr  # 昨日份额 = 当前份额 - 新增份额
                        if yesterday_shares > 0:
                            rate = (shares_incr / yesterday_shares * 100)
                            if rate >= 0:
                                incr_rate_text = f'(+{rate:.0f}%)'
                            else:
                                incr_rate_text = f'({rate:.0f}%)'
                    
                    # 根据数值大小决定显示格式
                    if abs(incr_wan) >= 1:
                        # 大于等于1万，显示整数
                        if incr_wan >= 0:
                            shares_info = f' 📈+{incr_wan:.0f}万{incr_rate_text}'
                        else:
                            shares_info = f' 📉{incr_wan:.0f}万{incr_rate_text}'
                    else:
                        # 小于1万，显示一位小数
                        if incr_wan >= 0:
                            shares_info = f' 📈+{incr_wan:.1f}万{incr_rate_text}'
                        else:
                            shares_info = f' 📉{incr_wan:.1f}万{incr_rate_text}'
                
                content += f"{idx}. {fund['code']} {fund['name']}\n"
                content += f"   折价 {abs(fund['rate']):.2f}% {purchase_status}{shares_info}\n"
            content += "\n"
        else:
            content += f"🔻 折价基金: 无\n\n"
        
        # 总结
        total_count = len(premium_funds) + len(discount_funds)
        content += "━━━━━━━━━━━━━━━━━━━━━━\n"
        content += f"合计: {total_count}只 (溢价{len(premium_funds)}只 + 折价{len(discount_funds)}只)\n"
        content += "⚠️ 数据仅供参考，投资需谨慎"
        
        # 发送消息
        success = wework_notifier.send_text_message(content)
        
        if success:
            logger.info(f"[企业微信] 每日报告发送成功")
            logger.info(f"   - 溢价基金: {len(premium_funds)} 只")
            logger.info(f"   - 折价基金: {len(discount_funds)} 只")
            logger.info(f"   - 跳过暂停申购: {skipped_count} 只")
            logger.info(f"   - 总计通知: {total_count} 只")
            return ok({"message": "基金日报发送成功", "count": total_count})
        else:
            return error("通知发送失败", 500)
            
    except Exception as e:
        logger.error(f"手动发送基金日报失败: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return error(f"发送失败: {str(e)}", 500)


# ══════════════════════════════════════════════════════════════════
# 本地开发启动入口
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 62)
    print("  LOF基金数据服务  v1.2")
    print("  数据源: 东方财富 + 天天基金网（免费公开，无需Key）")
    print("=" * 62)
    print("✅ 服务已启动（后台初始化中）")
    print(f"   API文档: http://localhost:{Config.PORT}/api/funds")
    print(f"   健康检查: http://localhost:{Config.PORT}/health")
    print(f"   溢价排行: http://localhost:{Config.PORT}/api/rankings")
    print(f"   刷新间隔: {Config.REFRESH_INTERVAL_SECONDS}秒（用户访问时触发）")
    print("=" * 62)

    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG,
        use_reloader=False,
        threaded=True,
    )
