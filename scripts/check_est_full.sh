#!/bin/bash
# 检查估算净值快照 + 调度器状态
# 数据库口令不硬编码：优先环境变量，其次读已 gitignore 的 env 文件；缺失即报错退出。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="${JINKUAICHA_ENV_FILE:-$REPO_ROOT/.env}"
read_env_value() {
  sed -n -E "s/^[[:space:]]*(export[[:space:]]+)?$1[[:space:]]*=[[:space:]]*//p" "$ENV_FILE" 2>/dev/null \
    | tail -n 1 | tr -d '\r' | tr -d "\"'"
}
PGPASSWORD="${PGPASSWORD:-${DB_PASSWORD:-}}"
if [ -z "$PGPASSWORD" ] && [ -f "$ENV_FILE" ]; then
  PGPASSWORD="$(read_env_value PGPASSWORD)"
  if [ -z "$PGPASSWORD" ]; then
    PGPASSWORD="$(read_env_value DB_PASSWORD)"
  fi
fi
if [ -z "$PGPASSWORD" ]; then
  echo "ERROR: 数据库口令缺失。请设置环境变量 PGPASSWORD，或在 $ENV_FILE 中配置 PGPASSWORD / DB_PASSWORD。" >&2
  exit 1
fi
export PGPASSWORD
echo "=== fund_est_nav 表 ==="
psql -h 101.200.129.61 -U deploy -d jinkuaicha -c "SELECT COUNT(*) AS cnt, MIN(trade_date) AS min_date, MAX(trade_date) AS max_date FROM fund_est_nav;" 2>&1

echo ""
echo "=== 最近5天快照行数 ==="
psql -h 101.200.129.61 -U deploy -d jinkuaicha -c "SELECT trade_date, COUNT(*) FROM fund_est_nav GROUP BY trade_date ORDER BY trade_date DESC LIMIT 7;" 2>&1

echo ""
echo "=== 调度器日志 (1小时) ==="
journalctl -u jinkuaicha --since '1 hour ago' --no-pager 2>&1 | grep -iE 'est_nav|scheduler|APScheduler|snapshot' | tail -25

echo ""
echo "=== 最近错误 ==="
journalctl -u jinkuaicha --since '6 hours ago' --no-pager 2>&1 | grep -iE 'ERROR|Traceback|Exception' | tail -15
