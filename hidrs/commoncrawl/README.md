# HIDRS Common Crawl 数据接入系统

## 🎯 功能概述

将HIDRS与Common Crawl集成，实现类XKeyscore的大规模历史网页搜索和分析功能。

**核心能力**：
- 📦 流式处理PB级WARC数据（无需完整下载）
- 🔍 搜索30-50亿网页的历史快照
- 🧠 集成HLIG拉普拉斯谱分析
- 💾 MongoDB流式导入（批量优化）
- 🎨 类XKeyscore高级查询界面

## 🆚 与XKeyscore对比

| 功能 | XKeyscore | HIDRS + Common Crawl |
|------|-----------|---------------------|
| 数据来源 | 实时流量拦截（非法） | 公开网页快照（合法） |
| 数据规模 | 20 TB/天 | 100 TB/月 |
| 历史数据 | 3-5天 | **永久存储** |
| 搜索功能 | ✅ | ✅ |
| 聚类分析 | 基础 | **HLIG增强** |
| 语义检索 | ❌ | **✅** |
| 合法性 | ⚠️ 有争议 | **✅ 完全合法** |

## 📚 架构设计

```
┌─────────────────────────────────────────────────────┐
│              用户查询界面 (Web UI)                      │
│         (类似XKeyscore的高级搜索界面)                   │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│          HIDRS 查询引擎 + 分析师工作台                  │
│  • 拉普拉斯谱分析                                       │
│  • 全息映射检索                                         │
│  • Query Builder (多条件查询)                          │
│  • 聚类分析                                            │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│         MongoDB / Elasticsearch 集群                 │
│  • 索引层：URL、域名、时间、关键词                       │
│  • 全文搜索：标题、内容、元数据                          │
│  • 向量嵌入：语义检索                                   │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│      Common Crawl 数据仓库 (50+ PB)                   │
│  • WARC文件存储 (Amazon S3)                           │
│  • 每月快照：2024-01, 2024-02, ...                    │
│  • 全球30-50亿网页                                     │
└─────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 1. 安装依赖

```bash
# 安装Common Crawl相关库
pip install warcio comcrawl boto3

# 安装MongoDB
docker run -d -p 27017:27017 --name mongodb mongo

# 安装其他依赖
pip install -r hidrs/requirements.txt
```

### 2. 基本使用

#### 搜索索引

```python
from hidrs.commoncrawl import CommonCrawlIndexClient

# 创建客户端
client = CommonCrawlIndexClient()

# 搜索Wikipedia相关页面
results = client.search(
    url_pattern='*.wikipedia.org/*',
    limit=100,
    filter_status=[200],
)

print(f"找到 {len(results)} 个结果")
for result in results:
    print(f"{result['url']} - {result['timestamp']}")
```

#### 流式解析WARC

```python
from hidrs.commoncrawl import WARCStreamParser

# 创建解析器
parser = WARCStreamParser()

# 流式处理WARC文件（无需完整下载）
warc_url = "https://data.commoncrawl.org/crawl-data/..."

for record in parser.stream_warc(warc_url):
    print(f"URL: {record['url']}")
    print(f"标题: {record['title']}")
    print(f"文本: {record['text'][:100]}...")
```

#### 导入数据到MongoDB

```python
from hidrs.commoncrawl import CommonCrawlImporter

# 创建导入器
importer = CommonCrawlImporter(
    mongo_uri='mongodb://localhost:27017/',
    database='hidrs_commoncrawl',
    batch_size=1000,
    enable_hlig_analysis=True,  # 启用HLIG分析
)

# 导入数据
stats = importer.import_from_url_pattern(
    url_pattern='*.example.com/*',
    limit=10000,
)

print(f"导入完成: {stats['inserted']} 条记录")
```

#### 高级查询

```python
from hidrs.commoncrawl import CommonCrawlQueryEngine

