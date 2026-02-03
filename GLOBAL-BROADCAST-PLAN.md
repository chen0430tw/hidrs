# 全球实时广播系统技术方案

## 📡 系统概述

**Global Real-time Broadcast System (全球实时广播系统)**

将 FAIRY-DESK 的右屏告警系统扩展为全球级实时广播平台，实现：
- 建立统一直播源（OBS/FFmpeg）
- 推流到流媒体平台（RTMP/HLS/WebRTC）
- 强制所有客户端设备全屏播放
- 多层级权限控制和紧急广播机制

**核心原理**：
```
直播源 → 流媒体服务器 → CDN分发 → 客户端强制播放
```

---

## 🎯 功能特性

### 1️⃣ 多源直播输入
- OBS Studio 推流（RTMP）
- FFmpeg 命令行推流
- 摄像头/屏幕直播
- 文件播放（循环播放视频/图片）
- 应急文字转语音（TTS紧急通知）

### 2️⃣ 流媒体分发
- RTMP 推流协议
- HLS (HTTP Live Streaming) 分发
- WebRTC 低延迟传输
- CDN 全球加速
- 多码率自适应

### 3️⃣ 客户端强制播放
- 自动全屏播放
- 禁止关闭/最小化
- 音量强制开启
- 覆盖所有窗口（最高 z-index）
- 断线自动重连

### 4️⃣ 权限分级控制
- **Level 0 (普通广播)**: 普通通知，可关闭
- **Level 1 (重要广播)**: 重要通知，需确认后关闭
- **Level 2 (紧急广播)**: 紧急通知，5分钟后可关闭
- **Level 3 (最高级广播)**: 强制播放，管理员权限才能关闭

### 5️⃣ 广播内容类型
- 视频直播（实时事件转播）
- 音频广播（语音通知）
- 图文滚动（紧急文字信息）
- 应急警报（地震、火灾、安全威胁）
- 系统维护通知

---

## 🏗️ 系统架构

```
┌────────────────────────────────────────────────────────────────────┐
│                         广播控制中心                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │ OBS Studio   │  │ FFmpeg CLI   │  │ TTS Engine   │            │
│  │ (GUI推流)    │  │ (脚本推流)    │  │ (文字转语音)  │            │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘            │
│         └──────────────────┼──────────────────┘                    │
│                            ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │            RTMP 推流服务器 (nginx-rtmp-module)              │  │
│  │  - 接收推流: rtmp://server:1935/live/emergency              │  │
│  │  - 推流认证: stream_key验证                                  │  │
│  │  - 录制存档: /var/media/broadcasts/                         │  │
│  └────────────────────────┬────────────────────────────────────┘  │
└───────────────────────────┼───────────────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│                    流媒体处理层 (FFmpeg)                            │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐ │
│  │ 转码器            │  │ HLS切片生成      │  │ WebRTC转换      │ │
│  │ - H.264/H.265    │  │ - .m3u8播放列表  │  │ - 低延迟传输     │ │
│  │ - AAC音频        │  │ - .ts视频切片    │  │ - P2P分发       │ │
│  │ - 多码率输出      │  │ - 10秒切片       │  │                 │ │
│  └──────────────────┘  └──────────────────┘  └─────────────────┘ │
└────────────────────────────┬───────────────────────────────────────┘
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│                  CDN 分发网络 (可选)                                │
│  - Cloudflare Stream / AWS CloudFront / 阿里云CDN                  │
│  - 全球节点加速                                                     │
│  - 自动负载均衡                                                     │
└────────────────────────────┬───────────────────────────────────────┘
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│                    广播管理 API (Flask)                             │
│  POST /api/broadcast/start      - 开始广播                         │
│  POST /api/broadcast/stop       - 停止广播                         │
│  POST /api/broadcast/emergency  - 紧急广播（Level 3）              │
│  GET  /api/broadcast/status     - 获取广播状态                     │
│  POST /api/broadcast/message    - 发送文字消息（TTS转语音）        │
│  GET  /api/broadcast/clients    - 获取在线客户端列表                │
│  POST /api/broadcast/force      - 强制刷新所有客户端                │
└────────────────────────────┬───────────────────────────────────────┘
                             ▼
                    WebSocket 推送通知
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│                    全球客户端设备                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              浏览器全屏播放器 (HTML5 Video)                  │  │
│  │  ┌───────────────────────────────────────────────────────┐  │  │
│  │  │  <video id="broadcast-player" autoplay>               │  │  │
│  │  │    <source src="https://cdn/live/emergency.m3u8"      │  │  │
│  │  │            type="application/x-mpegURL">              │  │  │
│  │  │  </video>                                             │  │  │
│  │  │                                                        │  │  │
│  │  │  - 接收 WebSocket 广播通知                             │  │  │
│  │  │  - 自动全屏并播放                                      │  │  │
│  │  │  - 禁止关闭（根据权限等级）                            │  │  │
│  │  │  - 断线自动重连                                        │  │  │
│  │  │  - 播放 HLS/RTMP/WebRTC 流                            │  │  │
│  │  └───────────────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  设备类型:                                                          │
│  - PC浏览器 (Chrome/Firefox/Edge)                                 │
│  - 移动设备 (iOS/Android)                                          │
│  - 嵌入式设备 (Raspberry Pi + Chromium Kiosk)                     │
│  - 智能电视 (WebOS/Android TV)                                     │
└────────────────────────────────────────────────────────────────────┘
```

