# Docker 部署指南

## 📋 目录结构

```
docker/
├── docker-compose.yml     # Docker Compose 配置文件
├── images/                # Docker 镜像导出文件（.tar/.tar.gz）
├── backups/               # 数据库备份文件（.sql/.sql.gz）
├── logs/                  # 应用日志文件
└── README.md              # 本说明文件
```

---

## 🚀 快速开始

### 一键启动

```bash
# 进入项目根目录
cd LOF-Fund-Tools

# 启动所有服务（PostgreSQL + Flask App）
docker compose -f docker/docker-compose.yml up -d

# 查看日志
docker compose -f docker/docker-compose.yml logs -f

# 访问应用
# Web: http://localhost:5000
# API: http://localhost:5000/api/funds
# Health: http://localhost:5000/health
```

### 停止服务

```bash
docker compose -f docker/docker-compose.yml down
```

---

## 🔧 配置说明

### 环境变量

在 `docker-compose.yml` 中配置：

```yaml
environment:
  # Flask 配置
  - HOST=0.0.0.0
  - PORT=5000
  - DEBUG=false
  - LOG_LEVEL=INFO
  
  # PostgreSQL 配置
  - DB_HOST=postgres
  - DB_PORT=5432
  - DB_NAME=lof_funds
  - DB_USER=postgres
  - DB_PASSWORD=postgres123  # ⚠️ 生产环境请修改
```

### 端口映射

- **5000**: Flask 应用端口
- **5432**: PostgreSQL 数据库端口（可选，仅用于外部访问）

### 数据持久化

数据存储在 Docker volumes 中：
- `postgres_data`: PostgreSQL 数据目录
- `app_logs`: 应用日志目录

---

## 📋 常用命令

### 管理服务

```bash
# 启动服务
docker compose -f docker/docker-compose.yml up -d

# 停止服务
docker compose -f docker/docker-compose.yml down

# 重启服务
docker compose -f docker/docker-compose.yml restart

# 查看状态
docker compose -f docker/docker-compose.yml ps

# 查看日志
docker compose -f docker/docker-compose.yml logs -f app
docker compose -f docker/docker-compose.yml logs -f postgres
```

### 数据库操作

```bash
# 连接数据库
docker exec -it lof-postgres psql -U postgres -d lof_funds

# 备份数据库
docker exec lof-postgres pg_dump -U postgres lof_funds > docker/backups/backup_$(date +%Y%m%d).sql

# 恢复数据库
cat docker/backups/backup_20260516.sql | docker exec -i lof-postgres psql -U postgres -d lof_funds
```

### 清理资源

```bash
# 停止并删除容器、网络
docker compose -f docker/docker-compose.yml down

# 删除卷（⚠️ 会清除所有数据！）
docker compose -f docker/docker-compose.yml down -v
```

---

## 🗄️ 数据库管理

### 查看数据库状态

```bash
# 连接数据库
docker exec -it lof-postgres psql -U postgres -d lof_funds

# 查看表
\dt

# 查看数据量
SELECT COUNT(*) FROM premium_snapshots;
SELECT COUNT(*) FROM daily_kline;

# 退出
\q
```

### 定期备份

建议设置定时任务自动备份：

```bash
# 每天凌晨 2 点备份
0 2 * * * docker exec lof-postgres pg_dump -U postgres lof_funds | gzip > /path/to/backups/backup_$(date +\%Y\%m\%d).sql.gz
```

---

## 🔍 故障排查

### 容器无法启动

```bash
# 查看日志
docker logs lof-app
docker logs lof-postgres

# 检查容器状态
docker ps -a
```

### 数据库连接失败

```bash
# 测试数据库连接
docker exec lof-app python -c "
import psycopg2
try:
    conn = psycopg2.connect(
        host='postgres',
        database='lof_funds',
        user='postgres',
        password='postgres123'
    )
    print('✓ 数据库连接成功')
    conn.close()
except Exception as e:
    print(f'✗ 连接失败: {e}')
"
```

### 重新构建

```bash
# 清除缓存重新构建
docker compose -f docker/docker-compose.yml build --no-cache

# 重新启动
docker compose -f docker/docker-compose.yml up -d
```

---

## 📊 监控

### 查看资源使用

```bash
# 实时资源监控
docker stats

# 查看特定容器
docker stats lof-app lof-postgres
```

### 健康检查

```bash
# 检查应用健康状态
curl http://localhost:5000/health

# 检查数据库健康状态
docker exec lof-postgres pg_isready
```

---

## 🔐 安全建议

### 生产环境配置

1. **修改默认密码**
   ```yaml
   environment:
     - DB_PASSWORD=your_strong_password_here
     - POSTGRES_PASSWORD=your_strong_password_here
   ```

2. **限制端口暴露**
   ```yaml
   ports:
     - "127.0.0.1:5000:5000"  # 仅绑定到 localhost
   ```

3. **使用 Docker Secret**
   ```yaml
   secrets:
     db_password:
       file: ./secrets/db_password.txt
   ```

4. **启用 HTTPS**
   - 使用 Nginx 反向代理
   - 配置 Let's Encrypt 证书

---

## 📝 相关文档

- [Docker 构建指南](../build/README.md)
- [快速开始指南](../DOCKER_QUICKSTART.md)
- [项目 README](../README.md)
- [技术文档](../docs/TECH.md)

---

## 💡 提示

1. **首次启动**可能需要几分钟下载镜像和初始化数据库
2. **生产环境**请务必修改默认密码
3. **定期备份**数据库以防数据丢失
4. **查看日志**是排查问题的最佳方式
