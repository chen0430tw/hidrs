"""
拉普拉斯矩阵计算类，构建图的拉普拉斯矩阵
"""
import numpy as np
import scipy.sparse as sp


class LaplacianMatrixCalculator:
    """拉普拉斯矩阵计算类，构建图的拉普拉斯矩阵"""
    
    def __init__(self, normalized=True):
        """
        初始化拉普拉斯矩阵计算器
        
        参数:
        - normalized: 是否使用归一化的拉普拉斯矩阵
        """
        self.normalized = normalized
    
    def compute_laplacian(self, adjacency_matrix):
        """
        计算拉普拉斯矩阵
        
        参数:
        - adjacency_matrix: 邻接矩阵，可以是稠密矩阵或稀疏矩阵
        
        返回:
        - laplacian_matrix: 拉普拉斯矩阵
        """
        # 转换为稀疏矩阵以提高大规模数据的计算效率
        if not sp.issparse(adjacency_matrix):
            adjacency_matrix = sp.csr_matrix(adjacency_matrix)
        
        # 计算度矩阵
        degrees = np.array(adjacency_matrix.sum(axis=1)).flatten()
        D = sp.diags(degrees)
        
        if self.normalized:
            # 归一化的拉普拉斯矩阵: L = I - D^(-1/2) * A * D^(-1/2)
            with np.errstate(divide='ignore'):
                d_inv_sqrt = np.power(degrees, -0.5)
                d_inv_sqrt[np.isinf(d_inv_sqrt)] = 0
            D_inv_sqrt = sp.diags(d_inv_sqrt)
            
            I = sp.eye(adjacency_matrix.shape[0])
            normalized_laplacian = I - D_inv_sqrt @ adjacency_matrix @ D_inv_sqrt
            return normalized_laplacian
        else:
            # 非归一化的拉普拉斯矩阵: L = D - A
            return D - adjacency_matrix