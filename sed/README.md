# SED 数据安全平台

## Social Engineering Database Security Platform

基于 ELK 技术栈的数据安全分析平台，支持多主题切换、LLM辅助分析、插件系统。

> 整合了银狼数据安全平台 (Silver Wolf) 的功能，支持主题切换

---

## 功能特性

- **全文搜索** — 基于 Elasticsearch 的高性能 N-gram 搜索
- **数据分析** — 来源分布、时间线、邮箱域名统计等可视化
- **多格式导入** — 支持 TXT/CSV/SQL/XLS/MDB 等格式
- **号码归属地** — 手机号归属地、身份证地区解析
- **LLM分析** — 集成 LLM 进行聚类、模式分析、风险评估
- **插件系统** — 前后端统一的轻量级插件架构
- **主题切换** — 支持多套主题：
  - 银狼 (Silver Wolf) - 紫色 `#6A79E3`
  - SED 经典 - 蓝色 `#4b9cd3`
  - 赛博朋克 - 青/粉
  - 暗夜猎手 - 暗红
- **暗黑模式** — 完整的明暗主题切换

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue.js 2.x + Vuex + Vue Router + ECharts |
| 后端 | Python 3.9+ + Flask |
| 搜索 | Elasticsearch 7.15 |
| 管道 | Logstash 7.15 |
| 可视化 | Kibana 7.15 |
| 部署 | Docker + Docker Compose |

---

## 快速开始

### 环境要求

- Docker 20.10+
- Docker Compose 1.29+
- 4GB+ 内存
- 10GB+ 磁盘

### 启动服务

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 访问地址

| 服务 | 地址 |
|------|------|
| 前端界面 | http://localhost:8080 |
| 后端 API | http://localhost:5000 |
| Kibana | http://localhost:5601 |
| Elasticsearch | http://localhost:9200 |

---

## 项目结构

```
sed/
├── frontend/               # Vue.js 前端
│   ├── src/
│   │   ├── components/     # 组件 (Search, Analysis, Login...)
│   │   ├── views/          # 页面 (Home, Import, Tools, Admin)
│   │   ├── plugins/        # 前端插件系统
│   │   ├── router/         # 路由配置
│   │   ├── store/          # Vuex 状态 (含主题系统)
│   │   └── styles/         # 主题样式
│   └── Dockerfile
├── backend/                # Flask 后端
│   ├── api/                # API 路由
│   │   ├── tools/          # 工具 API (手机号/身份证)
│   │   ├── llm.py          # LLM 分析 API
│   │   └── ...
│   ├── plugins/            # 后端插件系统
│   ├── utils/              # ES客户端、数据处理器
│   ├── data/               # 归属地数据
│   └── Dockerfile
├── logstash/               # 数据管道配置
├── kibana/                 # Kibana 仪表盘
├── configs/                # 运行时配置
├── tools/                  # 数据处理工具
├── docker-compose.yml
├── install.sh
├── run.sh
└── uninstall.sh
```

---

## API 文档

### 搜索

```
GET /api/find/{field}/{value}?limit=10&skip=0
```

支持字段: `user`, `email`, `password`, `source`, `xtime`

### 分析

```
GET /api/analysis/{type}
```

类型: `source`, `xtime`, `suffix_email`, `create_time`

### 号码查询

```
POST /api/tools/mobile/lookup   # { "number": "13800138000" }
POST /api/tools/idcard/lookup   # { "number": "110101199001011234" }
```

### LLM 分析

```
POST /api/llm/analyze  # { "type": "risk_report", "data": "..." }
GET  /api/llm/templates
```

---

## 主题系统

在页面底部可以切换主题，支持：

1. **银狼 Silver Wolf** - 默认紫色主题
2. **SED 经典** - 原版蓝色主题
3. **赛博朋克** - 青色/粉色霓虹风
4. **暗夜猎手** - 深色暗红风格

每个主题都支持暗黑模式切换。

---

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MODE` | 运行模式 (local/remote) | local |
| `ES_HOST` | ES 主机 | elasticsearch |
| `ES_PORT` | ES 端口 | 9200 |
| `ES_INDEX` | 索引名 | socialdb |
| `LLM_API_KEY` | LLM API密钥 | - |
| `LLM_BASE_URL` | LLM API地址 | https://api.openai.com/v1 |

---

## 许可证

MIT License

---

> SED 数据安全平台 — 让数据安全分析更高效
