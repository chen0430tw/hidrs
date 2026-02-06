# HIDRS 联邦搜索系统

## 概述

基于HLIG（Holographic Laplacian Internet Graph）理论的联邦搜索系统，实现了分层架构和智能降级策略。

### 核心设计原则

1. **HIDRS Core（HLIG理论）是主搜索路径** - 这是船的龙骨
2. **外部源是降级层** - 这是应急方案，不是主体
3. **所有结果都经过HLIG重排序** - 保持HIDRS身份
4. **清晰的统计和监控** - 知道何时触发降级

### 忒修斯之船判断标准

- 核心路径使用HLIG理论 ✅ → 还是HIDRS
- 外部源只是数据补充 ✅ → 还是HIDRS
- 外部源替代核心功能 ❌ → 变成搜索聚合器

## 架构

```
用户查询
    ↓
HIDRS Core (HLIG)  ← Priority 1, 默认路径
    ↓ (失败时)
Google搜索         ← Priority 2, 降级层
    ↓ (失败时)
百度搜索           ← Priority 3, 降级层
    ↓ (失败时)
Internet Archive   ← Priority 4, 降级层
    ↓
HLIG重排序         ← 保持核心身份
    ↓
返回结果
```

## 组件说明

### 1. 基础适配器 (`base_adapter.py`)

定义搜索适配器的抽象基类和类型系统。

```python
from hidrs.federated_search import SearchAdapter, AdapterType

class MyAdapter(SearchAdapter):
    def __init__(self):
        super().__init__(
            name="My Adapter",
            adapter_type=AdapterType.FALLBACK,
            priority=5
        )

    def search(self, query: str, limit: int = 10, **kwargs):
        # 实现搜索逻辑
        return results
```

**适配器类型:**
- `AdapterType.CORE` - 核心适配器（HIDRS自己的索引）
- `AdapterType.FALLBACK` - 降级适配器（外部搜索源）
- `AdapterType.DATA` - 数据适配器（仅用于采集）

### 2. HIDRS核心适配器 (`hidrs_adapter.py`)

实现HLIG理论的核心搜索引擎。

**关键特性:**
- 使用Elasticsearch作为基础索引
- 应用Fiedler向量重排序（HLIG核心算法）
- 计算拉普拉斯矩阵和谱分析
- 融合Elasticsearch得分和Fiedler得分（7:3）

```python
from hidrs.federated_search import HIDRSAdapter

adapter = HIDRSAdapter(
    elasticsearch_host='localhost',
    elasticsearch_port=9200,
    index_name='hidrs_documents'
)

results = adapter.search("拉普拉斯矩阵", limit=10)
```

**HLIG重排序算法:**
1. 提取搜索结果的特征向量（使用sentence-transformers）
2. 构建相似度矩阵 W（余弦相似度）
3. 构建拉普拉斯矩阵 L = D - W
4. 计算Fiedler向量（第二小特征值对应的特征向量）
5. 使用Fiedler向量分量作为重要性得分
6. 融合原始得分：`final_score = 0.7 * fiedler_score + 0.3 * es_score`

### 3. 外部搜索适配器

#### Google搜索适配器 (`google_adapter.py`)

使用Google Custom Search API。

**配置要求:**
- Google Cloud Console创建API凭证
- 设置环境变量：
  - `GOOGLE_SEARCH_API_KEY`
  - `GOOGLE_SEARCH_ENGINE_ID`

**限制:**
- 免费额度：100次/天
- 单次最多返回10个结果

```python
from hidrs.federated_search import GoogleSearchAdapter

adapter = GoogleSearchAdapter(
    api_key="YOUR_API_KEY",
    search_engine_id="YOUR_SEARCH_ENGINE_ID"
)

results = adapter.search("HLIG theory", limit=5)
```

#### 百度搜索适配器 (`baidu_adapter.py`)

通过网页抓取实现（百度无公开API）。

**特性:**
- 使用BeautifulSoup解析HTML
- 模拟浏览器User-Agent
- 支持时间过滤（day/week/month/year）
- 需要注意反爬虫机制

```python
from hidrs.federated_search import BaiduSearchAdapter

adapter = BaiduSearchAdapter(use_api=False)
results = adapter.search("拉普拉斯矩阵", limit=10, time_filter='week')
```

#### Internet Archive适配器 (`archive_adapter.py`)

使用Archive.org API搜索历史文档。

**特性:**
- 无需API密钥
- 支持多种媒体类型（texts/movies/audio/software等）
- 支持Wayback Machine查询
- 基于下载次数的得分

```python
from hidrs.federated_search import ArchiveSearchAdapter

adapter = ArchiveSearchAdapter()
results = adapter.search("internet topology", limit=5, media_type='texts')

# Wayback Machine查询
archive_info = adapter.search_wayback("https://example.com")
```