---

## 🔧 技术栈

### 推流端
- **OBS Studio**: GUI 推流工具（适合非技术人员）
- **FFmpeg**: 命令行推流（适合自动化脚本）
- **Python opencv-python**: 程序化视频流生成

### 流媒体服务器
- **nginx + nginx-rtmp-module**: RTMP 推流接收
- **FFmpeg**: 转码和 HLS 切片生成
- **SRS (Simple Realtime Server)**: 可选的专业流媒体服务器
- **Janus WebRTC Server**: 低延迟 WebRTC 传输

### 后端 API
- **Flask + Flask-SocketIO**: 广播管理和 WebSocket 推送
- **Redis**: 广播状态缓存和客户端会话管理
- **PostgreSQL**: 广播历史记录存储

### 前端播放器
- **Video.js**: HTML5 视频播放器（支持 HLS/RTMP）
- **hls.js**: 纯 JavaScript HLS 播放器
- **WebRTC**: 浏览器原生 P2P 传输

### CDN（可选）
- **Cloudflare Stream**: 全球 CDN + 视频托管
- **AWS CloudFront**: 低延迟全球分发
- **阿里云 CDN**: 国内加速

---

## 📐 数据模型

### 广播记录 (broadcasts)

```json
{
  "broadcast_id": "bc_20260203_152030",
  "title": "紧急安全通知",
  "description": "检测到网络攻击，所有系统进入防御模式",
  "level": 3,  // 0=普通, 1=重要, 2=紧急, 3=最高级
  "type": "emergency",  // normal/important/emergency/system
  "source": "rtmp://server:1935/live/emergency",
  "hls_url": "https://cdn.example.com/live/emergency.m3u8",
  "webrtc_url": "wss://server:8443/webrtc/emergency",
  "start_time": "2026-02-03T15:20:30Z",
  "end_time": null,  // null表示正在播放
  "duration": 0,  // 秒，实时更新
  "status": "live",  // scheduled/live/ended/error
  "target_audience": "all",  // all/region/department/specific
  "target_clients": [],  // 如果是specific，列出客户端ID
  "created_by": "admin_001",
  "priority": 100,  // 优先级，高优先级覆盖低优先级
  "metadata": {
    "thumbnail": "https://cdn/thumbnails/bc_20260203_152030.jpg",
    "record_file": "/var/media/broadcasts/bc_20260203_152030.mp4",
    "viewer_count": 52800,
    "avg_bitrate": 2500,  // kbps
    "codec": "H.264/AAC"
  }
}
```

### 客户端连接 (broadcast_clients)

```json
{
  "client_id": "client_8a2f3d9c",
  "device_type": "browser",  // browser/mobile/tv/embedded
  "device_info": {
    "ua": "Mozilla/5.0 Chrome/120.0.0.0",
    "platform": "Linux x86_64",
    "screen": "1920x1080"
  },
  "ip_address": "203.0.113.45",
  "location": {
    "country": "CN",
    "city": "Beijing",
    "lat": 39.9042,
    "lon": 116.4074
  },
  "connected_at": "2026-02-03T15:21:00Z",
  "last_heartbeat": "2026-02-03T15:25:30Z",
  "status": "playing",  // idle/buffering/playing/paused/error
  "current_broadcast": "bc_20260203_152030",
  "permissions": {
    "can_close": false,  // Level 3广播不允许关闭
    "can_mute": false,
    "can_minimize": false
  },
  "playback_quality": {
    "bitrate": 2500,  // kbps
    "buffer_length": 15,  // 秒
    "dropped_frames": 0,
    "latency": 3.2  // 秒
  }
}
```

---

## 🔌 API 端点设计

### 1. 开始广播

```
POST /api/broadcast/start
```

**请求体**:
```json
{
  "title": "系统维护通知",
  "description": "将于今晚22:00进行系统升级",
  "level": 1,
  "type": "system",
  "source_type": "rtmp",  // rtmp/file/tts/screen
  "source_url": "rtmp://192.168.1.100:1935/live/maintenance",
  "target_audience": "all",
  "scheduled_start": null,  // null表示立即开始
  "auto_end_after": 600  // 10分钟后自动结束，null表示手动结束
}
```

