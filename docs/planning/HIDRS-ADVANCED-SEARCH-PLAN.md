# HIDRS高级搜索功能规划

**文档版本**: 1.0.0
**创建日期**: 2026-02-05
**参考**: NSA XKeyscore高级搜索界面

---

## 📸 XKeyscore高级搜索界面分析

从泄露截图中看到XKeyscore的高级搜索界面特点：

### 核心功能模块

```
┌─────────────────────────────────────────────────────┐
│     User Activity Possible Queries                  │
├─────────────────────────────────────────────────────┤
│                                                      │
│  Datetime:  [1 Day ▼]  Start: [2009-09-21][00:00]  │
│                        Stop:  [2009-09-22][00:00]  │
│                                                      │
│  Search For:   [username ▼]                         │
│  Search Value: [1234567890]                         │
│  Realm:        [facebook]                           │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### 设计特点

1. **时间范围选择**
   - 下拉菜单：快速选择（1 Day, 1 Week, 1 Month等）
   - 日期时间选择器：Start/Stop精确控制
   - 时间格式：YYYY-MM-DD HH:MM

2. **结构化字段搜索**
   - Search For: 下拉菜单选择字段类型
     - username（用户名）
     - email（邮箱）
     - IP address（IP地址）
     - phone number（电话号码）
     - domain（域名）
     - etc.
   - Search Value: 输入具体值
   - Realm: 限定搜索范围（facebook, netlog, twitter等）

3. **视觉设计**
   - 绿色背景区分查询区域
   - 清晰的字段标签（右对齐）
   - 简洁的表单布局

---

## 🔍 HIDRS当前搜索界面分析

### 当前实现（`hidrs/templates/search.html`）

```html
<!-- 搜索框 -->
<input type="text" id="search-input" class="form-control"
       placeholder="输入搜索关键词...">
<button class="btn btn-primary" id="search-button">搜索</button>

<!-- 缓存选项 -->
<input type="checkbox" id="use-cache" checked>
<label>使用缓存（更快的搜索结果）</label>
```

### 搜索结果显示

```html
<!-- 结果卡片 -->
<div class="result-item bg-light">
    <h5><a href="...">标题</a></h5>
    <p class="text-muted">URL</p>
    <span class="badge bg-info">相关度: XX%</span>
    <span class="badge bg-secondary">聚类: XX</span>
</div>
```

### 问题诊断

✅ **优点**:
- 简单易用
- 响应式设计
- 支持缓存

❌ **缺点**:
- **界面单调**: 只有一个搜索框和一个复选框
- **无高级筛选**: 不能按时间、平台、类型等维度过滤
- **结果简单**: 只显示标题、URL、相关度，无法一目了然看到关键信息
- **无可视化**: 缺少图表、时间线、地理分布等可视化
- **无预设查询**: 不支持保存常用查询、快速筛选器

---

## 💡 HIDRS高级搜索功能规划

### 阶段一：基础高级搜索（2-3天开发）

#### 1.1 时间范围筛选

```html
<!-- 快速时间选择 -->
<select id="time-range">
  <option value="1h">过去1小时</option>
  <option value="24h" selected>过去24小时</option>
  <option value="7d">过去7天</option>
  <option value="30d">过去30天</option>
  <option value="custom">自定义</option>
</select>

<!-- 自定义时间范围 -->
<div id="custom-time-range" style="display:none;">
  <input type="datetime-local" id="start-time">
  <input type="datetime-local" id="end-time">
</div>
```

**后端修改**:
```python
# hidrs/realtime_search/search_engine.py
def search(self, query_text=None, start_time=None, end_time=None, ...):
    # 在MongoDB查询中添加时间范围过滤
    query = {}
    if start_time:
        query['timestamp'] = {'$gte': start_time}
    if end_time:
        query['timestamp']['$lte'] = end_time
```

#### 1.2 结构化字段搜索

```html
<!-- 字段类型选择 -->
<div class="row">
  <div class="col-md-4">
    <label>搜索字段:</label>
    <select id="search-field">
      <option value="all">所有字段</option>
      <option value="title">标题</option>
      <option value="url">URL</option>
      <option value="content">内容</option>
      <option value="domain">域名</option>
      <option value="author">作者</option>
    </select>
  </div>
  <div class="col-md-8">
    <label>搜索值:</label>
    <input type="text" id="search-value" class="form-control">
  </div>
</div>

<!-- 平台/来源筛选 -->
<div class="row mt-3">
  <div class="col-md-12">
    <label>数据来源:</label>
    <div class="btn-group" role="group">
      <input type="checkbox" class="btn-check" id="source-wikipedia">
      <label class="btn btn-outline-primary" for="source-wikipedia">Wikipedia</label>

      <input type="checkbox" class="btn-check" id="source-zhihu">
      <label class="btn btn-outline-primary" for="source-zhihu">知乎</label>

      <input type="checkbox" class="btn-check" id="source-bilibili">
      <label class="btn btn-outline-primary" for="source-bilibili">Bilibili</label>

      <input type="checkbox" class="btn-check" id="source-github">
      <label class="btn btn-outline-primary" for="source-github">GitHub</label>

      <input type="checkbox" class="btn-check" id="source-arxiv">
      <label class="btn btn-outline-primary" for="source-arxiv">arXiv</label>
    </div>
  </div>
