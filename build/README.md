# Docker 构建和部署指南

## 📋 目录结构

```
LOF-Fund-Tools/
├── build/                      # Docker 构建文件
│   ├── Dockerfile             # Docker 镜像构建文件
│   ├── docker-compose.yml     # Docker Compose 配置
│   └── README.md              # 本文件
├── docker/                     # Docker 运行产物（构建后生成）
│   ├── images/                # Docker 镜像导出文件
│   └── logs/                  # 应用日志
└── ...
```

---

## 🚀 快速开始

### 1. 构建 Docker 镜像

```bash
# 进入项目根目录
cd LOF-Fund-Tools

# 构建镜像
docker build -f build/Dockerfile -t lof-fund-app .
```

### 2. 使用 Docker Compose 启动（推荐）

```bash
# 启动所有服务（PostgreSQL + Flask App）
docker compose -f build/docker-compose.yml up -d

# 查看日志
docker compose -f build/docker-compose.yml logs -f

# 停止服务
docker compose -f build/docker-compose.yml down
```

### 3. 访问应用

- **Web 界面**: http://localhost:5000
- **健康检查**: http://localhost:5000/health
- **API 文档**: http://localhost:5000/api/funds

---

## 🔧 高级用法

### 单独启动 PostgreSQL

```bash
# 仅启动数据库
docker compose -f build/docker-compose.yml up -d postgres

# 连接数据库
docker exec -it lof-postgres psql -U postgres -d lof_funds
```

### 单独启动 Flask 应用

```bash
# 确保 PostgreSQL 已启动
docker compose -f build/docker-compose.yml up -d postgres

# 构建并启动应用
docker build -f build/Dockerfile -t lof-fund-app .
docker run -d \
  --name lof-app \
  --network lof-fund-tools_lof-network \
  -p 5000:5000 \
  -e DB_HOST=lof-postgres \
  -e DB_PASSWORD=postgres123 \
  lof-fund-app
```

### 自定义环境变量

创建 `.env` 文件覆盖默认配置：

```bash
# 复制模板
cp .env.example .env

# 编辑 .env 文件
nano .env

# 使用自定义环境变量启动
docker compose -f build/docker-compose.yml --env-file .env up -d
```

---

## 📦 镜像管理

### 导出镜像

```bash
# 导出为 tar 文件
docker save lof-fund-app -o docker/images/lof-fund-app.tar

# 压缩
gzip docker/images/lof-fund-app.tar
```

### 导入镜像

```bash
# 从 tar 文件加载
docker load -i docker/images/lof-fund-app.tar.gz
```

### 清理镜像

```bash
# 删除未使用的镜像
docker image prune -a

# 删除指定镜像
docker rmi lof-fund-app
```

---

## 🗄️ 数据库管理

### 备份数据库

```bash
# 备份到 sql 文件
docker exec lof-postgres pg_dump -U postgres lof_funds > docker/backups/backup_$(date +%Y%m%d).sql

# 压缩备份
docker exec lof-postgres pg_dump -U postgres lof_funds | gzip > docker/backups/backup_$(date +%Y%m%d).sql.gz
```

### 恢复数据库

```bash
# 从 sql 文件恢复
cat docker/backups/backup_20260516.sql | docker exec -i lof-postgres psql -U postgres -d lof_funds

# 从压缩文件恢复
gunzip -c docker/backups/backup_20260516.sql.gz | docker exec -i lof-postgres psql -U postgres -d lof_funds
```

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

---

## 🔍 故障排查

### 查看容器状态

```bash
# 查看所有容器
docker ps -a

# 查看容器日志
docker logs lof-app
docker logs lof-postgres

# 实时查看日志
docker logs -f lof-app
```

### 进入容器调试

```bash
# 进入 Flask 应用容器
docker exec -it lof-app bash

# 进入 PostgreSQL 容器
docker exec -it lof-postgres bash
```

### 检查网络连接

```bash
# 测试数据库连接
docker exec lof-app python -c "
import psycopg2
conn = psycopg2.connect(
    host='postgres',
    port=5432,
    database='lof_funds',
    user='postgres',
    password='postgres123'
)
print('Database connection successful!')
conn.close()
"
```

### 重启服务

```bash
# 重启单个服务
docker compose -f build/docker-compose.yml restart app

# 重启所有服务
docker compose -f build/docker-compose.yml restart
```

---

## 📊 性能优化

### 资源限制

在 `docker-compose.yml` 中添加资源限制：

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
  
  postgres:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```

### 数据卷优化

使用本地卷提高 I/O 性能：

```yaml
volumes:
  postgres_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /path/to/fast/storage
```

---

## 🔐 安全建议

### 生产环境配置

1. **修改默认密码**
   ```bash
   # 在 .env 文件中设置强密码
   DB_PASSWORD=your_strong_password_here
   POSTGRES_PASSWORD=your_strong_password_here
   ```

2. **限制端口暴露**
   ```yaml
   # 仅绑定到 localhost
   ports:
     - "127.0.0.1:5000:5000"
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

## 📝 常见问题

### Q: 容器启动失败怎么办？

A: 检查日志找出错误原因：
```bash
docker logs lof-app
docker logs lof-postgres
```

### Q: 如何更新应用到最新版本？

A:
```bash
# 拉取最新代码
git pull

# 重新构建镜像
docker build -f build/Dockerfile -t lof-fund-app .

# 重启服务
docker compose -f build/docker-compose.yml up -d --build
```

### Q: 数据库数据丢失了怎么办？

A: 数据存储在 Docker volume 中，除非手动删除 volume，否则数据不会丢失：
```bash
# 查看 volume
docker volume ls

# 不要执行以下命令（会删除数据）
# docker volume rm lof-fund-tools_postgres_data
```

### Q: 如何监控容器资源使用？

A:
```bash
# 查看实时资源使用
docker stats

# 查看特定容器
docker stats lof-app lof-postgres
```

---

## 📞 支持

如有问题，请查看：
- [项目 README](../README.md)
- [技术文档](../docs/TECH.md)
- [环境配置](../ENV_SETUP.md)

或提交 Issue 到 GitHub 仓库。
