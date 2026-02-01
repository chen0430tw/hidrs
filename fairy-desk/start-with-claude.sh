#!/bin/bash
# FAIRY-DESK + Claude Code Web 启动脚本
# 同时启动 FAIRY-DESK 和 claude-code-web 服务

set -e

# 颜色定义
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}"
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║      🧚 FAIRY-DESK + Claude Code         ║"
echo "  ║         启动脚本 v1.0.0                  ║"
echo "  ╚═══════════════════════════════════════════╝"
echo -e "${NC}"

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js 未安装${NC}"
    echo "请先安装 Node.js: https://nodejs.org/"
    exit 1
fi

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 未安装${NC}"
    exit 1
fi

# 检查 claude CLI
if ! command -v claude &> /dev/null; then
    echo -e "${YELLOW}⚠️  Claude Code CLI 未安装${NC}"
    echo "安装命令: curl -fsSL https://claude.ai/install.sh | bash"
    echo ""
    read -p "是否继续启动 FAIRY-DESK（不含 Claude Code）? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
    SKIP_CLAUDE=true
fi

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 启动 claude-code-web（后台）
if [ -z "$SKIP_CLAUDE" ]; then
    echo -e "${GREEN}▶ 启动 claude-code-web...${NC}"

    # 使用 npx 运行（自动下载如果未安装）
    npx claude-code-web --port 3000 &
    CLAUDE_PID=$!

    echo -e "${GREEN}✓ claude-code-web 已启动 (PID: $CLAUDE_PID)${NC}"
    echo -e "  地址: ${CYAN}http://localhost:3000${NC}"
    echo ""

    # 等待 claude-code-web 启动
    sleep 2
fi

# 安装 Python 依赖（如果需要）
if [ ! -d "venv" ]; then
    echo -e "${GREEN}▶ 创建 Python 虚拟环境...${NC}"
    python3 -m venv venv
fi

echo -e "${GREEN}▶ 安装 Python 依赖...${NC}"
source venv/bin/activate
pip install -q -r requirements.txt

# 启动 FAIRY-DESK
echo -e "${GREEN}▶ 启动 FAIRY-DESK...${NC}"
python3 app.py &
FAIRY_PID=$!

echo ""
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ 全部服务已启动${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo ""
echo -e "  FAIRY-DESK:       ${CYAN}http://localhost:8080${NC}"
echo -e "  三联屏预览:       ${CYAN}http://localhost:8080/preview${NC}"
if [ -z "$SKIP_CLAUDE" ]; then
    echo -e "  Claude Code Web:  ${CYAN}http://localhost:3000${NC}"
fi
echo ""
echo -e "${YELLOW}按 Ctrl+C 停止所有服务${NC}"
echo ""

# 等待并处理退出
cleanup() {
    echo ""
    echo -e "${YELLOW}正在停止服务...${NC}"

    if [ ! -z "$CLAUDE_PID" ]; then
        kill $CLAUDE_PID 2>/dev/null || true
    fi

    if [ ! -z "$FAIRY_PID" ]; then
        kill $FAIRY_PID 2>/dev/null || true
    fi

    echo -e "${GREEN}✓ 已停止${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 保持脚本运行
wait
