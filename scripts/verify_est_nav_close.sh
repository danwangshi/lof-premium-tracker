#!/usr/bin/env bash
# 只在源站运行：验证新的"每日收盘估算净值"取法。
# 关键对照：161725 在 2026-09-30 应取到 0.5317（15:07 切片），而不是 0.5466（22:57 切片）。
set -u
set -a
. /opt/jinkuaicha/backend-v2/.env
set +a
PSQL="${DATABASE_URL/+asyncpg/}"

echo "=========== 1. 新查询：单只基金每日收盘估算（含耗时） ==========="
time psql "$PSQL" -c "
WITH day_open AS (
    SELECT trade_date, min(snapshot_time) AS first_ts
    FROM fund_est_nav WHERE code = '161725' AND trade_date >= CURRENT_DATE - 30
    GROUP BY trade_date
),
day_baseline AS (
    SELECT o.trade_date, e.nav AS open_nav
    FROM day_open o
    JOIN fund_est_nav e ON e.code = '161725' AND e.trade_date = o.trade_date
                       AND e.snapshot_time = o.first_ts
)
SELECT DISTINCT ON (e.trade_date)
       e.trade_date, e.est_nav, e.nav AS base_nav, e.snapshot_time,
       fd.nav AS realized_nav, fd.nav_date,
       round((e.est_nav - fd.nav) / fd.nav * 100, 4) AS err_pct
FROM fund_est_nav e
JOIN day_baseline b ON b.trade_date = e.trade_date
LEFT JOIN fund_daily fd ON fd.code = e.code AND fd.trade_date = e.trade_date
WHERE e.code = '161725'
  AND e.trade_date >= CURRENT_DATE - 30
  AND (e.snapshot_time AT TIME ZONE 'Asia/Shanghai')::time <= TIME '15:10'
  AND e.nav IS NOT DISTINCT FROM b.open_nav
ORDER BY e.trade_date DESC, e.snapshot_time DESC
LIMIT 12;"

echo "=========== 2. 旧查询（对照）：每天最后一条切片 ==========="
psql "$PSQL" -c "
SELECT DISTINCT ON (trade_date) trade_date, est_nav, nav AS base_nav, snapshot_time
FROM fund_est_nav WHERE code = '161725' AND trade_date >= CURRENT_DATE - 30
ORDER BY trade_date DESC, snapshot_time DESC LIMIT 6;"

echo "=========== 3. 全市场：新口径下每个交易日有多少只基金取到收盘估算 ==========="
psql "$PSQL" -c "
WITH day_open AS (
    SELECT code, trade_date, min(snapshot_time) AS first_ts
    FROM fund_est_nav WHERE trade_date >= CURRENT_DATE - 6
    GROUP BY code, trade_date
),
day_baseline AS (
    SELECT o.code, o.trade_date, e.nav AS open_nav
    FROM day_open o
    JOIN fund_est_nav e ON e.code = o.code AND e.trade_date = o.trade_date
                       AND e.snapshot_time = o.first_ts
)
SELECT e.trade_date, count(DISTINCT e.code) AS funds_with_close_est
FROM fund_est_nav e
JOIN day_baseline b ON b.code = e.code AND b.trade_date = e.trade_date
WHERE e.trade_date >= CURRENT_DATE - 6
  AND (e.snapshot_time AT TIME ZONE 'Asia/Shanghai')::time <= TIME '15:10'
  AND e.nav IS NOT DISTINCT FROM b.open_nav
GROUP BY e.trade_date ORDER BY e.trade_date DESC;"