# 创建查询引擎
engine = CommonCrawlQueryEngine(
    mongo_uri='mongodb://localhost:27017/',
    database='hidrs_commoncrawl',
)

# 高级多条件查询（类XKeyscore）
results = engine.advanced_search(
    keywords=["网络攻击", "APT"],
    domain="*.gov.cn",
    from_date="2024-01-01",
    to_date="2024-12-31",
    status_codes=[200],
    limit=1000
)

print(f"找到 {len(results)} 条结果")

# 聚类分析
clusters = engine.cluster_results(results, n_clusters=5)
print(f"识别出 {len(clusters['clusters'])} 个簇")

# 时间线分析
timeline = engine.get_timeline({}, interval='day')
for point in timeline[:10]:
    print(f"{point['timestamp']}: {point['count']} 条记录")
```

## 📊 完整演示

运行完整演示程序：

```bash
python examples/commoncrawl_demo.py
```

演示包括：
1. ✅ 搜索Common Crawl索引
2. ✅ 流式解析WARC文件
3. ✅ 导入数据到MongoDB
4. ✅ 高级多条件查询
5. ✅ 聚类分析（HLIG）
6. ✅ 完整工作流（威胁情报收集）

## 🔧 核心组件

### 1. WARCStreamParser - 流式WARC解析器

**功能**：
- 流式读取WARC文件（无需完整下载）
- 自动解压gzip格式
- HTML解析（BeautifulSoup）
- 文本提取、链接提取
- 多线程批量处理

**优化**：
- 增量解析（每次只加载一个record）
- 自动重试机制
- 内存占用控制

### 2. CommonCrawlIndexClient - 索引搜索客户端

**功能**：
- 搜索Common Crawl CDX索引
- 多备用接口（comcrawl / CDX API / boto3）
- 自动降级策略
- 时间范围筛选
- 状态码过滤

**接口优先级**：
1. comcrawl（推荐，最简单）
2. CDX API（备用，无依赖）
3. boto3 S3直连（大规模处理）

### 3. CommonCrawlImporter - 数据导入器

**功能**：
- MongoDB流式导入
- 批量写入优化（batch_size=1000）
- 异步写入队列
- 重复数据去重
- HLIG拉普拉斯分析集成
- 自动关键词提取

**性能**：
- 批量upsert操作
- 多线程并发
- 进度追踪

### 4. CommonCrawlQueryEngine - 查询引擎

**功能**：
- 多条件复合查询
- 全文搜索（MongoDB text index）
- 时间范围筛选
- 域名/TLD筛选
- 聚类分析（HLIG）
- 时间线趋势分析
- 域名统计

**查询能力**：
- URL精确匹配/通配符
- 关键词AND/OR逻辑
- HTTP状态码过滤
- Content-Type过滤
- 地理位置（TLD）

## 💡 实际应用场景

### 1. 开源情报收集 (OSINT)

```python
# 追踪APT组织C2服务器历史
results = engine.advanced_search(
    domain="*.suspicious-domain.com",
    from_date="2023-01-01",
    to_date="2024-12-31",
)

# 提取IOC
unique_ips = set(r.get('server_ip') for r in results if r.get('server_ip'))
print(f"发现 {len(unique_ips)} 个唯一IP")
```

### 2. 品牌监控

```python
# 发现山寨网站
results = engine.search("假冒品牌", limit=1000)
clusters = engine.cluster_results(results)

# 按域名分组
for cluster in clusters['clusters']:
    print(f"域名: {cluster['domain']}, 数量: {cluster['size']}")
```

### 3. 学术研究

```python
# 互联网考古学：研究网页内容变迁
timeline = engine.get_timeline(
    query={'domain': 'archive.org'},
    interval='month'
)

# 分析趋势
for point in timeline:
    print(f"{point['timestamp']}: {point['count']} 次快照")
```

### 4. 安全研究

```python
# 发现暴露的敏感信息
results = engine.advanced_search(
    keywords=["password", "api_key", "secret"],
    content_types=["text/plain", "application/json"],
    limit=5000
)

