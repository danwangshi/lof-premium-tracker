#!/usr/bin/env bash
# 只在源站运行：检查 fund_est_nav 的真实表结构与落盘情况。
# 用法: bash /tmp/diag_est_nav_db.sh
set -u
set -a
. /opt/jinkuaicha/backend-v2/.env
set +a
PSQL="${DATABASE_URL/+asyncpg/}"

echo "=========== 1. 表结构 ==========="
psql "$PSQL" -c '\d fund_est_nav'

echo "=========== 2. 主键 / 唯一约束 ==========="
psql "$PSQL" -c "
SELECT c.conname, c.contype, pg_get_constraintdef(c.oid) AS def
FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
WHERE t.relname = 'fund_est_nav';"

echo "=========== 3. 索引 ==========="
psql "$PSQL" -c "SELECT indexdef FROM pg_indexes WHERE tablename = 'fund_est_nav';"

echo "=========== 4. 总量 / 日期跨度 ==========="
psql "$PSQL" -c "
SELECT count(*) AS rows, count(DISTINCT code) AS funds,
       count(DISTINCT trade_date) AS days,
       min(trade_date) AS first_day, max(trade_date) AS last_day
FROM fund_est_nav;"

echo "=========== 5. 最近 14 个交易日的落盘行数 ==========="
psql "$PSQL" -c "
SELECT trade_date, count(*) AS rows, count(DISTINCT code) AS funds,
       count(DISTINCT snapshot_time) AS slices
FROM fund_est_nav
GROUP BY trade_date ORDER BY trade_date DESC LIMIT 14;"

echo "=========== 6. 每日切片数分布（判断是否每5分钟一条） ==========="
psql "$PSQL" -c "
SELECT trade_date, min(snapshot_time) AS first_slice, max(snapshot_time) AS last_slice,
       count(DISTINCT snapshot_time) AS slices
FROM fund_est_nav WHERE trade_date >= CURRENT_DATE - 20
GROUP BY trade_date ORDER BY trade_date DESC;"

echo "=========== 7. est_nav 是否为基准净值副本（<=0.0001 视为无意义） ==========="
psql "$PSQL" -c "
SELECT trade_date,
       count(*) AS rows,
       count(*) FILTER (WHERE est_nav IS NULL) AS est_null,
       count(*) FILTER (WHERE nav IS NULL) AS nav_null,
       count(*) FILTER (WHERE est_nav IS NOT NULL AND nav IS NOT NULL
                          AND abs(est_nav - nav) <= 0.0001) AS identical_to_nav
FROM fund_est_nav WHERE trade_date >= CURRENT_DATE - 20
GROUP BY trade_date ORDER BY trade_date DESC;"

echo "=========== 8. 抽样 5 行 ==========="
psql "$PSQL" -c "
SELECT * FROM fund_est_nav ORDER BY trade_date DESC, snapshot_time DESC LIMIT 5;"
