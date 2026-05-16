# 多阶段构建 - 第一阶段：构建依赖
FROM python:3.11-slim AS builder

WORKDIR /build

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制 requirements.txt
COPY requirements.txt .

# 安装 Python 依赖到指定目录
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# 多阶段构建 - 第二阶段：运行环境
FROM python:3.11-slim

WORKDIR /app

# 安装运行时系统依赖
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 阶段复制已安装的 Python 包
COPY --from=builder /install /usr/local

# 复制应用代码
COPY index.html .
COPY css/ ./css/
COPY js/ ./js/
COPY assets/ ./assets/
COPY pages/ ./pages/
COPY backend/ ./backend/

# 复制环境变量模板
COPY .env.example .env

# 暴露端口
EXPOSE 5000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# 启动命令
CMD ["python", "backend/app.py"]