</div>
```

**后端修改**:
```python
def search(self, query_text=None, field=None, sources=None, ...):
    # 按字段搜索
    if field and field != 'all':
        # 使用text索引或正则表达式
        query[field] = {'$regex': query_text, '$options': 'i'}

    # 按来源筛选
    if sources:
        query['source'] = {'$in': sources}
```

#### 1.3 高级筛选器

```html
<!-- 展开/折叠高级选项 -->
<button class="btn btn-link" type="button" data-bs-toggle="collapse"
        data-bs-target="#advanced-filters">
  <i class="bi bi-filter"></i> 高级筛选
</button>

<div class="collapse" id="advanced-filters">
  <div class="card card-body">
    <!-- 文件类型筛选 -->
    <div class="mb-3">
      <label>文件类型:</label>
      <select id="file-type" multiple>
        <option value="html">HTML</option>
        <option value="pdf">PDF</option>
        <option value="doc">DOC/DOCX</option>
        <option value="md">Markdown</option>
        <option value="json">JSON</option>
      </select>
    </div>

    <!-- 语言筛选 -->
    <div class="mb-3">
      <label>语言:</label>
      <select id="language">
        <option value="all">所有语言</option>
        <option value="zh">中文</option>
        <option value="en">English</option>
        <option value="ar">العربية</option>
      </select>
    </div>

    <!-- 聚类筛选 -->
    <div class="mb-3">
      <label>聚类ID:</label>
      <input type="text" id="cluster-id" class="form-control"
             placeholder="留空表示所有聚类">
    </div>

    <!-- 相关度阈值 -->
    <div class="mb-3">
      <label>最低相关度: <span id="score-value">0.5</span></label>
      <input type="range" id="min-score" class="form-range"
             min="0" max="1" step="0.05" value="0.5">
    </div>
  </div>
</div>
```

---

### 阶段二：增强搜索结果展示（3-4天开发）

#### 2.1 卡片式结果展示（灵感来自Google）

```html
<!-- 丰富的结果卡片 -->
<div class="result-card shadow-sm mb-3">
  <!-- 标题栏 -->
  <div class="card-header d-flex justify-content-between">
    <div>
      <span class="badge bg-primary">Wikipedia</span>
      <span class="badge bg-info">聚类 #42</span>
      <span class="badge bg-success">相关度 87%</span>
    </div>
    <div class="text-muted small">
      <i class="bi bi-clock"></i> 2小时前
    </div>
  </div>

  <!-- 内容区 -->
  <div class="card-body">
    <h5 class="card-title">
      <a href="..." target="_blank">NSA XKeyscore Surveillance Program</a>
    </h5>
    <p class="card-text text-muted">
      https://en.wikipedia.org/wiki/XKeyscore
    </p>
    <p class="card-text">
      XKeyscore is a secret computer system used by the NSA for searching
      and analyzing global Internet data, which it collects continuously...
      <a href="#" class="text-primary">更多</a>
    </p>

    <!-- 元数据 -->
    <div class="metadata mt-3">
      <div class="row g-2">
        <div class="col-md-3">
          <small class="text-muted">作者:</small>
          <div>Multiple Contributors</div>
        </div>
        <div class="col-md-3">
          <small class="text-muted">发布时间:</small>
          <div>2013-07-31</div>
        </div>
        <div class="col-md-3">
          <small class="text-muted">关键词:</small>
          <div>
            <span class="badge badge-pill badge-secondary">NSA</span>
            <span class="badge badge-pill badge-secondary">surveillance</span>
          </div>
        </div>
        <div class="col-md-3">
          <small class="text-muted">语言:</small>
          <div>English</div>
        </div>
      </div>
    </div>
  </div>

  <!-- 操作按钮 -->
  <div class="card-footer bg-transparent">
    <button class="btn btn-sm btn-outline-primary">
      <i class="bi bi-eye"></i> 预览
    </button>
    <button class="btn btn-sm btn-outline-secondary">
      <i class="bi bi-bookmark"></i> 收藏
    </button>
    <button class="btn btn-sm btn-outline-info">
      <i class="bi bi-share"></i> 分享
    </button>
  </div>
</div>
```

#### 2.2 搜索结果统计面板

```html
<!-- 搜索结果概览 -->
<div class="search-stats card mb-4">
  <div class="card-body">
    <div class="row text-center">
      <div class="col-md-3">
        <h3 class="text-primary">1,234</h3>
        <p class="text-muted">总结果</p>
      </div>
      <div class="col-md-3">
        <h3 class="text-success">42</h3>
        <p class="text-muted">聚类数</p>
      </div>
      <div class="col-md-3">
        <h3 class="text-info">8</h3>
        <p class="text-muted">数据源</p>
      </div>
      <div class="col-md-3">
        <h3 class="text-warning">127ms</h3>
        <p class="text-muted">搜索时间</p>
      </div>
    </div>
  </div>
</div>
```

#### 2.3 可视化面板

```html
<!-- 搜索结果可视化 -->
<div class="visualization-panel">
  <!-- Tab导航 -->
  <ul class="nav nav-tabs" role="tablist">
    <li class="nav-item">
      <a class="nav-link active" data-bs-toggle="tab" href="#timeline">
        <i class="bi bi-graph-up"></i> 时间分布
      </a>
    </li>
    <li class="nav-item">
      <a class="nav-link" data-bs-toggle="tab" href="#sources">
        <i class="bi bi-pie-chart"></i> 来源分布
      </a>
    </li>
    <li class="nav-item">
      <a class="nav-link" data-bs-toggle="tab" href="#clusters">
        <i class="bi bi-diagram-3"></i> 聚类网络
      </a>
    </li>
  </ul>

  <!-- Tab内容 -->
  <div class="tab-content">
    <div id="timeline" class="tab-pane fade show active">
      <canvas id="timeline-chart"></canvas>
    </div>
    <div id="sources" class="tab-pane fade">
      <canvas id="sources-chart"></canvas>
    </div>
    <div id="clusters" class="tab-pane fade">
      <div id="cluster-network"></div>
    </div>
  </div>
