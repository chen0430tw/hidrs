"""
HIDRS HLIG (Holographic Laplacian Internet Graph) 统一库

功能：
1. 文本向量化（TF-IDF + 词嵌入）
2. 拉普拉斯矩阵计算
3. Fiedler向量计算
4. 全息映射嵌入
5. 谱聚类
6. 批量处理优化

使用示例：
    from hidrs.hlig import HLIGAnalyzer

    analyzer = HLIGAnalyzer()

    # 单文档分析
    vector = analyzer.compute_document_vector(text)

    # 批量文档分析
    vectors = analyzer.compute_batch_vectors(texts)

    # 聚类分析
    clusters = analyzer.cluster_documents(texts, n_clusters=5)
"""

from .hlig_analyzer import HLIGAnalyzer
from .text_vectorizer import TextVectorizer
from .spectral_clustering import SpectralClustering

__all__ = [
    'HLIGAnalyzer',
    'TextVectorizer',
    'SpectralClustering',
]

__version__ = '1.0.0'
