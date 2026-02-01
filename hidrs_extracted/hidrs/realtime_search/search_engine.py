"""
实时搜索引擎类，提供基于全息索引的高效搜索接口
"""
import os
import json
import time
import threading
import numpy as np
from datetime import datetime, timedelta
from pymongo import MongoClient
from kafka import KafkaProducer


class RealtimeSearchEngine:
    """实时搜索引擎类，提供基于全息索引的高效搜索接口"""
    
    def __init__(self, config_path="config/realtime_search_config.json"):
        """初始化实时搜索引擎"""
        # 读取配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # 导入全息映射层的HolographicMappingManager类
        import sys
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from holographic_mapping.holographic_mapping_manager import HolographicMappingManager
        
        # 创建全息映射管理器
        self.mapping_manager = HolographicMappingManager(
            config_path=self.config['holographic_mapping_manager_config_path']
        )
        
        # 初始化MongoDB连接
        self.mongo_client = MongoClient(self.config['mongodb_uri'])
        self.db = self.mongo_client[self.config['mongodb_db']]
        self.search_logs_collection = self.db[self.config['search_logs_collection']]
        
        # 初始化Kafka生产者，用于发送搜索事件
        self.producer = KafkaProducer(
            bootstrap_servers=self.config['kafka_servers'],
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        # 搜索缓存
        self.search_cache = {}
        self.cache_lock = threading.Lock()
        
        # 缓存清理线程
        self.cache_cleanup_thread = None
        self.running = False
    
    def _cache_cleanup_worker(self):
        """缓存清理线程，定期清理过期缓存"""
        while self.running:
            try:
                # 获取当前时间
                now = datetime.now()
                
                # 清理过期缓存项
                with self.cache_lock:
                    expired_keys = []
                    for key, (timestamp, _) in self.search_cache.items():
                        if now - timestamp > timedelta(seconds=self.config['cache_expiry_seconds']):
                            expired_keys.append(key)
                    
                    # 删除过期项
                    for key in expired_keys:
                        del self.search_cache[key]
                    
                    if expired_keys:
                        print(f"Cleared {len(expired_keys)} expired cache items")
                
                # 等待下一次清理
                time.sleep(self.config['cache_cleanup_interval'])
                
            except Exception as e:
                print(f"Cache cleanup error: {str(e)}")
                time.sleep(60)  # 出错后等待一段时间再继续
    
    def start(self):
        """启动搜索引擎服务"""
        self.running = True
        
        # 启动缓存清理线程
        self.cache_cleanup_thread = threading.Thread(
            target=self._cache_cleanup_worker,
            daemon=True
        )
        self.cache_cleanup_thread.start()
        
        print("Realtime search engine started")
    
    def stop(self):
        """停止搜索引擎服务"""
        self.running = False
        
        # 等待线程结束
        if self.cache_cleanup_thread:
            self.cache_cleanup_thread.join(timeout=10)
        
        # 关闭资源
        self.mongo_client.close()
        self.producer.close()
        
        print("Realtime search engine stopped")
    
    def search(self, query_text=None, local_laplacian=None, limit=10, use_cache=True):
        """
        执行搜索查询
        
        参数:
        - query_text: 查询文本
        - local_laplacian: 局部拉普拉斯矩阵（可选）
        - limit: 返回结果数量限制
        - use_cache: 是否使用缓存
        
        返回:
        - 搜索结果列表
        """
        # 生成缓存键
        cache_key = None
        if use_cache and query_text:
            cache_key = f"text:{query_text}:limit:{limit}"
        
        # 检查缓存
        if use_cache and cache_key:
            with self.cache_lock:
                if cache_key in self.search_cache:
                    timestamp, results = self.search_cache[cache_key]
                    # 检查缓存是否仍然有效
                    if datetime.now() - timestamp < timedelta(seconds=self.config['cache_expiry_seconds']):
                        return results
        
        # 执行搜索
        start_time = time.time()
        results = self.mapping_manager.search_similar(
            holographic_vector=None,
            local_laplacian=local_laplacian,
            query_text=query_text,
            limit=limit
        )
        search_time = time.time() - start_time
        
        # 记录搜索日志
        log_entry = {
            'query_text': query_text,
            'has_local_laplacian': local_laplacian is not None,
            'limit': limit,
            'results_count': len(results),
            'search_time_ms': search_time * 1000,
            'timestamp': datetime.now()
        }
        self.search_logs_collection.insert_one(log_entry)
        
        # 发送搜索事件到Kafka
        self.producer.send(
            self.config['kafka_search_events_topic'],
            {
                'query_text': query_text,
                'results_count': len(results),
                'search_time_ms': search_time * 1000,
                'timestamp': datetime.now().isoformat()
            }
        )
        
        # 更新缓存
        if use_cache and cache_key:
            with self.cache_lock:
                self.search_cache[cache_key] = (datetime.now(), results)
        
        return results
    
    def get_search_stats(self, time_range_hours=24):
        """
        获取搜索统计信息
        
        参数:
        - time_range_hours: 统计范围（过去多少小时）
        
        返回:
        - 搜索统计信息
        """
        # 计算时间范围
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=time_range_hours)
        
        # 查询时间范围内的搜索日志
        logs = self.search_logs_collection.find({
            'timestamp': {'$gte': start_time, '$lte': end_time}
        })
        
        # 统计信息
        total_searches = 0
        total_time_ms = 0
        empty_results = 0
        query_counts = {}
        
        for log in logs:
            total_searches += 1
            total_time_ms += log.get('search_time_ms', 0)
            
            if log.get('results_count', 0) == 0:
                empty_results += 1
            
            query_text = log.get('query_text', '')
            if query_text:
                query_counts[query_text] = query_counts.get(query_text, 0) + 1
        
        # 计算平均搜索时间
        avg_time_ms = total_time_ms / total_searches if total_searches > 0 else 0
        
        # 找出最热门查询
        popular_queries = sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            'total_searches': total_searches,
            'empty_results_count': empty_results,
            'empty_results_percentage': (empty_results / total_searches * 100) if total_searches > 0 else 0,
            'avg_search_time_ms': avg_time_ms,
            'popular_queries': popular_queries,
            'time_range_hours': time_range_hours
        }