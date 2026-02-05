# HIDRS 全球广播系统 - OBS推流配置指南

## 📡 系统架构

```
OBS Studio / FFmpeg
       ↓ RTMP推流
nginx-rtmp服务器 (端口1935)
       ↓ HLS切片
HTTP服务器 (端口8080)
       ↓ HLS播放
客户端播放器 (Video.js)
```

---

## 🚀 快速开始

### 1. 安装流媒体服务器

```bash
# 安装nginx-rtmp
cd /home/user/hidrs
sudo bash scripts/install_nginx_rtmp.sh

# 启动服务
sudo systemctl start nginx-rtmp

# 查看状态
sudo systemctl status nginx-rtmp
```

### 2. 获取推流地址和密钥

**方式一：使用API生成**
```bash
curl -X POST http://localhost:5000/api/broadcast/stream-key/generate
```

**方式二：使用默认密钥**
- Stream Key: `emergency_key_2026`
- RTMP URL: `rtmp://localhost:1935/live/emergency?key=emergency_key_2026`

---

## 🎥 OBS Studio 推流配置

### 安装 OBS Studio

**Linux:**
```bash
sudo apt install obs-studio
```

**Windows:**
下载：https://obsproject.com/download

**Mac:**
```bash
brew install --cask obs
```

### 配置推流

1. **打开 OBS Studio**

