# GitHub XKeyscore 项目 + FAIRY-DESK 集成方案

## 🔍 GitHub XKeyscore 项目调研

### 主要项目对比

| 项目 | 技术栈 | 完成度 | 功能 | 推荐度 |
|------|--------|--------|------|--------|
| **AIOSINT/Xkeystroke** | Node.js (JS 71%, CSS 29%) | ✅ 成熟 | OSINT工具、数据抓取、API集成、文件扫描 | ⭐⭐⭐⭐⭐ |
| **mistih/XKeyScore** | Python | ❌ <1% | 大规模监控系统（构思阶段） | ⭐ |
| **osresearch/xkeyscore** | JavaScript | ✅ Beta | Twitter通知过滤工具 | ⭐⭐ |
| **dwiktor/xkeyscore** | 未知 | ❓ | XKeyscore源代码（文档缺失） | ⭐ |

---

## 🎯 推荐项目: AIOSINT/Xkeystroke

**GitHub**: https://github.com/AIOSINT/Xkeystroke

### 系统概述

**Xkeystroke** 是一个高级开源情报（OSINT）工具，受NSA XKeyscore能力启发，提供强大的Web界面，用于执行复杂的数据抓取和API利用，进行深度信息检索。

### 技术栈

```
Frontend: JavaScript (70.9%), CSS (28.8%), HTML (0.3%)
Backend:  Node.js (v14+), npm (v6+)
架构:     Client-Server 分离架构
协议:     RESTful API
```

### 核心功能

#### 1️⃣ Web界面
- 📊 可自定义仪表板
- 👥 多用户支持
- 🎨 主题选项

#### 2️⃣ 数据抓取
- 🌐 从各种来源检索信息
- 🔄 代理管理
- ⚡ 动态内容处理

#### 3️⃣ API集成
- 🔌 连接流行API
- 🛠️ 自定义端点支持

#### 4️⃣ 文件分析
- 🛡️ 恶意软件检测
- 📄 元数据提取

#### 5️⃣ 数据可视化
- 🕸️ 网络图生成
- 🔗 关系映射

#### 6️⃣ 安全层
- 🔐 用户认证
- 🔒 数据加密

#### 7️⃣ 团队协作
- 👨‍👩‍👧‍👦 共享访问
- 📊 集体数据分析

---

## 🔗 FAIRY-DESK 集成方案

### 方案 1️⃣: 左屏 Tab 嵌入（推荐）

**优势**:
- 完整的 Xkeystroke 功能体验
- OSINT 数据收集和分析
- 文件扫描和恶意软件检测
- 网络关系可视化

**实现步骤**:

#### 1. 安装并启动 Xkeystroke

```bash
# 克隆仓库
cd /home/user/hidrs
git clone https://github.com/AIOSINT/Xkeystroke.git
cd Xkeystroke

# 安装服务端依赖
cd server
npm install

# 安装客户端依赖
cd ..
npm install

# 启动应用
npm start
```

**访问地址**: http://localhost:3000

#### 2. 在 `fairy-desk/config.json` 添加 Tab

```json
{
  "left_screen": {
    "tabs": [
      {
        "id": "xkeystroke-dashboard",
        "name": "XKeystroke OSINT",
        "icon": "🔍",
        "url": "http://localhost:3000",
        "loadStrategy": "lazy",
        "category": "security",
        "builtIn": false
      }
    ]
  }
}
```

#### 3. 访问
- FAIRY-DESK 左屏选择 "XKeystroke OSINT" Tab

---

### 方案 2️⃣: 中屏 OSINT 快捷查询小组件

**优势**:
- 快速 OSINT 查询
- 不占用左屏空间
- 集成到控制台

**实现步骤**:

