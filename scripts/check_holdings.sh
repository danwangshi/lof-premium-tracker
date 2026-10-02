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
DBH="101.200.129.61"
DBU="deploy"
DBN="jinkuaicha"

echo "=== fund_holdings for 162216 ==="
psql -h "$DBH" -U "$DBU" -d "$DBN" -c "SELECT code, quarter, report_date, holdings FROM fund_holdings WHERE code='162216';"

echo ""
echo "=== fund_asset_map for 162216 ==="
psql -h "$DBH" -U "$DBU" -d "$DBN" -c "SELECT fund_code, asset_code, report_date, weight FROM fund_asset_map WHERE fund_code='162216' ORDER BY report_date DESC, weight DESC LIMIT 20;"

echo ""
echo "=== 688525 in fund_asset_map ==="
psql -h "$DBH" -U "$DBU" -d "$DBN" -c "SELECT fund_code, asset_code, report_date, weight FROM fund_asset_map WHERE asset_code='688525' ORDER BY report_date DESC LIMIT 20;"

echo ""
echo "=== holdings JSON detail ==="
psql -h "$DBH" -U "$DBU" -d "$DBN" -c "SELECT jsonb_array_elements(holdings) FROM fund_holdings WHERE code='162216';"

echo ""
echo "=== asset_master for 688525 ==="
psql -h "$DBH" -U "$DBU" -d "$DBN" -c "SELECT * FROM asset_master WHERE code='688525';"
