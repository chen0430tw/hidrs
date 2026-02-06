# HIDRS HLIG (Holographic Laplacian Internet Graph) 统一库

## 🎯 概述

HLIG是HIDRS的核心理论基础，将网络结构的拉普拉斯谱分析与全息映射相结合，实现高效的文档向量化、相似度计算和聚类分析。

**核心理论**：
- **拉普拉斯矩阵**: L = D - W（度矩阵 - 邻接矩阵）
- **Fiedler向量**: λ₂对应的特征向量（图的代数连通性）
- **全息映射**: 局部拉普拉斯矩阵 → 全局全息表示
- **谱聚类**: 利用拉普拉斯矩阵的前k个特征向量进行聚类

## 📦 组件

### 1. HLIGAnalyzer - 核心分析器

统一接口，整合所有HLIG功能。

```python
from hidrs.hlig import HLIGAnalyzer

analyzer = HLIGAnalyzer(
    output_dim=256,
    normalized_laplacian=True,
    enable_holographic_mapping=True,
)

# 单文档向量化
vector = analyzer.compute_document_vector(text, method='tfidf')

# 批量向量化
vectors = analyzer.compute_batch_vectors(texts, method='laplacian')

# 提取关键词
keywords = analyzer.extract_keywords(text, top_n=10)

# 计算相似度
similarity = analyzer.compute_similarity(vector1, vector2, metric='cosine')
```

### 2. TextVectorizer - 文本向量化器

支持多种向量化方法。

```python
from hidrs.hlig import TextVectorizer

vectorizer = TextVectorizer(output_dim=256)

# TF-IDF向量化
vector = vectorizer.vectorize_tfidf(text)

# 批量向量化
vectors = vectorizer.vectorize_batch(texts, method='tfidf')

# 分词
tokens = vectorizer.tokenize(text)

# 提取关键词
keywords = vectorizer.extract_keywords(text, top_n=10)
```

### 3. SpectralClustering - 谱聚类

基于拉普拉斯谱的文档聚类。

```python
from hidrs.hlig import SpectralClustering

clustering = SpectralClustering(
    n_clusters=5,
    normalized=True,
    affinity='rbf',
)

# 训练聚类
labels = clustering.fit_predict(document_vectors)

# 获取聚类摘要
summary = clustering.get_cluster_summary(texts=texts, top_n=5)

# 获取Fiedler向量
fiedler_vector = clustering.get_fiedler_vector()
```

## 🔧 向量化方法

### 1. TF-IDF (推荐)

```python
vector = analyzer.compute_document_vector(text, method='tfidf')
```

**优点**：
- 快速（无需预训练模型）
- 效果好（捕捉关键词）
- 支持批量处理

**适用场景**：
- 关键词搜索
- 文档分类
- 相似度匹配

### 2. Laplacian Vector

```python
vector = analyzer.compute_document_vector(text, method='laplacian')
```

**原理**：
1. 构建词共现图
2. 计算拉普拉斯矩阵
3. 提取Fiedler向量

**优点**：
- 捕捉词之间的结构关系
- 保留图的拓扑信息

**适用场景**：
- 主题发现
- 语义分析
- 关系抽取

### 3. Holographic Vector

```python
vector = analyzer.compute_document_vector(text, method='holographic')
```

**原理**：
1. 计算局部拉普拉斯矩阵
2. 使用全息映射器映射到全局表示

**优点**：
- 局部信息 → 全局表示
- 保留多尺度特征

**适用场景**：
- 全局视角的文档分析
- 跨文档关联发现

### 4. Embedding (待完善)

```python
vector = analyzer.compute_document_vector(text, method='embedding')
```

**说明**: 当前使用TF-IDF备用，完整的词嵌入需要集成预训练模型（Word2Vec/BERT）。

## 📊 完整示例

### 示例1: 文档聚类

```python
from hidrs.hlig import HLIGAnalyzer, SpectralClustering

# 准备文档
documents = [
    "Machine learning is a subset of artificial intelligence",
    "Deep learning uses neural networks",
    "Python is a programming language",
    "JavaScript is used for web development",
    "Natural language processing analyzes text data",
]

# 1. 向量化文档
analyzer = HLIGAnalyzer(output_dim=128)
vectors = analyzer.compute_batch_vectors(documents, method='tfidf')

print(f"向量化完成: {vectors.shape}")

# 2. 谱聚类
clustering = SpectralClustering(n_clusters=2)
labels = clustering.fit_predict(vectors)

print(f"聚类标签: {labels}")

# 3. 查看聚类结果
summary = clustering.get_cluster_summary(texts=documents)

for cluster in summary:
    print(f"\n簇 {cluster['id']} ({cluster['size']} 个文档):")
    for text in cluster['sample_texts']:
        print(f"  - {text}")
```

### 示例2: 文档相似度搜索