# 分析泄露模式
for result in results:
    if "password" in result['text']:
        print(f"⚠️ 潜在密码泄露: {result['url']}")
```

## 🎨 类XKeyscore查询示例

### 基础查询

```python
# 查找.gov.cn域名中包含"网络攻击"的页面
results = engine.advanced_search(
    keywords=["网络攻击"],
    tld=".gov.cn",
    status_codes=[200],
)
```

### 复杂查询

```python
# 查找2024年1-3月间，GitHub上所有包含"漏洞"字样的issue页面
results = engine.advanced_search(
    keywords=["漏洞", "vulnerability"],
    url="https://github.com/*/issues/*",
    from_date="2024-01-01",
    to_date="2024-03-31",
    status_codes=[200],
    limit=5000
)
```

### 时间线分析

```python
# 分析某个话题的热度趋势
timeline = engine.get_timeline(
    query={'keywords': {'$regex': '人工智能'}},
    interval='month'
)

# 绘制趋势图
import matplotlib.pyplot as plt
dates = [p['timestamp'] for p in timeline]
counts = [p['count'] for p in timeline]
plt.plot(dates, counts)
plt.title('人工智能话题热度趋势')
plt.show()
```

## 💰 成本估算

### 小规模测试（10万网页）

```
数据量: ~10 GB
MongoDB存储: $0.25/GB/月 = $2.5/月
计算资源: 可忽略
总成本: ~$5/月
```

### 中等规模（100万网页）

```
数据量: ~100 GB
MongoDB存储: $25/月
Elasticsearch: $50/月
计算资源: $20/月
总成本: ~$100/月
```

### 大规模（1000万网页）

```
数据量: ~1 TB
MongoDB Atlas (M200): $2,000/月
Elasticsearch (m5.4xlarge): $800/月
计算资源: $200/月
总成本: ~$3,000/月
```

### 超大规模（1亿网页+）

```
数据量: ~10 TB
MongoDB Atlas (M400 Cluster): $6,500/月
Elasticsearch (m5.12xlarge × 3): $5,000/月
计算资源: $1,000/月
总成本: ~$12,500/月
```

## ⚠️ 注意事项

### 数据隐私

✅ **完全合法**：
- Common Crawl数据是公开的
- 所有网页均为公开可访问
- 遵守robots.txt规范

⚠️ **使用限制**：
- 不得用于侵犯隐私
- 不得用于非法目的
- 遵守本地法律法规

### 技术限制

- **数据延迟**：每月更新1次，最新数据有1个月延迟
- **覆盖不完整**：某些网站禁止爬取
- **需要登录的内容**：无法获取
- **动态加载**：JavaScript渲染的内容可能丢失

### 性能优化

1. **MongoDB索引**：确保创建合适的索引
2. **批量操作**：使用bulk_write而非单条插入
3. **流式处理**：避免一次性加载大文件
4. **分片集群**：大规模数据使用MongoDB分片

## 📖 参考资料

### Common Crawl

- 官网: https://commoncrawl.org/
- 数据下载: https://data.commoncrawl.org/
- WARC格式: https://iipc.github.io/warc-specifications/

### Python库

- warcio: https://github.com/webrecorder/warcio
- comcrawl: https://pypi.org/project/comcrawl/
- cc-pyspark: https://github.com/commoncrawl/cc-pyspark

### HIDRS相关

- HLIG理论: `/home/user/hidrs/CLAUDE.md`
- XKeyscore对比: `/home/user/hidrs/XKEYSCORE-VS-XKEYSTROKE.md`
- 可行性分析: `/home/user/hidrs/HIDRS-COMMONCRAWL-XKEYSCORE-ANALYSIS.md`

## 🤝 贡献

欢迎提交Issue和Pull Request！

## 📄 许可证

MIT License

---

**版本**: 1.0.0
**作者**: HIDRS Team
**创建日期**: 2026-02-06
