"""
优化的Elasticsearch客户端
支持引用模式和数据分区
"""
import os
import time
import hashlib
import logging
from elasticsearch import Elasticsearch, helpers
from elasticsearch.exceptions import NotFoundError
from typing import Dict, List, Tuple, Any, Optional

# 设置日志
logger = logging.getLogger(__name__)

class ESClient:
    """优化的Elasticsearch客户端"""
    
    def __init__(self):
        """初始化ES客户端"""
        # 从环境变量或配置中获取参数
        self.host = os.getenv('ES_HOST', 'localhost')
        self.port = int(os.getenv('ES_PORT', 9200))
        self.index_name = os.getenv('ES_INDEX', 'socialdb')
        self.username = os.getenv('ES_USERNAME', '')
        self.password = os.getenv('ES_PASSWORD', '')
        
        # 连接到ES
        self.es = self._connect()
        
        # 缓存
        self._cache = {}
        
    def _connect(self):
        """连接到Elasticsearch"""
        try:
            # 构建连接参数
            conn_params = {
                'hosts': [f"{self.host}:{self.port}"]
            }
            
            # 如果配置了用户名和密码，添加到连接参数
            if self.username and self.password:
                conn_params['http_auth'] = (self.username, self.password)
            
            # 超时设置
            conn_params['timeout'] = 30
            
            es = Elasticsearch(**conn_params)
            
            # 检查连接状态
            if not es.ping():
                logger.error("无法连接到Elasticsearch")
                raise ConnectionError("无法连接到Elasticsearch")
                
            logger.info(f"成功连接到Elasticsearch: {self.host}:{self.port}")
            return es
            
        except Exception as e:
            logger.error(f"Elasticsearch连接失败: {str(e)}")
            raise
    
    def create_index_if_not_exists(self, index_name=None):
        """如果索引不存在则创建"""
        try:
            index_name = index_name or self.index_name
            
            if not self.es.indices.exists(index=index_name):
                # 索引映射
                mapping = {
                    "settings": {
                        "number_of_shards": 5,
                        "number_of_replicas": 0,
                        "index.codec": "best_compression",
                        "index.refresh_interval": "30s"
                    },
                    "mappings": {
                        "properties": {
                            "user": {"type": "keyword", "doc_values": False},
                            "email": {"type": "keyword", "doc_values": False},
                            "password": {"type": "keyword", "doc_values": False, "index": True},
                            "passwordHash": {"type": "keyword", "doc_values": False},
                            "source": {"type": "keyword"},
                            "xtime": {"type": "keyword"},
                            "suffix_email": {"type": "keyword"},
                            "create_time": {"type": "date", "format": "yyyy/MM/dd HH:mm:ss||yyyy/MM/dd||epoch_millis"},
                            "reference": {
                                "properties": {
                                    "file": {"type": "keyword"},
                                    "line": {"type": "integer"}
                                }
                            }
                        }
                    }
                }
                
                # 创建索引
                self.es.indices.create(index=index_name, body=mapping)
                logger.info(f"创建索引 {index_name} 成功")
                
            return True
        except Exception as e:
            logger.error(f"创建索引失败: {str(e)}")
            return False
    
    def get_index_name(self, doc):
        """基于分区策略获取索引名称"""
        # 获取分区设置
        use_partitioning = os.getenv('USE_PARTITIONING', 'false').lower() in ('true', '1', 't')
        partition_strategy = os.getenv('PARTITION_STRATEGY', 'source')
        
        if not use_partitioning:
            return self.index_name
            
        base_name = self.index_name
        
        # 根据策略生成索引名称
        if partition_strategy == 'source' and 'source' in doc:
            return f"{base_name}_{doc['source'].lower()}"
        elif partition_strategy == 'time' and 'xtime' in doc:
            return f"{base_name}_{doc['xtime']}"
        elif partition_strategy == 'both':
            if 'source' in doc and 'xtime' in doc:
                return f"{base_name}_{doc['source'].lower()}_{doc['xtime']}"
        
        return base_name
    
    def bulk_insert(self, docs):
        """批量插入文档"""
        if not docs:
            return 0, 0
            
        try:
            # 创建操作列表
            actions = []
            
            for doc in docs:
                # 获取索引名称
                index_name = self.get_index_name(doc)
                
                # 确保索引存在
                self.create_index_if_not_exists(index_name)
                
                # 添加操作
                actions.append({
                    "_index": index_name,
                    "_source": doc
                })
            
            # 执行批量插入
            success, failed = helpers.bulk(
                self.es, 
                actions, 
                chunk_size=1000,
                max_retries=3,
                raise_on_error=False
            )
            
            logger.debug(f"批量插入完成: 成功 {success} 条，失败 {len(failed) if isinstance(failed, list) else 0} 条")
            return success, failed
            
        except Exception as e:
            logger.error(f"批量插入失败: {str(e)}")
            return 0, len(docs)
    
    def search(self, query, limit=10, skip=0, index=None):
        """执行搜索"""
        try:
            # 确定索引名称
            index_name = index or self.index_name
            
            # 是否使用分区
            use_partitioning = os.getenv('USE_PARTITIONING', 'false').lower() in ('true', '1', 't')
            
            # 如果启用了分区，搜索所有相关索引
            if use_partitioning and not index:
                index_name = f"{self.index_name}*"
            
            # 缓存键
            cache_key = hashlib.md5(f"{index_name}:{str(query)}:{limit}:{skip}".encode()).hexdigest()
            
            # 检查缓存
            if cache_key in self._cache:
                return self._cache[cache_key]
            
            # 执行搜索
            result = self.es.search(
                index=index_name,
                body=query,
                size=limit,
                from_=skip
            )
            
            # 提取结果
            hits = result.get('hits', {})
            total = hits.get('total', {})
            
            # 兼容不同ES版本
            if isinstance(total, dict):
                total_count = total.get('value', 0)
            else:
                total_count = total
                
            # 提取文档
            docs = [hit['_source'] for hit in hits.get('hits', [])]
            
            # 缓存结果
            self._cache[cache_key] = (docs, total_count)
            
            return docs, total_count
            
        except Exception as e:
            logger.error(f"搜索失败: {str(e)}")
            return [], 0
    
    def count(self, query, index=None):
        """获取匹配查询的文档数量"""
        try:
            # 确定索引名称
            index_name = index or self.index_name
            
            # 是否使用分区
            use_partitioning = os.getenv('USE_PARTITIONING', 'false').lower() in ('true', '1', 't')
            
            # 如果启用了分区，搜索所有相关索引
            if use_partitioning and not index:
                index_name = f"{self.index_name}*"
            
            # 执行计数查询
            result = self.es.count(
                index=index_name,
                body=query
            )
            
            return result.get('count', 0)
            
        except Exception as e:
            logger.error(f"计数查询失败: {str(e)}")
            return 0
    
    def aggregate(self, agg_query, index=None):
        """执行聚合查询"""
        try:
            # 确定索引名称
            index_name = index or self.index_name
            
            # 是否使用分区
            use_partitioning = os.getenv('USE_PARTITIONING', 'false').lower() in ('true', '1', 't')
            
            # 如果启用了分区，搜索所有相关索引
            if use_partitioning and not index:
                index_name = f"{self.index_name}*"
            
            # 执行聚合查询
            result = self.es.search(
                index=index_name,
                body=agg_query,
                size=0
            )
            
            return result.get('aggregations', {})
            
        except Exception as e:
            logger.error(f"聚合查询失败: {str(e)}")
            return {}
    
    def get_doc(self, doc_id, index=None):
        """获取单个文档"""
        try:
            # 确定索引名称
            index_name = index or self.index_name
            
            # 执行获取文档
            result = self.es.get(
                index=index_name,
                id=doc_id
            )
            
            return result.get('_source', {})
            
        except NotFoundError:
            return None
        except Exception as e:
            logger.error(f"获取文档失败: {str(e)}")
            return None
    
    def insert_doc(self, doc, index=None):
        """插入单个文档"""
        try:
            # 确定索引名称
            index_name = index or self.get_index_name(doc)
            
            # 确保索引存在
            self.create_index_if_not_exists(index_name)
            
            # 插入文档
            result = self.es.index(
                index=index_name,
                body=doc
            )
            
            return True, result.get('_id')
            
        except Exception as e:
            logger.error(f"插入文档失败: {str(e)}")
            return False, str(e)
    
    def clear_cache(self):
        """清除缓存"""
        self._cache = {}