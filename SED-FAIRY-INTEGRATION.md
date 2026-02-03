# SED + FAIRY-DESK 集成方案

## 📊 SED 系统概述

**Social Engineering Database (社会工程数据库)**
- **功能**: 查询和分析泄露的用户凭证数据（用户名、邮箱、密码、密码哈希等）
- **技术栈**: Elasticsearch + Kibana + Logstash + Flask API + Vue.js
- **数据来源**: 各类数据泄露事件的记录

### 系统架构
```
┌─────────────────┐
│ Vue.js Frontend │ :8080
│   (搜索界面)     │
└────────┬────────┘
         │
┌────────▼────────┐
│   Flask API     │ :5000
│  /api/find/*    │
└────────┬────────┘
         │
┌────────▼────────┐
│ Elasticsearch   │ :9200
│   (数据存储)     │
└─────────────────┘
         │
┌────────▼────────┐
│    Kibana       │ :5601
│  (数据分析)      │
└─────────────────┘
```

### API 端点
- `GET /api/find/user/<username>` - 按用户名查询
- `GET /api/find/email/<email>` - 按邮箱查询
- `GET /api/find/password/<password>` - 按明文密码查询
- `GET /api/find/passwordHash/<hash>` - 按密码哈希查询
- `GET /api/find/source/<source>` - 按数据来源查询
- `GET /api/find/time/<time>` - 按时间查询
- `GET /api/find?q=<query>` - 通用查询
- `GET /api/analysis/<type>` - 数据统计分析
- `GET /api/stats` - 获取数据库统计信息

---

## 🔗 集成方案

### 方案一：左屏 Tab 嵌入（推荐）

**优势**：
- 完整的全屏体验
- 保留 SED 的所有功能
- 适合深度查询分析

**实现步骤**：

1. **在 fairy-desk/config.json 添加 Tab 配置**：
```json
{
  "left_screen": {
    "tabs": [
      {
        "id": "sed",
        "name": "数据查询",
        "icon": "🔍",
        "url": "http://localhost:8080",
        "loadStrategy": "lazy",
        "category": "security",
        "builtIn": false
      }
    ]
  }
}
```

2. **启动 SED 服务**：
```bash
cd sed
docker-compose up -d
```

3. **访问**：
- FAIRY-DESK 左屏选择"数据查询" Tab
- SED 前端: http://localhost:8080
- SED API: http://localhost:5000
- Kibana: http://localhost:5601

---

### 方案二：右屏搜索小组件

**优势**：
- 快速查询功能
- 不占用左屏空间
- 实时告警显示

**实现步骤**：

1. **创建 SED 搜索小组件** (`fairy-desk/templates/widgets/sed_search.html`)：
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>SED 快速查询</title>
  <style>
    body {
      background: #0a0e17;
      color: #e5e7eb;
      font-family: sans-serif;
      padding: 20px;
    }
    .search-box {
      margin-bottom: 20px;
    }
    input {
      width: 100%;
      padding: 10px;
      background: #1a1f2e;
      border: 1px solid #00f0ff;
      color: #e5e7eb;
      border-radius: 4px;
    }
    .results {
      max-height: 400px;
      overflow-y: auto;
    }
    .result-item {
      padding: 10px;
      margin-bottom: 10px;
      background: rgba(0, 240, 255, 0.1);
      border-left: 3px solid #00f0ff;
      border-radius: 4px;
    }
  </style>
</head>
<body>
  <div class="search-box">
    <input type="text" id="search-input" placeholder="输入邮箱、用户名或密码查询...">
  </div>
  <div id="results" class="results"></div>

  <script>
    const API_BASE = 'http://localhost:5000';
    
    document.getElementById('search-input').addEventListener('keyup', function(e) {
      if (e.key === 'Enter') {
        const query = this.value;
        searchSED(query);
      }
    });

    async function searchSED(query) {
      try {
        const response = await fetch(`${API_BASE}/api/find?q=${encodeURIComponent(query)}`);
        const result = await response.json();
        displayResults(result.data || []);
      } catch (error) {
        console.error('查询失败:', error);
      }
    }

    function displayResults(data) {
      const resultsDiv = document.getElementById('results');
      if (data.length === 0) {
        resultsDiv.innerHTML = '<p>未找到结果</p>';
        return;
      }
      
      resultsDiv.innerHTML = data.map(item => `
        <div class="result-item">
          <div><strong>用户:</strong> ${item.user || 'N/A'}</div>
          <div><strong>邮箱:</strong> ${item.email || 'N/A'}</div>
          <div><strong>来源:</strong> ${item.source || 'N/A'}</div>
          <div><strong>时间:</strong> ${item.time || 'N/A'}</div>
        </div>
      `).join('');
    }
  </script>
