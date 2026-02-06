#!/bin/bash
# kiosk_linux.sh
# Linux Kiosk模式 - 将设备锁定为只显示广播页面

set -e

BROADCAST_URL="http://192.168.1.100:5000/broadcast-player"
SIMULATION_MODE=false

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --url)
            BROADCAST_URL="$2"
            shift 2
            ;;
        --simulation)
            SIMULATION_MODE=true
            shift
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

echo "=============================="
echo "⚠️  Linux Kiosk模式启动脚本"
echo "=============================="
echo "广播URL: $BROADCAST_URL"
echo "模拟模式: $SIMULATION_MODE"
echo "=============================="

if [ "$SIMULATION_MODE" = true ]; then
    echo "🎭 模拟模式：以下命令将被执行（实际不会执行）"
    echo ""
    echo "1. 禁用键盘和鼠标："
    echo "   xinput disable 'AT Translated Set 2 keyboard'"
    echo "   xinput disable 'ImPS/2 Generic Wheel Mouse'"
    echo ""
    echo "2. 启动Chromium Kiosk模式："
    echo "   chromium-browser --kiosk --noerrdialogs --disable-infobars \\"
    echo "     --disable-session-crashed-bubble --no-first-run --disable-pinch \\"
    echo "     --overscroll-history-navigation=0 --disable-features=TranslateUI \\"
    echo "     --app=$BROADCAST_URL"
    echo ""
    echo "3. 防止退出全屏（持续监控）："
    echo "   while true; do"
    echo "     xdotool search --onlyvisible --class chromium windowactivate --sync key F11"
    echo "     sleep 5"
    echo "   done"
    echo ""
    echo "4. 创建systemd服务："
    echo "   /etc/systemd/system/kiosk-broadcast.service"
    echo ""
    exit 0
fi

# 检查是否安装了所需工具
if ! command -v chromium-browser &> /dev/null; then
    echo "❌ Chromium未安装，请先安装: sudo apt install chromium-browser"
    exit 1
fi

if ! command -v xdotool &> /dev/null; then
    echo "❌ xdotool未安装，请先安装: sudo apt install xdotool"
    exit 1
fi

if ! command -v xinput &> /dev/null; then
    echo "❌ xinput未安装，请先安装: sudo apt install xinput"
    exit 1
fi

echo "⚠️⚠️⚠️ 警告：即将进入Kiosk模式！⚠️⚠️⚠️"
echo "键盘和鼠标将被禁用，只能通过物理重启退出！"
echo ""
read -p "确定继续吗？(yes/NO) " -r
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "已取消"
    exit 0
fi

echo "✅ 3秒后启动Kiosk模式..."
sleep 3

# 禁用所有输入设备（保留触摸屏）
echo "🔒 禁用键盘和鼠标..."
xinput list --name-only | while read device; do
    if [[ $device == *"keyboard"* ]] || [[ $device == *"Keyboard"* ]]; then
        xinput disable "$device" 2>/dev/null || true
    fi
    if [[ $device == *"mouse"* ]] || [[ $device == *"Mouse"* ]]; then
        xinput disable "$device" 2>/dev/null || true
    fi
done

# 隐藏鼠标光标
unclutter -idle 0 &

# 启动Chromium Kiosk模式
echo "🚀 启动Chromium Kiosk模式..."
chromium-browser \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --no-first-run \
  --disable-pinch \
  --overscroll-history-navigation=0 \
  --disable-features=TranslateUI \
  --disable-background-timer-throttling \
  --disable-renderer-backgrounding \
  --disable-backgrounding-occluded-windows \
  --check-for-update-interval=31536000 \
  --app="$BROADCAST_URL" &

CHROMIUM_PID=$!

# 防止退出全屏（持续监控）
echo "🔐 监控全屏状态..."
while true; do
    sleep 5

    # 检查Chromium是否还在运行
    if ! kill -0 $CHROMIUM_PID 2>/dev/null; then
        echo "⚠️ Chromium已退出，重新启动..."
        chromium-browser --kiosk --noerrdialogs --app="$BROADCAST_URL" &
        CHROMIUM_PID=$!
    fi

    # 强制全屏
    xdotool search --onlyvisible --class chromium windowactivate --sync key F11 2>/dev/null || true
done