**响应**:
```json
{
  "success": true,
  "broadcast_id": "bc_20260203_220000",
  "hls_url": "https://cdn.example.com/live/bc_20260203_220000.m3u8",
  "webrtc_url": "wss://server:8443/webrtc/bc_20260203_220000",
  "status": "live",
  "message": "广播已启动，正在推送到 52800 个客户端"
}
```

---

### 2. 紧急广播（Level 3）

```
POST /api/broadcast/emergency
```

**请求体**:
```json
{
  "message": "检测到网络攻击，所有系统立即进入防御模式",
  "type": "security_alert",
  "duration": 300,  // 持续5分钟
  "tts_voice": "zh-CN-XiaoxiaoNeural",  // Azure TTS语音
  "background_color": "#ff0000",
  "text_size": 48
}
```

**响应**:
```json
{
  "success": true,
  "broadcast_id": "bc_emergency_20260203_152030",
  "hls_url": "https://cdn.example.com/live/emergency.m3u8",
  "status": "live",
  "clients_notified": 52800,
  "tts_generated": true,
  "audio_file": "/tmp/tts_emergency_20260203_152030.mp3"
}
```

---

### 3. 停止广播

```
POST /api/broadcast/stop
```

**请求体**:
```json
{
  "broadcast_id": "bc_20260203_220000",
  "reason": "scheduled_end"
}
```

**响应**:
```json
{
  "success": true,
  "broadcast_id": "bc_20260203_220000",
  "status": "ended",
  "duration": 610,  // 秒
  "total_viewers": 52800,
  "peak_viewers": 48500,
  "record_file": "/var/media/broadcasts/bc_20260203_220000.mp4"
}
```

---

### 4. 获取广播状态

```
GET /api/broadcast/status?broadcast_id=bc_20260203_220000
```

**响应**:
```json
{
  "success": true,
  "broadcast": {
    "broadcast_id": "bc_20260203_220000",
    "title": "系统维护通知",
    "status": "live",
    "start_time": "2026-02-03T22:00:00Z",
    "duration": 305,
    "current_viewers": 48500,
    "peak_viewers": 48500,
    "hls_url": "https://cdn.example.com/live/bc_20260203_220000.m3u8",
    "bitrate": 2500,
    "health": "good"  // good/buffering/unstable/error
  }
}
```

---

### 5. 发送文字消息（TTS转语音广播）

```
POST /api/broadcast/message
```

**请求体**:
```json
{
  "message": "所有人员请注意，现在是消防演习时间，请有序撤离",
  "level": 2,
  "duration": 120,
  "tts_config": {
    "voice": "zh-CN-YunxiNeural",
    "rate": "+0%",
    "pitch": "+0Hz",
    "volume": "+0%"
  },
  "repeat": 3  // 重复播放3次
}
```

**响应**:
```json
{
  "success": true,
  "broadcast_id": "bc_tts_20260203_154530",
  "audio_file": "/tmp/tts_20260203_154530.mp3",
  "duration": 15,  // 单次播放时长
  "total_duration": 45,  // 重复3次总时长
  "hls_url": "https://cdn.example.com/live/tts_20260203_154530.m3u8"
}
```

---

### 6. 获取在线客户端列表

```
GET /api/broadcast/clients?status=playing&limit=100
```

**响应**:
```json
{
  "success": true,
  "total": 52800,
  "playing": 48500,
  "buffering": 3200,
  "error": 1100,
  "clients": [
    {
      "client_id": "client_8a2f3d9c",
      "device_type": "browser",
      "location": "Beijing, CN",
      "status": "playing",
      "current_broadcast": "bc_20260203_220000",
      "bitrate": 2500,
      "latency": 3.2,
      "connected_at": "2026-02-03T22:00:05Z"
    }
  ]
}
```

---

### 7. 强制刷新客户端

```
POST /api/broadcast/force
```

**请求体**:
```json
{
  "action": "reload",  // reload/fullscreen/unmute/reconnect
  "target_clients": [],  // 空数组表示所有客户端
  "reason": "stream_quality_upgrade"
}
```

**响应**:
```json
{
  "success": true,
  "action": "reload",
  "clients_affected": 52800,
  "notifications_sent": 52800
}
```

---

## 🎨 前端实现

