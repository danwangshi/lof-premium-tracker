# LOF 基金数据库备份说明

## 📅 备份时间
2026-05-17 13:14

## 📊 数据库统计

### 表结构
- `funds` - 基金基本信息表（538 条记录）
- `fund_shares` - 基金份额历史表（1191 条记录）
- `daily_kline` - 日K线数据表
- `premium_snapshots` - 溢价率快照表

### 份额数据
- 最新日期：2026-05-15
- 数据量：397 条/天
- 历史天数：3 天（2026-05-13 至 2026-05-15）

## 📦 备份文件

### 1. 自定义格式备份（推荐用于恢复）
**文件**: `lof_funds_backup_20260517_131344.dump`
- 格式：PostgreSQL custom format
- 压缩：级别 9（最高压缩）
- 大小：约 58 KB
- 用途：使用 `pg_restore` 恢复

### 2. SQL 格式备份（可读性强）
**文件**: `lof_funds_backup_20260517_131400.sql`
- 格式：纯文本 SQL
- 编码：UTF-8
- 大小：约 60 KB
- 用途：可直接查看和编辑 SQL 语句

## 🔄 恢复方法

### 方法 1：使用 pg_restore（推荐，适用于 .dump 文件）

```bash
# 停止当前服务
docker compose down

# 启动 PostgreSQL（单独启动）
docker compose up -d postgres

# 等待数据库就绪
docker compose exec postgres pg_isready -U postgres

# 删除旧数据库（如果需要）
docker compose exec postgres dropdb -U postgres lof_funds

# 创建新数据库
docker compose exec postgres createdb -U postgres lof_funds

# 恢复数据
docker compose exec -T postgres pg_restore -U postgres -d lof_funds < lof_funds_backup_20260517_131344.dump

# 重启所有服务
docker compose up -d
```

### 方法 2：使用 psql（适用于 .sql 文件）

```bash
# 停止当前服务
docker compose down

# 启动 PostgreSQL（单独启动）
docker compose up -d postgres

# 等待数据库就绪
docker compose exec postgres pg_isready -U postgres

# 删除旧数据库（如果需要）
docker compose exec postgres dropdb -U postgres lof_funds

# 创建新数据库
docker compose exec postgres createdb -U postgres lof_funds

# 恢复数据
docker compose exec -T postgres psql -U postgres -d lof_funds < lof_funds_backup_20260517_131400.sql

# 重启所有服务
docker compose up -d
```

### 方法 3：在本地 PostgreSQL 中恢复

```bash
# 创建数据库
createdb -U postgres lof_funds

# 恢复数据（.dump 格式）
pg_restore -U postgres -d lof_funds lof_funds_backup_20260517_131344.dump

# 或恢复数据（.sql 格式）
psql -U postgres -d lof_funds < lof_funds_backup_20260517_131400.sql
```

## ⚠️ 注意事项

1. **版本兼容性**：备份来自 PostgreSQL 15，建议在相同或更高版本中恢复
2. **字符编码**：数据库使用 UTF-8 编码
3. **依赖关系**：恢复时会自动处理表之间的依赖关系
4. **数据覆盖**：恢复操作会覆盖目标数据库中的现有数据
5. **权限问题**：确保执行恢复的用户有足够的权限

## 🔍 验证恢复

恢复后运行以下命令验证数据：

```bash
docker compose exec postgres psql -U postgres -d lof_funds -c "\dt"
docker compose exec postgres psql -U postgres -d lof_funds -c "SELECT COUNT(*) FROM funds;"
docker compose exec postgres psql -U postgres -d lof_funds -c "SELECT COUNT(*) FROM fund_shares;"
```

预期结果：
- 4 个表
- funds: 538 条记录
- fund_shares: 1191 条记录

## 📝 备份策略建议

### 自动备份脚本

可以创建定时任务定期备份：

```bash
#!/bin/bash
# backup.sh - 自动备份脚本

BACKUP_DIR="/path/to/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="lof_funds"
CONTAINER="lof-postgres"

# 创建备份目录
mkdir -p $BACKUP_DIR

# 执行备份
docker exec $CONTAINER pg_dump -U postgres -d $DB_NAME \
  --format=custom \
  --compress=9 \
  --file=/tmp/${DB_NAME}_${DATE}.dump

# 复制到本地
docker cp $CONTAINER:/tmp/${DB_NAME}_${DATE}.dump $BACKUP_DIR/

# 清理容器中的临时文件
docker exec $CONTAINER rm /tmp/${DB_NAME}_${DATE}.dump

# 删除 30 天前的备份
find $BACKUP_DIR -name "*.dump" -mtime +30 -delete

echo "备份完成: $BACKUP_DIR/${DB_NAME}_${DATE}.dump"
```

### Cron 定时任务

```cron
# 每天凌晨 2 点备份
0 2 * * * /path/to/backup.sh >> /var/log/lof_backup.log 2>&1
```

## 🎯 快速参考

| 操作 | 命令 |
|------|------|
| 查看表列表 | `\dt` |
| 查看基金数量 | `SELECT COUNT(*) FROM funds;` |
| 查看份额数据 | `SELECT date, COUNT(*) FROM fund_shares GROUP BY date;` |
| 查看最新数据 | `SELECT MAX(date) FROM fund_shares;` |
| 导出为 CSV | `\copy (SELECT * FROM funds) TO 'funds.csv' WITH CSV HEADER` |

---

**备份生成工具**: Docker PostgreSQL pg_dump  
**备份格式**: Custom format (.dump) + SQL format (.sql)  
**压缩级别**: 9（最高）  
**文件大小**: ~60 KB
