import logging
import time
import hashlib
import os
from elasticsearch import Elasticsearch, helpers
from elasticsearch.exceptions import NotFoundError
from conf.config import ElasticConfig, StorageConfig

logger = logging.getLogger(__name__)

class ESClient:
    """Elasticsearch客户端工具类"""
    
    def __init__(self):
        """初始化ES客户端连接"""
        self.es = None
        self.connect()
        
    def connect(self):
        """连接到Elasticsearch"""
        try:
            # 构建连接参数
            conn_params = {
                'hosts': [f"localhost:{ElasticConfig.ES_PORT}"]
            }
            
            # 如果配置了用户名和密码，添加到连接参数
            if ElasticConfig.ES_USERNAME and ElasticConfig.ES_PASSWORD:
                conn_params['http_auth'] = (ElasticConfig.ES_USERNAME, ElasticConfig.ES_PASSWORD)
            
            self.es = Elasticsearch(**conn_params)
            
            # 检查连接状态
            if not self.es.ping():
                logger.error("无法连接到Elasticsearch")
                raise ConnectionError("无法连接到Elasticsearch")
                
            logger.info("成功连接到Elasticsearch")
            
        except Exception as e:
            logger.error(f"Elasticsearch连接失败: {str(e)}")
            raise
            
    def create_index_if_not_exists(self, index_name=None):
        """如果索引不存在则创建"""
        if not index_name:
            index_name = ElasticConfig.ES_INDEX
            
        try:
            if not self.es.indices.exists(index=index_name):
                self.es.indices.create(
                    index=index_name,
                    body=ElasticConfig.ES_MAPPING
                )
                logger.info(f"创建索引 {index_name} 成功")
        except Exception as e:
            logger.error(f"创建索引失败: {str(e)}")
            raise
    
    def get_index_name(self, doc):
        """基于分区策略获取索引名称"""
        if not StorageConfig.USE_PARTITIONING:
            return ElasticConfig.ES_INDEX
            
        base_name = ElasticConfig.ES_INDEX
        
        if StorageConfig.PARTITION_STRATEGY == 'source' and 'source' in doc:
            return f"{base_name}_{doc['source'].lower()}"
        elif StorageConfig.PARTITION_STRATEGY == 'time' and 'xtime' in doc:
            return f"{base_name}_{doc['xtime']}"
        elif StorageConfig.PARTITION_STRATEGY == 'both':
            if 'source' in doc and 'xtime' in doc:
                return f"{base_name}_{doc['source'].lower()}_{doc['xtime']}"
        
        return base_name
            
    def bulk_insert(self, docs, source_file=None):
        """批量插入文档"""
        try:
            # 应用存储模式
            if StorageConfig.STORAGE_MODE == 'reference' and source_file:
                processed_docs = []
                for i, doc in enumerate(docs):
                    ref_doc = self._create_reference_doc(doc, source_file, i)
                    processed_docs.append(ref_doc)
                docs = processed_docs
            
            # 创建操作列表
            actions = []
            for doc in docs:
                index_name = self.get_index_name(doc)
                
                # 确保索引存在
                self.create_index_if_not_exists(index_name)
                
                actions.append({
                    "_index": index_name,
                    "_source": doc
                })
            
            # 执行批量插入
            success, failed = helpers.bulk(
                self.es, 
                actions, 
                chunk_size=ElasticConfig.BULK_SIZE,
                max_retries=3,
                raise_on_error=False
            )
            
            logger.info(f"批量插入完成: 成功 {success} 条，失败 {len(failed) if isinstance(failed, list) else 0} 条")
            return success, failed
        except Exception as e:
            logger.error(f"批量插入失败: {str(e)}")
            raise
    
    def _create_reference_doc(self, doc, source_file, line_number):
        """创建引用模式的文档"""
        reference_doc = {
            # 仅包含搜索必要的字段
            "user": doc.get("user", ""),
            "email": doc.get("email", ""),
            "suffix_email": doc.get("suffix_email", ""),
            "password": doc.get("password", ""),  # 添加密码字段用于测试
            "passwordHash": doc.get("passwordHash", ""),
            "source": doc.get("source", ""),
            "xtime": doc.get("xtime", ""),
            "create_time": doc.get("create_time", time.strftime('%Y/%m/%d %H:%M:%S', time.localtime())),
            # 添加引用信息
            "reference": {
                "file": os.path.basename(source_file),
                "line": line_number + 1
            }
        }
        return reference_doc
            
    def search(self, query, limit=10, skip=0, index=None):
        """执行搜索"""
        try:
            index_name = index if index else ElasticConfig.ES_INDEX
            
            # 如果启用了分区，则搜索所有相关索引
            if StorageConfig.USE_PARTITIONING and not index:
                index_name = f"{ElasticConfig.ES_INDEX}*"
            
            result = self.es.search(
                index=index_name,
                body=query,
                size=limit,
                from_=skip
            )
            
            hits = result.get('hits', {})
            total = hits.get('total', {}).get('value', 0)
            docs = [hit['_source'] for hit in hits.get('hits', [])]
            
            return docs, total
        except Exception as e:
            logger.error(f"搜索失败: {str(e)}")
            raise
            
    def count(self, query, index=None):
        """获取匹配查询的文档数量"""
        try:
            index_name = index if index else ElasticConfig.ES_INDEX
            
            # 如果启用了分区，则搜索所有相关索引
            if StorageConfig.USE_PARTITIONING and not index:
                index_name = f"{ElasticConfig.ES_INDEX}*"
                
            result = self.es.count(
                index=index_name,
                body=query
            )
            return result.get('count', 0)
        except Exception as e:
            logger.error(f"Count查询失败: {str(e)}")
            raise
            
    def aggregate(self, agg_query, index=None):
        """执行聚合查询"""
        try:
            index_name = index if index else ElasticConfig.ES_INDEX
            
            # 如果启用了分区，则搜索所有相关索引
            if StorageConfig.USE_PARTITIONING and not index:
                index_name = f"{ElasticConfig.ES_INDEX}*"
            
            result = self.es.search(
                index=index_name,
                body=agg_query,
                size=0
            )
            
            return result.get('aggregations', {})
        except Exception as e:
            logger.error(f"聚合查询失败: {str(e)}")
            raise
    
    def get_document(self, doc_id, index=None):
        """获取单个文档"""
        try:
            index_name = index if index else ElasticConfig.ES_INDEX
            
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
            
    def insert_doc(self, doc, source_file=None, line_number=None):
        """插入单个文档"""
        try:
            # 如果包含email字段但不包含suffix_email，则添加
            if 'email' in doc and 'suffix_email' not in doc:
                email_parts = doc['email'].split('@')
                if len(email_parts) > 1:
                    doc['suffix_email'] = email_parts[1].lower()
                    doc['user'] = doc.get('user', email_parts[0])
                    
            # 如果有password但没有passwordHash，则计算
            if 'password' in doc and 'passwordHash' not in doc:
                doc['passwordHash'] = hashlib.md5(doc['password'].encode('utf-8')).hexdigest()
                
            # 添加创建时间
            if 'create_time' not in doc:
                doc['create_time'] = time.strftime('%Y/%m/%d %H:%M:%S', time.localtime())
            
            # 应用存储模式
            if StorageConfig.STORAGE_MODE == 'reference' and source_file:
                doc = self._create_reference_doc(doc, source_file, line_number or 0)
                
            # 获取索引名称
            index_name = self.get_index_name(doc)
            
            # 确保索引存在
            self.create_index_if_not_exists(index_name)
                
            # 检查文档是否已存在（基于用户名和邮箱）
            if 'user' in doc and 'email' in doc:
                exists_query = {
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"user": doc['user']}},
                                {"term": {"email": doc['email']}}
                            ]
                        }
                    }
                }
                
                count = self.count(exists_query, index_name)
                if count > 0:
                    logger.info(f"文档已存在: {doc['user']} {doc['email']}")
                    return False, f"{doc['user']} {doc['email']} already exists."
            
            # 插入文档
            self.es.index(
                index=index_name,
                body=doc
            )
            
            logger.info(f"插入文档成功: {doc.get('user', 'unknown')} {doc.get('email', 'unknown')}")
            return True, "Created successfully"
            
        except Exception as e:
            logger.error(f"插入文档失败: {str(e)}")
            raise