### 全屏播放器组件 (`broadcast_player.html`)

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>全球实时广播</title>
  <link href="https://vjs.zencdn.net/8.6.1/video-js.css" rel="stylesheet">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      background: #000;
      overflow: hidden;
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* 全屏容器 */
    #broadcast-container {
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      z-index: 999999;  /* 覆盖所有元素 */
      background: #000;
    }

    /* 视频播放器 */
    #broadcast-player {
      width: 100%;
      height: 100%;
      object-fit: contain;
    }

    /* 广播信息叠加层 */
    .broadcast-overlay {
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      padding: 20px;
      background: linear-gradient(to bottom, rgba(0,0,0,0.8), transparent);
      color: white;
      z-index: 10;
    }

    .broadcast-title {
      font-size: 28px;
      font-weight: bold;
      margin-bottom: 10px;
      text-shadow: 2px 2px 4px rgba(0,0,0,0.8);
    }

    .broadcast-level {
      display: inline-block;
      padding: 5px 15px;
      border-radius: 4px;
      font-size: 14px;
      font-weight: bold;
      text-transform: uppercase;
    }

    .level-0 { background: #3b82f6; }  /* 普通 */
    .level-1 { background: #f59e0b; }  /* 重要 */
    .level-2 { background: #ef4444; }  /* 紧急 */
    .level-3 {
      background: #dc2626;
      animation: pulse 1s infinite;
    }  /* 最高级 */

    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.7; }
    }

    /* 关闭按钮（仅低权限广播可见） */
    .close-btn {
      position: absolute;
      top: 20px;
      right: 20px;
      width: 50px;
      height: 50px;
      background: rgba(255, 255, 255, 0.2);
      border: 2px solid white;
      border-radius: 50%;
      color: white;
      font-size: 24px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 20;
      transition: background 0.3s;
    }

    .close-btn:hover {
      background: rgba(255, 255, 255, 0.4);
    }

    .close-btn.disabled {
      opacity: 0.3;
      cursor: not-allowed;
    }

    /* 连接状态指示器 */
    .connection-status {
      position: absolute;
      bottom: 20px;
      left: 20px;
      padding: 10px 20px;
      background: rgba(0, 0, 0, 0.7);
      border-radius: 20px;
      color: white;
      font-size: 14px;
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .status-indicator {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: #10b981;
    }

    .status-indicator.buffering { background: #f59e0b; }
    .status-indicator.error { background: #ef4444; }

    /* 观看人数 */
    .viewer-count {
      position: absolute;
      bottom: 20px;
      right: 20px;
      padding: 10px 20px;
      background: rgba(0, 0, 0, 0.7);
      border-radius: 20px;
      color: white;
      font-size: 14px;
    }
  </style>
</head>
<body>
  <div id="broadcast-container">
    <!-- 视频播放器 -->
    <video id="broadcast-player" class="video-js vjs-big-play-centered" controls autoplay muted></video>

    <!-- 广播信息叠加层 -->
    <div class="broadcast-overlay">
      <div class="broadcast-title" id="broadcast-title">系统广播</div>
      <span class="broadcast-level level-0" id="broadcast-level">普通</span>
    </div>

    <!-- 关闭按钮 -->
    <button class="close-btn" id="close-btn" title="关闭广播">✕</button>

    <!-- 连接状态 -->
    <div class="connection-status">
      <div class="status-indicator" id="status-indicator"></div>
      <span id="status-text">正在连接...</span>
    </div>

    <!-- 观看人数 -->
    <div class="viewer-count">
      <span id="viewer-count">🔴 观看: 0人</span>
    </div>
  </div>

  <script src="https://vjs.zencdn.net/8.6.1/video.min.js"></script>
  <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
  <script>
    const API_BASE = 'http://localhost:5000';
    const WS_URL = 'ws://localhost:5000';

    let player = null;
    let socket = null;
    let currentBroadcast = null;

    // 初始化播放器
    function initPlayer() {
      player = videojs('broadcast-player', {
        controls: true,
        autoplay: true,
        preload: 'auto',
        fluid: true,
        liveui: true,
        html5: {
          hls: {
            enableLowInitialPlaylist: true,
            smoothQualityChange: true,
            overrideNative: true
          }
        }
      });

      // 播放器事件
      player.on('playing', () => updateStatus('playing', 'live'));
      player.on('waiting', () => updateStatus('buffering', 'buffering'));
      player.on('error', () => updateStatus('error', 'error'));
      player.on('loadeddata', () => {
        // 强制取消静音
        player.muted(false);
        player.volume(1.0);
      });
    }

    // WebSocket 连接
    function connectWebSocket() {
      socket = io(WS_URL);

      socket.on('connect', () => {
        console.log('WebSocket已连接');
        updateStatus('connected', 'live');
      });

      socket.on('broadcast_start', (data) => {
        console.log('收到广播开始通知:', data);
        startBroadcast(data);
      });

      socket.on('broadcast_stop', (data) => {
        console.log('收到广播停止通知:', data);
        stopBroadcast();
      });

      socket.on('broadcast_update', (data) => {
        console.log('广播信息更新:', data);
        updateBroadcastInfo(data);
      });

      socket.on('force_action', (data) => {
        console.log('收到强制操作指令:', data);
        handleForceAction(data);
      });

      socket.on('viewer_count_update', (data) => {
        document.getElementById('viewer-count').textContent =
          `🔴 观看: ${formatNumber(data.count)}人`;
      });

      socket.on('disconnect', () => {
        console.log('WebSocket断开，尝试重连...');
        updateStatus('disconnected', 'error');
        setTimeout(connectWebSocket, 3000);
      });
    }

    // 开始广播
    function startBroadcast(broadcast) {
      currentBroadcast = broadcast;

      // 更新广播信息
      document.getElementById('broadcast-title').textContent = broadcast.title;

      const levelBadge = document.getElementById('broadcast-level');
      levelBadge.className = `broadcast-level level-${broadcast.level}`;
      levelBadge.textContent = getLevelLabel(broadcast.level);

      // 设置关闭按钮权限
      const closeBtn = document.getElementById('close-btn');
      if (broadcast.level >= 2) {
        closeBtn.classList.add('disabled');
        closeBtn.onclick = null;
        closeBtn.title = '该广播级别不允许关闭';
      } else {
        closeBtn.classList.remove('disabled');
        closeBtn.onclick = requestCloseBroadcast;
        closeBtn.title = '关闭广播';
      }

      // 加载视频源
      player.src({
        src: broadcast.hls_url,
        type: 'application/x-mpegURL'
      });

      // 进入全屏
      enterFullscreen();

      // 取消静音
      player.muted(false);
      player.volume(1.0);

      // 开始播放
      player.play().catch(err => {
        console.error('自动播放失败:', err);
        // 尝试静音播放
        player.muted(true);
        player.play();
      });
    }

    // 停止广播
    function stopBroadcast() {
      if (player) {
        player.pause();
        player.src('');
      }

      currentBroadcast = null;

      // 退出全屏
      exitFullscreen();

      // 可以选择隐藏播放器或显示待机画面
      // document.getElementById('broadcast-container').style.display = 'none';
    }

    // 更新广播信息
    function updateBroadcastInfo(data) {
      if (data.title) {
        document.getElementById('broadcast-title').textContent = data.title;
      }

      if (typeof data.level !== 'undefined') {
        const levelBadge = document.getElementById('broadcast-level');
        levelBadge.className = `broadcast-level level-${data.level}`;
        levelBadge.textContent = getLevelLabel(data.level);
      }
    }

    // 处理强制操作
    function handleForceAction(data) {
      switch(data.action) {
        case 'reload':
          location.reload();
          break;
        case 'fullscreen':
          enterFullscreen();
          break;
        case 'unmute':
          player.muted(false);
          player.volume(1.0);
          break;
        case 'reconnect':
          if (currentBroadcast) {
            player.src({
              src: currentBroadcast.hls_url,
              type: 'application/x-mpegURL'
            });
            player.play();
          }
          break;
      }
    }

    // 请求关闭广播
    function requestCloseBroadcast() {
      if (!currentBroadcast || currentBroadcast.level >= 2) {
        alert('该广播级别不允许关闭');
        return;
      }

      if (confirm('确定要关闭当前广播吗？')) {
        fetch(`${API_BASE}/api/broadcast/client/close`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client_id: getClientId(),
            broadcast_id: currentBroadcast.broadcast_id
          })
        });

        stopBroadcast();
      }
    }

    // 进入全屏
    function enterFullscreen() {
      const elem = document.getElementById('broadcast-container');
      if (elem.requestFullscreen) {
        elem.requestFullscreen();
      } else if (elem.webkitRequestFullscreen) {
        elem.webkitRequestFullscreen();
      } else if (elem.mozRequestFullScreen) {
        elem.mozRequestFullScreen();
      }
    }

    // 退出全屏
    function exitFullscreen() {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
      } else if (document.mozCancelFullScreen) {
        document.mozCancelFullScreen();
      }
    }

    // 更新状态
    function updateStatus(status, type) {
      const indicator = document.getElementById('status-indicator');
      const statusText = document.getElementById('status-text');

      indicator.className = `status-indicator ${type}`;

      const statusLabels = {
        'connected': '已连接',
        'live': '直播中',
        'buffering': '缓冲中...',
        'error': '连接错误',
        'disconnected': '已断开'
      };

      statusText.textContent = statusLabels[status] || status;
    }

    // 获取客户端ID
    function getClientId() {
      let clientId = localStorage.getItem('broadcast_client_id');
      if (!clientId) {
        clientId = 'client_' + Math.random().toString(36).substr(2, 9);
        localStorage.setItem('broadcast_client_id', clientId);
      }
      return clientId;
    }

    // 获取级别标签
    function getLevelLabel(level) {
      const labels = {
        0: '普通',
        1: '重要',
        2: '紧急',
        3: '最高级'
      };
      return labels[level] || '未知';
    }

    // 格式化数字
    function formatNumber(num) {
      return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }

    // 防止用户关闭页面（Level 2+）
    window.addEventListener('beforeunload', (e) => {
      if (currentBroadcast && currentBroadcast.level >= 2) {
        e.preventDefault();
        e.returnValue = '当前正在播放重要广播，确定要离开吗？';
        return e.returnValue;
      }
    });

    // 防止F11全屏切换（Level 3）
    document.addEventListener('keydown', (e) => {
      if (currentBroadcast && currentBroadcast.level >= 3) {
        if (e.key === 'F11' || (e.key === 'Escape' && document.fullscreenElement)) {
          e.preventDefault();
        }
      }
    });

    // 页面加载完成后初始化
    window.addEventListener('DOMContentLoaded', () => {
      initPlayer();
      connectWebSocket();

      // 定期发送心跳
      setInterval(() => {
        if (socket && socket.connected) {
          socket.emit('heartbeat', {
            client_id: getClientId(),
            broadcast_id: currentBroadcast?.broadcast_id,
            status: player ? (player.paused() ? 'paused' : 'playing') : 'idle'
          });
        }
      }, 30000);  // 每30秒
    });
  </script>