```python
from hidrs.hlig import HLIGAnalyzer

# 准备查询和文档库
query = "What is machine learning?"
corpus = [
    "Machine learning is a branch of AI",
    "Python programming for data science",
    "Deep learning with neural networks",
    "Web development with React",
]

# 向量化
analyzer = HLIGAnalyzer()
query_vector = analyzer.compute_document_vector(query, method='tfidf')
corpus_vectors = analyzer.compute_batch_vectors(corpus, method='tfidf')

# 计算相似度
similarities = []
for i, doc_vector in enumerate(corpus_vectors):
    sim = analyzer.compute_similarity(query_vector, doc_vector, metric='cosine')
    similarities.append((i, sim))

# 排序
similarities.sort(key=lambda x: x[1], reverse=True)

# 输出Top 3
print(f"查询: {query}\n")
print("最相关的文档:")
for rank, (idx, score) in enumerate(similarities[:3], 1):
    print(f"{rank}. [{score:.3f}] {corpus[idx]}")
```

### 示例3: 关键词提取

```python
from hidrs.hlig import HLIGAnalyzer

text = """
Machine learning is a method of data analysis that automates
analytical model building. It is a branch of artificial intelligence
based on the idea that systems can learn from data, identify patterns
and make decisions with minimal human intervention.
"""

analyzer = HLIGAnalyzer()
keywords = analyzer.extract_keywords(text, top_n=10)

print("关键词:")
for keyword in keywords:
    print(f"  - {keyword}")
```

## 🔗 集成到Common Crawl

```python
from hidrs.commoncrawl import CommonCrawlImporter
from hidrs.hlig import HLIGAnalyzer

# 创建导入器（启用HLIG分析）
importer = CommonCrawlImporter(
    mongo_uri='mongodb://localhost:27017/',
    database='hidrs_commoncrawl',
    enable_hlig_analysis=True,  # ← 启用HLIG
)

# HLIG分析会自动应用到每个文档：
# 1. 提取关键词
# 2. 计算拉普拉斯向量（可选）
# 3. 全息映射（可选）

stats = importer.import_from_url_pattern(
    url_pattern='*.example.com/*',
    limit=10000,
)
```

## 🎨 可视化

### Fiedler向量可视化

```python
import matplotlib.pyplot as plt
from hidrs.hlig import SpectralClustering

clustering = SpectralClustering(n_clusters=2)
clustering.fit(vectors)

fiedler_vector = clustering.get_fiedler_vector()

plt.figure(figsize=(10, 4))
plt.plot(fiedler_vector, 'o-')
plt.title('Fiedler Vector (二分图切割)')
plt.xlabel('Document Index')
plt.ylabel('Fiedler Value')
plt.axhline(y=0, color='r', linestyle='--')
plt.grid(True)
plt.show()
```

### 聚类结果可视化

```python
from sklearn.decomposition import PCA

# 降维到2D
pca = PCA(n_components=2)
vectors_2d = pca.fit_transform(vectors)

# 绘制
plt.figure(figsize=(8, 6))
for k in range(clustering.n_clusters):
    cluster_points = vectors_2d[labels == k]
    plt.scatter(cluster_points[:, 0], cluster_points[:, 1], label=f'Cluster {k}')

plt.title('Spectral Clustering Results (PCA 2D)')
plt.xlabel('PC1')
plt.ylabel('PC2')
plt.legend()
plt.grid(True)
plt.show()
```

## 🧮 数学背景

### 拉普拉斯矩阵

**定义**：
```
L = D - W
```
其中：
- D: 度矩阵（对角矩阵）
- W: 邻接矩阵（权重矩阵）

**归一化拉普拉斯矩阵**：
```
L_norm = I - D^(-1/2) * W * D^(-1/2)
```

**性质**：
1. L是半正定的
2. λ₁ = 0（最小特征值）
3. λ₂ > 0（当且仅当图连通）
4. λ₂称为代数连通性（algebraic connectivity）

### Fiedler向量

**定义**：
λ₂对应的特征向量

**应用**：
- **图的二分割**: Fiedler向量的符号可用于将图分为两部分
- **节点重要性**: Fiedler向量的绝对值表示节点的重要性
- **社区发现**: 多个特征向量可用于社区检测

### 谱聚类算法

**步骤**：
1. 构建相似度矩阵 W
2. 计算拉普拉斯矩阵 L
3. 计算L的特征值和特征向量
4. 使用前k个特征向量作为新的特征表示
5. 在新特征空间中进行K-means聚类

**理论保证**：
- 谱聚类等价于图切割问题
- 最小化归一化切割（normalized cut）
- 在某些假设下可以找到全局最优解

## 📚 参考文献

1. **拉普拉斯矩阵**:
   - Mohar, B. (1991). "The Laplacian spectrum of graphs"

2. **Fiedler向量**:
   - Fiedler, M. (1973). "Algebraic connectivity of graphs"

3. **谱聚类**:
   - Ng, A., Jordan, M., & Weiss, Y. (2001). "On spectral clustering: Analysis and an algorithm"

4. **全息映射**:
   - HIDRS内部技术报告

## 🤝 贡献

欢迎贡献代码和改进！

**TODO**:
- [ ] 集成预训练词嵌入模型（Word2Vec/FastText）
- [ ] 集成BERT/Transformer
- [ ] 优化大规模矩阵计算（使用稀疏矩阵）
- [ ] GPU加速
- [ ] 中文分词支持（jieba）
- [ ] 更多相似度度量方法

---

**版本**: 1.0.0
**作者**: HIDRS Team
**创建日期**: 2026-02-06