</div>
```

---

### 阶段三：预设查询和保存（2-3天开发）

#### 3.1 常用查询模板

```html
<!-- 快速查询模板 -->
<div class="query-templates">
  <h6>常用查询:</h6>
  <div class="btn-group-vertical" role="group">
    <button class="btn btn-outline-secondary btn-sm"
            data-template="recent">最近24小时</button>
    <button class="btn btn-outline-secondary btn-sm"
            data-template="high-score">高相关度 (>0.8)</button>
    <button class="btn btn-outline-secondary btn-sm"
            data-template="tech">技术文档</button>
    <button class="btn btn-outline-secondary btn-sm"
            data-template="social">社交媒体</button>
  </div>
</div>
```

#### 3.2 保存自定义查询

```html
<!-- 保存查询对话框 -->
<button class="btn btn-success" data-bs-toggle="modal"
        data-bs-target="#save-query-modal">
  <i class="bi bi-save"></i> 保存查询
</button>

<div class="modal" id="save-query-modal">
  <div class="modal-dialog">
    <div class="modal-content">
      <div class="modal-header">
        <h5>保存查询</h5>
      </div>
      <div class="modal-body">
        <input type="text" class="form-control"
               placeholder="查询名称" id="query-name">
        <textarea class="form-control mt-2"
                  placeholder="描述（可选）" id="query-desc"></textarea>
      </div>
      <div class="modal-footer">
        <button class="btn btn-primary" id="save-query-btn">保存</button>
        <button class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
      </div>
    </div>
  </div>
</div>
```

**后端支持**:
```python
# 新增API: /api/saved-queries
@app.route('/api/saved-queries', methods=['GET', 'POST', 'DELETE'])
def manage_saved_queries():
    if request.method == 'POST':
        # 保存查询
        query_data = request.json
        saved_queries_collection.insert_one({
            'name': query_data['name'],
            'description': query_data.get('description'),
            'filters': query_data['filters'],
            'created_at': datetime.now(),
            'user_id': session.get('user_id')  # 如果有用户系统
        })
        return jsonify({'success': True})

    elif request.method == 'GET':
        # 获取保存的查询列表
        queries = list(saved_queries_collection.find())
        return jsonify(queries)

    elif request.method == 'DELETE':
        # 删除查询
        query_id = request.args.get('id')
        saved_queries_collection.delete_one({'_id': ObjectId(query_id)})
        return jsonify({'success': True})
```

---

### 阶段四：分析师工作台（3-5天开发）

#### 4.1 查询构建器（Query Builder）

灵感来自XKeyscore的Persona Session Collection查询构建器：

```html
<!-- 多条件查询构建器 -->
<div class="query-builder card">
  <div class="card-header">
    <h5><i class="bi bi-funnel"></i> 查询构建器</h5>
  </div>
  <div class="card-body">
    <!-- 条件组 -->
    <div id="query-conditions">
      <!-- 条件1 -->
      <div class="condition-row" data-condition-id="1">
        <div class="row mb-2">
          <div class="col-md-3">
            <select class="form-select" name="field">
              <option value="title">标题</option>
              <option value="url">URL</option>
              <option value="content">内容</option>
              <option value="author">作者</option>
              <option value="domain">域名</option>
            </select>
          </div>
          <div class="col-md-2">
            <select class="form-select" name="operator">
              <option value="contains">包含</option>
              <option value="equals">等于</option>
              <option value="not_contains">不包含</option>
              <option value="regex">正则表达式</option>
            </select>
          </div>
          <div class="col-md-5">
            <input type="text" class="form-control" name="value"
                   placeholder="搜索值">
          </div>
          <div class="col-md-2">
            <button class="btn btn-danger btn-sm" onclick="removeCondition(1)">
              <i class="bi bi-trash"></i> 删除
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 添加条件按钮 -->
    <div class="mt-3">
      <button class="btn btn-success btn-sm" onclick="addCondition()">
        <i class="bi bi-plus-circle"></i> 添加条件
      </button>
      <select class="form-select d-inline-block w-auto ms-2">
        <option value="AND">AND (且)</option>
        <option value="OR">OR (或)</option>
      </select>
    </div>

    <!-- 执行查询 -->
    <div class="mt-3">
      <button class="btn btn-primary" onclick="executeQuery()">
        <i class="bi bi-search"></i> 执行查询
      </button>
      <button class="btn btn-outline-secondary" onclick="clearQuery()">
        <i class="bi bi-x-circle"></i> 清空
      </button>
    </div>
  </div>
</div>
```

**后端API**:
```python
@app.route('/api/search/query-builder', methods=['POST'])
def query_builder_search():
    """查询构建器API"""
    query_data = request.json
    conditions = query_data['conditions']  # 条件列表
    logic = query_data.get('logic', 'AND')  # AND/OR

    # 构建MongoDB查询
    if logic == 'AND':
        mongo_query = {'$and': []}
        for cond in conditions:
            mongo_query['$and'].append(
                build_condition(cond['field'], cond['operator'], cond['value'])
            )
    else:  # OR
        mongo_query = {'$or': []}
        for cond in conditions:
            mongo_query['$or'].append(
                build_condition(cond['field'], cond['operator'], cond['value'])
            )

    # 执行查询
    results = search_engine.query_builder_search(mongo_query)
    return jsonify(results)
