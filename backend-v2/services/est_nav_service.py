"""
估算净值服务 — 独立模块，不依赖其他服务 (v2: 含持仓明细)

职责:
  1. 拉取资产涨跌幅 (asset_quote)
  2. 计算估算净值 (est_nav)
  3. 缓存结果到 Redis

Redis Key:
  est_nav:all  → 全部基金估算净值 (TTL 300s)
"""
import logging
import time

import httpx

import database
from cache import cache_get, cache_set
from fetchers.asset_quote import fetch_asset_quotes
from processors.est_nav import calc_all_est_navs, load_fund_meta, load_holdings
from metrics import metrics

logger = logging.getLogger("app")

# Redis Key (v2 = 包含 holding_details/index_detail/nav 完整字段)
EST_NAV_KEY = "est_nav:v2"
# 生成时间单独放一个键：塞进上面的 dict 会被 _est_nav_data_to_records 当成基金代码。
EST_NAV_META_KEY = "est_nav:meta"
EST_NAV_TTL = 259200  # 72小时 — 覆盖周末及长假，非交易时段仍可查看最近估算值


async def run_est_nav(client: httpx.AsyncClient) -> dict:
    """
    执行一次估算净值计算。

    Args:
        client: httpx.AsyncClient (复用调度器的连接)

    Returns:
        {fund_code: {est_nav, est_change_pct, ...}} 或空字典
    """
    start = time.monotonic()

    sf = database.async_session_factory
    if not sf:
        logger.warning("[EST_NAV_SERVICE] 数据库未初始化")
        return {}

    try:
        async with sf() as session:
            # 1. 加载元数据
            meta = await load_fund_meta(session)
            holdings = await load_holdings(session)
            both = set(meta.keys()) & set(holdings.keys())

            if not both:
                logger.warning("[EST_NAV_SERVICE] 无可计算的基金")
                return {}

            # 2. 收集需要查询的资产
            from sqlalchemy import text as sql_text
            r = await session.execute(sql_text(
                'SELECT code, market, asset_type FROM asset_master'
            ))
            asset_info = {
                row[0]: {'code': row[0], 'market': row[1], 'asset_type': row[2]}
                for row in r.fetchall()
            }

            need_quotes = set()
            for fc in both:
                for h in holdings[fc]:
                    need_quotes.add(h['asset_code'])
                m = meta[fc]
                if m['index_tcode']:
                    need_quotes.add(m['index_tcode'])

            quote_assets = []
            for acode in need_quotes:
                if acode in asset_info:
                    quote_assets.append(asset_info[acode])
                elif acode.startswith(('sh', 'sz', 'hk')):
                    quote_assets.append({'code': acode, 'market': '', 'asset_type': 'index'})

            # 3. 拉涨跌幅
            quotes = await fetch_asset_quotes(client, quote_assets)

            # 4. 计算估算净值
            results = await calc_all_est_navs(session, quotes)

        # 5. 序列化结果
        data = {}
        for fc, r in results.items():
            data[fc] = {
                'est_nav': r.est_nav,
                'est_change_pct': r.est_change_pct,
                'holdings_contrib': r.holdings_contrib,
                'index_contrib': r.index_contrib,
                'coverage': r.coverage,
                'holding_details': r.holding_details or [],
                'index_detail': r.index_detail,
                'nav': r.nav,
                # 基准净值的日期。估算描述的是"这一天之后的下一个交易日"，
                # 落盘时用它判断这份估算到底属于哪个 trade_date。
                'nav_date': r.nav_date.isoformat() if r.nav_date else None,
            }

        # 6. 写入 Redis
        await cache_set(EST_NAV_KEY, data, EST_NAV_TTL)
        # 单独记一份生成时间。前端原来把「估算净值」旁边的时刻写成
        # `new Date()`（浏览器当前时间），等于给一份几小时前算出来的估算值
        # 盖上"刚刚"的时间戳 —— 必须由后端给出真实的计算时刻。
        from utils import beijing_now
        await cache_set(EST_NAV_META_KEY,
                        {"updated_at": beijing_now().isoformat()},
                        EST_NAV_TTL)

        elapsed = (time.monotonic() - start) * 1000
        ok = len(data) > 0
        metrics.record_fetch("est_nav", ok, elapsed)

        logger.info(
            "[EST_NAV_SERVICE] 完成: %d 只基金, %d 个涨跌幅, %.0fms",
            len(data), len(quotes), elapsed,
        )
        return data

    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        metrics.record_fetch("est_nav", False, elapsed)
        logger.error("[EST_NAV_SERVICE] 失败: %s", e, exc_info=True)
        return {}