</body>
</html>
```

---

## 🚀 部署方案

### 方案一：自建流媒体服务器

#### 1. 安装 nginx + rtmp 模块

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y build-essential libpcre3 libpcre3-dev libssl-dev zlib1g-dev

# 下载nginx和rtmp模块
cd /tmp
wget http://nginx.org/download/nginx-1.24.0.tar.gz
git clone https://github.com/arut/nginx-rtmp-module.git

# 编译安装
tar -zxvf nginx-1.24.0.tar.gz
cd nginx-1.24.0
./configure --with-http_ssl_module --add-module=../nginx-rtmp-module
make
sudo make install
```

#### 2. 配置 nginx.conf

```nginx
# /usr/local/nginx/conf/nginx.conf

worker_processes auto;
events {
    worker_connections 1024;
}

# RTMP 推流配置
rtmp {
    server {
        listen 1935;
        chunk_size 4096;

        application live {
            live on;
            record off;

            # 推流认证
            on_publish http://localhost:5000/api/broadcast/auth;

            # HLS 输出
            hls on;
            hls_path /var/media/hls;
            hls_fragment 3s;
            hls_playlist_length 60s;

            # 录制
            record all;
            record_path /var/media/broadcasts;
            record_suffix _%Y%m%d_%H%M%S.mp4;
        }
    }
}

# HTTP 服务器
http {
    server {
        listen 8080;

        # HLS 文件分发
        location /hls {
            types {
                application/vnd.apple.mpegurl m3u8;
                video/mp2t ts;
            }
            root /var/media;
            add_header Cache-Control no-cache;
            add_header Access-Control-Allow-Origin *;
        }

        # 广播录像下载
        location /broadcasts {
            alias /var/media/broadcasts;
            add_header Access-Control-Allow-Origin *;
        }
    }
}
```

