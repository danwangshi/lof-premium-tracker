#!/usr/bin/env bash
# 只在源站运行：并发建立 fund_est_nav 的 (code, trade_date, snapshot_time) 索引。
#
# 两个坑：
#   1. 库/角色上设了 statement_timeout=5s，普通 CREATE INDEX 会被直接掐断
#      （第一次执行就是这样，还留下一个 INVALID 索引）。用 PGOPTIONS 关掉本会话超时。
#   2. CONCURRENTLY 不能在事务块里跑，所以只能单条 -c，不能多条用 ; 串联。
set -u
set -a
. /opt/jinkuaicha/backend-v2/.env
set +a
PSQL="${DATABASE_URL/+asyncpg/}"

echo "=== 当前 statement_timeout ==="
psql "$PSQL" -Atc "SHOW statement_timeout;"

echo "=== 清理上次失败留下的 INVALID 索引 ==="
psql "$PSQL" -c "DROP INDEX IF EXISTS idx_est_nav_code_date;"

echo "=== CREATE INDEX CONCURRENTLY（1.5GB 表，关掉超时） ==="
time PGOPTIONS="-c statement_timeout=0 -c lock_timeout=0" psql "$PSQL" -v ON_ERROR_STOP=1 -c \
  "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_est_nav_code_date ON fund_est_nav (code, trade_date DESC, snapshot_time DESC);"

echo "=== 结果 ==="
psql "$PSQL" -c "SELECT c.relname, i.indisvalid, pg_size_pretty(pg_relation_size(c.oid)) AS size
FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
WHERE c.relname LIKE 'idx_est_nav%';"
