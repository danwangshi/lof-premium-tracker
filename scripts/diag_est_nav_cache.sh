#!/usr/bin/env bash
# 只在源站运行：估算净值的 Redis 缓存体检。
#
# 为什么要查这个（2026-10-02 实测）：
#   `est_nav:v2` 是整个键空间里最大的键（2.4 MB，因为内嵌了 1937 只基金的
#   holding_details），而它只在交易日的 9:25–23:00 被写、其余时间几乎不被读。
#   Redis 配的是 maxmemory 512MB + allkeys-lru，实测 used_memory_peak 已经
#   到过 515.97M、累计淘汰 22772 个键 —— est_nav:v2 正是 LRU 最理想的淘汰对象。
#   结果就是：TTL 明明写着 72 小时（注释说"覆盖周末及长假，非交易时段仍可
#   查看最近估算值"），键却在周末/假期中途消失，页面上的估算净值整列变 `--`。
#
#   更麻烦的是没人会发现：`cache_set` 把异常全 `pass` 掉了。
set -u
set -a
. /opt/jinkuaicha/backend-v2/.env
set +a
r() { redis-cli -u "$REDIS_URL" --no-auth-warning "$@"; }
PSQL="${DATABASE_URL/+asyncpg/}"

echo "=== 1. 估算净值相关键 ==="
for k in 'est_nav:v2' 'est_nav:meta' 'nav:all' 'rt:all'; do
  printf '%-14s exists=%s ttl=%-8s strlen=%s\n' \
    "$k" "$(r exists "$k")" "$(r ttl "$k")" "$(r strlen "$k")"
done
echo "键总数: $(r dbsize)"

echo
echo "=== 2. meta 内容（估算值的真实生成时刻） ==="
r get 'est_nav:meta'

echo
echo "=== 3. 缓存里几只基金的估算 ==="
r get 'est_nav:v2' | python3 -c "
import json, sys
raw = sys.stdin.read().strip()
if not raw or raw == 'nil':
    print('  est_nav:v2 不存在 —— 页面上的估算净值会整列显示 --')
    raise SystemExit
d = json.loads(raw)
print('  基金数: %d' % len(d))
for c in ('161725', '501046', '159509'):
    v = d.get(c)
    print('  %s: %s' % (c, ('不在缓存里' if v is None else
          'est_nav=%s nav=%s nav_date=%s chg=%s' % (
              v.get('est_nav'), v.get('nav'),
              v.get('nav_date'), v.get('est_change_pct')))))
"

echo
echo "=== 4. 淘汰证据（关键） ==="
r info memory | grep -E 'used_memory_human|used_memory_peak_human|maxmemory_human|maxmemory_policy'
r info stats  | grep -E 'evicted_keys|expired_keys'

echo
echo "=== 5. 最大的键（est_nav:v2 是不是最容易被 LRU 盯上） ==="
r --bigkeys 2>/dev/null | grep -iE 'biggest string' | tail -n 5

echo
echo "=== 6. 管理端有没有清过缓存（排除人为） ==="
psql "$PSQL" -c "SELECT created_at, user_id, action, detail FROM admin_audit_log WHERE action LIKE 'ops_%' ORDER BY created_at DESC LIMIT 10;" 2>&1

echo
echo "=== 7. est_nav 作业最近执行 ==="
psql "$PSQL" -c "SELECT job_name, status, started_at FROM job_log WHERE job_name IN ('est_nav','save_est_nav') ORDER BY started_at DESC LIMIT 5;"
