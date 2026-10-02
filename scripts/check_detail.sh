#!/bin/bash
# 凭证从根 .env 读取
set -a; source "$(dirname "$0")/../.env"; set +a
# 凭据不硬编码：口令只从环境变量 / 已 gitignore 的 .env 读取，缺失则显式报错并非零退出
ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env"
PGPASSWORD="${PGPASSWORD:-${DB_PASSWORD:-}}"
if [ -z "$PGPASSWORD" ]; then
  echo "ERROR: 数据库口令缺失。请设置环境变量 PGPASSWORD，或在 $ENV_FILE 里配置 PGPASSWORD / DB_PASSWORD。" >&2
  exit 1
fi
export PGPASSWORD
echo "=== save_est_nav 07-29~31 detail ==="
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT job_name, status, started_at, duration_ms, LEFT(detail::text, 300) AS detail FROM job_log WHERE job_name = 'save_est_nav' AND started_at BETWEEN '2026-07-28' AND '2026-08-01' ORDER BY started_at;" 2>&1

echo ""
echo "=== fund_est_nav 07-29 是否存在 501025 ==="
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT * FROM fund_est_nav WHERE code='501025' ORDER BY trade_date DESC LIMIT 5;" 2>&1

echo ""
echo "=== job_log 07-28 与 07-29 行对比 ==="
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT trade_date, COUNT(*) FROM fund_est_nav GROUP BY trade_date ORDER BY trade_date DESC LIMIT 10;" 2>&1