```

#### 4.2 分析师仪表板（Analyst Dashboard）

```html
<!-- 分析师工作台 -->
<div class="analyst-dashboard">
  <!-- 顶部统计栏 -->
  <div class="row mb-4">
    <div class="col-md-3">
      <div class="stat-card bg-primary text-white">
        <div class="stat-icon"><i class="bi bi-search"></i></div>
        <div class="stat-number">127</div>
        <div class="stat-label">今日查询次数</div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="stat-card bg-success text-white">
        <div class="stat-icon"><i class="bi bi-bookmark"></i></div>
        <div class="stat-number">42</div>
        <div class="stat-label">保存的查询</div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="stat-card bg-warning text-white">
        <div class="stat-icon"><i class="bi bi-graph-up"></i></div>
        <div class="stat-number">8,324</div>
        <div class="stat-label">索引文档总数</div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="stat-card bg-info text-white">
        <div class="stat-icon"><i class="bi bi-clock-history"></i></div>
        <div class="stat-number">23ms</div>
        <div class="stat-label">平均查询时间</div>
      </div>
    </div>
  </div>

  <!-- 快捷操作面板 -->
  <div class="row mb-4">
    <div class="col-md-12">
      <div class="card">
        <div class="card-header">
          <h5><i class="bi bi-lightning"></i> 快捷操作</h5>
        </div>
        <div class="card-body">
          <div class="btn-group" role="group">
            <button class="btn btn-outline-primary">
              <i class="bi bi-clock"></i> 最近1小时
            </button>
            <button class="btn btn-outline-primary">
              <i class="bi bi-fire"></i> 高相关度 (&gt;0.8)
            </button>
            <button class="btn btn-outline-primary">
              <i class="bi bi-globe"></i> Wikipedia
            </button>
            <button class="btn btn-outline-primary">
              <i class="bi bi-github"></i> GitHub
            </button>
            <button class="btn btn-outline-primary">
              <i class="bi bi-file-earmark-code"></i> 技术文档
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 查询历史 -->
  <div class="row">
    <div class="col-md-6">
      <div class="card">
        <div class="card-header">
          <h5><i class="bi bi-clock-history"></i> 最近查询</h5>
        </div>
        <div class="card-body">
          <ul class="list-group">
            <li class="list-group-item d-flex justify-content-between align-items-center">
              <div>
                <strong>XKeyscore surveillance</strong>
                <br>
                <small class="text-muted">
                  source=wikipedia, time&gt;24h
                </small>
              </div>
              <span class="badge bg-primary">127 结果</span>
            </li>
            <li class="list-group-item d-flex justify-content-between align-items-center">
              <div>
                <strong>NSA PRISM</strong>
                <br>
                <small class="text-muted">
                  all fields, time&gt;7d
                </small>
              </div>
              <span class="badge bg-primary">89 结果</span>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <div class="col-md-6">
      <div class="card">
        <div class="card-header">
          <h5><i class="bi bi-bookmark-star"></i> 保存的查询</h5>
        </div>
        <div class="card-body">
          <ul class="list-group">
            <li class="list-group-item d-flex justify-content-between align-items-center">
              <div>
                <strong>网络安全威胁监控</strong>
                <br>
                <small class="text-muted">
                  keywords: APT, malware, 0day
                </small>
              </div>
              <div>
                <button class="btn btn-sm btn-primary">
                  <i class="bi bi-play"></i> 运行
                </button>
                <button class="btn btn-sm btn-outline-secondary">
                  <i class="bi bi-pencil"></i>
                </button>
              </div>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</div>
```

#### 4.3 用户活动分析（User Activity Analysis）

灵感来自XKeyscore的User Activity Possible Queries：

```html
<!-- 用户活动分析面板 -->
<div class="user-activity-panel">
  <h4 class="text-center mb-4">
    <i class="bi bi-person-circle"></i> 用户活动分析
  </h4>

  <!-- 活动类型选择 -->
  <div class="row mb-3">
    <label class="col-md-3 field-label">活动类型:</label>
    <div class="col-md-9">
      <select class="form-select">
        <option>搜索活动 (Search Activity)</option>
        <option>浏览历史 (Browse History)</option>
        <option>文档访问 (Document Access)</option>
        <option>社交互动 (Social Interaction)</option>
      </select>
    </div>
  </div>

  <!-- 用户标识符 -->
  <div class="row mb-3">
    <label class="col-md-3 field-label">用户标识:</label>
    <div class="col-md-9">
      <div class="input-group">
        <select class="form-select" style="max-width: 200px;">
          <option>username</option>
          <option>email</option>
          <option>session_id</option>
          <option>ip_address</option>
        </select>
        <input type="text" class="form-control" placeholder="输入标识符">
      </div>
    </div>
  </div>

  <!-- 时间线可视化 -->
  <div class="row mt-4">
    <div class="col-md-12">
      <h6>活动时间线:</h6>
      <canvas id="activity-timeline-chart"></canvas>
    </div>
  </div>

  <!-- 活动详情表格 -->
  <div class="row mt-4">
    <div class="col-md-12">
      <table class="table table-striped">
        <thead>
          <tr>
            <th>时间</th>
            <th>活动类型</th>
            <th>目标</th>
            <th>来源IP</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody id="activity-details">
          <!-- 动态加载 -->
        </tbody>
      </table>
    </div>
  </div>
