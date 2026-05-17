#!/bin/bash
# Docker 构建和导出脚本
# 用法: ./build.sh [版本号]

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 配置
IMAGE_NAME="danwangshi/lof-fund-app"
IMAGE_TAG="${1:-latest}"
FULL_IMAGE_NAME="${IMAGE_NAME}:${IMAGE_TAG}"
EXPORT_DIR="docker/images"
EXPORT_FILE="${EXPORT_DIR}/${IMAGE_NAME//\//-}-${IMAGE_TAG}.tar"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Docker 构建和导出脚本${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 检查是否在正确的目录
if [ ! -f "build/Dockerfile" ]; then
    echo -e "${RED}错误: 请在项目根目录运行此脚本${NC}"
    exit 1
fi

# 创建导出目录
echo -e "${YELLOW}[1/4] 创建导出目录...${NC}"
mkdir -p "${EXPORT_DIR}"

# 构建镜像
echo -e "${YELLOW}[2/4] 构建 Docker 镜像...${NC}"
echo -e "镜像名称: ${FULL_IMAGE_NAME}"
docker compose -f build/docker-compose.build.yml build || \
docker build -f build/Dockerfile -t "${FULL_IMAGE_NAME}" .

# 重新标记镜像（确保标签正确）
docker tag danwangshi/lof-fund-app:latest "${FULL_IMAGE_NAME}" 2>/dev/null || true

if [ $? -ne 0 ]; then
    echo -e "${RED}错误: 镜像构建失败${NC}"
    exit 1
fi

echo -e "${GREEN}✓ 镜像构建成功${NC}"
echo ""

# 导出镜像
echo -e "${YELLOW}[3/4] 导出镜像到 ${EXPORT_FILE}...${NC}"
docker save "${FULL_IMAGE_NAME}" -o "${EXPORT_FILE}"

if [ $? -ne 0 ]; then
    echo -e "${RED}错误: 镜像导出失败${NC}"
    exit 1
fi

# 压缩文件
echo -e "${YELLOW}[4/4] 压缩镜像文件...${NC}"
gzip -f "${EXPORT_FILE}"
COMPRESSED_FILE="${EXPORT_FILE}.gz"

if [ $? -ne 0 ]; then
    echo -e "${RED}错误: 文件压缩失败${NC}"
    exit 1
fi

echo -e "${GREEN}✓ 镜像导出成功${NC}"
echo ""

# 显示结果
FILE_SIZE=$(du -h "${COMPRESSED_FILE}" | cut -f1)
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  构建完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "镜像名称: ${FULL_IMAGE_NAME}"
echo -e "导出文件: ${COMPRESSED_FILE}"
echo -e "文件大小: ${FILE_SIZE}"
echo ""
echo -e "${YELLOW}使用以下命令加载镜像:${NC}"
echo -e "  docker load -i ${COMPRESSED_FILE}"
echo ""
echo -e "${YELLOW}使用以下命令运行容器:${NC}"
echo -e "  cd docker"
echo -e "  cp .env.example .env"
echo -e "  # 编辑 .env 文件，修改数据库密码"
echo -e "  docker compose up -d"
echo ""