### 4. 降级处理器 (`fallback_handler.py`)

实现分层降级策略。

**降级流程:**
1. 尝试核心适配器（Priority 1）
2. 如果核心失败或结果不足，按优先级尝试降级适配器
3. 返回第一个成功的结果，带有降级标记

```python
from hidrs.federated_search import FallbackHandler

handler = FallbackHandler(
    adapters=[hidrs_adapter, google_adapter, baidu_adapter],
    min_results_threshold=3,
    enable_cascade=True
)

result = handler.search("query", limit=10)
# result = {
#     'results': [...],
#     'source': 'core' or 'fallback',
#     'adapter_used': 'adapter_name',
#     'fallback_triggered': True/False
# }
```

### 5. 联邦搜索引擎 (`federated_engine.py`)

系统的核心协调器，负责保持HIDRS身份。

**关键功能:**
- 协调所有适配器
- 强制HLIG重排序（即使对外部结果）
- 监控系统身份纯度
- 提供忒修斯之船判断

```python
from hidrs.federated_search import FederatedSearchEngine

engine = FederatedSearchEngine(
    adapters=[hidrs_adapter, google_adapter, baidu_adapter, archive_adapter],
    min_results_threshold=3,
    enable_fallback=True,
    always_use_hlig=True  # 关键：保持HIDRS身份
)

# 执行搜索
result = engine.search("拉普拉斯矩阵", limit=10)

# 检查系统状态
status = engine.get_system_status()
print(status['identity_analysis']['judgment'])
```

**身份纯度计算:**
```python
identity_purity = (core_success_rate * 100) - (fallback_rate * 50)
```

**判断标准:**
- `≥ 90`: ✅ 纯粹的HIDRS - 核心路径主导
- `≥ 70`: ✅ HIDRS - 核心功能为主
- `≥ 50`: ⚠️ HIDRS - 降级较频繁，但保持HLIG核心
- `≥ 30`: ⚠️ 混合系统 - 身份模糊
- `< 30`: ❌ 搜索聚合器 - HIDRS身份已稀释

## 使用示例

### 基础使用

```python
from hidrs.federated_search import (
    HIDRSAdapter,
    GoogleSearchAdapter,
    BaiduSearchAdapter,
    ArchiveSearchAdapter,
    FederatedSearchEngine
)

# 初始化适配器
adapters = [
    HIDRSAdapter(elasticsearch_host='localhost'),  # Priority 1
    GoogleSearchAdapter(),                         # Priority 2
    BaiduSearchAdapter(),                          # Priority 3
    ArchiveSearchAdapter()                         # Priority 4
]

# 创建引擎
engine = FederatedSearchEngine(
    adapters=adapters,
    enable_fallback=True,
    always_use_hlig=True
)

# 执行搜索
result = engine.search("HLIG理论", limit=10)

# 显示结果
for item in result['results']:
    print(f"{item['title']} - {item['source']}")
    if item['metadata'].get('hlig_reranked'):
        print(f"  Fiedler得分: {item['metadata']['fiedler_score']:.4f}")
```

### 监控系统身份

```python
status = engine.get_system_status()

# 身份分析
identity = status['identity_analysis']
print(f"身份纯度: {identity['identity_purity']:.1f}/100")
print(f"仍是HIDRS: {identity['still_hidrs']}")
print(f"判断: {identity['judgment']}")

# 健康状态
health = status['health']
print(f"核心适配器: {health['core_adapter']}")
print(f"可用适配器: {health['available_adapters']}/{health['total_adapters']}")

# 统计信息
stats = health['stats']
print(f"核心成功率: {stats['core_success_rate']:.2%}")
print(f"降级率: {stats['fallback_rate']:.2%}")
```

### 完整演示

运行演示脚本：

```bash
# 设置环境变量（可选）
export GOOGLE_SEARCH_API_KEY="your_api_key"
export GOOGLE_SEARCH_ENGINE_ID="your_engine_id"

# 运行演示
python examples/federated_search_demo.py
```

演示内容：
1. 基础搜索 - 展示核心路径
2. 降级场景 - 模拟核心失败
3. 身份监控 - 显示系统状态
4. 适配器对比 - 比较不同适配器

## 配置文件

配置文件位于 `hidrs/config/federated_search_config.json`

**关键配置项:**

```json
{
  "core_adapter": {
    "enabled": true,
    "hlig": {
      "enable_rerank": true,
      "rerank_weight": {
        "fiedler": 0.7,
        "elasticsearch": 0.3
      }
    }
  },

  "federated_engine": {
    "min_results_threshold": 3,
    "enable_fallback": true,
    "always_use_hlig": true
  },

  "identity_monitoring": {
    "enabled": true,
    "purity_threshold": 50.0
  }
}
```

## 依赖

