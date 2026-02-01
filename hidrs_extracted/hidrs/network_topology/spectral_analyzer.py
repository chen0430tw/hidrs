"""
谱分析类，进行特征值分解并计算Fiedler值等谱指标
"""
import numpy as np
import scipy.sparse as sp


class SpectralAnalyzer:
    """谱分析类，进行特征值分解并计算Fiedler值等谱指标"""
    
    def __init__(self, use_sparse=True, k=10):
        """
        初始化谱分析器
        
        参数:
        - use_sparse: 是否使用稀疏矩阵计算方法
        - k: 计算的特征值数量（对于大型矩阵，计算前k个特征值和特征向量）
        """
        self.use_sparse = use_sparse
        self.k = k
    
    def compute_eigenvalues(self, laplacian_matrix):
        """
        计算拉普拉斯矩阵的特征值
        
        参数:
        - laplacian_matrix: 拉普拉斯矩阵
        
        返回:
        - eigenvalues: 特征值数组，从小到大排序
        """
        if laplacian_matrix.shape[0] <= 1:
            return np.array([0.0])
        
        if self.use_sparse and sp.issparse(laplacian_matrix):
            # 使用稀疏矩阵方法计算前k个最小特征值
            from scipy.sparse.linalg import eigsh
            try:
                eigenvalues, _ = eigsh(
                    laplacian_matrix, 
                    k=min(self.k, laplacian_matrix.shape[0]-1), 
                    which='SM'
                )
                # 确保包含最小特征值（通常应该接近0）
                if eigenvalues[0] > 1e-10:
                    eigenvalues = np.insert(eigenvalues, 0, 0.0)
                return np.sort(eigenvalues)
            except:
                # 如果稀疏计算失败，回退到稠密矩阵计算
                print("Sparse eigenvalue computation failed, falling back to dense computation")
                laplacian_matrix = laplacian_matrix.toarray()
        
        # 使用稠密矩阵方法计算所有特征值
        eigenvalues = np.linalg.eigvalsh(laplacian_matrix)
        return np.sort(eigenvalues)
    
    def compute_eigenvectors(self, laplacian_matrix, k=None):
        """
        计算拉普拉斯矩阵的特征向量
        
        参数:
        - laplacian_matrix: 拉普拉斯矩阵
        - k: 计算的特征向量数量，默认使用初始化时设置的k值
        
        返回:
        - eigenvalues: 特征值数组，从小到大排序
        - eigenvectors: 对应的特征向量，每列是一个特征向量
        """
        if k is None:
            k = self.k
        
        if laplacian_matrix.shape[0] <= 1:
            return np.array([0.0]), np.ones((1, 1))
        
        if self.use_sparse and sp.issparse(laplacian_matrix):
            # 使用稀疏矩阵方法计算前k个最小特征值和特征向量
            from scipy.sparse.linalg import eigsh
            try:
                eigenvalues, eigenvectors = eigsh(
                    laplacian_matrix, 
                    k=min(k, laplacian_matrix.shape[0]-1), 
                    which='SM'
                )
                # 按特征值大小排序
                idx = eigenvalues.argsort()
                eigenvalues = eigenvalues[idx]
                eigenvectors = eigenvectors[:, idx]
                return eigenvalues, eigenvectors
            except:
                # 如果稀疏计算失败，回退到稠密矩阵计算
                print("Sparse eigenvector computation failed, falling back to dense computation")
                laplacian_matrix = laplacian_matrix.toarray()
        
        # 使用稠密矩阵方法计算所有特征值和特征向量
        eigenvalues, eigenvectors = np.linalg.eigh(laplacian_matrix)
        # 取前k个最小特征值和特征向量
        idx = eigenvalues.argsort()[:k]
        return eigenvalues[idx], eigenvectors[:, idx]
    
    def compute_fiedler_value(self, laplacian_matrix):
        """
        计算Fiedler值（拉普拉斯矩阵的第二小特征值）
        
        参数:
        - laplacian_matrix: 拉普拉斯矩阵
        
        返回:
        - fiedler_value: Fiedler值
        """
        eigenvalues = self.compute_eigenvalues(laplacian_matrix)
        # 找到第二小的特征值（Fiedler值）
        if len(eigenvalues) >= 2:
            # 如果第一个特征值接近0（浮点误差），则第二个是Fiedler值
            if abs(eigenvalues[0]) < 1e-10:
                return float(eigenvalues[1])
            # 否则第一个是Fiedler值（这种情况在图不连通时可能发生）
            return float(eigenvalues[0])
        # 如果只有一个特征值，返回它（这种情况在只有一个节点时可能发生）
        return float(eigenvalues[0]) if len(eigenvalues) > 0 else 0.0
    
    def compute_fiedler_vector(self, laplacian_matrix):
        """
        计算Fiedler向量（与Fiedler值对应的特征向量）
        
        参数:
        - laplacian_matrix: 拉普拉斯矩阵
        
        返回:
        - fiedler_vector: Fiedler向量
        """
        eigenvalues, eigenvectors = self.compute_eigenvectors(laplacian_matrix, k=2)
        # 找到对应Fiedler值的特征向量
        if len(eigenvalues) >= 2:
            # 如果第一个特征值接近0，则Fiedler向量是第二个特征向量
            if abs(eigenvalues[0]) < 1e-10:
                return eigenvectors[:, 1]
            # 否则Fiedler向量是第一个特征向量
            return eigenvectors[:, 0]
        # 如果只有一个特征向量，返回它
        return eigenvectors[:, 0] if eigenvectors.shape[1] > 0 else np.array([])
    
    def compute_spectral_gap(self, laplacian_matrix):
        """
        计算谱间隙（第二小特征值与第三小特征值之间的差）
        
        参数:
        - laplacian_matrix: 拉普拉斯矩阵
        
        返回:
        - spectral_gap: 谱间隙值
        """
        eigenvalues = self.compute_eigenvalues(laplacian_matrix)
        if len(eigenvalues) >= 3:
            # 忽略接近0的特征值
            if abs(eigenvalues[0]) < 1e-10:
                return float(eigenvalues[2] - eigenvalues[1])
            return float(eigenvalues[2] - eigenvalues[1])
        return 0.0
    
    def spectral_clustering(self, laplacian_matrix, n_clusters=2):
        """
        基于拉普拉斯矩阵进行谱聚类
        
        参数:
        - laplacian_matrix: 拉普拉斯矩阵
        - n_clusters: 聚类数量
        
        返回:
        - cluster_labels: 节点的聚类标签
        """
        from sklearn.cluster import KMeans
        
        # 计算前n_clusters个特征向量
        _, eigenvectors = self.compute_eigenvectors(laplacian_matrix, k=n_clusters)
        
        # 使用K-means对特征向量进行聚类
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        cluster_labels = kmeans.fit_predict(eigenvectors)
        
        return cluster_labels