#!/bin/bash
# 银狼数据安全平台 - 安装脚本

set -e

echo "======================================"
echo "  银狼数据安全平台 安装程序"
echo "  Silver Wolf Security Platform"
echo "======================================"

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo "错误: 未安装Docker，请先安装Docker"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "错误: 未安装Docker Compose，请先安装"
    exit 1
fi

# 创建必要目录
echo "[1/5] 创建目录结构..."
mkdir -p data logs configs backend/data

# 复制环境变量文件
if [ ! -f .env ]; then
    echo "[2/5] 创建环境配置..."
    cp _env.example .env 2>/dev/null || cp .env.example .env 2>/dev/null || echo "使用默认环境配置"
fi

# 调整系统参数（Elasticsearch需要）
echo "[3/5] 调整系统参数..."
if [ "$(sysctl -n vm.max_map_count 2>/dev/null)" -lt 262144 ] 2>/dev/null; then
    echo "设置 vm.max_map_count=262144"
    sudo sysctl -w vm.max_map_count=262144 2>/dev/null || echo "警告: 无法设置vm.max_map_count，ES可能启动失败"
fi

# 构建镜像
echo "[4/5] 构建Docker镜像..."
docker-compose build --no-cache

# 启动服务
echo "[5/5] 启动服务..."
docker-compose up -d

echo ""
echo "======================================"
echo "  安装完成！"
echo "======================================"
echo ""
echo "  前端界面:  http://localhost:8080"
echo "  后端API:   http://localhost:5000"
echo "  Kibana:    http://localhost:5601"
echo "  ES:        http://localhost:9200"
echo ""
echo "  使用 docker-compose logs -f 查看日志"
echo "  使用 ./uninstall.sh 卸载"
echo "======================================"
