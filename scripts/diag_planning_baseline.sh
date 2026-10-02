#!/usr/bin/env bash
# 只在源站运行：为「存储重构」和「基金资产清单完善」两项排期做现状体检。
set -u
set -a
. /opt/jinkuaicha/backend-v2/.env
set +a
PSQL="${DATABASE_URL/+asyncpg/}"

echo "=========== 1. 表体积排行（只看 >1MB） ==========="
psql "$PSQL" -c "
SELECT relname AS table,
       pg_size_pretty(pg_total_relation_size(relid)) AS total,
       (SELECT reltuples::bigint FROM pg_class WHERE oid = relid) AS approx_rows
FROM pg_stat_user_tables
WHERE pg_total_relation_size(relid) > 1024*1024
ORDER BY pg_total_relation_size(relid) DESC;"

echo "=========== 2. 物化视图 / 视图 ==========="
psql "$PSQL" -c "
SELECT matviewname AS name, pg_size_pretty(pg_total_relation_size(format('%I', matviewname)::regclass)) AS size
FROM pg_matviews;"

echo "=========== 3. 全库体积 ==========="
psql "$PSQL" -c "SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size;"

echo "=========== 4. 基金清单：按类型 ==========="
psql "$PSQL" -c "
SELECT COALESCE(fund_type,'(空)') AS fund_type, count(*) AS n
FROM fund_info GROUP BY 1 ORDER BY 2 DESC;"

echo "=========== 5. 资产清单完整度（每一项都是估值得不得到数的前提） ==========="
psql "$PSQL" -c "
SELECT
  (SELECT count(*) FROM fund_info)                                   AS 基金总数,
  (SELECT count(DISTINCT code) FROM fund_daily WHERE nav IS NOT NULL) AS 有净值,
  (SELECT count(DISTINCT fund_code) FROM fund_asset_map WHERE weight > 0) AS 有持仓映射,
  (SELECT count(DISTINCT code) FROM fund_holdings)                   AS 有十大持仓,
  (SELECT count(*) FROM fund_info WHERE index_code IS NOT NULL AND index_code <> '') AS 有跟踪标的,
  (SELECT count(DISTINCT code) FROM asset_master)                    AS 资产主表条数,
  (SELECT count(*) FROM fund_snapshot)                               AS 快照视图行数;"

echo "=========== 6. 按板块看持仓覆盖率（估算净值能不能算） ==========="
psql "$PSQL" -c "
SELECT COALESCE(fi.fund_type,'(空)') AS 板块,
       count(*) AS 基金数,
       count(*) FILTER (WHERE fi.index_code IS NOT NULL AND fi.index_code <> '') AS 有跟踪标的,
       count(*) FILTER (WHERE m.cnt > 0)  AS 有持仓映射,
       count(*) FILTER (WHERE h.cnt > 0)  AS 有十大持仓
FROM fund_info fi
LEFT JOIN (SELECT fund_code, count(*) cnt FROM fund_asset_map WHERE weight>0 GROUP BY 1) m ON m.fund_code = fi.code
LEFT JOIN (SELECT code, count(*) cnt FROM fund_holdings GROUP BY 1) h ON h.code = fi.code
GROUP BY 1 ORDER BY 2 DESC;"

echo "=========== 7. 估算净值表：切片粒度与增长 ==========="
psql "$PSQL" -c "
SELECT count(DISTINCT trade_date) AS 天数,
       count(DISTINCT code)       AS 基金数,
       count(*)                   AS 总行数,
       round(count(*)::numeric / NULLIF(count(DISTINCT trade_date),0)) AS 每天行数
FROM fund_est_nav;" 2>&1 | head -n 12

echo "=========== 8. fund_daily 分区情况 ==========="
psql "$PSQL" -c "
SELECT inhrelid::regclass AS partition, pg_size_pretty(pg_total_relation_size(inhrelid)) AS size
FROM pg_inherits WHERE inhparent = 'fund_daily'::regclass ORDER BY 1 LIMIT 8;" 2>&1

echo "=========== 9. 无持仓映射的基金抽样（清单缺口长什么样） ==========="
psql "$PSQL" -c "
SELECT fi.code, left(fi.name, 28) AS 名称, fi.fund_type
FROM fund_info fi
LEFT JOIN (SELECT fund_code FROM fund_asset_map WHERE weight>0 GROUP BY 1) m ON m.fund_code = fi.code
WHERE m.fund_code IS NULL
ORDER BY fi.code LIMIT 12;"