async def get_est_nav_cache() -> dict:
    """从 Redis 读取估算净值缓存"""
    return await cache_get(EST_NAV_KEY) or {}


async def get_est_nav_meta() -> dict:
    """估算净值的生成时间等元信息：{updated_at: ISO8601}"""
    return await cache_get(EST_NAV_META_KEY) or {}


async def save_est_nav_snapshot(client: httpx.AsyncClient) -> int:
    """
    收盘后保存估算净值快照到数据库。
    复用 run_est_nav 的计算逻辑，将结果写入 fund_est_nav 表。
    trade_date 为今日（估算净值是当日盘中基于昨日净值计算的）。
    返回保存的记录数。
    """
    from processors.saver import save_est_nav_batch
    from utils import beijing_now, beijing_today_date

    data = await run_est_nav(client)
    if not data:
        logger.warning("[EST_NAV_SNAPSHOT] 无数据可保存")
        return 0

    trade_date = beijing_today_date()
    snapshot_time = beijing_now()
    records = _est_nav_data_to_records(data, trade_date)
    if not records:
        logger.warning("[EST_NAV_SNAPSHOT] 当日净值已公布，无归属今日的估算可保存")
        return 0

    sf = database.async_session_factory
    result = await save_est_nav_batch(sf, records, trade_date, snapshot_time)
    saved = result.get('success', 0)
    logger.info("[EST_NAV_SNAPSHOT] 保存完成: %d 条, trade_date=%s", saved, trade_date)
    return saved


async def save_est_nav_slice(data: dict) -> int:
    """
    5分钟切片入库 — 将 run_est_nav 的计算结果写入 fund_est_nav 表。
    每个切片都有独立的 snapshot_time，允许多条/天。

    Args:
        data: run_est_nav() 返回的计算结果 {fund_code: {est_nav, ...}}

    Returns:
        保存的记录数
    """
    from processors.saver import save_est_nav_batch
    from utils import beijing_now, beijing_today_date

    if not data:
        return 0

    trade_date = beijing_today_date()
    snapshot_time = beijing_now()
    records = _est_nav_data_to_records(data, trade_date)
    if not records:
        # 当日净值公布之后，所有估算都属于下一个交易日 —— 不该再写进今天
        logger.info("[EST_NAV_SLICE] 当日净值已公布，本切片无归属今日的估算，跳过")
        return 0

    sf = database.async_session_factory
    result = await save_est_nav_batch(sf, records, trade_date, snapshot_time)
    saved = result.get('success', 0)
    logger.info("[EST_NAV_SLICE] 切片入库: %d 条, snapshot=%s", saved,
                snapshot_time.strftime('%H:%M:%S'))
    return saved


def _est_nav_data_to_records(data: dict, trade_date=None) -> list[dict]:
    """将 run_est_nav() 返回的 dict 转为 saver 所需 records 列表。

    传入 `trade_date` 时会剔除"估算对象已经是下一个交易日"的记录 —— 见
    `_is_next_session` 的说明。不传（仅测试用）则原样转换。
    """
    td = None
    if trade_date is not None:
        td = trade_date.isoformat() if hasattr(trade_date, "isoformat") else str(trade_date)

    records = []
    skipped = 0
    for fc, info in data.items():
        if td is not None and _is_next_session(info.get('nav_date'), td):
            skipped += 1
            continue
        records.append({
            'code': fc,
            'est_nav': info.get('est_nav'),
            'est_change_pct': info.get('est_change_pct'),
            'holdings_contrib': info.get('holdings_contrib'),
            'index_contrib': info.get('index_contrib'),
            'coverage': info.get('coverage'),
            'nav': info.get('nav'),
        })
    if skipped:
        logger.info("[EST_NAV] 当日净值已公布，跳过归属于下一交易日的估算: %d 只", skipped)
    return records