#### 3. 创建媒体目录

```bash
sudo mkdir -p /var/media/hls
sudo mkdir -p /var/media/broadcasts
sudo chown -R www-data:www-data /var/media
```

#### 4. 启动 nginx

```bash
sudo /usr/local/nginx/sbin/nginx
```

---

### 方案二：使用 SRS 流媒体服务器

```bash
# Docker 部署 SRS
docker run -d \
  --name srs \
  -p 1935:1935 \
  -p 1985:1985 \
  -p 8080:8080 \
  -v /var/media:/usr/local/srs/objs/nginx/html \
  ossrs/srs:5
```

**SRS 配置** (`srs.conf`):
```conf
listen              1935;
max_connections     1000;
daemon              off;

http_server {
    enabled         on;
    listen          8080;
    dir             ./objs/nginx/html;
}

vhost __defaultVhost__ {
    hls {
        enabled         on;
        hls_path        /var/media/hls;
        hls_fragment    3;
        hls_window      60;
    }

    http_remux {
        enabled     on;
        mount       [vhost]/[app]/[stream].flv;
    }
}
```

---

### 方案三：使用云服务（推荐生产环境）

#### Cloudflare Stream

```python
import requests

# 上传视频到 Cloudflare Stream
def upload_to_cloudflare_stream(video_file):
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/stream"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}"
    }
    files = {
        "file": open(video_file, "rb")
    }

    response = requests.post(url, headers=headers, files=files)
    data = response.json()

    return data['result']['playback']['hls']  # HLS URL
```