</div>
```

#### 4.4 聚类网络可视化（Cluster Network）

```html
<!-- 聚类关联分析 -->
<div class="cluster-analysis">
  <h5><i class="bi bi-diagram-3"></i> 聚类关联分析</h5>

  <!-- 聚类选择 -->
  <div class="mb-3">
    <label>选择聚类:</label>
    <select class="form-select" id="cluster-selector" multiple>
      <option value="42">聚类 #42 (NSA监控) - 127个文档</option>
      <option value="89">聚类 #89 (网络安全) - 89个文档</option>
      <option value="15">聚类 #15 (隐私保护) - 156个文档</option>
    </select>
  </div>

  <!-- 网络图 -->
  <div id="cluster-network-graph" style="height: 500px; border: 1px solid #ddd;">
    <!-- 使用D3.js或Cytoscape.js绘制网络图 -->
  </div>

  <!-- 聚类详情 -->
  <div class="mt-3">
    <h6>聚类 #42 详情:</h6>
    <ul>
      <li><strong>关键词:</strong> NSA, surveillance, XKeyscore, PRISM</li>
      <li><strong>文档数:</strong> 127</li>
      <li><strong>主要来源:</strong> Wikipedia (45%), 知乎 (30%), GitHub (25%)</li>
      <li><strong>相关聚类:</strong> #89 (网络安全), #15 (隐私保护)</li>
    </ul>
  </div>
</div>
```

#### 4.5 导出和报告生成

```html
<!-- 导出功能 -->
<div class="export-panel">
  <h5><i class="bi bi-file-earmark-arrow-down"></i> 导出和报告</h5>

  <div class="row">
    <div class="col-md-6">
      <label>导出格式:</label>
      <select class="form-select" id="export-format">
        <option value="json">JSON</option>
        <option value="csv">CSV</option>
        <option value="excel">Excel (XLSX)</option>
        <option value="pdf">PDF报告</option>
        <option value="html">HTML报告</option>
      </select>
    </div>
    <div class="col-md-6">
      <label>包含内容:</label>
      <div class="form-check">
        <input class="form-check-input" type="checkbox" id="export-results" checked>
        <label class="form-check-label">搜索结果</label>
      </div>
      <div class="form-check">
        <input class="form-check-input" type="checkbox" id="export-stats">
        <label class="form-check-label">统计图表</label>
      </div>
      <div class="form-check">
        <input class="form-check-input" type="checkbox" id="export-timeline">
        <label class="form-check-label">时间线分析</label>
      </div>
    </div>
  </div>

  <button class="btn btn-success mt-3" onclick="exportResults()">
    <i class="bi bi-download"></i> 导出
  </button>
</div>
```

**后端API**:
```python
@app.route('/api/export', methods=['POST'])
def export_results():
    """导出搜索结果"""
    data = request.json
    format_type = data['format']
    results = data['results']

    if format_type == 'json':
        return jsonify(results)
    elif format_type == 'csv':
        # 转换为CSV
        csv_data = convert_to_csv(results)
        return Response(csv_data, mimetype='text/csv',
                       headers={'Content-Disposition': 'attachment;filename=results.csv'})
    elif format_type == 'excel':
        # 转换为Excel
        excel_file = convert_to_excel(results)
        return send_file(excel_file, as_attachment=True)
    elif format_type == 'pdf':
        # 生成PDF报告
        pdf_file = generate_pdf_report(results)
        return send_file(pdf_file, as_attachment=True)
```

#### 4.6 协作和批注功能

```html
<!-- 结果批注 -->
<div class="result-annotation">
  <h6>分析师批注:</h6>
  <textarea class="form-control" rows="3"
            placeholder="添加你的分析和备注..."></textarea>

  <!-- 标签 -->
  <div class="mt-2">
    <label>标签:</label>
    <div class="btn-group" role="group">
      <button class="btn btn-sm btn-outline-primary">
        <i class="bi bi-tag"></i> 重要
      </button>
      <button class="btn btn-sm btn-outline-warning">
        <i class="bi bi-exclamation-triangle"></i> 需核实
      </button>
      <button class="btn btn-sm btn-outline-success">
        <i class="bi bi-check-circle"></i> 已确认
      </button>
      <button class="btn btn-sm btn-outline-danger">
        <i class="bi bi-x-circle"></i> 误报
      </button>
    </div>
  </div>

  <!-- 分享给团队 -->
  <div class="mt-2">
    <button class="btn btn-sm btn-outline-secondary">
      <i class="bi bi-share"></i> 分享给团队
    </button>
  </div>
</div>
```

---

### 阶段五：XKeyscore风格界面（1-2天美化）

#### 5.1 绿色主题配色

```css
/* XKeyscore风格配色 */
:root {
  --xks-green: #90EE90;
  --xks-dark-green: #228B22;
  --xks-bg: #F0F8F0;
  --xks-border: #32CD32;
}

.advanced-search-panel {
  background: var(--xks-green);
  border: 2px solid var(--xks-border);
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}

.field-label {
  font-weight: bold;
  text-align: right;
  padding-right: 10px;
  color: #000;
}

