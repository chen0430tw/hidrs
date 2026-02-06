"""
谱聚类 - 基于HLIG理论的文档聚类

算法步骤：
1. 计算文档相似度矩阵 W
2. 计算拉普拉斯矩阵 L = D - W
3. 计算L的特征值和特征向量
4. 使用前k个特征向量进行K-means聚类

理论基础：
- 利用图的拉普拉斯矩阵的谱性质进行聚类
- Fiedler向量（第二小特征值对应的特征向量）可以用于二分图
- 前k个特征向量span的空间可以实现k-way聚类
"""

import logging
import numpy as np
from typing import List, Dict, Any, Optional
import sys
from pathlib import Path

try:
    from hidrs.network_topology.laplacian_matrix_calculator import LaplacianMatrixCalculator
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from network_topology.laplacian_matrix_calculator import LaplacianMatrixCalculator

try:
    from sklearn.cluster import KMeans
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logging.warning("sklearn未安装，聚类功能受限")

logger = logging.getLogger(__name__)


class SpectralClustering:
    """谱聚类算法（基于HLIG）"""

    def __init__(
        self,
        n_clusters: int = 5,
        normalized: bool = True,
        affinity: str = 'rbf',
        gamma: float = 1.0,
    ):
        """
        初始化谱聚类

        Args:
            n_clusters: 聚类数量
            normalized: 是否使用归一化拉普拉斯矩阵
            affinity: 相似度计算方法
                - 'rbf': RBF核（高斯相似度）
                - 'cosine': 余弦相似度
                - 'precomputed': 预计算的相似度矩阵
            gamma: RBF核的参数
        """
        self.n_clusters = n_clusters
        self.normalized = normalized
        self.affinity = affinity
        self.gamma = gamma

        self.laplacian_calculator = LaplacianMatrixCalculator(normalized=normalized)

        self.labels_ = None
        self.cluster_centers_ = None
        self.affinity_matrix_ = None
        self.embedding_ = None

    def fit(self, X: np.ndarray) -> 'SpectralClustering':
        """
        训练聚类模型

        Args:
            X: 数据矩阵 (n_samples, n_features) 或 相似度矩阵 (n_samples, n_samples)

        Returns:
            self
        """
        n_samples = X.shape[0]

        # 1. 计算相似度矩阵（如果不是预计算的）
        if self.affinity == 'precomputed':
            self.affinity_matrix_ = X
        else:
            self.affinity_matrix_ = self._compute_affinity_matrix(X)

        # 2. 计算拉普拉斯矩阵
        laplacian_matrix = self.laplacian_calculator.compute_laplacian(self.affinity_matrix_)

        # 转换为稠密矩阵（对于小规模数据）
        if hasattr(laplacian_matrix, 'toarray'):
            laplacian_matrix = laplacian_matrix.toarray()

        # 3. 特征分解
        eigenvalues, eigenvectors = np.linalg.eigh(laplacian_matrix)

        # 按特征值升序排序
        idx = eigenvalues.argsort()
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]

        # 4. 选择前k个特征向量（对应最小的k个特征值）
        self.embedding_ = eigenvectors[:, :self.n_clusters]

        # 5. 在嵌入空间中进行K-means聚类
        if SKLEARN_AVAILABLE:
            kmeans = KMeans(n_clusters=self.n_clusters, random_state=42)
            self.labels_ = kmeans.fit_predict(self.embedding_)
            self.cluster_centers_ = kmeans.cluster_centers_
        else:
            # 简单的K-means实现（备用）
            self.labels_ = self._simple_kmeans(self.embedding_)

        logger.info(f"✅ 谱聚类完成: {n_samples} 个样本 → {self.n_clusters} 个簇")

        return self

    def fit_predict(self, X: np.ndarray) -> np.ndarray:
        """
        训练并返回聚类标签

        Args:
            X: 数据矩阵

        Returns:
            聚类标签 (n_samples,)
        """
        self.fit(X)
        return self.labels_

    def _compute_affinity_matrix(self, X: np.ndarray) -> np.ndarray:
        """
        计算相似度矩阵

        Args:
            X: 数据矩阵 (n_samples, n_features)

        Returns:
            相似度矩阵 (n_samples, n_samples)
        """
        n_samples = X.shape[0]
        affinity_matrix = np.zeros((n_samples, n_samples))

        if self.affinity == 'rbf':
            # RBF核：K(x, y) = exp(-gamma * ||x - y||^2)
            for i in range(n_samples):
                for j in range(i, n_samples):
                    distance_sq = np.sum((X[i] - X[j]) ** 2)
                    similarity = np.exp(-self.gamma * distance_sq)
                    affinity_matrix[i, j] = similarity
                    affinity_matrix[j, i] = similarity

        elif self.affinity == 'cosine':
            # 余弦相似度
            for i in range(n_samples):
                for j in range(i, n_samples):
                    norm_i = np.linalg.norm(X[i])
                    norm_j = np.linalg.norm(X[j])
                    if norm_i > 0 and norm_j > 0:
                        similarity = np.dot(X[i], X[j]) / (norm_i * norm_j)
                    else:
                        similarity = 0.0
                    affinity_matrix[i, j] = similarity
                    affinity_matrix[j, i] = similarity

        return affinity_matrix

    def _simple_kmeans(
        self,
        X: np.ndarray,
        max_iter: int = 100
    ) -> np.ndarray:
        """
        简单的K-means实现（sklearn的备用方案）

        Args:
            X: 数据矩阵 (n_samples, n_features)
            max_iter: 最大迭代次数

        Returns:
            聚类标签 (n_samples,)
        """
        n_samples, n_features = X.shape

        # 随机初始化中心点
        np.random.seed(42)
        center_indices = np.random.choice(n_samples, self.n_clusters, replace=False)
        centers = X[center_indices]

        labels = np.zeros(n_samples, dtype=int)

        for iteration in range(max_iter):
            # 分配样本到最近的中心
            for i in range(n_samples):
                distances = [np.linalg.norm(X[i] - center) for center in centers]
                labels[i] = np.argmin(distances)

            # 更新中心点
            old_centers = centers.copy()
            for k in range(self.n_clusters):
                cluster_points = X[labels == k]
                if len(cluster_points) > 0:
                    centers[k] = cluster_points.mean(axis=0)

            # 检查收敛
            if np.allclose(centers, old_centers):
                logger.debug(f"K-means收敛于第 {iteration+1} 次迭代")
                break

        self.cluster_centers_ = centers
        return labels

    def get_cluster_summary(
        self,
        texts: Optional[List[str]] = None,
        top_n: int = 5
    ) -> List[Dict[str, Any]]:
        """
        获取聚类摘要

        Args:
            texts: 原始文本列表（可选）
            top_n: 每个簇返回的代表样本数

        Returns:
            聚类摘要列表
        """
        if self.labels_ is None:
            raise ValueError("模型未训练，请先调用fit()")

        clusters = []

        for k in range(self.n_clusters):
            cluster_indices = np.where(self.labels_ == k)[0]

            cluster_info = {
                'id': k,
                'size': len(cluster_indices),
                'percentage': len(cluster_indices) / len(self.labels_) * 100,
                'sample_indices': cluster_indices[:top_n].tolist(),
            }

            if texts is not None:
                cluster_info['sample_texts'] = [
                    texts[idx] for idx in cluster_indices[:top_n]
                ]

            clusters.append(cluster_info)

        # 按大小排序
        clusters.sort(key=lambda x: x['size'], reverse=True)

        return clusters

    def get_fiedler_vector(self) -> Optional[np.ndarray]:
        """
        获取Fiedler向量（第二小特征值对应的特征向量）

        Returns:
            Fiedler向量 (n_samples,) 或 None
        """
        if self.embedding_ is not None and self.embedding_.shape[1] > 1:
            return self.embedding_[:, 1]
        return None
