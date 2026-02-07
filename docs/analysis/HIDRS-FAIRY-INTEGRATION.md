# HIDRS (XKeyscore) + FAIRY-DESK 集成方案

## 📊 HIDRS 系统概述

**HIDRS - 全息互联网动态实时搜索系统 (Holographic Internet Dynamic Real-time Search)**
- **别名**: XKeyscore (在项目文档中的代号)
- **功能**: 分布式网络爬虫、拓扑分析、全息搜索、决策反馈
- **技术栈**: Python + MongoDB + Kafka + Elasticsearch + NetworkX
- **架构**: 6层分布式架构

---

## 🏗️ HIDRS 六层架构

```
┌─────────────────────────────────────────────────────────┐
│ 6. 用户交互与展示层 (UserInterfaceLayer)                │
│    - Flask API Server (:5000)                           │
│    - 网页UI (Dashboard, Search, Network, Feedback)     │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 5. 实时搜索与决策反馈层 (RealtimeSearchLayer)           │
│    - 搜索引擎 (全息索引查询)                             │
│    - 决策反馈系统 (搜索结果优化)                         │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 4. 全息映射与索引构建层 (HolographicMappingLayer)       │
│    - 全息映射器 (局部拉普拉斯 → 全息表示)               │
│    - 全息索引 (向量索引与检索)                           │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 3. 网络拓扑构建与谱分析层 (NetworkTopologyLayer)        │
│    - 拓扑构建器 (节点关系图)                             │
│    - 拉普拉斯矩阵计算器                                   │
│    - 谱分析器 (Fiedler值异常检测)                       │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 2. 数据处理与特征抽取层 (DataProcessingLayer)           │
│    - 文本预处理 (分词、去停用词)                         │
│    - 特征提取器 (TF-IDF, Word2Vec)                      │
│    - 降维器 (PCA, t-SNE)                                │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 1. 数据采集与存储层 (DataAcquisitionLayer)              │
│    - 分布式爬虫 (多线程网页抓取)                         │
│    - 端口扫描器 (资产发现)                               │
│    - 数据管理器 (MongoDB/Elasticsearch存储)             │
└─────────────────────────────────────────────────────────┘
```

---

## 🔌 HIDRS API 端点

### 页面路由
- `GET /` - 主页
- `GET /dashboard` - 仪表板
- `GET /search` - 搜索页面
- `GET /network` - 网络拓扑可视化
- `GET /feedback` - 反馈页面

### API 端点
| 端点 | 方法 | 功能 | 参数 |
|------|------|------|------|
| `/api/search` | GET | 全息搜索 | `q` (查询), `limit` (数量), `cache` (缓存) |
| `/api/network/graph` | GET | 获取网络拓扑图 | `color_by` (着色方式) |
| `/api/network/metrics` | GET | 获取网络指标 | - |
| `/api/network/communities` | GET | 获取网络社区 | - |
| `/api/search/stats` | GET | 搜索统计 | - |
| `/api/feedback/recent` | GET | 最近反馈 | `limit` (数量) |
| `/api/metrics/plot` | GET | 指标图表 | - |

---

## 🔗 集成方案

### 方案 1️⃣: 左屏 Tab 嵌入（推荐 - 完整功能）

**优势**:
- 完整的 HIDRS 功能体验
- 网络拓扑可视化
- 实时搜索与反馈
- Fiedler 值异常检测

**实现步骤**:

#### 1. 在 `fairy-desk/config.json` 添加 HIDRS Tab:

```json
{
  "left_screen": {
    "tabs": [
      {
        "id": "hidrs-dashboard",
        "name": "HIDRS 仪表板",
        "icon": "📊",
        "url": "http://localhost:5000/dashboard",
        "loadStrategy": "background",
        "category": "search",
        "builtIn": false
      },
      {
        "id": "hidrs-search",
        "name": "全息搜索",
        "icon": "🔍",
        "url": "http://localhost:5000/search",
        "loadStrategy": "lazy",
        "category": "search",
        "builtIn": false
      },
      {
        "id": "hidrs-network",
        "name": "网络拓扑",
        "icon": "🕸️",
        "url": "http://localhost:5000/network",
        "loadStrategy": "lazy",
        "category": "security",
        "builtIn": false
      }
    ]
  }
}
```

