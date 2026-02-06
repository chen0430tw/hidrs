#!/bin/bash
#
# HIDRS Kali Linux安装脚本
# 将HIDRS安装到Kali Linux系统
#
# 使用方式:
#   sudo ./kali_install.sh
#
# 或一键安装:
#   curl -sSL https://github.com/your-repo/hidrs/raw/main/kali_install.sh | sudo bash
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印函数
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查是否为root
if [ "$EUID" -ne 0 ]; then
    print_error "请使用sudo运行此脚本"
    exit 1
fi

# 检查是否为Kali Linux
if ! grep -q "Kali" /etc/os-release 2>/dev/null; then
    print_warning "此脚本为Kali Linux设计，但也可用于其他Debian系统"
    read -p "是否继续安装? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
fi

print_info "开始安装HIDRS到Kali Linux..."

# 1. 更新系统
print_info "步骤 1/8: 更新系统包"
apt update
apt upgrade -y

# 2. 安装Python依赖
print_info "步骤 2/8: 安装Python 3.11和pip"
apt install -y python3.11 python3-pip python3-venv

# 3. 安装系统依赖
print_info "步骤 3/8: 安装系统依赖"
apt install -y \
    git \
    curl \
    wget \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    mongodb \
    elasticsearch \
    redis-server \
    nginx

# 4. 克隆或更新HIDRS
INSTALL_DIR="/opt/hidrs"

if [ -d "$INSTALL_DIR" ]; then
    print_info "步骤 4/8: 更新现有HIDRS安装"
    cd "$INSTALL_DIR"
    git pull
else
    print_info "步骤 4/8: 克隆HIDRS仓库"
    git clone https://github.com/your-repo/hidrs.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 5. 创建Python虚拟环境
print_info "步骤 5/8: 创建Python虚拟环境"
if [ ! -d "venv" ]; then
    python3.11 -m venv venv
fi

source venv/bin/activate

# 6. 安装Python依赖
print_info "步骤 6/8: 安装Python依赖包"
pip install --upgrade pip
pip install -r requirements.txt

# 安装OSINT整合依赖
print_info "安装OSINT工具整合依赖..."
pip install stix2 pycti

# 7. 配置服务
print_info "步骤 7/8: 配置系统服务"

# MongoDB配置
print_info "配置MongoDB..."
systemctl enable mongodb
systemctl start mongodb

# Elasticsearch配置
print_info "配置Elasticsearch..."
systemctl enable elasticsearch
systemctl start elasticsearch

# Redis配置
print_info "配置Redis..."
systemctl enable redis-server
systemctl start redis-server

# 创建HIDRS systemd服务
cat > /etc/systemd/system/hidrs.service <<EOF
[Unit]
Description=HIDRS - Holographic Internet Discovery & Retrieval System
After=network.target mongodb.service elasticsearch.service redis-server.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin"
ExecStart=$INSTALL_DIR/venv/bin/python hidrs/main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 创建HIDRS OSINT API服务
cat > /etc/systemd/system/hidrs-api.service <<EOF
[Unit]
Description=HIDRS OSINT API Server
After=network.target hidrs.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin"
ExecStart=$INSTALL_DIR/venv/bin/python -m hidrs.integrations.osint_api run --host 0.0.0.0 --port 8080
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 重新加载systemd
systemctl daemon-reload

# 8. 创建命令行快捷方式
print_info "步骤 8/8: 创建命令行工具"

# 创建hidrs命令
cat > /usr/local/bin/hidrs <<EOF
#!/bin/bash
cd $INSTALL_DIR
source venv/bin/activate
python -m hidrs.cli "\$@"
EOF

chmod +x /usr/local/bin/hidrs

# 创建hidrs-search命令
cat > /usr/local/bin/hidrs-search <<EOF
#!/bin/bash
cd $INSTALL_DIR
source venv/bin/activate
python -c "
from hidrs.realtime_search.search_engine import RealtimeSearchEngine
import sys
import json

if len(sys.argv) < 2:
    print('用法: hidrs-search <查询>')
    sys.exit(1)

query = ' '.join(sys.argv[1:])
engine = RealtimeSearchEngine(elasticsearch_host='localhost:9200', enable_hlig=True)
results = engine.search(query_text=query, limit=20)
print(json.dumps(results, indent=2, ensure_ascii=False))
" "\$@"
EOF

chmod +x /usr/local/bin/hidrs-search

# 创建hidrs-export-stix命令
cat > /usr/local/bin/hidrs-export-stix <<EOF
#!/bin/bash
cd $INSTALL_DIR
source venv/bin/activate
python -c "
from hidrs.integrations.stix_exporter import STIXExporter
from hidrs.realtime_search.search_engine import RealtimeSearchEngine
import sys

if len(sys.argv) < 2:
    print('用法: hidrs-export-stix <查询> [输出文件]')
    sys.exit(1)

query = sys.argv[1]
output_file = sys.argv[2] if len(sys.argv) > 2 else 'hidrs_stix.json'

engine = RealtimeSearchEngine(elasticsearch_host='localhost:9200', enable_hlig=True)
results = engine.search(query_text=query, limit=100)

exporter = STIXExporter()
bundle = exporter.export_search_results(results.get('results', []))
exporter.save_to_file(bundle, output_file)
print(f'STIX导出完成: {output_file}')
" "\$@"
EOF

chmod +x /usr/local/bin/hidrs-export-stix

# 创建hidrs-api命令（管理API服务）
cat > /usr/local/bin/hidrs-api <<EOF
#!/bin/bash
cd $INSTALL_DIR
source venv/bin/activate

case "\$1" in
    start)
        systemctl start hidrs-api
        echo "HIDRS API服务已启动"
        ;;
    stop)
        systemctl stop hidrs-api
        echo "HIDRS API服务已停止"
        ;;
    restart)
        systemctl restart hidrs-api
        echo "HIDRS API服务已重启"
        ;;
    status)
        systemctl status hidrs-api
        ;;
    genkey)
        python -m hidrs.integrations.osint_api genkey --name "\${2:-default}"
        ;;
    *)
        echo "用法: hidrs-api {start|stop|restart|status|genkey [name]}"
        exit 1
        ;;
esac
EOF

chmod +x /usr/local/bin/hidrs-api

# 完成安装
print_success "HIDRS安装完成！"
echo ""
print_info "可用命令:"
echo "  hidrs              - HIDRS主程序"
echo "  hidrs-search       - 快速搜索"
echo "  hidrs-export-stix  - 导出STIX格式"
echo "  hidrs-api          - 管理OSINT API服务"
echo ""
print_info "服务管理:"
echo "  systemctl start hidrs       - 启动HIDRS服务"
echo "  systemctl start hidrs-api   - 启动OSINT API服务"
echo "  systemctl enable hidrs      - 开机自启动"
echo ""
print_info "Web界面:"
echo "  HIDRS主界面: http://localhost:5000"
echo "  OSINT API:   http://localhost:8080"
echo ""
print_info "OSINT工具整合:"
echo "  Maltego Transform: $INSTALL_DIR/hidrs/integrations/maltego_transform.py"
echo "  SpiderFoot模块:    $INSTALL_DIR/hidrs/integrations/spiderfoot_module.py"
echo "  STIX 2.1导出:      hidrs-export-stix <查询>"
echo ""
print_warning "首次使用前，请运行:"
echo "  1. hidrs-api genkey mykey    # 生成API密钥"
echo "  2. systemctl start hidrs     # 启动HIDRS"
echo "  3. systemctl start hidrs-api # 启动API服务"
echo ""
print_success "安装完成，享受HIDRS！"
