#!/bin/bash
# 银狼数据安全平台 - 卸载脚本

echo "======================================"
echo "  银狼数据安全平台 卸载"
echo "======================================"
echo ""
read -p "确定要卸载吗？这将删除所有容器和数据卷 (y/N): " confirm

if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "取消卸载"
    exit 0
fi

echo "停止并删除容器..."
docker-compose down -v --remove-orphans

echo "删除镜像..."
docker-compose down --rmi local 2>/dev/null || true

echo ""
echo "卸载完成。数据文件保留在 ./data 目录"
echo "如需完全清除，请手动删除项目目录"
