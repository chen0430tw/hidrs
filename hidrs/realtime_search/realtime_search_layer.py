"""
实时搜索与决策反馈层 - 整合搜索和决策反馈功能
"""
from .search_engine import RealtimeSearchEngine
from .decision_feedback import DecisionFeedbackSystem


class RealtimeSearchLayer:
    """实时搜索与决策反馈层，整合搜索和决策反馈功能"""
    
    def __init__(self):
        """初始化实时搜索层"""
        self.search_engine = RealtimeSearchEngine()
        self.feedback_system = DecisionFeedbackSystem()
    
    def start(self):
        """启动实时搜索层服务"""
        self.search_engine.start()
        self.feedback_system.start()
        print("Realtime search layer started")
    
    def stop(self):
        """停止实时搜索层服务"""
        self.search_engine.stop()
        self.feedback_system.stop()
        print("Realtime search layer stopped")
    
    def search(self, query_text=None, local_laplacian=None, limit=10, use_cache=True):
        """执行搜索查询"""
        return self.search_engine.search(
            query_text=query_text,
            local_laplacian=local_laplacian,
            limit=limit,
            use_cache=use_cache
        )
    
    def get_search_stats(self, time_range_hours=24):
        """获取搜索统计信息"""
        return self.search_engine.get_search_stats(time_range_hours=time_range_hours)
    
    def get_recent_feedback(self, limit=10):
        """获取最近的决策反馈"""
        return self.feedback_system.get_recent_feedback(limit=limit)