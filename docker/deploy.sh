#!/bin/bash
# ============================================
# LOF 基金监控系统 - Docker 生产环境部署脚本
# ============================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}LOF 基金监控系统 - Docker 部署脚本${NC}"
echo -e "${GREEN}========================================${NC}"

# 检查 Docker 是否安装
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: Docker 未安装${NC}"
    exit 1
fi

# 检查 Docker Compose 是否可用（Docker Desktop 已内置）
if ! docker compose version &> /dev/null; then
    echo -e "${RED}错误: Docker Compose 不可用${NC}"
    exit 1
fi

# 切换到脚本所在目录
cd "$(dirname "$0")"

# 检查环境变量文件
if [ ! -f .env ]; then
    echo -e "${YELLOW}警告: .env 文件不存在${NC}"
    echo -e "${YELLOW}正在从模板创建...${NC}"
    cp .env.example .env
    echo -e "${RED}请编辑 .env 文件，修改数据库密码等配置！${NC}"
    exit 1
fi

# 函数：显示菜单
show_menu() {
    echo ""
    echo "请选择操作："
    echo "1) 拉取最新镜像并启动服务（推荐）"
    echo "2) 仅启动服务（使用本地已有镜像）"
    echo "3) 停止服务"
    echo "4) 重启服务"
    echo "5) 查看日志"
    echo "6) 查看服务状态"
    echo "7) 清理无用资源"
    echo "8) 备份数据库"
    echo "9) 恢复数据库"
    echo "0) 退出"
    echo ""
}

# 函数：拉取镜像并启动
build_and_start() {
    echo -e "${GREEN}拉取最新 Docker 镜像...${NC}"
    docker compose --env-file .env pull
    
    echo -e "${GREEN}启动服务...${NC}"
    docker compose --env-file .env up -d
    
    echo -e "${GREEN}等待服务启动...${NC}"
    sleep 10
    
    echo -e "${GREEN}检查服务状态...${NC}"
    docker compose --env-file .env ps
    
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}部署完成！${NC}"
    echo -e "${GREEN}访问地址: http://localhost${NC}"
    echo -e "${GREEN}健康检查: http://localhost/health${NC}"
    echo -e "${GREEN}========================================${NC}"
}

# 函数：仅启动
start_only() {
    echo -e "${GREEN}启动服务...${NC}"
    docker compose --env-file .env up -d
    
    echo -e "${GREEN}服务已启动${NC}"
    docker compose --env-file .env ps
}

# 函数：停止服务
stop_services() {
    echo -e "${YELLOW}停止服务...${NC}"
    docker compose --env-file .env down
    
    echo -e "${GREEN}服务已停止${NC}"
}

# 函数：重启服务
restart_services() {
    echo -e "${YELLOW}重启服务...${NC}"
    docker compose --env-file .env restart
    
    echo -e "${GREEN}服务已重启${NC}"
}

# 函数：查看日志
view_logs() {
    echo -e "${GREEN}查看日志（按 Ctrl+C 退出）...${NC}"
    docker compose --env-file .env logs -f
}

# 函数：查看状态
view_status() {
    echo -e "${GREEN}服务状态：${NC}"
    docker compose --env-file .env ps
    echo ""
    echo -e "${GREEN}资源使用情况：${NC}"
    docker stats --no-stream lof-app lof-postgres lof-nginx 2>/dev/null || echo "服务未运行"
}

# 函数：清理资源
cleanup() {
    echo -e "${YELLOW}清理无用的 Docker 资源...${NC}"
    docker system prune -f
    docker volume prune -f
    echo -e "${GREEN}清理完成${NC}"
}

# 函数：备份数据库
backup_db() {
    BACKUP_FILE="backup_$(date +%Y%m%d_%H%M%S).sql"
    echo -e "${GREEN}备份数据库到: $BACKUP_FILE${NC}"
    
    docker exec lof-postgres pg_dump -U ${DB_USER:-postgres} ${DB_NAME:-lof_funds} > "$BACKUP_FILE"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}备份成功: $BACKUP_FILE${NC}"
    else
        echo -e "${RED}备份失败${NC}"
        exit 1
    fi
}

# 函数：恢复数据库
restore_db() {
    echo -e "${YELLOW}请输入备份文件路径：${NC}"
    read BACKUP_FILE
    
    if [ ! -f "$BACKUP_FILE" ]; then
        echo -e "${RED}文件不存在: $BACKUP_FILE${NC}"
        exit 1
    fi
    
    echo -e "${YELLOW}警告：此操作将覆盖现有数据！继续吗？(y/N)${NC}"
    read CONFIRM
    
    if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
        echo -e "${YELLOW}操作已取消${NC}"
        exit 0
    fi
    
    echo -e "${GREEN}恢复数据库...${NC}"
    cat "$BACKUP_FILE" | docker exec -i lof-postgres psql -U ${DB_USER:-postgres} ${DB_NAME:-lof_funds}
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}恢复成功${NC}"
    else
        echo -e "${RED}恢复失败${NC}"
        exit 1
    fi
}

# 主循环
while true; do
    show_menu
    read -p "请输入选项 [0-9]: " choice
    
    case $choice in
        1) build_and_start ;;
        2) start_only ;;
        3) stop_services ;;
        4) restart_services ;;
        5) view_logs ;;
        6) view_status ;;
        7) cleanup ;;
        8) backup_db ;;
        9) restore_db ;;
        0) echo -e "${GREEN}再见！${NC}"; exit 0 ;;
        *) echo -e "${RED}无效选项${NC}" ;;
    esac
    
    echo ""
    read -p "按回车键继续..."
done
