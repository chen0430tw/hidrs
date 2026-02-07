"""
HLIG核心分析器 - 统一接口

整合：
1. 拉普拉斯矩阵计算
2. Fiedler向量计算
3. 全息映射嵌入
4. 文本向量化
5. 批量处理
"""

import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
import sys
from pathlib import Path

# 导入现有的HLIG组件
try:
    from hidrs.network_topology.laplacian_matrix_calculator import LaplacianMatrixCalculator
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from network_topology.laplacian_matrix_calculator import LaplacianMatrixCalculator

try:
    from hidrs.holographic_mapping.holographic_mapper import HolographicMapper
except ImportError:
    from holographic_mapping.holographic_mapper import HolographicMapper

from .text_vectorizer import TextVectorizer

logger = logging.getLogger(__name__)


class HLIGAnalyzer:
    """HLIG统一分析器"""

    def __init__(
        self,
        output_dim: int = 256,
        normalized_laplacian: bool = True,
        enable_holographic_mapping: bool = True,
    ):
        """
        初始化HLIG分析器

        Args:
            output_dim: 输出向量维度
            normalized_laplacian: 是否使用归一化拉普拉斯矩阵
            enable_holographic_mapping: 是否启用全息映射
        """
        self.output_dim = output_dim
        self.normalized_laplacian = normalized_laplacian
        self.enable_holographic_mapping = enable_holographic_mapping

        # 初始化组件
        self.text_vectorizer = TextVectorizer(output_dim=output_dim)
        self.laplacian_calculator = LaplacianMatrixCalculator(normalized=normalized_laplacian)

        # 全局Fiedler向量：由语料库级别的词图计算得到，用于Φ_hol映射
        # 当处理足够多的文档后，通过 update_global_fiedler() 更新
        self.global_fiedler = None
        # 累积的全局词共现矩阵（用于计算全局Fiedler向量）
        self._global_cooccurrence = None
        self._global_token_to_idx = {}
        self._global_unique_tokens = []
        self._docs_since_last_update = 0
        self._global_fiedler_update_interval = 50  # 每处理50篇文档更新一次全局Fiedler

        if enable_holographic_mapping:
            try:
                self.holographic_mapper = HolographicMapper()
                self.holographic_mapper.output_dim = output_dim
            except Exception as e:
                logger.warning(f"全息映射器初始化失败: {e}，将使用基础向量")
                self.enable_holographic_mapping = False

        logger.info(f"HLIG分析器已初始化 (dim={output_dim}, holographic={enable_holographic_mapping})")

    def compute_document_vector(
        self,
        text: str,
        method: str = 'tfidf',
    ) -> np.ndarray:
        """
        计算单个文档的向量表示

        Args:
            text: 文档文本
            method: 向量化方法
                - 'tfidf': TF-IDF向量
                - 'embedding': 词嵌入 (需要预训练模型)
                - 'laplacian': 拉普拉斯向量（基于图结构）
                - 'holographic': 全息映射向量

        Returns:
            文档向量 (output_dim维)
        """
        if not text or not text.strip():
            return np.zeros(self.output_dim)

        if method == 'tfidf':
            return self.text_vectorizer.vectorize_tfidf(text)

        elif method == 'embedding':
            return self.text_vectorizer.vectorize_embedding(text)

        elif method == 'laplacian':
            return self._compute_laplacian_vector(text)

        elif method == 'holographic':
            if not self.enable_holographic_mapping:
                logger.warning("全息映射未启用，使用TF-IDF备用")
                return self.text_vectorizer.vectorize_tfidf(text)
            return self._compute_holographic_vector(text)

        else:
            raise ValueError(f"未知的向量化方法: {method}")

    def compute_batch_vectors(
        self,
        texts: List[str],
        method: str = 'tfidf',
        batch_size: int = 100,
    ) -> np.ndarray:
        """
        批量计算文档向量（优化版）

        Args:
            texts: 文档列表
            method: 向量化方法
            batch_size: 批处理大小

        Returns:
            文档向量矩阵 (n_docs, output_dim)
        """
        if not texts:
            return np.array([])

        logger.info(f"批量向量化: {len(texts)} 个文档, method={method}")

        vectors = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]

            if method in ['tfidf', 'embedding']:
                # 使用向量化器的批量处理
                batch_vectors = self.text_vectorizer.vectorize_batch(batch, method=method)
            else:
                # 逐个处理
                batch_vectors = [
                    self.compute_document_vector(text, method=method)
                    for text in batch
                ]
                batch_vectors = np.array(batch_vectors)

            vectors.append(batch_vectors)

            if (i // batch_size + 1) % 10 == 0:
                logger.info(f"  处理进度: {min(i+batch_size, len(texts))}/{len(texts)}")

        result = np.vstack(vectors) if vectors else np.array([])
        logger.info(f"✅ 批量向量化完成: shape={result.shape}")

        return result

    def _compute_laplacian_vector(self, text: str) -> np.ndarray:
        """
        计算文档的拉普拉斯向量（基于词图结构）

        策略：
        1. 构建词共现图
        2. 计算拉普拉斯矩阵
        3. 提取Fiedler向量
        """
        try:
            # 分词
            tokens = self.text_vectorizer.tokenize(text)
            if len(tokens) < 2:
                return np.zeros(self.output_dim)

            # 构建词共现矩阵（窗口大小=5）
            adjacency_matrix = self._build_word_cooccurrence_matrix(tokens, window_size=5)

            # 计算拉普拉斯矩阵
            laplacian_matrix = self.laplacian_calculator.compute_laplacian(adjacency_matrix)

            # 转换为稠密矩阵（小矩阵可以这样做）
            if hasattr(laplacian_matrix, 'toarray'):
                laplacian_matrix = laplacian_matrix.toarray()

            # 计算Fiedler向量（第二小特征值对应的特征向量）
            eigenvalues, eigenvectors = np.linalg.eigh(laplacian_matrix)
            idx = eigenvalues.argsort()
            fiedler_vector = eigenvectors[:, idx[1]] if len(idx) > 1 else eigenvectors[:, 0]

            # 调整维度
            if len(fiedler_vector) > self.output_dim:
                fiedler_vector = fiedler_vector[:self.output_dim]
            elif len(fiedler_vector) < self.output_dim:
                padding = np.zeros(self.output_dim - len(fiedler_vector))
                fiedler_vector = np.concatenate([fiedler_vector, padding])

            return fiedler_vector

        except Exception as e:
            logger.debug(f"拉普拉斯向量计算失败: {e}")
            return np.zeros(self.output_dim)

    def _compute_holographic_vector(self, text: str) -> np.ndarray:
        """
        计算文档的全息映射向量

        策略：
        1. 计算局部拉普拉斯矩阵
        2. 累积到全局词共现图，定期更新全局Fiedler向量
        3. 使用全息映射器映射到全局表示（传入全局Fiedler向量）
        """
        try:
            # 计算局部拉普拉斯矩阵
            tokens = self.text_vectorizer.tokenize(text)
            if len(tokens) < 2:
                return np.zeros(self.output_dim)

            adjacency_matrix = self._build_word_cooccurrence_matrix(tokens, window_size=5)
            local_laplacian = self.laplacian_calculator.compute_laplacian(adjacency_matrix)

            # 转换为稠密矩阵
            if hasattr(local_laplacian, 'toarray'):
                local_laplacian = local_laplacian.toarray()

            # 累积全局词共现信息并定期更新全局Fiedler向量
            self._accumulate_global_cooccurrence(tokens)
            self._docs_since_last_update += 1
            if self._docs_since_last_update >= self._global_fiedler_update_interval:
                self.update_global_fiedler()

            # 使用全息映射器，传入全局Fiedler向量
            holographic_vector = self.holographic_mapper.map_local_to_global(
                local_laplacian,
                global_fiedler=self.global_fiedler
            )

            return holographic_vector

        except Exception as e:
            logger.debug(f"全息映射计算失败: {e}")
            return np.zeros(self.output_dim)

    def _accumulate_global_cooccurrence(self, tokens: List[str]):
        """
        将文档的词共现信息累积到全局共现矩阵

        Args:
            tokens: 当前文档的词列表
        """
        # 找出新出现的词
        new_tokens = [t for t in set(tokens) if t not in self._global_token_to_idx]

        if new_tokens:
            # 扩展全局矩阵以容纳新词
            old_n = len(self._global_unique_tokens)
            self._global_unique_tokens.extend(new_tokens)
            for t in new_tokens:
                self._global_token_to_idx[t] = len(self._global_token_to_idx)

            new_n = len(self._global_unique_tokens)
            if self._global_cooccurrence is None:
                self._global_cooccurrence = np.zeros((new_n, new_n))
            else:
                # 扩展矩阵
                expanded = np.zeros((new_n, new_n))
                expanded[:old_n, :old_n] = self._global_cooccurrence
                self._global_cooccurrence = expanded

        if self._global_cooccurrence is None:
            n = len(self._global_unique_tokens)
            self._global_cooccurrence = np.zeros((n, n))

        # 累积共现（窗口大小=5）
        window_size = 5
        for i, token in enumerate(tokens):
            idx_i = self._global_token_to_idx[token]
            for j in range(max(0, i - window_size), min(len(tokens), i + window_size + 1)):
                if i != j:
                    idx_j = self._global_token_to_idx[tokens[j]]
                    self._global_cooccurrence[idx_i, idx_j] += 1

    def update_global_fiedler(self):
        """
        从全局词共现矩阵计算全局Fiedler向量

        全局Fiedler向量u₂反映了整个语料库的词图拓扑结构，
        是Φ_hol映射中局部→全局信息编码的关键。
        """
        if self._global_cooccurrence is None or len(self._global_unique_tokens) < 3:
            return

        try:
            # 对称化
            sym_matrix = (self._global_cooccurrence + self._global_cooccurrence.T) / 2

            # 计算全局拉普拉斯矩阵
            global_laplacian = self.laplacian_calculator.compute_laplacian(sym_matrix)

            # 转换为稠密矩阵
            if hasattr(global_laplacian, 'toarray'):
                global_laplacian = global_laplacian.toarray()

            # 计算Fiedler向量（第二小特征值对应的特征向量）
            eigenvalues, eigenvectors = np.linalg.eigh(global_laplacian)
            idx = eigenvalues.argsort()
            self.global_fiedler = eigenvectors[:, idx[1]] if len(idx) > 1 else eigenvectors[:, 0]

            self._docs_since_last_update = 0
            logger.info(f"全局Fiedler向量已更新 (dim={len(self.global_fiedler)}, "
                        f"词数={len(self._global_unique_tokens)})")

        except Exception as e:
            logger.warning(f"全局Fiedler向量更新失败: {e}")

    def _build_word_cooccurrence_matrix(
        self,
        tokens: List[str],
        window_size: int = 5
    ) -> np.ndarray:
        """
        构建词共现矩阵

        Args:
            tokens: 词列表
            window_size: 窗口大小

        Returns:
            邻接矩阵 (n_words, n_words)
        """
        # 构建词到索引的映射
        unique_tokens = list(set(tokens))
        token_to_idx = {token: idx for idx, token in enumerate(unique_tokens)}
        n = len(unique_tokens)

        # 初始化邻接矩阵
        adjacency_matrix = np.zeros((n, n))

        # 统计共现
        for i, token in enumerate(tokens):
            idx_i = token_to_idx[token]

            # 检查窗口内的其他词
            for j in range(max(0, i-window_size), min(len(tokens), i+window_size+1)):
                if i != j:
                    other_token = tokens[j]
                    idx_j = token_to_idx[other_token]
                    adjacency_matrix[idx_i, idx_j] += 1

        # 对称化
        adjacency_matrix = (adjacency_matrix + adjacency_matrix.T) / 2

        return adjacency_matrix

    def compute_similarity(
        self,
        vector1: np.ndarray,
        vector2: np.ndarray,
        metric: str = 'cosine'
    ) -> float:
        """
        计算两个向量的相似度

        Args:
            vector1: 向量1
            vector2: 向量2
            metric: 相似度度量
                - 'cosine': 余弦相似度
                - 'euclidean': 欧氏距离
                - 'dot': 点积

        Returns:
            相似度分数
        """
        if metric == 'cosine':
            norm1 = np.linalg.norm(vector1)
            norm2 = np.linalg.norm(vector2)
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return np.dot(vector1, vector2) / (norm1 * norm2)

        elif metric == 'euclidean':
            return -np.linalg.norm(vector1 - vector2)  # 负距离（越大越相似）

        elif metric == 'dot':
            return np.dot(vector1, vector2)

        else:
            raise ValueError(f"未知的相似度度量: {metric}")

    def compute_similarity_matrix(
        self,
        vectors: np.ndarray,
        metric: str = 'cosine'
    ) -> np.ndarray:
        """
        计算相似度矩阵

        Args:
            vectors: 向量矩阵 (n_docs, dim)
            metric: 相似度度量

        Returns:
            相似度矩阵 (n_docs, n_docs)
        """
        n = len(vectors)
        similarity_matrix = np.zeros((n, n))

        for i in range(n):
            for j in range(i, n):
                sim = self.compute_similarity(vectors[i], vectors[j], metric=metric)
                similarity_matrix[i, j] = sim
                similarity_matrix[j, i] = sim

        return similarity_matrix

    def extract_keywords(
        self,
        text: str,
        top_n: int = 10
    ) -> List[str]:
        """
        提取文档关键词

        Args:
            text: 文档文本
            top_n: 返回前N个关键词

        Returns:
            关键词列表
        """
        return self.text_vectorizer.extract_keywords(text, top_n=top_n)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'output_dim': self.output_dim,
            'normalized_laplacian': self.normalized_laplacian,
            'holographic_mapping_enabled': self.enable_holographic_mapping,
            'vectorizer_stats': self.text_vectorizer.get_stats(),
        }