.search-input {
  border: 1px solid #666;
  padding: 8px;
  font-family: monospace;
}
```

#### 5.2 专业UI布局

```html
<!-- XKeyscore风格的高级搜索面板 -->
<div class="advanced-search-panel">
  <h4 class="text-center mb-4">全息搜索 - 高级查询</h4>

  <!-- 时间范围 -->
  <div class="row mb-3 align-items-center">
    <label class="col-md-3 field-label">时间范围:</label>
    <div class="col-md-2">
      <select class="form-select search-input">
        <option>1小时</option>
        <option selected>1天</option>
        <option>7天</option>
        <option>30天</option>
        <option>自定义</option>
      </select>
    </div>
    <label class="col-md-1 field-label text-center">起:</label>
    <div class="col-md-2">
      <input type="date" class="form-control search-input">
    </div>
    <div class="col-md-2">
      <input type="time" class="form-control search-input">
    </div>
    <label class="col-md-1 field-label text-center">止:</label>
    <div class="col-md-2">
      <input type="date" class="form-control search-input">
    </div>
    <div class="col-md-2">
      <input type="time" class="form-control search-input">
    </div>
  </div>

  <!-- 搜索字段 -->
  <div class="row mb-3 align-items-center">
    <label class="col-md-3 field-label">搜索字段:</label>
    <div class="col-md-9">
      <select class="form-select search-input">
        <option>title - 标题</option>
        <option>url - URL地址</option>
        <option>content - 内容</option>
        <option>author - 作者</option>
        <option>domain - 域名</option>
      </select>
    </div>
  </div>

  <!-- 搜索值 -->
  <div class="row mb-3 align-items-center">
    <label class="col-md-3 field-label">搜索值:</label>
    <div class="col-md-9">
      <input type="text" class="form-control search-input"
             placeholder="输入搜索关键词...">
    </div>
  </div>

  <!-- 数据来源 -->
  <div class="row mb-3 align-items-center">
    <label class="col-md-3 field-label">数据来源:</label>
    <div class="col-md-9">
      <select class="form-select search-input">
        <option>all - 所有来源</option>
        <option>wikipedia - 维基百科</option>
        <option>zhihu - 知乎</option>
        <option>bilibili - 哔哩哔哩</option>
        <option>github - GitHub</option>
        <option>arxiv - arXiv</option>
      </select>
    </div>
  </div>

  <!-- 搜索按钮 -->
  <div class="row">
    <div class="col-md-12 text-center">
      <button class="btn btn-dark btn-lg px-5">
        <i class="bi bi-search"></i> 执行搜索
      </button>
      <button class="btn btn-outline-dark btn-lg px-5 ms-2">
        <i class="bi bi-arrow-clockwise"></i> 重置
      </button>
    </div>
  </div>