2. **设置 → 推流**
   - 服务: **自定义**
   - 服务器: `rtmp://你的服务器IP:1935/live`
   - 串流密钥: `emergency?key=emergency_key_2026`

   ![OBS推流设置](https://i.imgur.com/example.png)

3. **添加来源**
   - 视频捕获设备（摄像头）
   - 屏幕捕获（屏幕录制）
   - 图像（一图流）
   - 文本（文字广播）
   - 媒体源（视频文件）

4. **点击 "开始推流"**

### 推荐设置

**视频设置:**
- 基础分辨率: 1920x1080
- 输出分辨率: 1920x1080 或 1280x720
- 帧率: 25 FPS 或 30 FPS

**输出设置:**
- 输出模式: 简单
- 视频比特率: 2500 Kbps
- 编码器: x264 或 Hardware (NVENC/QuickSync)
- 音频比特率: 128 Kbps

**高级设置:**
- 关键帧间隔: 2秒
- 预设: veryfast 或 faster
- 配置: baseline

---

## 🖥️ FFmpeg 命令行推流

### 1. 推流视频文件（循环播放）

```bash
ffmpeg -re -stream_loop -1 -i video.mp4 \
  -c:v libx264 -preset veryfast -tune zerolatency \
  -b:v 2500k -maxrate 2500k -bufsize 5000k \
  -pix_fmt yuv420p -g 50 -c:a aac -b:a 128k -ar 44100 \
  -f flv rtmp://localhost:1935/live/emergency?key=emergency_key_2026
```

### 2. 推流静态图片（一图流）

```bash
ffmpeg -loop 1 -i image.jpg \
  -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 \
  -c:v libx264 -preset veryfast -tune stillimage \
  -b:v 1000k -maxrate 1000k -bufsize 2000k \
  -pix_fmt yuv420p -r 25 -g 50 \
  -c:a aac -b:a 128k -ar 44100 \
  -shortest -f flv rtmp://localhost:1935/live/emergency?key=emergency_key_2026
```

### 3. 屏幕录制推流

```bash
# Linux (X11)
ffmpeg -f x11grab -s 1920x1080 -i :0.0 \
  -f pulse -i default \
  -c:v libx264 -preset veryfast -tune zerolatency \
  -b:v 3000k -maxrate 3000k -bufsize 6000k \
  -pix_fmt yuv420p -g 50 -c:a aac -b:a 128k -ar 44100 \
  -f flv rtmp://localhost:1935/live/emergency?key=emergency_key_2026

# Windows
ffmpeg -f gdigrab -framerate 30 -i desktop \
  -f dshow -i audio="Microphone" \
  -c:v libx264 -preset veryfast -tune zerolatency \
  -b:v 3000k -c:a aac -b:a 128k \
  -f flv rtmp://localhost:1935/live/emergency?key=emergency_key_2026

# Mac
ffmpeg -f avfoundation -framerate 30 -i "1:0" \
  -c:v libx264 -preset veryfast -tune zerolatency \
  -b:v 3000k -c:a aac -b:a 128k \
  -f flv rtmp://localhost:1935/live/emergency?key=emergency_key_2026
```

### 4. 文字转视频（TTS广播）

```bash
ffmpeg -f lavfi -i "color=c=red:s=1920x1080:r=25" \
  -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 \
  -vf "drawtext=text='紧急通知：系统维护中':fontcolor=white:fontsize=60:x=(w-text_w)/2:y=(h-text_h)/2:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" \
  -c:v libx264 -preset veryfast -tune stillimage \
  -b:v 1000k -c:a aac -b:a 128k \
  -f flv rtmp://localhost:1935/live/emergency?key=emergency_key_2026
```

### 使用脚本工具

```bash
# 运行交互式推流工具
cd /home/user/hidrs
bash scripts/stream_with_ffmpeg.sh

# 选择推流源：
# 1) 视频文件循环播放
# 2) 图片（一图流）
# 3) 屏幕录制
# 4) 摄像头
# 5) 文字转视频
```

---

## 📺 播放广播流

### 方式一：使用内置播放器

浏览器访问：`http://localhost:5000/broadcast-player`

### 方式二：直接播放HLS流

```
http://localhost:8080/hls/emergency.m3u8
```

### 方式三：使用VLC播放器

```bash
vlc http://localhost:8080/hls/emergency.m3u8
```

### 方式四：使用ffplay

```bash
ffplay http://localhost:8080/hls/emergency.m3u8
```

---

## 🛠️ 故障排查

### 1. 推流失败：403 Forbidden

**原因：**Stream Key验证失败

**解决：**
- 检查Stream Key是否正确
- 确认URL格式：`rtmp://server:1935/live/stream_name?key=YOUR_KEY`
- 查看服务器日志：`tail -f /var/log/nginx/error.log`

### 2. 无法播放HLS流

**检查清单：**
```bash
# 1. 确认nginx-rtmp服务运行
sudo systemctl status nginx-rtmp

# 2. 检查HLS文件是否生成
ls -lh /var/www/hidrs/hls/

# 3. 测试HLS端点
curl http://localhost:8080/hls/emergency.m3u8

# 4. 检查防火墙
sudo ufw status
sudo ufw allow 8080/tcp
sudo ufw allow 1935/tcp
```

### 3. 推流延迟过高

**优化方案：**

**OBS设置：**
- 降低关键帧间隔（1-2秒）
- 使用硬件编码器（NVENC/QuickSync）
- 降低输出分辨率和比特率

**nginx配置：**
```nginx
# 减少HLS切片时长
hls_fragment 2s;  # 从10s改为2s
hls_playlist_length 10s;  # 从60s改为10s
```

**FFmpeg推流参数：**
```bash
-tune zerolatency  # 零延迟调优
-preset ultrafast  # 最快编码速度
-g 50              # 每50帧一个关键帧
```

### 4. 推流中断/断线

**原因分析：**
- 网络不稳定
- 编码性能不足
- 服务器资源耗尽

**解决方案：**
```bash
# 1. 增加FFmpeg缓冲区
-bufsize 5000k

# 2. OBS重连设置
# 设置 → 高级 → 自动重连
# 重连延迟: 2秒
# 最大重试次数: 10

# 3. 监控服务器资源
htop
df -h
```

---

## 🔐 安全最佳实践

### 1. 使用强Stream Key

```bash
# 生成安全的Stream Key
openssl rand -hex 32

# 或使用API生成
curl -X POST http://localhost:5000/api/broadcast/stream-key/generate
```

### 2. 限制推流IP

编辑 `/usr/local/nginx/conf/nginx.conf`:

```nginx
application live {
    live on;

    # 只允许本地和内网推流
    allow publish 127.0.0.1;
    allow publish 192.168.0.0/16;
    allow publish 10.0.0.0/8;
    deny publish all;

    # 允许所有人播放
    allow play all;
}
```

### 3. 启用HTTPS播放

```bash
# 生成SSL证书（已在安装脚本中完成）
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/broadcast.key \
  -out /etc/nginx/ssl/broadcast.crt

# 使用HTTPS播放
https://localhost:8443/hls/emergency.m3u8
```

### 4. 定期清理录制文件

```bash
# 添加cron任务清理7天前的录制
crontab -e

# 每天凌晨2点清理
0 2 * * * find /var/www/hidrs/recordings -type f -mtime +7 -delete
```

---

## 📊 监控和统计

### nginx-rtmp 统计页面

访问：`http://localhost:8080/stat`

显示信息：
- 当前活跃流
- 观众数量
- 比特率
- 上行/下行流量

### 使用API查询

```bash
# 获取活跃广播
curl http://localhost:5000/api/broadcast/active

# 获取HLS播放地址
curl http://localhost:5000/api/broadcast/hls/urls

# 获取统计信息
curl http://localhost:5000/api/broadcast/stats
```

---

## 🎯 使用场景示例

### 场景一：紧急通知广播

```bash
# 1. 生成推流密钥
STREAM_KEY=$(curl -s -X POST http://localhost:5000/api/broadcast/stream-key/generate | jq -r '.stream_key')

# 2. 推流紧急通知图片
ffmpeg -loop 1 -i emergency_notice.jpg \
  -f lavfi -i anullsrc \
  -c:v libx264 -preset veryfast -tune stillimage \
  -b:v 1000k -c:a aac -b:a 128k \
  -f flv rtmp://localhost:1935/emergency?key=$STREAM_KEY

# 3. 通知所有客户端播放
curl -X POST http://localhost:5000/api/broadcast/oneimage/set \
  -H "Content-Type: application/json" \
  -d '{"image_url": "http://localhost:8080/hls/emergency.m3u8", "title": "紧急通知", "duration": 300}'
```

### 场景二：会议直播

```bash
# 1. OBS推流会议画面
# 设置 → 推流
# 服务器: rtmp://server:1935/live
# 串流密钥: meeting?key=YOUR_KEY

# 2. 启动广播
curl -X POST http://localhost:5000/api/broadcast/start \
  -H "Content-Type: application/json" \
  -d '{
    "title": "全体会议直播",
    "level": 1,
    "content_type": "stream",
    "content": "http://localhost:8080/hls/meeting.m3u8"
  }'
```

### 场景三：一图流强制广播

```bash
# 1. 推流静态图片
ffmpeg -loop 1 -i warning.jpg \
  -c:v libx264 -preset veryfast -tune stillimage \
  -f flv rtmp://localhost:1935/static/alert?key=YOUR_KEY

# 2. 激活一图流（Level 3 - 无法关闭）
curl -X POST http://localhost:5000/api/broadcast/oneimage/set \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "http://localhost:8080/hls/static/alert.m3u8",
    "title": "系统警报",
    "duration": 0
  }'
```

---

## 📚 相关资源

- **OBS官方文档**: https://obsproject.com/wiki/
- **nginx-rtmp模块**: https://github.com/arut/nginx-rtmp-module
- **FFmpeg文档**: https://ffmpeg.org/documentation.html
- **Video.js**: https://videojs.com/
- **HLS规范**: https://datatracker.ietf.org/doc/html/rfc8216

---

## 🆘 获取帮助

如遇问题，请：

1. 查看日志：`tail -f /var/log/nginx/error.log`
2. 检查服务状态：`systemctl status nginx-rtmp`
3. 测试推流：`bash scripts/stream_with_ffmpeg.sh --simulation`
4. 提交Issue：https://github.com/your-repo/hidrs/issues
