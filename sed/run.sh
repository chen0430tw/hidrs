#!/bin/bash
# 银狼数据安全平台 - 启动脚本

set -e

echo "启动银狼数据安全平台..."

# 检查是否已安装
if ! docker-compose ps &> /dev/null 2>&1; then
    echo "请先运行 ./install.sh 安装"
    exit 1
fi

# 启动所有服务
docker-compose up -d

echo ""
echo "服务已启动:"
echo "  前端: http://localhost:8080"
echo "  API:  http://localhost:5000"
echo "  Kibana: http://localhost:5601"
echo ""
echo "查看日志: docker-compose logs -f"
echo "停止服务: docker-compose down"
