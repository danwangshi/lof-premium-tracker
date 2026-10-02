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
echo "=== fund_est_nav 最近3天 ==="
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT trade_date, COUNT(*) AS cnt FROM fund_est_nav GROUP BY trade_date ORDER BY trade_date DESC LIMIT 3;" 2>&1

echo ""
echo "=== job_log 最新 save_est_nav ==="
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT job_name, status, started_at, duration_ms FROM job_log WHERE job_name='save_est_nav' ORDER BY started_at DESC LIMIT 3;" 2>&1

echo ""
echo "=== 手动触发日志 ==="
journalctl -u jinkuaicha --since '10 min ago' --no-pager 2>&1 | grep -iE 'EST_NAV_SNAPSHOT|save_est' | tail -5