#### 1. 创建 Xkeystroke 查询小组件 (`fairy-desk/templates/widgets/xkeystroke.html`)

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <link rel="icon" href="data:image/svg+xml,&lt;svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'&gt;&lt;text y='.9em' font-size='90'&gt;🔍&lt;/text&gt;&lt;/svg&gt;">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>XKeystroke OSINT</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      background: #0a0e17;
      color: #e5e7eb;
      font-family: 'Segoe UI', sans-serif;
      padding: 20px;
    }

    .osint-container {
      max-width: 900px;
      margin: 0 auto;
    }

    .search-section {
      margin-bottom: 30px;
    }

    .search-header {
      font-size: 18px;
      color: #00f0ff;
      margin-bottom: 12px;
      font-weight: bold;
    }

    .search-tabs {
      display: flex;
      gap: 8px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }

    .tab-btn {
      padding: 8px 16px;
      background: rgba(0, 240, 255, 0.1);
      border: 1px solid #00f0ff;
      color: #00f0ff;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.3s;
      font-size: 13px;
    }

    .tab-btn:hover, .tab-btn.active {
      background: rgba(0, 240, 255, 0.25);
      box-shadow: 0 0 8px rgba(0, 240, 255, 0.4);
    }

    .search-input-group {
      display: flex;
      gap: 8px;
      margin-bottom: 20px;
    }

    .search-input {
      flex: 1;
      padding: 12px 16px;
      background: #1a1f2e;
      border: 2px solid #00f0ff;
      color: #e5e7eb;
      border-radius: 8px;
      font-size: 14px;
      transition: all 0.3s;
    }

    .search-input:focus {
      outline: none;
      box-shadow: 0 0 12px rgba(0, 240, 255, 0.4);
    }

    .search-btn {
      padding: 12px 24px;
      background: linear-gradient(135deg, #00f0ff, #0080ff);
      border: none;
      color: #fff;
      border-radius: 8px;
      cursor: pointer;
      font-weight: bold;
      transition: all 0.3s;
    }

    .search-btn:hover {
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(0, 240, 255, 0.5);
    }

    .results-section {
      margin-top: 20px;
    }

    .result-card {
      padding: 16px;
      margin-bottom: 12px;
      background: rgba(17, 24, 39, 0.9);
      border-left: 4px solid #00f0ff;
      border-radius: 8px;
      transition: all 0.2s;
    }

    .result-card:hover {
      background: rgba(0, 240, 255, 0.15);
      transform: translateX(4px);
    }

    .result-title {
      color: #00f0ff;
      font-weight: bold;
      margin-bottom: 8px;
      font-size: 15px;
    }

    .result-meta {
      display: flex;
      gap: 16px;
      font-size: 12px;
      color: #9ca3af;
      margin-bottom: 8px;
      flex-wrap: wrap;
    }

    .result-meta-item {
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .result-content {
      color: #d1d5db;
      font-size: 13px;
      line-height: 1.6;
    }

    .loading {
      text-align: center;
      padding: 40px;
      color: #9ca3af;
    }

    .spinner {
      border: 3px solid rgba(0, 240, 255, 0.2);
      border-top-color: #00f0ff;
      border-radius: 50%;
      width: 40px;
      height: 40px;
      margin: 0 auto 16px;
      animation: spin 1s linear infinite;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 12px;
      margin-bottom: 20px;
    }

    .stat-card {
      padding: 12px;
      background: rgba(0, 240, 255, 0.1);
      border-left: 3px solid #00f0ff;
      border-radius: 6px;
    }

    .stat-label {
      font-size: 11px;
      color: #9ca3af;
      margin-bottom: 4px;
    }

    .stat-value {
      font-size: 20px;
      color: #00f0ff;
      font-weight: bold;
    }
  </style>
</head>
<body>
  <div class="osint-container">
    <div class="search-section">
      <div class="search-header">🔍 XKeystroke OSINT 情报收集</div>

      <div class="search-tabs">
        <button class="tab-btn active" data-type="domain">🌐 域名查询</button>
        <button class="tab-btn" data-type="email">📧 邮箱查询</button>
        <button class="tab-btn" data-type="ip">🖥️ IP地址</button>
        <button class="tab-btn" data-type="phone">📱 手机号</button>
        <button class="tab-btn" data-type="username">👤 用户名</button>
        <button class="tab-btn" data-type="hash">🔐 哈希值</button>
      </div>

      <div class="search-input-group">
        <input type="text" id="osint-input" class="search-input"
               placeholder="输入域名、IP、邮箱、用户名等进行 OSINT 查询..." autofocus>
        <button class="search-btn" onclick="performOSINT()">搜索</button>
      </div>

      <div id="stats" class="stats-grid" style="display: none;"></div>
    </div>

    <div id="results" class="results-section"></div>
  </div>

  <script>
    const XKEYSTROKE_API = 'http://localhost:3000';
    let currentSearchType = 'domain';

    // Tab切换
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', function() {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        currentSearchType = this.dataset.type;
        updatePlaceholder();
      });
    });

    function updatePlaceholder() {
      const placeholders = {
        domain: '例如: example.com',
        email: '例如: user@example.com',
        ip: '例如: 8.8.8.8',
        phone: '例如: +86 138****1234',
        username: '例如: johndoe',
        hash: '例如: 5f4dcc3b5aa765d61d8327deb882cf99'
      };
      document.getElementById('osint-input').placeholder =
        `输入${currentSearchType}进行 OSINT 查询... ${placeholders[currentSearchType] || ''}`;
    }

    // Enter键搜索
    document.getElementById('osint-input').addEventListener('keyup', function(e) {
      if (e.key === 'Enter') performOSINT();
    });

    async function performOSINT() {
      const query = document.getElementById('osint-input').value.trim();
      if (!query) return;

      const resultsDiv = document.getElementById('results');
      const statsDiv = document.getElementById('stats');

      resultsDiv.innerHTML = '<div class="loading"><div class="spinner"></div>正在进行 OSINT 查询...</div>';
      statsDiv.style.display = 'none';

      try {
        // 注意: Xkeystroke 的实际 API 端点需要根据其文档调整
        // 这里是示例结构
        const response = await fetch(`${XKEYSTROKE_API}/api/osint/${currentSearchType}?q=${encodeURIComponent(query)}`);

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        if (data.results && data.results.length > 0) {
          displayResults(data.results);
          displayStats(data.stats);
        } else {
          resultsDiv.innerHTML = '<div class="loading">❌ 未找到相关情报</div>';
        }
      } catch (error) {
        console.error('OSINT查询失败:', error);
        resultsDiv.innerHTML = `
          <div class="loading" style="color: #ef4444;">
            ⚠️ 查询失败: ${error.message}<br>
            <small>请确保 Xkeystroke 服务正在运行 (http://localhost:3000)</small>
          </div>
        `;
      }
    }

    function displayResults(results) {
      const resultsDiv = document.getElementById('results');
      resultsDiv.innerHTML = results.map(item => `
        <div class="result-card">
          <div class="result-title">${escapeHtml(item.title || item.name || '未命名结果')}</div>
          <div class="result-meta">
            ${item.source ? `<div class="result-meta-item">📍 来源: ${escapeHtml(item.source)}</div>` : ''}
            ${item.timestamp ? `<div class="result-meta-item">🕐 时间: ${escapeHtml(item.timestamp)}</div>` : ''}
            ${item.confidence ? `<div class="result-meta-item">🎯 可信度: ${item.confidence}%</div>` : ''}
          </div>
          <div class="result-content">
            ${escapeHtml(item.description || item.content || JSON.stringify(item, null, 2))}
          </div>
        </div>
      `).join('');
    }

    function displayStats(stats) {
      if (!stats) return;

      const statsDiv = document.getElementById('stats');
      statsDiv.style.display = 'grid';
      statsDiv.innerHTML = `
        <div class="stat-card">
          <div class="stat-label">📊 结果数</div>
          <div class="stat-value">${stats.total || 0}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">⏱️ 查询时间</div>
          <div class="stat-value">${stats.queryTime || 'N/A'}ms</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">💾 数据源</div>
          <div class="stat-value">${stats.sources || 0}</div>
        </div>
      `;
    }

    function escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }
  </script>
