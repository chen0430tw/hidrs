"""
拓扑构建类，整合特征向量、相似度计算、拉普拉斯矩阵构建和谱分析
"""
import os
import json
import numpy as np
import networkx as nx
import scipy.sparse as sp

from .similarity_calculator import SimilarityCalculator
from .laplacian_matrix_calculator import LaplacianMatrixCalculator
from .spectral_analyzer import SpectralAnalyzer


class TopologyBuilder:
    """拓扑构建类，整合特征向量、相似度计算、拉普拉斯矩阵构建和谱分析"""
    
    def __init__(self, config_path="config/topology_builder_config.json"):
        """初始化拓扑构建器"""
        # 读取配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # 初始化组件
        self.similarity_calculator = SimilarityCalculator(
            metric=self.config['similarity_metric'],
            threshold=self.config['similarity_threshold']
        )
        self.laplacian_calculator = LaplacianMatrixCalculator(
            normalized=self.config['use_normalized_laplacian']
        )
        self.spectral_analyzer = SpectralAnalyzer(
            use_sparse=self.config['use_sparse_computation'],
            k=self.config['k_eigenvalues']
        )
        
        # 存储拓扑结构
        self.adjacency_matrix = None
        self.laplacian_matrix = None
        self.node_ids = []  # 存储节点ID，与矩阵索引对应
        self.node_urls = []  # 存储节点URL，与矩阵索引对应
        self.node_features = []  # 存储节点特征向量
        
        # 谱分析结果
        self.fiedler_value = 0.0
        self.fiedler_vector = None
        self.spectral_gap = 0.0
        self.cluster_labels = None
        
        # 网络图对象（用于可视化和图算法）
        self.graph = nx.Graph()
    
    def build_topology_from_features(self, feature_vectors, node_ids, node_urls=None):
        """
        从特征向量构建网络拓扑
        
        参数:
        - feature_vectors: 特征向量列表
        - node_ids: 节点ID列表，与特征向量一一对应
        - node_urls: 节点URL列表，与特征向量一一对应（可选）
        
        返回:
        - 构建是否成功
        """
        if not feature_vectors or len(feature_vectors) < 2:
            print("Not enough feature vectors to build topology")
            return False
        
        # 存储节点信息
        self.node_ids = node_ids
        self.node_urls = node_urls if node_urls else node_ids
        self.node_features = feature_vectors
        
        # 计算相似度矩阵（作为邻接矩阵）
        self.adjacency_matrix = self.similarity_calculator.compute_similarity_matrix(feature_vectors)
        
        # 构建拉普拉斯矩阵
        self.laplacian_matrix = self.laplacian_calculator.compute_laplacian(self.adjacency_matrix)
        
        # 计算谱分析结果
        self.fiedler_value = self.spectral_analyzer.compute_fiedler_value(self.laplacian_matrix)
        self.fiedler_vector = self.spectral_analyzer.compute_fiedler_vector(self.laplacian_matrix)
        self.spectral_gap = self.spectral_analyzer.compute_spectral_gap(self.laplacian_matrix)
        
        # 执行谱聚类
        n_clusters = self.config['default_n_clusters']
        self.cluster_labels = self.spectral_analyzer.spectral_clustering(
            self.laplacian_matrix, 
            n_clusters=n_clusters
        )
        
        # 构建NetworkX图对象
        self.build_networkx_graph()
        
        print(f"Built topology with {len(node_ids)} nodes, Fiedler value: {self.fiedler_value:.6f}")
        return True
    
    def build_networkx_graph(self):
        """构建NetworkX图对象，用于可视化和图算法"""
        # 创建一个新的无向图
        self.graph = nx.Graph()
        
        # 添加节点
        for i, node_id in enumerate(self.node_ids):
            # 添加节点属性：URL、聚类标签
            node_attrs = {
                'url': self.node_urls[i] if i < len(self.node_urls) else '',
                'cluster': int(self.cluster_labels[i]) if self.cluster_labels is not None else 0,
                'fiedler_component': float(self.fiedler_vector[i]) if self.fiedler_vector is not None else 0.0
            }
            self.graph.add_node(node_id, **node_attrs)
        
        # 添加边（基于邻接矩阵）
        if self.adjacency_matrix is not None:
            for i in range(len(self.node_ids)):
                for j in range(i+1, len(self.node_ids)):
                    weight = self.adjacency_matrix[i, j]
                    if weight > 0:  # 只添加权重大于0的边
                        self.graph.add_edge(self.node_ids[i], self.node_ids[j], weight=float(weight))
    
    def update_topology(self, new_feature_vectors, new_node_ids, new_node_urls=None):
        """
        更新拓扑结构（添加新节点和特征向量）
        
        参数:
        - new_feature_vectors: 新的特征向量列表
        - new_node_ids: 新的节点ID列表
        - new_node_urls: 新的节点URL列表（可选）
        
        返回:
        - 更新是否成功
        """
        if not new_feature_vectors:
            return False
        
        # 对于新添加的节点，检查ID是否已存在
        existing_ids = set(self.node_ids)
        valid_indices = []
        valid_ids = []
        valid_urls = []
        valid_features = []
        
        for i, node_id in enumerate(new_node_ids):
            if node_id not in existing_ids:
                valid_indices.append(i)
                valid_ids.append(node_id)
                valid_urls.append(new_node_urls[i] if new_node_urls and i < len(new_node_urls) else node_id)
                valid_features.append(new_feature_vectors[i])
        
        if not valid_ids:
            return False
        
        # 合并节点信息
        all_features = self.node_features + valid_features
        all_ids = self.node_ids + valid_ids
        all_urls = self.node_urls + valid_urls
        
        # 重新构建拓扑
        return self.build_topology_from_features(all_features, all_ids, all_urls)
    
    def get_spectral_info(self):
        """获取谱分析信息"""
        return {
            'fiedler_value': self.fiedler_value,
            'spectral_gap': self.spectral_gap,
            'n_clusters': len(set(self.cluster_labels)) if self.cluster_labels is not None else 0,
            'node_count': len(self.node_ids),
            'edge_count': self.graph.number_of_edges() if self.graph else 0
        }
    
    def get_community_structure(self):
        """获取社区结构信息"""
        if self.cluster_labels is None:
            return {}
        
        communities = {}
        for i, cluster_id in enumerate(self.cluster_labels):
            cluster_id = int(cluster_id)
            if cluster_id not in communities:
                communities[cluster_id] = []
            communities[cluster_id].append(self.node_ids[i])
        
        return communities
    
    def detect_anomalies(self, threshold=0.1):
        """
        检测网络异常
        
        参数:
        - threshold: Fiedler值变化阈值，超过此阈值视为异常
        
        返回:
        - is_anomaly: 是否检测到异常
        - anomaly_info: 异常信息
        """
        # 默认Fiedler值变化率阈值
        if not hasattr(self, 'previous_fiedler_value'):
            self.previous_fiedler_value = self.fiedler_value
            return False, {}
        
        # 计算Fiedler值变化率
        fiedler_change = abs(self.fiedler_value - self.previous_fiedler_value) / (self.previous_fiedler_value + 1e-10)
        
        # 判断是否异常
        is_anomaly = fiedler_change > threshold
        
        # 更新历史Fiedler值
        self.previous_fiedler_value = self.fiedler_value
        
        return is_anomaly, {
            'fiedler_change': fiedler_change,
            'threshold': threshold,
            'current_fiedler': self.fiedler_value,
            'previous_fiedler': self.previous_fiedler_value
        }
    
    def generate_multi_scale_laplacians(self, n_scales=3):
        """
        生成多尺度拉普拉斯矩阵，用于多尺度全息映射

        通过图粗化（graph coarsening）在不同尺度上构建拉普拉斯矩阵：
        - 尺度0：原始图的拉普拉斯矩阵
        - 尺度1..n：通过谱聚类将节点合并后的粗化图拉普拉斯矩阵

        每一级粗化将节点数减半，保留图的谱特性。

        参数:
        - n_scales: 尺度数量（包含原始尺度）

        返回:
        - laplacian_matrices: 多尺度拉普拉斯矩阵列表，从精细到粗糙
        """
        if self.laplacian_matrix is None or self.adjacency_matrix is None:
            return []

        laplacian_matrices = [self.laplacian_matrix]
        current_adjacency = self.adjacency_matrix

        for scale in range(1, n_scales):
            # 获取当前邻接矩阵的大小
            if sp.issparse(current_adjacency):
                n = current_adjacency.shape[0]
            else:
                n = len(current_adjacency)

            if n < 4:  # 节点太少，无法继续粗化
                break

            # 计算当前尺度的拉普拉斯矩阵用于聚类
            current_laplacian = self.laplacian_calculator.compute_laplacian(current_adjacency)

            # 通过谱聚类确定粗化后的簇分配
            n_clusters = max(2, n // 2)
            try:
                cluster_labels = self.spectral_analyzer.spectral_clustering(
                    current_laplacian, n_clusters=n_clusters
                )
            except Exception:
                # 如果谱聚类失败，使用简单的均匀划分
                cluster_labels = np.array([i % n_clusters for i in range(n)])

            # 构建粗化后的邻接矩阵
            if sp.issparse(current_adjacency):
                current_adjacency_dense = current_adjacency.toarray()
            else:
                current_adjacency_dense = np.array(current_adjacency)

            coarse_adjacency = np.zeros((n_clusters, n_clusters))
            for i in range(n):
                for j in range(i + 1, n):
                    ci, cj = cluster_labels[i], cluster_labels[j]
                    if ci != cj:
                        coarse_adjacency[ci, cj] += current_adjacency_dense[i, j]
                        coarse_adjacency[cj, ci] += current_adjacency_dense[i, j]

            # 计算粗化图的拉普拉斯矩阵
            coarse_laplacian = self.laplacian_calculator.compute_laplacian(coarse_adjacency)
            laplacian_matrices.append(coarse_laplacian)

            # 为下一级粗化准备
            current_adjacency = coarse_adjacency

        return laplacian_matrices

    def save_topology(self, filepath):
        """保存拓扑结构到文件"""
        import pickle
        
        data = {
            'node_ids': self.node_ids,
            'node_urls': self.node_urls,
            'adjacency_matrix': self.adjacency_matrix,
            'fiedler_value': self.fiedler_value,
            'fiedler_vector': self.fiedler_vector,
            'spectral_gap': self.spectral_gap,
            'cluster_labels': self.cluster_labels
        }
        
        with open(filepath, 'wb') as f:
            pickle.dump(data, f)
        
        print(f"Saved topology to {filepath}")
    
    def load_topology(self, filepath):
        """从文件加载拓扑结构"""
        import pickle
        
        with open(filepath, 'rb') as f:
            data = pickle.load(f)
        
        # 恢复拓扑结构
        self.node_ids = data['node_ids']
        self.node_urls = data['node_urls']
        self.adjacency_matrix = data['adjacency_matrix']
        self.fiedler_value = data['fiedler_value']
        self.fiedler_vector = data['fiedler_vector']
        self.spectral_gap = data['spectral_gap']
        self.cluster_labels = data['cluster_labels']
        
        # 构建拉普拉斯矩阵
        self.laplacian_matrix = self.laplacian_calculator.compute_laplacian(self.adjacency_matrix)
        
        # 构建NetworkX图对象
        self.build_networkx_graph()
        
        print(f"Loaded topology from {filepath} with {len(self.node_ids)} nodes")
        return True