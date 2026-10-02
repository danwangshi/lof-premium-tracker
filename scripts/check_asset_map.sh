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
echo "=== report_date distribution ==="
psql -h 101.200.129.61 -U deploy -d jinkuaicha -c "SELECT report_date, COUNT(*) FROM fund_asset_map GROUP BY report_date ORDER BY report_date DESC LIMIT 5;"
echo ""
echo "=== TOP weights for 162216 ==="
psql -h 101.200.129.61 -U deploy -d jinkuaicha -c "SELECT fund_code, asset_code, report_date, weight FROM fund_asset_map WHERE fund_code='162216' ORDER BY weight DESC LIMIT 15;"
echo ""
echo "=== 688525 for 162216 ==="
psql -h 101.200.129.61 -U deploy -d jinkuaicha -c "SELECT * FROM fund_asset_map WHERE fund_code='162216' AND asset_code='688525';"
echo ""
echo "=== count weights > 100 ==="
psql -h 101.200.129.61 -U deploy -d jinkuaicha -c "SELECT COUNT(*) AS bad_weight_count FROM fund_asset_map WHERE weight > 100;"
echo ""
echo "=== TOP bad weights ==="
psql -h 101.200.129.61 -U deploy -d jinkuaicha -c "SELECT fund_code, asset_code, weight FROM fund_asset_map WHERE weight > 100 ORDER BY weight DESC LIMIT 15;"
