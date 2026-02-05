#!/bin/bash
# stream_with_ffmpeg.sh
# 使用 FFmpeg 进行流媒体推流

set -e

# 配置
RTMP_SERVER="rtmp://localhost:1935/live"
STREAM_KEY="emergency?key=YOUR_KEY"
RTMP_URL="${RTMP_SERVER}/${STREAM_KEY}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}===== HIDRS FFmpeg 推流工具 =====${NC}"
echo ""

# 检查 FFmpeg 是否安装
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${RED}❌ FFmpeg 未安装，请先安装: sudo apt install ffmpeg${NC}"
    exit 1
fi

# 显示菜单
echo "请选择推流源："
echo "  1) 视频文件循环播放"
echo "  2) 图片（一图流）"
echo "  3) 屏幕录制"
echo "  4) 摄像头"
echo "  5) 文字转视频（TTS + 静态画面）"
echo ""
read -p "请输入选项 (1-5): " choice

case $choice in
    1)
        # 视频文件循环播放
        read -p "请输入视频文件路径: " video_file
        if [ ! -f "$video_file" ]; then
            echo -e "${RED}❌ 文件不存在: $video_file${NC}"
            exit 1
        fi

        echo -e "${GREEN}🎬 开始推流视频文件...${NC}"
        ffmpeg -re -stream_loop -1 -i "$video_file" \
            -c:v libx264 -preset veryfast -tune zerolatency \
            -b:v 2500k -maxrate 2500k -bufsize 5000k \
            -pix_fmt yuv420p -g 50 -c:a aac -b:a 128k -ar 44100 \
            -f flv "$RTMP_URL"
        ;;

    2)
        # 一图流
        read -p "请输入图片文件路径: " image_file
        if [ ! -f "$image_file" ]; then
            echo -e "${RED}❌ 文件不存在: $image_file${NC}"
            exit 1
        fi

        echo -e "${YELLOW}🖼️  开始推流静态图片（一图流）...${NC}"

        # 创建静音音频
        ffmpeg -loop 1 -i "$image_file" \
            -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 \
            -c:v libx264 -preset veryfast -tune stillimage \
            -b:v 1000k -maxrate 1000k -bufsize 2000k \
            -pix_fmt yuv420p -r 25 -g 50 \
            -c:a aac -b:a 128k -ar 44100 \
            -shortest -f flv "$RTMP_URL"
        ;;

    3)
        # 屏幕录制
        read -p "请输入屏幕分辨率 (如 1920x1080): " resolution
        resolution=${resolution:-1920x1080}

        echo -e "${GREEN}🖥️  开始推流屏幕录制...${NC}"
        echo -e "${YELLOW}提示: 使用 Ctrl+C 停止推流${NC}"

        ffmpeg -f x11grab -s "$resolution" -i :0.0 \
            -f pulse -i default \
            -c:v libx264 -preset veryfast -tune zerolatency \
            -b:v 3000k -maxrate 3000k -bufsize 6000k \
            -pix_fmt yuv420p -g 50 -c:a aac -b:a 128k -ar 44100 \
            -f flv "$RTMP_URL"
        ;;

    4)
        # 摄像头
        read -p "请输入摄像头设备 (默认 /dev/video0): " camera
        camera=${camera:-/dev/video0}

        if [ ! -e "$camera" ]; then
            echo -e "${RED}❌ 摄像头不存在: $camera${NC}"
            exit 1
        fi

        echo -e "${GREEN}📹 开始推流摄像头...${NC}"

        ffmpeg -f v4l2 -i "$camera" \
            -f pulse -i default \
            -c:v libx264 -preset veryfast -tune zerolatency \
            -b:v 2000k -maxrate 2000k -bufsize 4000k \
            -pix_fmt yuv420p -g 50 -c:a aac -b:a 128k -ar 44100 \
            -f flv "$RTMP_URL"
        ;;

    5)
        # 文字转视频（TTS + 静态画面）
        read -p "请输入要显示的文字: " text
        read -p "背景颜色 (如 red, #ff0000, 默认 black): " bg_color
        bg_color=${bg_color:-black}
        read -p "文字颜色 (默认 white): " text_color
        text_color=${text_color:-white}

        echo -e "${GREEN}📝 生成文字视频并推流...${NC}"

        # 使用 drawtext 滤镜生成文字视频
        ffmpeg -f lavfi -i "color=c=${bg_color}:s=1920x1080:r=25" \
            -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 \
            -vf "drawtext=text='${text}':fontcolor=${text_color}:fontsize=60:x=(w-text_w)/2:y=(h-text_h)/2:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" \
            -c:v libx264 -preset veryfast -tune stillimage \
            -b:v 1000k -maxrate 1000k -bufsize 2000k \
            -pix_fmt yuv420p -g 50 \
            -c:a aac -b:a 128k -ar 44100 \
            -f flv "$RTMP_URL"
        ;;

    *)
        echo -e "${RED}❌ 无效的选项${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}✅ 推流已结束${NC}"