#### AWS CloudFront + MediaLive

```bash
# 使用 AWS CLI 创建 MediaLive 频道
aws medialive create-channel \
  --name "global-broadcast" \
  --role-arn "arn:aws:iam::ACCOUNT:role/MediaLiveRole" \
  --input-attachments InputId=input-123 \
  --destinations Id=dest1,Url=s3://bucket/live/
```

---

## 🎬 推流操作指南

### 使用 OBS Studio 推流

1. **打开 OBS Studio**
2. **设置 → 推流**:
   - 服务: 自定义
   - 服务器: `rtmp://server:1935/live`
   - 串流密钥: `emergency?key=YOUR_STREAM_KEY`
3. **来源**:
   - 添加"显示器采集"（屏幕直播）
   - 添加"视频采集设备"（摄像头）
   - 添加"文本"（紧急通知文字）
4. **开始推流**

---

### 使用 FFmpeg 推流

#### 推流文件

```bash
ffmpeg -re -i video.mp4 \
  -c:v libx264 -preset veryfast -b:v 2500k \
  -c:a aac -b:a 128k \
  -f flv rtmp://server:1935/live/emergency?key=YOUR_KEY
```

#### 推流屏幕

```bash
# Linux (X11)
ffmpeg -f x11grab -s 1920x1080 -i :0.0 \
  -c:v libx264 -preset ultrafast -b:v 3000k \
  -f flv rtmp://server:1935/live/screen?key=YOUR_KEY

# macOS
ffmpeg -f avfoundation -i "1:0" \
  -c:v libx264 -preset ultrafast -b:v 3000k \
  -f flv rtmp://server:1935/live/screen?key=YOUR_KEY

# Windows
ffmpeg -f gdigrab -i desktop \
  -c:v libx264 -preset ultrafast -b:v 3000k \
  -f flv rtmp://server:1935/live/screen?key=YOUR_KEY
```

#### 推流摄像头

```bash
# Linux
ffmpeg -f v4l2 -i /dev/video0 \
  -c:v libx264 -preset ultrafast -b:v 2000k \
  -f flv rtmp://server:1935/live/camera?key=YOUR_KEY

# macOS
ffmpeg -f avfoundation -i "0" \
  -c:v libx264 -preset ultrafast -b:v 2000k \
  -f flv rtmp://server:1935/live/camera?key=YOUR_KEY
```

#### TTS 文字转语音推流

```python
import pyttsx3
import subprocess

def text_to_broadcast(text, stream_key):
    # 生成TTS音频
    engine = pyttsx3.init()
    engine.save_to_file(text, '/tmp/tts.mp3')
    engine.runAndWait()

    # 创建带文字的视频
    subprocess.run([
        'ffmpeg', '-loop', '1', '-i', 'background.png',
        '-i', '/tmp/tts.mp3',
        '-c:v', 'libx264', '-tune', 'stillimage',
        '-c:a', 'aac', '-b:a', '128k',
        '-shortest',
        '-f', 'flv',
        f'rtmp://server:1935/live/tts?key={stream_key}'
    ])

# 使用
text_to_broadcast("这是一条紧急广播消息", "YOUR_STREAM_KEY")
```

---

## 🔐 安全考虑

### 1. 推流认证

```python
from flask import request, jsonify
import hashlib
import time

@app.route('/api/broadcast/auth', methods=['POST'])
def authenticate_stream():
    """RTMP推流认证"""
    stream_name = request.form.get('name')
    stream_key = request.args.get('key')

    # 验证stream_key
    expected_key = hashlib.sha256(
        f"{stream_name}:{STREAM_SECRET}:{int(time.time() / 3600)}"
    ).hexdigest()[:16]

    if stream_key != expected_key:
        return '', 403  # 拒绝推流

    return '', 200  # 允许推流
```

### 2. 客户端访问控制

```python
@app.route('/api/broadcast/client/register', methods=['POST'])
def register_client():
    """客户端注册（获取观看权限）"""
    data = request.json

    # 验证客户端身份
    client_token = validate_client_token(data.get('token'))
    if not client_token:
        return jsonify({"error": "未授权"}), 401

    # 生成临时观看凭证
    watch_token = generate_watch_token(client_token['client_id'])

    return jsonify({
        "success": True,
        "watch_token": watch_token,
        "expires_in": 3600
    })
```

### 3. HLS 加密（可选）

