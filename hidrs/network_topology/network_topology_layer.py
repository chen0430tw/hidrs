"""
网络拓扑构建与谱分析层 - 整合所有拓扑分析功能
"""
from .topology_manager import TopologyManager


class NetworkTopologyLayer:
    """网络拓扑构建与谱分析层，整合所有拓扑分析功能"""
    
    def __init__(self):
        """初始化网络拓扑层"""
        self.topology_manager = TopologyManager()
    
    def start(self):
        """启动网络拓扑层服务"""
        self.topology_manager.start()
        print("Network topology layer started")
    
    def stop(self):
        """停止网络拓扑层服务"""
        self.topology_manager.stop()
        print("Network topology layer stopped")
    
    def get_topology_info(self):
        """获取当前拓扑信息"""
        return self.topology_manager.get_topology_info()
    
    def get_community_structure(self):
        """获取社区结构"""
        return self.topology_manager.get_community_structure()
    
    def get_graph(self):
        """获取NetworkX图对象"""
        return self.topology_manager.get_graph()