</div>
```

---

## 🆚 HIDRS vs Google 核心区别

### 数据来源

| 对比维度 | Google | HIDRS |
|---------|--------|-------|
| **数据范围** | 整个公开互联网 | 特定平台爬取数据 |
| **索引方式** | 主动爬虫 + PageRank | 主动爬虫 + 全息映射 |
| **数据新鲜度** | 秒级-分钟级 | 小时级-天级 |
| **数据深度** | 表层内容 | 深度结构化数据 |

### 搜索算法

| 对比维度 | Google | HIDRS |
|---------|--------|-------|
| **核心算法** | PageRank + BERT + 机器学习 | 拉普拉斯谱分析 + 全息映射 |
| **排序依据** | 权威性 + 相关性 + 用户行为 | 全息相似度 + 聚类分析 |
| **个性化** | 基于用户画像 | 基于查询历史（可选） |
| **广告** | ✅ 竞价广告 | ❌ 无广告 |

### 功能特性

| 功能 | Google | HIDRS |
|------|--------|-------|
| **搜索速度** | 🏆 毫秒级 | 秒级（可优化） |
| **结果数量** | 🏆 数十亿 | 数万-数十万（取决于爬取） |
| **垂直搜索** | 🏆 图片/视频/新闻/地图/学术... | ⚠️ 需开发 |
| **知识图谱** | 🏆 丰富的卡片式结果 | ❌ 无 |
| **实时性** | 🏆 实时新闻 | ⚠️ 爬虫延迟 |
| **高级筛选** | 🏆 时间/地区/语言/类型 | ⚠️ 待开发（本文档规划） |
| **聚类分析** | ❌ 无 | ✅ **独特优势** |
| **全息映射** | ❌ 无 | ✅ **独特优势** |
| **决策反馈** | ❌ 无 | ✅ **独特优势** |
| **隐私保护** | ⚠️ 收集大量用户数据 | ✅ 本地部署，无跟踪 |
| **定制化** | ❌ 无法定制 | ✅ **开源，完全可定制** |

### HIDRS的独特优势

1. **全息映射技术**
   - Google: 传统向量空间模型
   - HIDRS: 拉普拉斯谱分析 + 全息投影
   - **优势**: 捕获高维语义关系，发现隐藏模式

2. **聚类分析**
   - Google: 无自动聚类
   - HIDRS: 自动将结果分组到语义聚类
   - **优势**: 快速发现主题和关联内容

3. **决策反馈系统**
   - Google: 无反馈机制
   - HIDRS: 用户可以标记结果质量，系统自动优化
   - **优势**: 持续学习，提升搜索质量

4. **隐私和控制**
   - Google: 中心化服务，收集用户数据
   - HIDRS: 本地部署，完全控制数据
   - **优势**: 企业/政府/研究机构的首选

5. **定制化和扩展性**
   - Google: 黑盒，无法定制
   - HIDRS: 开源，可以修改算法、添加数据源
   - **优势**: 满足特殊需求（例如内网搜索、专业领域）

### HIDRS的应用场景（Google不适用）

1. **企业内网搜索**
   - Google无法索引内网
   - HIDRS可以部署在内网，索引企业文档

2. **专业研究**
   - Google结果太泛化
   - HIDRS可以只爬取arXiv、PubMed等专业数据源

3. **情报分析**
   - Google无聚类和关联分析
   - HIDRS的全息映射可以发现隐藏联系

4. **隐私敏感场景**
   - Google会记录搜索历史
   - HIDRS本地部署，无跟踪

5. **定制化需求**
   - Google算法固定
   - HIDRS可以修改排序算法、添加自定义指标

---

## 📋 开发任务清单

### Phase 1: 基础高级搜索（优先级：高）

- [ ] **时间范围筛选**
  - [ ] 前端：添加时间选择器组件
  - [ ] 后端：修改search API支持start_time/end_time参数
  - [ ] 测试：验证时间过滤准确性

- [ ] **字段搜索**
  - [ ] 前端：添加字段类型下拉菜单
  - [ ] 后端：支持按title/url/content/author搜索
  - [ ] 测试：各字段搜索准确性

- [ ] **来源筛选**
  - [ ] 前端：添加来源多选按钮组
  - [ ] 后端：支持sources参数过滤
  - [ ] 测试：多来源组合筛选

### Phase 2: 结果展示增强（优先级：高）

- [ ] **卡片式结果**
  - [ ] 前端：重新设计result-item卡片
  - [ ] 添加元数据展示（作者、时间、关键词）
  - [ ] 添加操作按钮（预览、收藏、分享）

- [ ] **搜索统计**
  - [ ] 前端：添加统计面板组件
  - [ ] 后端：返回聚合统计数据
  - [ ] 显示总数、聚类数、来源数、搜索时间

- [ ] **可视化**
  - [ ] 集成Chart.js绘制时间分布柱状图
  - [ ] 绘制来源分布饼图
  - [ ] 绘制聚类网络图（D3.js）

### Phase 3: 预设查询（优先级：中）

- [ ] **查询模板**
  - [ ] 前端：添加常用查询按钮
  - [ ] 实现模板一键加载

- [ ] **保存查询**
  - [ ] 前端：保存查询对话框
  - [ ] 后端：新增/api/saved-queries端点
  - [ ] 实现查询CRUD操作

### Phase 4: 分析师工作台（优先级：高）⭐

- [ ] **查询构建器 (Query Builder)**
  - [ ] 前端：多条件动态添加/删除界面
  - [ ] 支持AND/OR逻辑组合
  - [ ] 后端：/api/search/query-builder端点
  - [ ] MongoDB复合查询构建

- [ ] **分析师仪表板**
  - [ ] 统计卡片（今日查询/保存查询/文档总数/平均时间）
  - [ ] 快捷操作面板（常用筛选器）
  - [ ] 查询历史列表（显示参数和结果数）
  - [ ] 保存的查询管理

- [ ] **用户活动分析**
  - [ ] 活动类型选择（搜索/浏览/文档访问/社交）
  - [ ] 用户标识符查询（username/email/session_id/IP）
  - [ ] 活动时间线可视化（Chart.js）
  - [ ] 活动详情表格

- [ ] **聚类网络可视化**
  - [ ] 聚类选择器（多选）
  - [ ] 网络图绘制（D3.js或Cytoscape.js）
  - [ ] 聚类详情展示（关键词/文档数/来源分布）
  - [ ] 关联聚类推荐

- [ ] **导出和报告生成**
  - [ ] 多格式支持（JSON/CSV/Excel/PDF/HTML）
  - [ ] 自定义导出内容（结果/图表/时间线）
  - [ ] PDF报告模板设计
  - [ ] Excel自动格式化

- [ ] **协作和批注**
  - [ ] 结果批注功能
  - [ ] 标签系统（重要/需核实/已确认/误报）
  - [ ] 团队分享功能
  - [ ] 批注历史记录

### Phase 5: XKeyscore风格界面（优先级：低）

- [ ] **绿色主题**
  - [ ] 设计XKeyscore风格的CSS
  - [ ] 实现可切换的主题系统

- [ ] **专业布局**
  - [ ] 重新设计高级搜索面板
  - [ ] 优化表单对齐和间距

---

## 🎨 UI设计mockup（文本版）

### 搜索页面整体布局

```
┌─────────────────────────────────────────────────────────────┐
│                      全息搜索系统                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [展开高级搜索 ▼]                                            │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  🟢 高级搜索面板                                       │ │
│  │                                                         │ │
│  │  时间范围: [1天 ▼]  起: [2026-02-05][00:00]           │ │
│  │                     止: [2026-02-06][00:00]           │ │
│  │                                                         │ │
│  │  搜索字段: [title - 标题 ▼]                           │ │
│  │  搜索值:   [XKeyscore                              ]   │ │
│  │  数据来源: [wikipedia ▼]                              │ │
│  │                                                         │ │
│  │             [🔍 执行搜索]  [🔄 重置]                   │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  📊 搜索统计                                           │ │
│  │  总结果: 1,234  聚类: 42  来源: 8  用时: 127ms        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  [时间分布] [来源分布] [聚类网络]                           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  📈 [柱状图：按时间分布的结果数量]                      │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ───────────────────────  搜索结果  ────────────────────────│
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ [Wikipedia] [聚类 #42] [相关度 87%]      2小时前       │ │
│  │                                                         │ │
│  │ 📄 NSA XKeyscore Surveillance Program                  │ │
│  │ 🔗 https://en.wikipedia.org/wiki/XKeyscore             │ │
│  │                                                         │ │
│  │ XKeyscore is a secret computer system used by the NSA  │ │
│  │ for searching and analyzing global Internet data...    │ │
│  │                                                         │ │
│  │ 作者: Multiple | 时间: 2013-07-31 | 语言: English      │ │
│  │ 标签: [NSA] [surveillance] [XKeyscore]                 │ │
│  │                                                         │ │
│  │ [👁️ 预览] [⭐ 收藏] [📤 分享]                           │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ [知乎] [聚类 #42] [相关度 82%]           5小时前        │ │
│  │ ...                                                     │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  [上一页] [1] [2] [3] [4] [5] [下一页]                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 技术实现细节

### 前端技术栈

- **框架**: Vanilla JavaScript (保持轻量)
- **UI库**: Bootstrap 5（已有）
- **图表**: Chart.js（时间线、饼图）
- **网络图**: D3.js或Cytoscape.js（聚类可视化）
- **日期选择**: Bootstrap Datepicker或原生datetime-local
- **状态管理**: 简单的对象存储（暂无需Redux等）

### 后端API扩展

```python
# hidrs/main.py 或新增 search_api.py

@app.route('/api/search/advanced', methods=['GET'])
def advanced_search():
    """高级搜索API"""
    # 获取参数
    query_text = request.args.get('q')
    field = request.args.get('field', 'all')
    sources = request.args.getlist('sources')  # 多选
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    min_score = float(request.args.get('min_score', 0.0))
    cluster_id = request.args.get('cluster_id')
    language = request.args.get('language')
    limit = int(request.args.get('limit', 20))

    # 构建查询
    results = search_engine.advanced_search(
        query_text=query_text,
        field=field,
        sources=sources,
        start_time=start_time,
        end_time=end_time,
        min_score=min_score,
        cluster_id=cluster_id,
        language=language,
        limit=limit
    )

    # 返回结果 + 统计
    return jsonify({
        'results': results,
        'stats': {
            'total': len(results),
            'clusters': len(set(r['cluster_id'] for r in results)),
            'sources': len(set(r['source'] for r in results)),
            'search_time_ms': results[0]['search_time_ms']
        }
    })

@app.route('/api/search/stats', methods=['GET'])
def search_stats():
    """获取搜索结果的统计数据（用于可视化）"""
    query_text = request.args.get('q')

    # 执行搜索
    results = search_engine.search(query_text, limit=1000)

    # 时间分布（按小时聚合）
    time_distribution = {}
    for r in results:
        hour = r['timestamp'].strftime('%Y-%m-%d %H:00')
        time_distribution[hour] = time_distribution.get(hour, 0) + 1

    # 来源分布
    source_distribution = {}
    for r in results:
        source = r['source']
        source_distribution[source] = source_distribution.get(source, 0) + 1

    # 聚类分布
    cluster_distribution = {}
    for r in results:
        cluster = r['cluster_id']
        cluster_distribution[cluster] = cluster_distribution.get(cluster, 0) + 1

    return jsonify({
        'time_distribution': time_distribution,
        'source_distribution': source_distribution,
        'cluster_distribution': cluster_distribution
    })
```

### MongoDB索引优化

```javascript
// 为高级搜索添加复合索引
db.holographic_data.createIndex({
  "source": 1,
  "timestamp": -1,
  "cluster_id": 1
})

// 全文索引（如果使用MongoDB全文搜索）
db.holographic_data.createIndex({
  "title": "text",
  "content": "text",
  "author": "text"
}, {
  weights: {
    title: 10,
    content: 5,
    author: 3
  },
  name: "full_text_search"
})
```

---

## 💡 总结与建议

### 立即可做（1周内）

1. **基础时间筛选**: 添加时间下拉菜单和日期选择器
2. **来源筛选**: 添加来源多选按钮
3. **卡片式结果**: 美化结果展示，添加元数据

### 中期目标（2-4周）

1. **可视化面板**: 集成Chart.js，显示时间/来源分布
2. **保存查询**: 实现查询保存和加载功能
3. **字段搜索**: 支持按title/url/content等字段搜索

### 长期愿景（1-3月）

1. **XKeyscore风格主题**: 完整的绿色主题UI
2. **高级筛选**: 文件类型、语言、聚类等多维筛选
3. **预设查询库**: 内置常用查询模板

### HIDRS vs Google 定位

**HIDRS不是要替代Google**，而是提供一个：
- 🎯 **专注于特定领域的搜索引擎**（可定制数据源）
- 🔐 **注重隐私的本地搜索方案**（企业/内网）
- 🧠 **具有高级分析能力的研究工具**（聚类、全息映射）
- 🛠️ **开源可定制的搜索平台**（满足特殊需求）

### 关键优势

1. **全息映射技术**（Google没有）
2. **聚类分析**（Google没有）
3. **决策反馈系统**（Google没有）
4. **完全可定制**（Google黑盒）
5. **隐私保护**（Google收集数据）

---

**文档版本**: 1.0.0
**最后更新**: 2026-02-05
**作者**: HIDRS Team
**参考**: NSA XKeyscore GUI截图 + Google搜索界面

https://claude.ai/code/session_017KHwuf6oyC7DjAqMXfFGK4