#### 2. 启动 HIDRS 服务:

```bash
cd /home/user/hidrs/hidrs
docker-compose up -d

# 或手动启动
python main.py
```

#### 3. 访问:
- FAIRY-DESK 左屏选择 "HIDRS 仪表板"、"全息搜索" 或 "网络拓扑"

---

### 方案 2️⃣: 中屏快捷搜索小组件

**优势**:
- 快速搜索访问
- 不占用左屏空间
- 集成到控制台

**实现步骤**:

#### 1. 创建 HIDRS 搜索小组件 (`fairy-desk/templates/widgets/hidrs_search.html`):

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <link rel="icon" href="data:image/svg+xml,&lt;svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'&gt;&lt;text y='.9em' font-size='90'&gt;🔍&lt;/text&gt;&lt;/svg&gt;">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>HIDRS 快速搜索</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    
    body {
      background: #0a0e17;
      color: #e5e7eb;
      font-family: 'Segoe UI', sans-serif;
      padding: 20px;
    }
    
    .search-container {
      max-width: 800px;
      margin: 0 auto;
    }
    
    .search-box {
      position: relative;
      margin-bottom: 20px;
    }
    
    .search-input {
      width: 100%;
      padding: 12px 40px 12px 16px;
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
      position: absolute;
      right: 8px;
      top: 50%;
      transform: translateY(-50%);
      background: transparent;
      border: none;
      color: #00f0ff;
      font-size: 18px;
      cursor: pointer;
      padding: 4px 8px;
    }
    
    .stats {
      display: flex;
      gap: 16px;
      margin-bottom: 20px;
      font-size: 12px;
      color: #9ca3af;
    }
    
    .stat-item {
      padding: 8px 12px;
      background: rgba(0, 240, 255, 0.1);
      border-left: 3px solid #00f0ff;
      border-radius: 4px;
    }
    
    .results {
      max-height: 500px;
      overflow-y: auto;
    }
    
    .result-item {
      padding: 12px;
      margin-bottom: 12px;
      background: rgba(17, 24, 39, 0.9);
      border-left: 3px solid #00f0ff;
      border-radius: 6px;
      transition: all 0.2s;
    }
    
    .result-item:hover {
      background: rgba(0, 240, 255, 0.15);
      transform: translateX(4px);
    }
    
    .result-title {
      color: #00f0ff;
      font-weight: bold;
      margin-bottom: 6px;
    }
    
    .result-url {
      color: #6b7280;
      font-size: 11px;
      margin-bottom: 4px;
      word-break: break-all;
    }
    
    .result-score {
      display: inline-block;
      padding: 2px 8px;
      background: rgba(0, 240, 255, 0.2);
      border-radius: 4px;
      font-size: 10px;
      color: #00f0ff;
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
  </style>
</head>
<body>
  <div class="search-container">
    <div class="search-box">
      <input type="text" id="search-input" class="search-input" 
             placeholder="输入关键词进行全息搜索..." autofocus>
      <button class="search-btn" onclick="search()">🔍</button>
    </div>
    
    <div id="stats" class="stats" style="display: none;"></div>
    <div id="results" class="results"></div>
  </div>

  <script>
    const HIDRS_API = 'http://localhost:5000';
    
    // Enter键搜索
    document.getElementById('search-input').addEventListener('keyup', function(e) {
      if (e.key === 'Enter') search();
    });

    async function search() {
      const query = document.getElementById('search-input').value.trim();
      if (!query) return;
      
      const resultsDiv = document.getElementById('results');
      const statsDiv = document.getElementById('stats');
      
      // 显示加载状态
      resultsDiv.innerHTML = '<div class="loading"><div class="spinner"></div>搜索中...</div>';
      statsDiv.style.display = 'none';
      
      try {
        const response = await fetch(`${HIDRS_API}/api/search?q=${encodeURIComponent(query)}&limit=20`);
        const data = await response.json();
        
        if (data.results && data.results.length > 0) {
          displayResults(data.results);
          displayStats(data);
        } else {
          resultsDiv.innerHTML = '<div class="loading">未找到相关结果</div>';
        }
      } catch (error) {
        console.error('搜索失败:', error);
        resultsDiv.innerHTML = '<div class="loading" style="color: #ef4444;">⚠️ 搜索失败，请检查 HIDRS 服务是否运行</div>';
      }
    }
    
    function displayResults(results) {
      const resultsDiv = document.getElementById('results');
      resultsDiv.innerHTML = results.map(item => `
        <div class="result-item">
          <div class="result-title">${escapeHtml(item.title || item.url || 'Untitled')}</div>
          <div class="result-url">${escapeHtml(item.url || 'N/A')}</div>
          <span class="result-score">相关度: ${(item.score * 100).toFixed(1)}%</span>
        </div>
      `).join('');
    }
    
    function displayStats(data) {
      const statsDiv = document.getElementById('stats');
      statsDiv.style.display = 'flex';
      statsDiv.innerHTML = `
        <div class="stat-item">📊 结果数: ${data.results.length}</div>
        <div class="stat-item">⏱️ 耗时: ${data.search_time || 'N/A'}ms</div>
        <div class="stat-item">💾 缓存: ${data.cache_hit ? '命中' : '未命中'}</div>
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

#### 2. 在 `fairy-desk/app.py` 添加路由:

```python
@app.route('/widget/hidrs')
def widget_hidrs():
    """HIDRS 全息搜索小组件"""
    return render_template('widgets/hidrs_search.html')
```

#### 3. 在中屏添加小组件链接。

---

### 方案 3️⃣: API 代理集成（轻量级）

**优势**:
- FAIRY-DESK 直接调用 HIDRS API
- 无需额外前端
- 数据聚合展示

**实现步骤**:

#### 1. 在 `fairy-desk/app.py` 添加 HIDRS API 代理:

```python
# HIDRS API 代理
@app.route('/api/hidrs/search/<query>')
def hidrs_search(query):
    """代理 HIDRS 搜索请求"""
    try:
        hidrs_api = config.get('hidrs', {}).get('endpoint', 'http://localhost:5000')
        limit = request.args.get('limit', 10, type=int)
        
        response = requests.get(
            f"{hidrs_api}/api/search",
            params={'q': query, 'limit': limit},
            timeout=10
        )
        return jsonify(response.json())
    except Exception as e:
        logger.error(f"HIDRS 搜索失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/hidrs/network/metrics')
def hidrs_network_metrics():
    """代理 HIDRS 网络指标请求"""
    try:
        hidrs_api = config.get('hidrs', {}).get('endpoint', 'http://localhost:5000')
        response = requests.get(f"{hidrs_api}/api/network/metrics", timeout=10)
        return jsonify(response.json())
    except Exception as e:
        logger.error(f"HIDRS 网络指标获取失败: {e}")
        return jsonify({"error": str(e)}), 500
```

#### 2. 修改 `fairy-desk/config.json`:

```json
{
  "hidrs": {
    "enabled": true,
    "endpoint": "http://localhost:5000",
    "auto_detect": true,
    "check_interval": 30
  }
}
```

---

## 🚀 部署步骤

### 方式 A: Docker Compose（推荐）

```bash
cd /home/user/hidrs/hidrs

# 启动完整 HIDRS 栈
docker-compose up -d

# 检查服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

**服务列表**:
- Elasticsearch: :9200
- MongoDB: :27017
- Kafka: :9092
- HIDRS API: :5000

### 方式 B: 手动启动

```bash
cd /home/user/hidrs/hidrs

# 1. 启动依赖服务
# MongoDB
mongod --dbpath ./data/mongodb

# Elasticsearch
elasticsearch

# Kafka + Zookeeper
./kafka/bin/zookeeper-server-start.sh config/zookeeper.properties
./kafka/bin/kafka-server-start.sh config/server.properties

# 2. 启动 HIDRS
python main.py
```

---

## ⚙️ 配置说明

### HIDRS 配置 (`hidrs/config/system_config.json`):

```json
{
  "enabled_layers": [
    "data_acquisition",
    "data_processing",
    "network_topology",
    "holographic_mapping",
    "realtime_search",
    "user_interface"
  ],
  "ui_host": "0.0.0.0",
  "ui_port": 5000,
  "layer_start_delays": {
    "data_acquisition": 0,
    "data_processing": 2,
    "network_topology": 4,
    "holographic_mapping": 6,
    "realtime_search": 8,
    "user_interface": 10
  }
}
```

### FAIRY-DESK 配置 (`fairy-desk/config.json`):

```json
{
  "hidrs": {
    "enabled": true,
    "endpoint": "http://localhost:5000",
    "auto_detect": true,
    "check_interval": 30,
    "features": {
      "search": true,
      "network_analysis": true,
      "fiedler_monitoring": true
    }
  }
}
```

---

## 🔒 安全考虑

1. **内网部署** - HIDRS 和 FAIRY-DESK 应部署在内网
2. **访问控制** - 添加认证机制（Flask-Login、JWT）
3. **数据加密** - MongoDB 和 Elasticsearch 启用加密
4. **端口限制** - 使用防火墙限制端口访问
5. **日志审计** - 记录所有搜索和访问操作

### Nginx 反向代理示例:

```nginx
# HIDRS 反向代理
location /hidrs/ {
    auth_basic "Restricted Access";
    auth_basic_user_file /etc/nginx/.htpasswd;
    proxy_pass http://localhost:5000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

---

## 📊 功能对比

| 功能 | FAIRY-DESK | HIDRS (XKeyscore) | 集成效果 |
|------|-----------|-------------------|---------|
| **实时监控** | ✅ 系统/网络/日志 | ✅ 网络拓扑/Fiedler值 | 🌟 完整监控 |
| **搜索能力** | ❌ 无 | ✅ 全息搜索 | 🌟 增强搜索 |
| **数据可视化** | ✅ 股票/新闻 | ✅ 网络图/谱分析 | 🌟 多维可视化 |
| **告警系统** | ✅ 系统告警 | ✅ 拓扑异常检测 | 🌟 双重告警 |
| **数据采集** | ✅ RSS/Twitter | ✅ 网页爬虫/端口扫描 | 🌟 全面采集 |

---

## 🎯 推荐集成方案

**根据使用场景选择**:

1. **SOC 运营中心** → 方案1（左屏完整集成）+ 方案3（API聚合）
2. **威胁情报分析** → 方案1（网络拓扑）+ 方案2（快速搜索）
3. **日常监控** → 方案2（中屏小组件）+ 方案3（API代理）

**推荐实施顺序**:
1. 先启动 HIDRS 服务测试功能
2. 使用方案1 在左屏添加 HIDRS Tab
3. 根据需要添加方案2 的快速搜索小组件
4. 使用方案3 实现数据聚合和告警联动

---

## 📝 TODO

- [ ] 启动 HIDRS Docker Compose 服务
- [ ] 验证 HIDRS API 可访问性
- [ ] 选择集成方案
- [ ] 修改 FAIRY-DESK 配置
- [ ] 创建小组件（如需）
- [ ] 添加 API 代理（如需）
- [ ] 配置访问控制
- [ ] 测试集成效果
- [ ] 配置 Fiedler 值告警联动

---

## 🔗 相关链接

- HIDRS 主程序: `/home/user/hidrs/hidrs/main.py`
- HIDRS API 服务: `/home/user/hidrs/hidrs/user_interface/api_server.py`
- HIDRS 配置目录: `/home/user/hidrs/hidrs/config/`
- Docker Compose: `/home/user/hidrs/hidrs/docker-compose.yml`

