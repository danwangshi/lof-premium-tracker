# 环境变量配置说明

## 快速开始

### 1. 安装依赖

```bash
pip install -r backend/requirements.txt
```

### 2. 配置环境变量

项目提供了两个环境变量文件：

- **`.env.example`**：模板文件，包含所有可配置项的说明
- **`.env`**：实际使用的配置文件（已在 .gitignore 中，不会被提交）

#### 方式一：复制模板并修改（推荐）

```bash
# Windows PowerShell
cp .env.example .env

# 然后编辑 .env 文件，修改数据库密码等敏感信息
```

#### 方式二：直接编辑 .env 文件

已为你创建了默认的 `.env` 文件，你可以根据实际情况修改以下配置：

```env
# 数据库配置（本地开发）
DB_HOST=localhost
DB_PORT=5432
DB_NAME=lof_funds
DB_USER=postgres
DB_PASSWORD=你的数据库密码  # ⚠️ 请修改为你的实际密码
```

### 3. 启动应用

```bash
cd backend
python app.py
```

访问 http://localhost:5000

---

## 配置项说明

### Flask 应用配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `HOST` | `0.0.0.0` | 服务器监听地址 |
| `PORT` | `5000` | 服务器端口 |
| `DEBUG` | `false` | 调试模式（本地开发建议设为 `true`） |
| `REFRESH_INTERVAL` | `300` | 数据刷新间隔（秒） |
| `LOG_LEVEL` | `INFO` | 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL） |

### PostgreSQL 数据库配置

有两种配置方式：

#### 方式一：使用 DATABASE_URL（推荐用于 Railway 等云平台）

```env
DATABASE_URL=postgresql://user:password@host:port/dbname
```

#### 方式二：使用独立环境变量（推荐用于本地开发）

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DB_HOST` | `localhost` | 数据库主机地址 |
| `DB_PORT` | `5432` | 数据库端口 |
| `DB_NAME` | `lof_funds` | 数据库名称 |
| `DB_USER` | `postgres` | 数据库用户名 |
| `DB_PASSWORD` | `` | 数据库密码 |
| `DB_POOL_MIN` | `2` | 连接池最小连接数 |
| `DB_POOL_MAX` | `10` | 连接池最大连接数 |

**注意**：如果同时设置了 `DATABASE_URL` 和独立环境变量，`DATABASE_URL` 优先。

---

## 本地 PostgreSQL 设置

### 使用 Docker（推荐）

```bash
docker run -d \
  --name lof-postgres \
  -e POSTGRES_DB=lof_funds \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres123 \
  -p 5432:5432 \
  postgres:15
```

### 或使用本地安装的 PostgreSQL

1. 安装 PostgreSQL
2. 创建数据库：
   ```sql
   CREATE DATABASE lof_funds;
   ```
3. 在 `.env` 文件中配置正确的密码

---

## 故障排查

### 问题：提示 "python-dotenv not installed"

**解决**：
```bash
pip install python-dotenv
```

### 问题：数据库连接失败

**检查**：
1. PostgreSQL 服务是否运行
2. `.env` 文件中的数据库配置是否正确
3. 数据库是否存在
4. 用户名和密码是否正确

### 问题：端口被占用

**解决**：修改 `.env` 中的 `PORT` 为其他端口，如 `8080`

---

## 安全提示

⚠️ **重要**：
- `.env` 文件包含敏感信息，已添加到 `.gitignore`
- 不要将 `.env` 文件提交到版本控制系统
- 生产环境建议使用平台提供的环境变量管理功能（如 Railway 的环境变量设置）
