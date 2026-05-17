# 🚀 LOF 基金监控系统 - Docker 部署指南

## 📋 目录

- [快速开始](#-快速开始)
- [架构说明](#-架构说明)
- [配置说明](#-配置说明)
- [常用命令](#-常用命令)
- [数据库管理](#-数据库管理)
- [故障排查](#-故障排查)
- [安全建议](#-安全建议)

---

## 🚀 快速开始

### 前置条件

- Docker 20.10+
- Docker Compose 2.0+
- 至少 4GB 可用内存

### 第 1 步：配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑配置文件（必须修改数据库密码）
nano .env  # Linux/macOS
notepad .env  # Windows
```

**⚠️ 必须修改的配置：**
```bash
DB_PASSWORD=YourStrongPassword123!  # 改为强密码
```

### 第 2 步：一键部署

**使用部署脚本（推荐）：**

Linux/macOS:
```bash
chmod +x deploy.sh
./deploy.sh
# 选择选项 1) 拉取最新镜像并启动服务
```

Windows PowerShell:
```powershell
.\deploy.ps1
# 选择选项 1) 拉取最新镜像并启动服务
```

**或手动部署：**
```bash
docker compose up -d
```

### 第 3 步：访问应用

打开浏览器访问：
- **Web 界面**: http://localhost
- **健康检查**: http://localhost/health
- **API 接口**: http://localhost/api/funds

---

## 🏗️ 架构说明

```
用户浏览器
    ↓
Nginx (端口 80/443)
    ├── 静态文件服务
    └── API 代理 → Flask App (内部网络)
                      ↓
                  PostgreSQL (内部网络)
```

**三个容器：**
1. **lof-nginx** - Nginx 反向代理 + 静态文件服务
2. **lof-app** - Flask 后端应用
3. **lof-postgres** - PostgreSQL 数据库

---

## 🔧 配置说明

### 环境变量

在 `.env` 文件中配置：

#### Flask 应用配置
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEBUG` | false | 调试模式（生产环境必须为false） |
| `LOG_LEVEL` | INFO | 日志级别（DEBUG/INFO/WARNING/ERROR） |
| `REFRESH_INTERVAL` | 300 | 数据刷新间隔（秒） |

#### PostgreSQL 配置
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DB_HOST` | postgres | 数据库主机（Docker 内部使用服务名） |
| `DB_PORT` | 5432 | 数据库端口 |
| `DB_NAME` | lof_funds | 数据库名称 |
| `DB_USER` | postgres | 数据库用户 |
| `DB_PASSWORD` | ⚠️ 必须修改 | 数据库密码 |
| `DB_POOL_MIN` | 2 | 最小连接池大小 |
| `DB_POOL_MAX` | 10 | 最大连接池大小 |

#### Nginx 配置
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HTTP_PORT` | 80 | HTTP 端口 |
| `HTTPS_PORT` | 443 | HTTPS 端口 |

#### 企业微信配置（可选）
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WEWORK_ENABLED` | false | 是否启用企微通知 |
| `WEWORK_CONFIG` | - | 企微配置字符串 |
| `WEWORK_PREMIUM_THRESHOLD` | 3.0 | 溢价通知阈值 |
| `WEWORK_DISCOUNT_THRESHOLD` | 1.5 | 折价通知阈值 |

### 端口映射

- **80**: HTTP 端口（通过 Nginx）
- **443**: HTTPS 端口（通过 Nginx，需配置 SSL）
- **5432**: PostgreSQL 数据库端口（可选，仅用于外部访问）

### 数据持久化

数据存储在 Docker volumes 中：
- `postgres_data`: PostgreSQL 数据目录
- `app_logs`: 应用日志目录
- `app_cache`: 缓存文件目录
- `nginx_logs`: Nginx 日志目录

---

## 🔧 常用命令

### 服务管理

```bash
# 启动服务
docker compose up -d

# 停止服务
docker compose down

# 重启服务
docker compose restart

# 查看状态
docker compose ps

# 查看日志
docker compose logs -f

# 查看指定服务日志
docker compose logs -f app
docker compose logs -f nginx
docker compose logs -f postgres
```

### 更新服务

```bash
# 拉取最新镜像
docker compose pull

# 重新构建并启动
docker compose up -d --build
```

### 清理资源

```bash
# 停止并删除容器、网络
docker compose down

# 删除卷（⚠️ 会清除所有数据！）
docker compose down -v

# 清理无用镜像和容器
docker system prune -f
docker volume prune -f
```

---

## 🗄️ 数据库管理

### 连接数据库

```bash
# 进入数据库命令行
docker exec -it lof-postgres psql -U postgres lof_funds

# 查看表
\dt

# 查看数据量
SELECT COUNT(*) FROM fund_snapshots;
SELECT COUNT(*) FROM daily_kline;

# 退出
\q
```

### 备份数据库

```bash
# 手动备份
docker exec lof-postgres pg_dump -U postgres lof_funds > backup_$(date +%Y%m%d_%H%M%S).sql

# 压缩备份
docker exec lof-postgres pg_dump -U postgres lof_funds | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz
```

### 恢复数据库

```bash
# 从 SQL 文件恢复
cat backup.sql | docker exec -i lof-postgres psql -U postgres lof_funds

# 从压缩文件恢复
gunzip -c backup.sql.gz | docker exec -i lof-postgres psql -U postgres lof_funds
```

### 自动备份（推荐）

创建定时任务每天凌晨 2 点备份：

```bash
# 编辑 crontab
crontab -e

# 添加以下内容
0 2 * * * docker exec lof-postgres pg_dump -U postgres lof_funds | gzip > /opt/backups/lof_$(date +\%Y\%m\%d).sql.gz
```

---

## 🔍 故障排查

### 容器无法启动

```bash
# 查看所有容器状态
docker compose ps

# 查看详细日志
docker compose logs

# 查看指定容器日志
docker logs lof-app
docker logs lof-postgres
docker logs lof-nginx
```

### 数据库连接失败

```bash
# 检查数据库容器状态
docker ps | grep postgres

# 测试数据库连接
docker exec lof-app python -c "
import psycopg2
try:
    conn = psycopg2.connect(
        host='postgres',
        database='lof_funds',
        user='postgres',
        password='your_password'
    )
    print('✓ 数据库连接成功')
    conn.close()
except Exception as e:
    print(f'✗ 连接失败: {e}')
"
```

### Nginx 502 错误

```bash
# 检查后端服务是否正常
curl http://localhost/health

# 查看 Nginx 错误日志
docker logs lof-nginx

# 重启 Nginx
docker compose restart nginx
```

### 内存不足

```bash
# 查看内存使用
free -h
docker stats

# 调整资源配置（编辑 docker-compose.yml）
# 减少 DB_POOL_MAX 或限制容器内存
```

### 重新部署

```bash
# 完全清理并重新部署
docker compose down -v
docker compose up -d
```

---

## 📊 监控

### 查看资源使用

```bash
# 实时资源监控
docker stats

# 查看特定容器
docker stats lof-app lof-postgres lof-nginx

# 一次性查看
docker stats --no-stream
```

### 健康检查

```bash
# 检查应用健康状态
curl http://localhost/health

# 检查数据库健康状态
docker exec lof-postgres pg_isready

# 检查容器健康状态
docker inspect --format='{{.State.Health.Status}}' lof-app
docker inspect --format='{{.State.Health.Status}}' lof-postgres
```

---

## 🔐 安全建议

### 生产环境配置

1. **修改默认密码**
   ```bash
   # 在 .env 文件中
   DB_PASSWORD=YourStrongPassword123!
   ```

2. **限制端口暴露**
   ```yaml
   # 在 docker-compose.yml 中
   ports:
     - "127.0.0.1:80:80"  # 仅绑定到 localhost
   ```

3. **不暴露数据库端口**
   ```yaml
   # 注释掉或删除数据库端口映射
   # ports:
   #   - "5432:5432"
   ```

4. **配置防火墙**
   ```bash
   # 只开放必要端口
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   sudo ufw enable
   ```

5. **启用 HTTPS**
   - 使用 Let's Encrypt 免费证书
   - 配置 Nginx SSL
   - 取消注释 `nginx.conf` 中的 HTTPS 配置

6. **定期更新**
   ```bash
   # 更新 Docker 镜像
   docker compose pull
   docker compose up -d
   
   # 清理旧镜像
   docker image prune -f
   ```

---

## ❓ 常见问题

### Q: 如何修改端口？

编辑 `.env` 文件：
```bash
HTTP_PORT=8080  # 改为 8080
```

### Q: 如何启用企业微信通知？

编辑 `.env` 文件：
```bash
WEWORK_ENABLED=true
WEWORK_CONFIG=corpid=xxx,agentid=xxx,touser=xxx,msgtype=text
```

### Q: 数据保存在哪里？

数据保存在 Docker volumes：
- `postgres_data` - 数据库文件
- `app_logs` - 应用日志
- `app_cache` - 缓存文件

### Q: 如何更新到最新版本？

```bash
git pull
docker compose pull
docker compose up -d
```

### Q: 首次启动需要多久？

- 下载镜像：1-3 分钟（取决于网络）
- 初始化数据库：30 秒 - 1 分钟
- 加载历史数据：2-5 分钟
- **总计**：约 5-10 分钟

---

## 📝 相关文档

- [项目主 README](../README.md)
- [技术文档](../docs/TECH.md)
- [Docker 架构说明](../DOCKER_ARCHITECTURE.md)
- [构建指南](../build/README.md)

---

## 💡 提示

1. ✅ **首次部署**可能需要几分钟下载镜像和初始化数据库
2. ✅ **生产环境**请务必修改数据库密码
3. ✅ **定期备份**数据库以防数据丢失
4. ✅ **查看日志**是排查问题的最佳方式
5. ✅ **不要现场构建**，使用预构建镜像即可
6. ✅ **监控资源**使用，确保服务器有足够内存

---

## 🆘 获取帮助

如有问题，请：
1. 查看日志：`docker compose logs -f`
2. 检查健康状态：`docker compose ps`
3. 提交 Issue：https://github.com/danwangshi/LOF-Fund-Tools/issues