```bash
pip install elasticsearch
pip install sentence-transformers
pip install numpy
pip install scipy
pip install scikit-learn
pip install requests
pip install beautifulsoup4
```

## API参考

### SearchAdapter

基础适配器接口。

```python
class SearchAdapter(ABC):
    def __init__(self, name: str, adapter_type: AdapterType, priority: int)
    def search(self, query: str, limit: int = 10, **kwargs) -> List[Dict]
    def is_available(self) -> bool
    def is_core(self) -> bool
    def get_stats(self) -> Dict
```

### FederatedSearchEngine

联邦搜索引擎。

```python
class FederatedSearchEngine:
    def __init__(
        self,
        adapters: List[SearchAdapter],
        min_results_threshold: int = 3,
        enable_fallback: bool = True,
        always_use_hlig: bool = True
    )

    def search(self, query: str, limit: int = 10) -> Dict
    def get_system_status(self) -> Dict
    def health_check(self) -> bool
    def get_stats(self) -> Dict
```

### 搜索结果格式

```python
{
    'title': str,           # 标题
    'url': str,             # URL
    'snippet': str,         # 摘要
    'source': str,          # 来源（适配器名称）
    'timestamp': str,       # ISO 8601时间戳
    'score': float,         # 原始得分
    'final_score': float,   # 最终得分（如果应用了HLIG）
    'metadata': {
        'adapter': str,
        'adapter_type': str,
        'priority': int,
        'hlig_reranked': bool,           # 是否经过HLIG重排序
        'fiedler_score': float,          # Fiedler得分
        'fiedler_value': float,          # Fiedler值（λ₂）
        'original_score': float,         # 原始得分
        ...                              # 其他适配器特定字段
    }
}
```

## 性能优化

### 1. 缓存（TODO）

实现Redis缓存以减少重复查询：

```python
from redis import Redis

cache = Redis(host='localhost', port=6379)
# 集成到FederatedSearchEngine
```

### 2. FAISS向量索引（TODO）

使用FAISS加速向量相似度计算：

```python
import faiss

# 创建FAISS索引
index = faiss.IndexIVFFlat(d=384, nlist=100)
# 集成到HIDRSAdapter
```

### 3. 批量查询

```python
# 批量搜索多个查询
queries = ["query1", "query2", "query3"]
results = [engine.search(q) for q in queries]
```

## 测试

```bash
# 运行单元测试
pytest tests/test_federated_search.py

# 运行集成测试
pytest tests/test_federated_search_integration.py
```

## 常见问题

### Q1: 为什么要用HLIG重排序外部结果？

**A:** 这是保持HIDRS身份的关键。如果只是简单聚合外部结果，系统就变成了普通搜索聚合器。通过应用HLIG理论（Fiedler向量）重排序，我们确保所有结果都经过HIDRS的核心算法处理，从而保持系统的理论身份。

### Q2: 什么是忒修斯之船悖论？

**A:** 如果一艘船的所有部件都被替换了，它还是原来的船吗？在HIDRS中，如果主要使用外部搜索源而不是自己的索引，它还是HIDRS吗？我们通过以下方式解决：
- 始终应用HLIG重排序（理论不变）
- 监控身份纯度指标（量化判断）
- 核心路径优先（保持主体）

### Q3: 如何提高核心成功率？

**A:**
1. 增加HIDRS索引的文档数量
2. 优化Elasticsearch配置
3. 提高向量编码质量
4. 调整相似度阈值

### Q4: 降级太频繁怎么办？

**A:**
1. 检查核心适配器健康状态
2. 增加 `min_results_threshold` 阈值
3. 优化核心搜索算法
4. 考虑增加更多核心数据源

### Q5: Google API超出配额怎么办？

**A:**
1. 升级到付费计划
2. 调整降级优先级（使用百度或Archive优先）
3. 实现查询缓存
4. 实现速率限制

## 未来工作

1. **FAISS向量索引优化** - 加速相似度计算
2. **Redis缓存集成** - 减少重复查询
3. **ML重排序** - 使用cross-encoder模型
4. **分布式搜索** - 支持多节点部署
5. **实时更新** - 监听Kafka事件更新索引
6. **A/B测试框架** - 比较不同配置效果

## 参考文献

1. HLIG理论文档 - `/home/user/hidrs/docs/HLIG_theory.md`
2. 拉普拉斯矩阵与谱图理论
3. Fiedler向量与代数连通度
4. 联邦学习与分布式搜索

## 许可

MIT License

## 贡献

欢迎提交Issue和Pull Request！

---

**核心理念:**
> "所有的系统最后都会变成被稀释的系统滋养其他系统（软件生态）" - HIDRS设计哲学

HLIG理论可能会超越HIDRS系统本身，就像Unix哲学超越了Unix一样。重要的是保持理论的纯粹性和可传播性。
