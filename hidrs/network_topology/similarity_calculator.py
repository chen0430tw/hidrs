"""
相似度计算类，计算节点间的相似度并构建加权矩阵
"""
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


class SimilarityCalculator:
    """相似度计算类，计算节点间的相似度并构建加权矩阵"""
    
    def __init__(self, metric='cosine', threshold=0.5):
        """
        初始化相似度计算器
        
        参数:
        - metric: 相似度度量方式，可选'cosine'、'euclidean'等
        - threshold: 相似度阈值，低于该值的相似度将被视为0（不连接）
        """
        self.metric = metric
        self.threshold = threshold
    
    def compute_similarity_matrix(self, vectors):
        """
        计算特征向量集合的相似度矩阵
        
        参数:
        - vectors: 特征向量列表，每个向量是一个numpy数组
        
        返回:
        - similarity_matrix: 相似度矩阵，形状为(n, n)，其中n是向量数量
        """
        if not vectors or len(vectors) < 2:
            return np.array([])
        
        # 将向量列表转换为矩阵，每行是一个向量
        vectors_matrix = np.vstack(vectors)
        
        if self.metric == 'cosine':
            # 计算余弦相似度
            similarity_matrix = cosine_similarity(vectors_matrix)
            
            # 应用阈值，将低于阈值的相似度置为0
            similarity_matrix[similarity_matrix < self.threshold] = 0
            
        else:
            raise ValueError(f"Unsupported similarity metric: {self.metric}")
        
        return similarity_matrix