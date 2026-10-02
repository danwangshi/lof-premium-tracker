#!/bin/bash
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
echo "=== job_log: save_est_nav 最近记录 ==="
psql -h 101.200.129.61 -U deploy -d jinkuaicha -c "SELECT job_name, status, started_at, finished_at, duration_ms FROM job_log WHERE job_name LIKE '%est%' ORDER BY started_at DESC LIMIT 15;" 2>&1

echo ""
echo "=== job_log: 最近所有任务 (今天) ==="
psql -h 101.200.129.61 -U deploy -d jinkuaicha -c "SELECT job_name, status, started_at, duration_ms FROM job_log WHERE started_at > NOW() - INTERVAL '1 day' ORDER BY started_at DESC LIMIT 25;" 2>&1

echo ""
echo "=== 07-28 ~ 08-02 所有 save_est_nav 记录 ==="
psql -h 101.200.129.61 -U deploy -d jinkuaicha -c "SELECT job_name, status, started_at, duration_ms FROM job_log WHERE job_name = 'save_est_nav' AND started_at BETWEEN '2026-07-26' AND '2026-08-03' ORDER BY started_at;" 2>&1
