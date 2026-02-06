"""
FAISS向量索引 - 加速相似度计算

使用Facebook AI Similarity Search (FAISS) 加速向量检索：
1. 支持大规模向量集合的快速搜索
2. 使用IVF (Inverted File) 索引结构
3. 支持GPU加速（可选）
4. 减少HLIG重排序的计算时间

性能对比:
- 暴力搜索: O(n²) - 慢但精确
- FAISS IVF: O(n·log(k)) - 快且近似精确

参考: https://github.com/facebookresearch/faiss
"""
import os
import logging
import numpy as np
from typing import List, Tuple, Optional
import pickle

logger = logging.getLogger(__name__)

# FAISS是可选依赖
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("[FAISSVectorIndex] FAISS未安装，将使用暴力搜索")


class FAISSVectorIndex:
    """FAISS向量索引 - 加速相似度计算"""

    def __init__(
        self,
        dimension: int = 384,
        index_type: str = 'IVF',
        nlist: int = 100,
        nprobe: int = 10,
        metric: str = 'cosine',
        use_gpu: bool = False
    ):
        """
        初始化FAISS索引

        参数:
        - dimension: 向量维度（默认384，对应all-MiniLM-L6-v2）
        - index_type: 索引类型
          - 'Flat': 暴力搜索，最精确但最慢
          - 'IVF': 倒排文件索引，速度和精度平衡（推荐）
          - 'HNSW': 层次导航小世界图，快速但内存占用大
        - nlist: IVF聚类中心数量（影响速度和精度）
        - nprobe: IVF搜索时探测的聚类数（值越大越精确但越慢）
        - metric: 距离度量
          - 'cosine': 余弦相似度（推荐）
          - 'euclidean': 欧氏距离
          - 'inner_product': 内积
        - use_gpu: 是否使用GPU加速（需要faiss-gpu）
        """
        if not FAISS_AVAILABLE:
            logger.error("[FAISSVectorIndex] FAISS不可用，无法初始化")
            self._available = False
            return

        self.dimension = dimension
        self.index_type = index_type
        self.nlist = nlist
        self.nprobe = nprobe
        self.metric = metric
        self.use_gpu = use_gpu

        self.index = None
        self.id_mapping = []  # 索引ID到原始ID的映射
        self._is_trained = False
        self._available = True

        # 创建索引
        self._create_index()

        logger.info(f"[FAISSVectorIndex] 初始化完成")
        logger.info(f"  索引类型: {index_type}")
        logger.info(f"  向量维度: {dimension}")
        logger.info(f"  距离度量: {metric}")
        logger.info(f"  GPU加速: {'启用' if use_gpu else '禁用'}")

    def _create_index(self):
        """创建FAISS索引"""
        try:
            # 1. 选择距离度量
            if self.metric == 'cosine':
                # 余弦相似度 = 归一化后的内积
                measure = faiss.METRIC_INNER_PRODUCT
            elif self.metric == 'euclidean':
                measure = faiss.METRIC_L2
            else:
                measure = faiss.METRIC_INNER_PRODUCT

            # 2. 创建基础索引
            if self.index_type == 'Flat':
                # 暴力搜索索引（最精确）
                self.index = faiss.IndexFlatIP(self.dimension)
                self._is_trained = True  # Flat索引不需要训练

            elif self.index_type == 'IVF':
                # 倒排文件索引（速度和精度平衡）
                quantizer = faiss.IndexFlatIP(self.dimension)
                self.index = faiss.IndexIVFFlat(
                    quantizer,
                    self.dimension,
                    self.nlist,
                    measure
                )
                self.index.nprobe = self.nprobe

            elif self.index_type == 'HNSW':
                # HNSW索引（快速但内存占用大）
                self.index = faiss.IndexHNSWFlat(self.dimension, 32)
                self.index.hnsw.efConstruction = 40
                self.index.hnsw.efSearch = 16
                self._is_trained = True  # HNSW不需要训练

            else:
                logger.warning(f"[FAISSVectorIndex] 未知索引类型: {self.index_type}, 使用Flat")
                self.index = faiss.IndexFlatIP(self.dimension)
                self._is_trained = True

            # 3. GPU加速（可选）
            if self.use_gpu:
                try:
                    gpu_resources = faiss.StandardGpuResources()
                    self.index = faiss.index_cpu_to_gpu(gpu_resources, 0, self.index)
                    logger.info("[FAISSVectorIndex] GPU加速已启用")
                except Exception as e:
                    logger.warning(f"[FAISSVectorIndex] GPU加速失败，使用CPU: {e}")
                    self.use_gpu = False

            logger.info(f"[FAISSVectorIndex] 索引创建成功")

        except Exception as e:
            logger.error(f"[FAISSVectorIndex] 索引创建失败: {e}")
            self._available = False

    def add_vectors(self, vectors: np.ndarray, ids: Optional[List[int]] = None):
        """
        添加向量到索引

        参数:
        - vectors: 向量数组，形状为(n, dimension)
        - ids: 向量ID列表（可选），如果不提供则自动生成
        """
        if not self._available:
            logger.warning("[FAISSVectorIndex] 索引不可用")
            return False

        try:
            # 确保向量是float32类型
            vectors = vectors.astype(np.float32)

            # 归一化（如果使用余弦相似度）
            if self.metric == 'cosine':
                faiss.normalize_L2(vectors)

            # 训练索引（IVF需要训练）
            if not self._is_trained and self.index_type == 'IVF':
                logger.info(f"[FAISSVectorIndex] 训练索引，使用 {len(vectors)} 个向量")
                self.index.train(vectors)
                self._is_trained = True

            # 添加向量
            self.index.add(vectors)

            # 更新ID映射
            if ids is None:
                ids = list(range(len(self.id_mapping), len(self.id_mapping) + len(vectors)))
            self.id_mapping.extend(ids)

            logger.info(f"[FAISSVectorIndex] 添加 {len(vectors)} 个向量，总数: {self.index.ntotal}")
            return True

        except Exception as e:
            logger.error(f"[FAISSVectorIndex] 添加向量失败: {e}")
            return False

    def search(self, query_vectors: np.ndarray, k: int = 10) -> Tuple[np.ndarray, np.ndarray]:
        """
        搜索最近邻向量

        参数:
        - query_vectors: 查询向量，形状为(n_queries, dimension)
        - k: 返回最近邻数量

        返回:
        - distances: 距离数组，形状为(n_queries, k)
        - indices: 索引数组，形状为(n_queries, k)
        """
        if not self._available or self.index.ntotal == 0:
            logger.warning("[FAISSVectorIndex] 索引不可用或为空")
            return np.array([]), np.array([])

        try:
            # 确保向量是float32类型
            query_vectors = query_vectors.astype(np.float32)

            # 归一化（如果使用余弦相似度）
            if self.metric == 'cosine':
                faiss.normalize_L2(query_vectors)

            # 搜索
            k = min(k, self.index.ntotal)  # k不能超过索引中的向量数
            distances, indices = self.index.search(query_vectors, k)

            # 如果使用余弦相似度，距离实际上是相似度（值越大越相似）
            # 需要转换为距离（值越小越相似）
            if self.metric == 'cosine':
                # 余弦相似度范围[-1, 1]，转换为距离[0, 2]
                distances = 1.0 - distances

            logger.debug(f"[FAISSVectorIndex] 搜索完成: {len(query_vectors)} queries, k={k}")
            return distances, indices

        except Exception as e:
            logger.error(f"[FAISSVectorIndex] 搜索失败: {e}")
            return np.array([]), np.array([])

    def compute_similarity_matrix(self, vectors: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        """
        计算向量集合的相似度矩阵（用于HLIG）

        参数:
        - vectors: 向量数组，形状为(n, dimension)
        - threshold: 相似度阈值，低于该值置为0

        返回:
        - similarity_matrix: 相似度矩阵，形状为(n, n)
        """
        if not self._available:
            logger.warning("[FAISSVectorIndex] 索引不可用，使用暴力计算")
            return self._compute_similarity_brute_force(vectors, threshold)

        try:
            n = len(vectors)

            # 确保向量是float32类型
            vectors = vectors.astype(np.float32)

            # 归一化
            if self.metric == 'cosine':
                faiss.normalize_L2(vectors)

            # 使用FAISS计算相似度
            # 对每个向量，找到与所有其他向量的相似度
            index_temp = faiss.IndexFlatIP(self.dimension)
            index_temp.add(vectors)

            # 搜索自己与所有向量的相似度
            distances, indices = index_temp.search(vectors, n)

            # 构建相似度矩阵
            similarity_matrix = np.zeros((n, n), dtype=np.float32)
            for i in range(n):
                for j, idx in enumerate(indices[i]):
                    sim = distances[i][j]
                    if sim >= threshold:
                        similarity_matrix[i, idx] = sim
                    else:
                        similarity_matrix[i, idx] = 0

            logger.debug(f"[FAISSVectorIndex] 相似度矩阵计算完成: {n}x{n}")
            return similarity_matrix

        except Exception as e:
            logger.error(f"[FAISSVectorIndex] 相似度矩阵计算失败: {e}")
            return self._compute_similarity_brute_force(vectors, threshold)

    def _compute_similarity_brute_force(self, vectors: np.ndarray, threshold: float) -> np.ndarray:
        """暴力计算相似度矩阵（备用方案）"""
        from sklearn.metrics.pairwise import cosine_similarity

        vectors = vectors.astype(np.float32)
        similarity_matrix = cosine_similarity(vectors)
        similarity_matrix[similarity_matrix < threshold] = 0

        return similarity_matrix

    def save(self, filepath: str):
        """保存索引到文件"""
        if not self._available:
            logger.warning("[FAISSVectorIndex] 索引不可用，无法保存")
            return False

        try:
            # 如果使用GPU，先转回CPU
            index_to_save = self.index
            if self.use_gpu:
                index_to_save = faiss.index_gpu_to_cpu(self.index)

            # 保存FAISS索引
            faiss.write_index(index_to_save, f"{filepath}.faiss")

            # 保存元数据
            metadata = {
                'dimension': self.dimension,
                'index_type': self.index_type,
                'nlist': self.nlist,
                'nprobe': self.nprobe,
                'metric': self.metric,
                'id_mapping': self.id_mapping,
                'is_trained': self._is_trained
            }

            with open(f"{filepath}.meta", 'wb') as f:
                pickle.dump(metadata, f)

            logger.info(f"[FAISSVectorIndex] 索引已保存到 {filepath}")
            return True

        except Exception as e:
            logger.error(f"[FAISSVectorIndex] 保存失败: {e}")
            return False

    def load(self, filepath: str):
        """从文件加载索引"""
        try:
            # 加载FAISS索引
            self.index = faiss.read_index(f"{filepath}.faiss")

            # 如果需要GPU，转到GPU
            if self.use_gpu:
                try:
                    gpu_resources = faiss.StandardGpuResources()
                    self.index = faiss.index_cpu_to_gpu(gpu_resources, 0, self.index)
                except Exception as e:
                    logger.warning(f"[FAISSVectorIndex] GPU加速失败: {e}")
                    self.use_gpu = False

            # 加载元数据
            with open(f"{filepath}.meta", 'rb') as f:
                metadata = pickle.load(f)

            self.dimension = metadata['dimension']
            self.index_type = metadata['index_type']
            self.nlist = metadata['nlist']
            self.nprobe = metadata.get('nprobe', 10)
            self.metric = metadata['metric']
            self.id_mapping = metadata['id_mapping']
            self._is_trained = metadata['is_trained']
            self._available = True

            logger.info(f"[FAISSVectorIndex] 索引已从 {filepath} 加载")
            logger.info(f"  向量数: {self.index.ntotal}")
            return True

        except Exception as e:
            logger.error(f"[FAISSVectorIndex] 加载失败: {e}")
            self._available = False
            return False

    def reset(self):
        """重置索引"""
        if not self._available:
            return

        try:
            self.index.reset()
            self.id_mapping = []
            self._is_trained = False
            logger.info("[FAISSVectorIndex] 索引已重置")
        except Exception as e:
            logger.error(f"[FAISSVectorIndex] 重置失败: {e}")

    def get_stats(self) -> dict:
        """获取统计信息"""
        if not self._available:
            return {'available': False}

        return {
            'available': True,
            'total_vectors': self.index.ntotal if self.index else 0,
            'dimension': self.dimension,
            'index_type': self.index_type,
            'metric': self.metric,
            'is_trained': self._is_trained,
            'use_gpu': self.use_gpu,
            'nlist': self.nlist,
            'nprobe': self.nprobe
        }

    def is_available(self) -> bool:
        """检查索引是否可用"""
        return self._available and FAISS_AVAILABLE


# 便捷函数
def create_faiss_index(
    dimension: int = 384,
    index_type: str = 'IVF',
    use_gpu: bool = False
) -> FAISSVectorIndex:
    """
    创建FAISS索引的便捷函数

    参数:
    - dimension: 向量维度
    - index_type: 索引类型 ('Flat', 'IVF', 'HNSW')
    - use_gpu: 是否使用GPU

    返回:
    - FAISSVectorIndex实例
    """
    return FAISSVectorIndex(
        dimension=dimension,
        index_type=index_type,
        use_gpu=use_gpu
    )
