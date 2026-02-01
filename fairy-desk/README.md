# 🧿 FAIRY-DESK

**妖精桌面情报台** - 三联屏网页化指挥桌面 + AI Agent

一个赛博朋克风格的多屏监控仪表板，支持实时态势感知、AI 助手、新闻聚合和系统监控。

![Preview](https://img.shields.io/badge/Preview-8080-cyan?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

## ✨ 功能特性

### 🖥️ 三屏布局

| 屏幕 | 功能 | 说明 |
|------|------|------|
| **左屏** | 态势监控 | CCTV、地图、航班、船舶、网络攻击地图 |
| **中屏** | 控制台 | 系统监控、终端、Claude Code、AI Agent |
| **右屏** | 情报视窗 | 社交媒体、新闻 RSS、股票行情、告警日志 |

### 🔧 核心功能

- **🗺️ 内置地图** - Leaflet + OpenStreetMap 暗色主题
- **🚢 船舶追踪** - MarineTraffic / VesselFinder 集成
- **📱 社交媒体轮播** - X/Twitter、Threads、Bluesky、Mastodon、Reddit、微博
- **🧿 Claude Code 终端** - 通过 claude-code-web 在浏览器中使用 Claude Code
- **📈 股票行情** - TradingView 图表小组件
- **📰 新闻聚合** - RSS 订阅（BBC、Reuters、NHK 等）
- **🚨 告警系统** - SSE 实时推送 + HIDRS 集成
- **⚙️ 可配置** - Tab 管理、主题、加载策略

## 🚀 快速开始

### 方式一：独立运行

```bash
cd fairy-desk

# 安装依赖
pip install -r requirements.txt

# 启动服务
python app.py
```

访问 http://localhost:8080

### 方式二：集成 Claude Code

```bash
cd fairy-desk

# Linux/macOS
./start-with-claude.sh

# Windows
start-with-claude.bat
```

这会同时启动：
- FAIRY-DESK @ http://localhost:8080
- claude-code-web @ http://localhost:3000

### 方式三：Docker

```bash
docker-compose up --build
```

## 📁 项目结构

```
fairy-desk/
├── app.py                 # Flask 后端主程序
├── config.json            # 配置文件
├── requirements.txt       # Python 依赖
├── start-with-claude.sh   # Linux/macOS 启动脚本
├── start-with-claude.bat  # Windows 启动脚本
├── static/
│   ├── css/
│   │   └── theme.css      # 赛博朋克主题
│   └── js/
│       └── core.js        # 核心 JavaScript
└── templates/
    ├── index.html         # 主入口
    ├── left.html          # 左屏
    ├── center.html        # 中屏
    ├── right.html         # 右屏
    ├── settings.html      # 设置页
    ├── preview.html       # 三联屏预览
    └── widgets/           # 内置小组件
        ├── map.html       # Leaflet 地图
        ├── marine.html    # 船舶追踪
        ├── social.html    # 社交媒体轮播
        └── terminal.html  # Claude Code 终端
```

## 🔗 路由说明

| 路由 | 说明 |
|------|------|
| `/` | 主入口页（选择屏幕） |
| `/left` | 左屏 - 态势监控 |
| `/center` | 中屏 - 控制台 |
| `/right` | 右屏 - 情报视窗 |
| `/preview` | 三联屏预览模式 |
| `/settings` | 设置页面 |
| `/widget/map` | 地图小组件 |
| `/widget/marine` | 船舶追踪小组件 |
| `/widget/social` | 社交媒体小组件 |
| `/widget/terminal` | Claude Code 终端 |

## ⚙️ API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/system/stats` | GET | 系统状态（CPU/内存/网络/GPU） |
| `/api/system/logs` | GET | 系统日志 SSE 流 |
| `/api/feeds/news` | GET | RSS 新闻聚合 |
| `/api/config` | GET/POST | 配置管理 |
| `/api/config/tabs` | GET/POST | Tab 管理 |
| `/api/config/tabs/<id>` | PUT/DELETE | 单个 Tab 操作 |
| `/api/events/stream` | GET | 事件/告警 SSE 流 |
| `/api/hidrs/status` | GET | HIDRS 连接状态 |
| `/api/hidrs/proxy/<path>` | GET | HIDRS API 代理 |
| `/health` | GET | 健康检查 |

## 🎨 配置说明

编辑 `config.json` 自定义：

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8080
  },
  "hidrs": {
    "endpoint": "http://localhost:5000",
    "auto_detect": true
  },
  "left_screen": {
    "tabs": [
      {
        "id": "custom",
        "name": "自定义",
        "icon": "🌐",
        "url": "https://example.com",
        "loadStrategy": "lazy"
      }
    ]
  },
  "right_screen": {
    "news": {
      "feeds": [
        {"name": "BBC", "url": "https://...", "enabled": true}
      ]
    },
    "stocks": {
      "symbols": ["AAPL", "BTCUSD"]
    }
  },
  "theme": {
    "primary_color": "#00f0ff"
  }
}
```

### 加载策略 (loadStrategy)

| 策略 | 说明 |
|------|------|
| `background` | 后台预加载，切换时立即显示 |
| `lazy` | 首次切换时才加载 |
| `smart` | 智能判断（根据网络和内存） |

## 🔌 HIDRS 集成

FAIRY-DESK 可作为 [HIDRS](../README.md)（全息拉普拉斯互联网爬虫系统）的可视化前端。

启用 HIDRS 后可获得：
- 🔗 网络拓扑实时监控
- 📊 Fiedler 值异常检测
- 🔍 全息搜索功能
- 🤖 AI 决策反馈

```bash
# 先启动 HIDRS
cd ../backend && python crawler_server.py

# 再启动 FAIRY-DESK
cd ../fairy-desk && python app.py
```

## 🧿 Claude Code 集成

### 前置条件

1. 安装 Claude Code CLI：
   ```bash
   # macOS/Linux
   curl -fsSL https://claude.ai/install.sh | bash

   # Windows
   irm https://claude.ai/install.ps1 | iex
   ```

2. 确保 Node.js 已安装

### 使用方式

1. 启动 claude-code-web：
   ```bash
   npx claude-code-web
   ```

2. 复制终端显示的 Token

3. 在 FAIRY-DESK 中屏点击「Claude」标签

4. 填入服务地址和 Token 连接

### 功能说明

- ✅ 完整的 Claude Code CLI 功能
- ✅ 可操作本地文件系统
- ✅ 支持 git、npm 等命令
- ✅ 会话持久化

## 📱 使用场景

### 单屏预览模式

访问 `/preview` 在单屏上预览三联屏效果，适合：
- 开发调试
- 没有多显示器时预览
- 演示展示

### 真实三联屏部署

1. 访问 `/preview`
2. 点击「开启三窗口模式」
3. 将三个窗口分别拖到三台显示器
4. 各窗口按 F11 进入全屏

## 🛠️ 开发

### 添加新的左屏 Tab

1. 在 `/settings` 页面添加
2. 或直接编辑 `config.json`
3. 或调用 API：
   ```bash
   curl -X POST http://localhost:8080/api/config/tabs \
     -H "Content-Type: application/json" \
     -d '{"name":"新Tab","url":"https://...","icon":"🌐"}'
   ```

### 添加新的小组件

1. 在 `templates/widgets/` 创建 HTML 文件
2. 在 `app.py` 添加路由
3. 在配置中引用 `/widget/xxx`

## 📄 许可证

MIT License

## 🔗 相关链接

- [HIDRS 主项目](../README.md)
- [claude-code-web](https://github.com/vultuk/claude-code-web)
- [Claude Code 官方文档](https://claude.ai/code)