</body>
</html>
```

#### 2. 在 `fairy-desk/app.py` 添加路由

```python
@app.route('/widget/xkeystroke')
def widget_xkeystroke():
    """XKeystroke OSINT 查询小组件"""
    return render_template('widgets/xkeystroke.html')
```

#### 3. 在中屏添加小组件链接

---

### 方案 3️⃣: API 代理集成（轻量级）

**优势**:
- FAIRY-DESK 直接调用 Xkeystroke API
- 无需额外前端
- 数据聚合展示

**实现步骤**:

#### 1. 在 `fairy-desk/app.py` 添加 Xkeystroke API 代理

```python
import requests

# XKeystroke API 代理
@app.route('/api/xkeystroke/osint/<query_type>/<query>')
def xkeystroke_osint(query_type, query):
    """代理 XKeystroke OSINT 查询请求"""
    try:
        xkeystroke_api = config.get('xkeystroke', {}).get('endpoint', 'http://localhost:3000')

        # 注意: 实际 API 端点需要根据 Xkeystroke 文档调整
        response = requests.get(
            f"{xkeystroke_api}/api/osint/{query_type}",
            params={'q': query},
            timeout=30
        )
        return jsonify(response.json())
    except Exception as e:
        logger.error(f"XKeystroke OSINT 查询失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/xkeystroke/scan/file', methods=['POST'])
def xkeystroke_file_scan():
    """代理 XKeystroke 文件扫描请求"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "未提供文件"}), 400

        file = request.files['file']
        xkeystroke_api = config.get('xkeystroke', {}).get('endpoint', 'http://localhost:3000')

        # 转发文件到 Xkeystroke
        files = {'file': (file.filename, file.stream, file.content_type)}
        response = requests.post(
            f"{xkeystroke_api}/api/scan/file",
            files=files,
            timeout=60
        )
        return jsonify(response.json())
    except Exception as e:
        logger.error(f"XKeystroke 文件扫描失败: {e}")
        return jsonify({"error": str(e)}), 500
```

#### 2. 修改 `fairy-desk/config.json`

```json
{
  "xkeystroke": {
    "enabled": true,
    "endpoint": "http://localhost:3000",
    "auto_detect": true,
    "check_interval": 60,
    "features": {
      "osint": true,
      "file_scan": true,
      "api_integration": true,
      "data_visualization": true
    }
  }
}
```

---

## 🚀 部署步骤

### 方式 A: Docker 部署（推荐）

**创建 Dockerfile** (`Xkeystroke/Dockerfile`)

```dockerfile
FROM node:14-alpine

WORKDIR /app

# 复制依赖文件
COPY package*.json ./
COPY server/package*.json ./server/

# 安装依赖
RUN npm install
RUN cd server && npm install

# 复制源代码
COPY . .

# 暴露端口
EXPOSE 3000

# 启动应用
CMD ["npm", "start"]
```

**创建 Docker Compose** (`Xkeystroke/docker-compose.yml`)

```yaml
version: '3.8'

services:
  xkeystroke:
    build: .
    container_name: xkeystroke
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
      - PORT=3000
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped
    networks:
      - fairy-network

networks:
  fairy-network:
    external: true
```

**启动服务**:

```bash
cd /home/user/hidrs/Xkeystroke
docker-compose up -d
```

### 方式 B: 手动启动

```bash
cd /home/user/hidrs/Xkeystroke

# 1. 安装服务端依赖
cd server
npm install

# 2. 安装客户端依赖
cd ..
npm install

# 3. 启动应用
npm start

# 应用运行在 http://localhost:3000
```

---

## ⚙️ 配置说明

### Xkeystroke 配置（如有配置文件）

根据项目结构，配置文件可能位于：
- `server/config.js`
- `.env`
- `config.json`

**示例配置**:

```json
{
  "server": {
    "port": 3000,
    "host": "0.0.0.0"
  },
  "security": {
    "enableAuth": true,
    "jwtSecret": "your-secret-key",
    "sessionTimeout": 3600
  },
  "osint": {
    "enabledSources": ["shodan", "virustotal", "whois", "dns"],
    "apiKeys": {
      "shodan": "YOUR_SHODAN_API_KEY",
      "virustotal": "YOUR_VT_API_KEY"
    }
  },
  "scanning": {
    "maxFileSize": 104857600,
    "allowedExtensions": ["*"]
  }
}
```

### FAIRY-DESK 配置修改

修改 `fairy-desk/config.json`:

```json
{
  "xkeystroke": {
    "enabled": true,
    "endpoint": "http://localhost:3000",
    "auto_detect": true,
    "check_interval": 60,
    "features": {
      "osint": true,
      "file_scan": true,
      "api_integration": true,
      "data_visualization": true
    },
    "osint_sources": {
      "shodan": true,
      "virustotal": true,
      "whois": true,
      "dns": true
    }
  }
}
```

---

## 🔒 安全考虑

1. **访问控制** - 启用 Xkeystroke 的用户认证
2. **API密钥管理** - 安全存储第三方 API 密钥（Shodan, VirusTotal等）
3. **内网部署** - Xkeystroke 不应暴露到公网
4. **HTTPS** - 生产环境使用 HTTPS
5. **日志审计** - 记录所有 OSINT 查询和文件扫描操作

### Nginx 反向代理示例

```nginx
# XKeystroke 反向代理
location /xkeystroke/ {
    auth_basic "Restricted Access";
    auth_basic_user_file /etc/nginx/.htpasswd;

    proxy_pass http://localhost:3000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # WebSocket 支持（如需）
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

---

## 📊 功能对比

| 功能 | FAIRY-DESK | Xkeystroke | HIDRS | SED | 集成效果 |
|------|-----------|------------|-------|-----|---------|
| **OSINT收集** | ❌ | ✅ 多源OSINT | ❌ | ❌ | 🌟 增强情报收集 |
| **文件扫描** | ❌ | ✅ 恶意软件检测 | ❌ | ❌ | 🌟 安全分析 |
| **数据可视化** | ✅ 股票/新闻 | ✅ 网络图/关系 | ✅ 拓扑图 | ❌ | 🌟 多维可视化 |
| **API集成** | ✅ RSS/Twitter | ✅ 多源API | ✅ 全息搜索 | ✅ ES查询 | 🌟 全面整合 |
| **告警系统** | ✅ 系统告警 | ❌ | ✅ 拓扑异常 | ❌ | 🌟 双重告警 |
| **团队协作** | ❌ | ✅ 多用户/共享 | ❌ | ❌ | 🌟 协作增强 |

---

## 🎯 推荐集成方案

**根据使用场景选择**:

1. **SOC 运营中心** → 方案1（左屏完整集成）+ 方案3（API聚合）
2. **威胁情报分析** → 方案1（OSINT全功能）+ 方案2（快速查询）
3. **安全研究** → 方案2（中屏小组件）+ 方案3（API代理）

**推荐实施顺序**:
1. 克隆并启动 Xkeystroke 服务测试功能
2. 使用方案1 在左屏添加 Xkeystroke Tab
3. 根据需要添加方案2 的 OSINT 快捷查询小组件
4. 使用方案3 实现数据聚合和告警联动
5. 配置 API 密钥（Shodan、VirusTotal等）

---

## 📝 TODO

- [ ] 克隆 Xkeystroke 仓库
- [ ] 安装依赖并启动服务
- [ ] 验证 Xkeystroke 功能可用性
- [ ] 选择集成方案
- [ ] 修改 FAIRY-DESK 配置
- [ ] 创建小组件（如需）
- [ ] 添加 API 代理（如需）
- [ ] 配置第三方 API 密钥
- [ ] 配置访问控制
- [ ] 测试集成效果

---

## 🔗 相关链接

### GitHub 项目
- **Xkeystroke 主仓库**: https://github.com/AIOSINT/Xkeystroke
- **AIOSINT 组织**: https://github.com/AIOSINT
- **其他 XKeyscore 项目**:
  - https://github.com/mistih/XKeyScore (Python, 早期阶段)
  - https://github.com/osresearch/xkeyscore (Twitter过滤工具)
  - https://github.com/dwiktor/xkeyscore (源代码档案)

### 参考资料
- **XKeyscore 维基百科**: https://en.wikipedia.org/wiki/XKeyscore
- **NSA 文档**: https://github.com/TransparencyToolkit/NSA-Data
- **The Intercept 报道**: https://theintercept.com/2015/07/01/nsas-google-worlds-private-communications/

---

## 💡 集成建议

### 完整安全运营平台架构

```
┌─────────────────────────────────────────────────────────────┐
│                    FAIRY-DESK 控制台                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  左屏                    中屏                    右屏         │
│  ┌──────────┐         ┌──────────┐         ┌──────────┐    │
│  │ HIDRS    │         │ 系统监控  │         │ 告警面板  │    │
│  │ 全息搜索  │         │ CPU/内存 │         │ RSS更新  │    │
│  ├──────────┤         │ 网络流量  │         │ 安全公告  │    │
│  │XKeystroke│         ├──────────┤         │ 服务健康  │    │
│  │ OSINT    │         │ 股票行情  │         ├──────────┤    │
│  ├──────────┤         │ 新闻聚合  │         │ Live2D   │    │
│  │ SED      │         ├──────────┤         │ 助手     │    │
│  │ 数据查询  │         │ Xkeystroke│         └──────────┘    │
│  │          │         │ 快捷查询  │                          │
│  └──────────┘         └──────────┘                          │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
        ┌─────────────────────────────────────┐
        │         后端服务层                   │
        ├─────────────────────────────────────┤
        │ HIDRS API (:5000)                   │
        │ Xkeystroke API (:3000)              │
        │ SED API (:5000)                     │
        │ FAIRY-DESK API (:5001)              │
        └─────────────────────────────────────┘
                            │
                            ▼
        ┌─────────────────────────────────────┐
        │         数据存储层                   │
        ├─────────────────────────────────────┤
        │ MongoDB (HIDRS)                     │
        │ Elasticsearch (HIDRS + SED)         │
        │ Files (FAIRY-DESK)                  │
        └─────────────────────────────────────┘
```

这个集成方案将把 Xkeystroke、HIDRS 和 SED 完整整合到 FAIRY-DESK 中，形成一个功能强大的安全运营和情报分析平台。

---

**许可证**: MIT License (Xkeystroke)
**最后更新**: 2026-02-03
