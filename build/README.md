# Docker 构建指南

## 📋 目录结构

```
build/
├── Dockerfile             # Docker 镜像构建文件
└── README.md              # 本文件
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

### 2. 运行容器

```bash
# 使用 docker-compose（推荐）
docker compose -f docker/docker-compose.yml up -d

# 或单独运行
docker run -d \
  --name lof-app \
  -p 5000:5000 \
  -e DB_HOST=postgres \
  -e DB_PASSWORD=postgres123 \
  lof-fund-app
```

### 3. 访问应用

- **Web 界面**: http://localhost:5000
- **健康检查**: http://localhost:5000/health
- **API 文档**: http://localhost:5000/api/funds

---

## 🔧 Dockerfile 说明

### 多阶段构建

**第一阶段（builder）**：
- 基于 `python:3.11-slim`
- 安装编译依赖（gcc, libpq-dev）
- 安装 Python 包到 `/install` 目录

**第二阶段（runtime）**：
- 基于 `python:3.11-slim`（精简镜像）
- 仅安装运行时依赖（libpq5, curl）
- 从 builder 复制已安装的 Python 包
- 复制应用代码和资源文件

### 优化特性

✅ **减小镜像体积** - 多阶段构建，不包含编译工具  
✅ **健康检查** - 自动监控服务状态  
✅ **分层缓存** - requirements.txt 单独一层，加速重建  

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

## 🔍 故障排查

### 构建失败

```bash
# 清除缓存重新构建
docker build -f build/Dockerfile --no-cache -t lof-fund-app .

# 查看详细日志
docker build -f build/Dockerfile --progress=plain -t lof-fund-app .
```

### 网络连接问题

如果遇到无法拉取基础镜像的问题：

1. 配置 Docker 镜像加速器
2. 或使用代理：
   ```bash
   export HTTP_PROXY=http://proxy:port
   export HTTPS_PROXY=http://proxy:port
   docker build -f build/Dockerfile -t lof-fund-app .
   ```

---

## 📊 性能优化

### 构建优化

1. **利用缓存**：不要频繁修改 Dockerfile 顺序
2. **减小上下文**：使用 `.dockerignore` 排除不必要文件
3. **多阶段构建**：分离构建和运行环境

### 运行时优化

参考 `docker/docker-compose.yml` 中的资源限制配置。

---

## 📝 相关文档

- [Docker Compose 使用](../docker/README.md)
- [快速开始指南](../docker/QUICKSTART.md)
- [项目 README](../README.md)