def _is_next_session(nav_date, trade_date_iso: str) -> bool:
    """这份估算描述的是不是 trade_date **之后**的交易日。

    估算值描述的是基准净值日之后的那个交易日：
        est_nav = 基准净值(基准日) × (1 + 当日涨跌)
    所以当**当日净值已经公布**时，`load_fund_meta` 取到的基准净值就是当日的，
    此后算出来的估算描述的是**下一个交易日**，却仍被挂到今天的 trade_date 上。

    实测 161725（2026-09-30，净值 20:02 到货）：
        15:07 切片  基准 0.5169（09-29 净值）  估算 0.5317  ← 09-30 的收盘估算
        20:02 切片  基准 0.5314（09-30 净值）  估算 0.5466  ← 其实是 10-01 的估算
    当天 164 条切片里有 36 条属于后者，占了 22%。

    这些行不只是无用（没有任何读取路径需要"下一日的早期估算"），而且有害：
    详情页原来按"每天最后一条切片"取值，正好选中它们，把 09-30 的估算误差从
    真实的 +0.06% 显示成 +2.86%。

    判据只用基准净值的日期，不做数值比较 —— 净值恰好没变时数值比较会误判。
    拿不到 nav_date（旧缓存/字段缺失）时返回 False，即**保留**记录：
    宁可多写，也不要让"字段缺失"变成"当天没有估算数据"。
    """
    if not nav_date:
        return False
    return str(nav_date) >= trade_date_iso


async def calc_single_est_nav(sf, code: str) -> dict | None:
    """
    按需计算单只基金的估算净值（缓存未命中时的降级方案）。
    返回与缓存格式相同的 dict，或 None。
    """
    from processors.est_nav import calc_est_nav, load_fund_meta, load_holdings
    from index_mapping import get_index_quote_code
    from sqlalchemy import text as sql_text
    import httpx

    fund_code = code.zfill(6)
    try:
        async with sf() as session:
            # 1. 获取该基金的净值和跟踪指数
            r = await session.execute(sql_text('''
                SELECT fd.nav, fi.index_code
                FROM fund_daily fd
                JOIN fund_info fi ON fi.code = fd.code
                WHERE fd.code = :code AND fd.nav IS NOT NULL
                AND fd.nav_date = (
                    SELECT MAX(nav_date) FROM fund_daily WHERE code = fd.code
                )
            '''), {'code': fund_code})
            row = r.fetchone()
            if not row or not row[0]:
                return None
            nav = float(row[0])
            idx_name = row[1]
            idx_tcode = get_index_quote_code(idx_name) if idx_name else None

            # 2. 获取持仓
            r2 = await session.execute(sql_text(
                'SELECT asset_code, weight FROM fund_asset_map WHERE fund_code = :code AND weight > 0'
            ), {'code': fund_code})
            holdings = [{'asset_code': ac, 'weight': float(wt)} for ac, wt in r2.fetchall()]
            if not holdings:
                return None

            # 3. 获取资产信息（含名称）
            need_quotes = {h['asset_code'] for h in holdings}
            if idx_tcode:
                need_quotes.add(idx_tcode)

            r3 = await session.execute(sql_text(
                'SELECT code, name, market, asset_type FROM asset_master WHERE code = ANY(:codes)'
            ), {'codes': list(need_quotes)})
            asset_info = {
                row[0]: {'code': row[0], 'name': row[1] or '', 'market': row[2], 'asset_type': row[3]}
                for row in r3.fetchall()
            }
            # 注入名称到持仓
            for h in holdings:
                ac = h['asset_code']
                if ac in asset_info:
                    h['name'] = asset_info[ac]['name']
                else:
                    h['name'] = ''

            quote_assets = []
            for acode in need_quotes:
                if acode in asset_info:
                    quote_assets.append(asset_info[acode])
                elif acode.startswith(('sh', 'sz', 'hk')):
                    quote_assets.append({'code': acode, 'market': '', 'asset_type': 'index'})

        # 4. 拉涨跌幅
        async with httpx.AsyncClient(timeout=10) as client:
            quotes = await fetch_asset_quotes(client, quote_assets)

        # 5. 计算
        result = calc_est_nav(nav=nav, holdings=holdings, quotes=quotes, index_tcode=idx_tcode)

        return {
            'est_nav': result.est_nav,
            'est_change_pct': result.est_change_pct,
            'holdings_contrib': result.holdings_contrib,
            'index_contrib': result.index_contrib,
            'coverage': result.coverage,
            'holding_details': result.holding_details or [],
            'index_detail': result.index_detail,
            'nav': result.nav,
        }
    except Exception as e:
        logger.error("[EST_NAV_SERVICE] 单基金计算失败 %s: %s", code, e, exc_info=True)
        return None
