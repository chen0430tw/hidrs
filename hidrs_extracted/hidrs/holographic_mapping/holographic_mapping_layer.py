"""
全息映射与索引构建层 - 整合全息映射和索引功能
"""
from .holographic_mapping_manager import HolographicMappingManager


class HolographicMappingLayer:
    """全息映射与索引构建层，整合全息映射和索引功能"""
    
    def __init__(self):
        """初始化全息映射层"""
        self.mapping_manager = HolographicMappingManager()
    
    def start(self):
        """启动全息映射层服务"""
        self.mapping_manager.start()
        print("Holographic mapping layer started")
    
    def stop(self):
        """停止全息映射层服务"""
        self.mapping_manager.stop()
        print("Holographic mapping layer stopped")
    
    def map_local_laplacian(self, local_laplacian, metadata=None):
        """
        执行局部拉普拉斯矩阵到全息表示的映射
        
        参数:
        - local_laplacian: 局部拉普拉斯矩阵
        - metadata: 节点元数据（可选）
        
        返回:
        - 全息表示向量
        """
        return self.mapping_manager.map_local_laplacian(local_laplacian, metadata)
    
    def search_similar(self, holographic_vector=None, local_laplacian=None, query_text=None, limit=10):
        """
        搜索与给定全息表示、局部拉普拉斯矩阵或查询文本相似的文档
        
        参数:
        - holographic_vector: 全息表示向量（可选）
        - local_laplacian: 局部拉普拉斯矩阵（可选）
        - query_text: 查询文本（可选）
        - limit: 返回结果数量限制
        
        返回:
        - 搜索结果列表
        """
        return self.mapping_manager.search_similar(
            holographic_vector=holographic_vector,
            local_laplacian=local_laplacian,
            query_text=query_text,
            limit=limit
        )