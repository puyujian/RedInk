#!/bin/bash

# RedInk Docker 快速启动脚本
# 自动化 Docker 环境的初始化和启动流程

set -e

echo "=================================================="
echo "  RedInk Docker 快速启动脚本"
echo "=================================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Docker 是否安装
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: Docker 未安装${NC}"
    echo "请先安装 Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# 检查 Docker Compose 是否可用
if ! docker compose version &> /dev/null; then
    echo -e "${RED}错误: Docker Compose 未安装或版本过低${NC}"
    echo "需要 Docker Compose V2，请更新 Docker"
    exit 1
fi

# 检查 .env 文件
if [ ! -f .env ]; then
    echo -e "${YELLOW}警告: .env 文件不存在${NC}"
    echo "正在从 .env.docker 创建 .env 文件..."
    cp .env.docker .env
    echo -e "${YELLOW}请编辑 .env 文件，填入你的 API Keys:${NC}"
    echo "  - GOOGLE_CLOUD_API_KEY"
    echo "  - IMAGE_API_KEY"
    echo "  - JWT_SECRET_KEY"
    echo ""
    read -p "按 Enter 键继续，或按 Ctrl+C 退出编辑配置..."
fi

# 检查 image_providers.yaml 文件
if [ ! -f image_providers.yaml ]; then
    echo -e "${YELLOW}警告: image_providers.yaml 文件不存在${NC}"
    if [ -f image_providers.yaml.example ]; then
        echo "正在从 image_providers.yaml.example 创建配置..."
        cp image_providers.yaml.example image_providers.yaml
        echo -e "${GREEN}✓ 已创建 image_providers.yaml${NC}"
    else
        echo -e "${RED}错误: 找不到 image_providers.yaml.example${NC}"
        exit 1
    fi
fi

# 创建必要的目录
echo "创建必要的目录..."
mkdir -p output history
echo -e "${GREEN}✓ 目录创建完成${NC}"
echo ""

# 提示用户选择操作
echo "请选择操作:"
echo "  1) 启动所有服务（首次启动会自动构建镜像）"
echo "  2) 重新构建并启动"
echo "  3) 仅构建镜像"
echo "  4) 停止所有服务"
echo "  5) 停止并删除所有数据（危险操作）"
echo "  6) 查看服务状态"
echo "  7) 查看日志"
echo ""
read -p "请输入选项 (1-7): " choice

case $choice in
    1)
        echo ""
        echo "启动所有服务..."
        docker compose up -d
        echo ""
        echo -e "${GREEN}✓ 服务启动成功！${NC}"
        ;;
    2)
        echo ""
        echo "重新构建并启动服务..."
        docker compose up -d --build
        echo ""
        echo -e "${GREEN}✓ 服务重建并启动成功！${NC}"
        ;;
    3)
        echo ""
        echo "构建镜像..."
        docker compose build
        echo ""
        echo -e "${GREEN}✓ 镜像构建完成！${NC}"
        exit 0
        ;;
    4)
        echo ""
        echo "停止所有服务..."
        docker compose down
        echo ""
        echo -e "${GREEN}✓ 服务已停止${NC}"
        exit 0
        ;;
    5)
        echo ""
        echo -e "${RED}警告: 这将删除所有数据，包括数据库和生成的文件！${NC}"
        read -p "确定要继续吗? (yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            docker compose down -v
            echo -e "${GREEN}✓ 服务已停止，数据已删除${NC}"
        else
            echo "操作已取消"
        fi
        exit 0
        ;;
    6)
        echo ""
        docker compose ps
        exit 0
        ;;
    7)
        echo ""
        echo "查看最近日志 (按 Ctrl+C 退出)..."
        docker compose logs -f --tail=100
        exit 0
        ;;
    *)
        echo -e "${RED}无效的选项${NC}"
        exit 1
        ;;
esac

# 等待服务启动
echo ""
echo "等待服务启动..."
sleep 5

# 检查服务状态
echo ""
echo "服务状态:"
docker compose ps

# 检查健康状态
echo ""
echo "检查服务健康状态..."

# 检查后端 API
if curl -f -s http://localhost:12398/ > /dev/null; then
    echo -e "${GREEN}✓ 后端 API 正常${NC}"
else
    echo -e "${YELLOW}⚠ 后端 API 尚未就绪，可能正在启动中...${NC}"
fi

# 检查前端
if curl -f -s http://localhost/ > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 前端服务正常${NC}"
else
    echo -e "${YELLOW}⚠ 前端服务尚未就绪，可能正在启动中...${NC}"
fi

echo ""
echo "=================================================="
echo "  服务访问地址:"
echo "=================================================="
echo -e "  前端界面: ${GREEN}http://localhost${NC}"
echo -e "  后端 API: ${GREEN}http://localhost:12398${NC}"
echo "=================================================="
echo ""
echo "常用命令:"
echo "  查看日志: docker compose logs -f"
echo "  停止服务: docker compose down"
echo "  重启服务: docker compose restart"
echo ""
echo -e "${GREEN}🎉 启动完成！${NC}"