```bash
# 生成AES-128密钥
openssl rand 16 > enc.key

# FFmpeg HLS加密推流
ffmpeg -i input.mp4 \
  -c:v libx264 -c:a aac \
  -hls_time 10 \
  -hls_key_info_file keyinfo.txt \
  -hls_playlist_type event \
  output.m3u8
```

**keyinfo.txt**:
```
http://server/keys/enc.key
/path/to/enc.key
$(openssl rand -hex 16)
```

### 4. 防止 DDoS

```nginx
# nginx 限流配置
http {
    limit_req_zone $binary_remote_addr zone=hls:10m rate=10r/s;

    server {
        location /hls {
            limit_req zone=hls burst=20;
            # ...
        }
    }
}
```

---

## 📊 与 FAIRY 右屏对比

| 特性 | FAIRY 右屏 | 全球广播系统 |
|------|-----------|-------------|
| **广播范围** | 单机（本地浏览器） | 全球（所有连接设备） |
| **内容类型** | 文字告警 + JSON数据 | 视频/音频/图文 |
| **推送方式** | 本地轮询 | WebSocket实时推送 |
| **延迟** | <1秒 | 3-10秒（HLS） / <1秒（WebRTC） |
| **带宽需求** | 极低（<1KB/s） | 中高（500KB/s - 5MB/s） |
| **客户端控制** | 无（用户完全控制） | 强制播放（Level 3不可关闭） |
| **适用场景** | 单人运维监控 | 大规模紧急通知/直播 |
| **基础设施** | Flask本地API | 流媒体服务器 + CDN |

**FAIRY 右屏实现 → 全球广播的进化路径**:
```
FAIRY 右屏告警系统
  └─ 本地Flask API (/api/alerts)
     └─ 前端轮询刷新
        └─ 显示JSON数据

            ↓ 扩展为全球广播

全球广播系统
  └─ 流媒体服务器 (nginx-rtmp / SRS)
     └─ WebSocket实时推送 (Socket.IO)
        └─ 强制视频播放 (HLS/WebRTC)
           └─ CDN全球分发
              └─ 5万+客户端同时观看
```

---

## 🎯 实施步骤

### 阶段一：基础设施搭建（1-2天）

1. ✅ 部署 nginx + rtmp 模块
2. ✅ 配置 HLS 输出
3. ✅ 测试 OBS/FFmpeg 推流
4. ✅ 验证 HLS 播放

### 阶段二：后端 API 开发（2-3天）

1. ✅ Flask 广播管理 API
2. ✅ WebSocket 推送通知 (Socket.IO)
3. ✅ 客户端会话管理（Redis）
4. ✅ 广播历史记录存储（PostgreSQL）
5. ✅ TTS 文字转语音功能

### 阶段三：前端播放器（1-2天）

1. ✅ Video.js 播放器集成
2. ✅ 全屏强制播放逻辑
3. ✅ 权限等级控制
4. ✅ 断线自动重连
5. ✅ 播放质量监控

### 阶段四：FAIRY 集成（1天）

1. ✅ 在 FAIRY-DESK 添加广播控制面板
2. ✅ 右屏告警触发全球广播（高级别告警自动转为Level 3广播）
3. ✅ 统一管理界面

### 阶段五：测试与优化（2-3天）

1. ✅ 负载测试（模拟5万+客户端）
2. ✅ 延迟优化（HLS → WebRTC）
3. ✅ CDN 配置（全球加速）
4. ✅ 安全审计

---

## 📝 TODO

- [ ] 搭建 nginx-rtmp 流媒体服务器
- [ ] 实现广播管理 Flask API
- [ ] 开发前端全屏播放器
- [ ] 集成 WebSocket 实时推送
- [ ] 实现 TTS 文字转语音广播
- [ ] 添加推流认证机制
- [ ] 配置 CDN 全球分发（可选）
- [ ] 集成到 FAIRY-DESK 右屏
- [ ] 负载测试和性能优化

---

## 🎬 使用示例

### 发起紧急广播

```bash
curl -X POST http://localhost:5000/api/broadcast/emergency \
  -H "Content-Type: application/json" \
  -d '{
    "message": "检测到网络攻击，所有系统进入防御模式",
    "type": "security_alert",
    "duration": 300
  }'
```

### 推流视频文件

```bash
ffmpeg -re -i alert.mp4 \
  -c copy \
  -f flv rtmp://server:1935/live/emergency?key=YOUR_KEY
```

### 查看在线客户端

```bash
curl http://localhost:5000/api/broadcast/clients?status=playing
```

---

**总结**：全球实时广播系统是 FAIRY-DESK 右屏告警系统的全球化扩展，通过流媒体技术实现了从单机监控到全球广播的进化。核心技术栈为 **nginx-rtmp + HLS + WebSocket + Video.js**，支持多级别权限控制和强制播放机制。