</body>
</html>
```

2. **在 fairy-desk/app.py 添加路由**：
```python
@app.route('/widget/sed')
def widget_sed():
    """SED 搜索小组件"""
    return render_template('widgets/sed_search.html')
```

3. **添加到右屏或中屏**。

---

### 方案三：API 集成（最轻量）

**优势**：
- 无需运行完整前端
- FAIRY-DESK 直接调用 API
- 自定义 UI

**实现步骤**：

1. **在 fairy-desk/app.py 添加 SED 代理 API**：
```python
@app.route('/api/sed/search/<query>')
def sed_search(query):
    """代理 SED 查询请求"""
    try:
        sed_api = 'http://localhost:5000'
        response = requests.get(f"{sed_api}/api/find?q={query}", timeout=10)
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

2. **在前端添加搜索功能**（可集成到右屏告警面板）。

---

## 🚀 部署步骤

### 1. 启动 SED 服务

```bash
cd /home/user/hidrs/sed

# 启动完整服务栈 (Elasticsearch + Kibana + API + Frontend)
docker-compose up -d

# 检查服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 2. 导入测试数据（可选）

```bash
# 准备数据文件（CSV、JSON或TXT格式）
# 格式示例：user,email,password,passwordHash,source,time

# 导入数据
cd /home/user/hidrs/sed
python import_all.py
```

### 3. 访问服务

- **SED 前端**: http://localhost:8080
- **SED API**: http://localhost:5000/api/stats
- **Kibana**: http://localhost:5601
- **Elasticsearch**: http://localhost:9200

### 4. 集成到 FAIRY-DESK

选择上述方案之一实施。

---

## ⚙️ 配置说明

### SED 环境变量 (.env)

```bash
# Elasticsearch 配置
ES_HOST=elasticsearch
ES_PORT=9200
ES_INDEX=socialdb

# 应用配置
DEBUG=True
HOST=0.0.0.0
PORT=5000
DATA_DIR=data
ERROR_LOG_FILE=logs/error.log

# Kibana 配置
KIBANA_URL=http://localhost:5601
```

### FAIRY-DESK 配置修改

修改 `fairy-desk/config.json`：

```json
{
  "sed": {
    "enabled": true,
    "api_endpoint": "http://localhost:5000",
    "frontend_url": "http://localhost:8080",
    "kibana_url": "http://localhost:5601"
  }
}
```

---

## 🔒 安全考虑

**警告**: SED 处理敏感的泄露数据，部署时需注意：

1. **仅内网访问** - 不要暴露到公网
2. **访问控制** - 添加认证机制（Elasticsearch Security、Nginx反向代理）
3. **数据加密** - 敏感字段加密存储
4. **日志审计** - 记录所有查询操作
5. **合规性** - 确保符合数据保护法规（GDPR、个人信息保护法等）

建议配置：
```nginx
# Nginx 反向代理 + 基础认证
location /sed/ {
    auth_basic "Restricted Access";
    auth_basic_user_file /etc/nginx/.htpasswd;
    proxy_pass http://localhost:8080/;
}
```

---

## 📊 数据格式

SED 支持的数据格式：

### CSV 格式
```csv
user,email,password,passwordHash,source,time
john,john@example.com,pass123,5f4dcc3b...,leak2023,2023-01-15
```

### JSON 格式
```json
{
  "user": "john",
  "email": "john@example.com",
  "password": "pass123",
  "passwordHash": "5f4dcc3b...",
  "source": "leak2023",
  "time": "2023-01-15"
}
```

### TXT 格式（引用模式）
```
user:email:password
john:john@example.com:pass123
```

---

## 🎯 推荐集成方案

**根据 FAIRY-DESK 的用途，推荐方案：**

1. **安全运营中心（SOC）** → 方案一（左屏完整集成）
2. **快速查询需求** → 方案二（右屏小组件）
3. **轻量级集成** → 方案三（API代理）

**建议实施顺序**：
1. 先启动 SED 服务测试功能
2. 使用方案一在左屏添加 Tab
3. 根据需要添加方案二的快速查询小组件
4. 配置安全访问控制

---

## 📝 TODO

- [ ] 启动 SED Docker 服务
- [ ] 导入测试数据验证功能
- [ ] 选择集成方案
- [ ] 修改 FAIRY-DESK 配置
- [ ] 添加访问控制（如需）
- [ ] 测试集成效果

