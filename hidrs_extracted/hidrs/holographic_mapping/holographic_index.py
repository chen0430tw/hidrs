"""
全息索引类，负责将全息表示向量构建为可查询的索引
"""
import json
from datetime import datetime
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from .holographic_mapper import HolographicMapper


class HolographicIndex:
    """全息索引类，负责将全息表示向量构建为可查询的索引"""
    
    def __init__(self, config_path="config/holographic_index_config.json"):
        """初始化全息索引构建器"""
        # 读取配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # 初始化全息映射器（确保这一行在使用mapper之前执行）
        self.mapper = HolographicMapper(config_path=self.config['holographic_mapper_config_path'])
        
        # 初始化Elasticsearch客户端
        self.es = Elasticsearch(
            self.config['elasticsearch_hosts'],
            basic_auth=(
                self.config.get('elasticsearch_username', ''),
                self.config.get('elasticsearch_password', '')
            ),
            timeout=30
        )
        
        # 索引名称
        self.index_name = self.config['index_name']
        
        # 确保索引存在
        self._ensure_index()
    
    def _ensure_index(self):
        """确保索引存在，不存在则创建"""
        if not self.es.indices.exists(index=self.index_name):
            # 创建索引
            index_settings = {
                "settings": {
                    "number_of_shards": self.config['number_of_shards'],
                    "number_of_replicas": self.config['number_of_replicas']
                },
                "mappings": {
                    "properties": {
                        "url": {"type": "keyword"},
                        "title": {"type": "text", "analyzer": "standard"},
                        "content": {"type": "text", "analyzer": "standard"},
                        "holographic_vector": {"type": "dense_vector", "dims": self.mapper.output_dim},
                        "cluster_id": {"type": "integer"},
                        "extraction_time": {"type": "date"},
                        "fiedler_component": {"type": "float"}
                    }
                }
            }
            self.es.indices.create(index=self.index_name, body=index_settings)
            print(f"Created index '{self.index_name}'")
    
    def index_holographic_representation(self, id, holographic_vector, metadata):
        """
        将全息表示向量索引到Elasticsearch
        
        参数:
        - id: 文档ID
        - holographic_vector: 全息表示向量
        - metadata: 元数据字典，包含url、title、content、cluster_id等
        """
        # 准备索引文档
        document = {
            "holographic_vector": holographic_vector.tolist(),
            "extraction_time": datetime.now().isoformat(),
            **metadata
        }
        
        # 索引文档
        self.es.index(index=self.index_name, id=id, document=document)
    
    def bulk_index_holographic_representations(self, items):
        """
        批量索引全息表示向量
        
        参数:
        - items: 列表，每个元素是(id, holographic_vector, metadata)元组
        """
        actions = []
        for id, holographic_vector, metadata in items:
            action = {
                "_index": self.index_name,
                "_id": id,
                "_source": {
                    "holographic_vector": holographic_vector.tolist(),
                    "extraction_time": datetime.now().isoformat(),
                    **metadata
                }
            }
            actions.append(action)
        
        if actions:
            success, failed = bulk(self.es, actions, refresh=True)
            print(f"Bulk indexed {success} documents, {len(failed)} failed")
            return success, len(failed)
        return 0, 0
    
    def search_similar(self, holographic_vector, limit=10):
        """
        搜索与给定全息表示向量相似的文档
        
        参数:
        - holographic_vector: 全息表示向量
        - limit: 返回结果数量限制
        
        返回:
        - 相似文档列表
        """
        query = {
            "script_score": {
                "query": {"match_all": {}},
                "script": {
                    "source": "cosineSimilarity(params.query_vector, 'holographic_vector') + 1.0",
                    "params": {"query_vector": holographic_vector.tolist()}
                }
            }
        }
        
        response = self.es.search(
            index=self.index_name,
            query=query,
            size=limit,
            sort=[{"_score": {"order": "desc"}}]
        )
        
        results = []
        for hit in response['hits']['hits']:
            results.append({
                "id": hit["_id"],
                "score": hit["_score"],
                "url": hit["_source"].get("url", ""),
                "title": hit["_source"].get("title", ""),
                "cluster_id": hit["_source"].get("cluster_id", -1)
            })
        
        return results
    
    def search_by_cluster(self, cluster_id, limit=100):
        """
        搜索特定聚类中的文档
        
        参数:
        - cluster_id: 聚类ID
        - limit: 返回结果数量限制
        
        返回:
        - 聚类中的文档列表
        """
        query = {
            "term": {"cluster_id": cluster_id}
        }
        
        response = self.es.search(
            index=self.index_name,
            query=query,
            size=limit
        )
        
        results = []
        for hit in response['hits']['hits']:
            results.append({
                "id": hit["_id"],
                "url": hit["_source"].get("url", ""),
                "title": hit["_source"].get("title", "")
            })
        
        return results
    
    def full_text_search(self, query_text, limit=10):
        """
        执行全文搜索
        
        参数:
        - query_text: 查询文本
        - limit: 返回结果数量限制
        
        返回:
        - 匹配文档列表
        """
        query = {
            "multi_match": {
                "query": query_text,
                "fields": ["title^3", "content"]
            }
        }
        
        response = self.es.search(
            index=self.index_name,
            query=query,
            size=limit
        )
        
        results = []
        for hit in response['hits']['hits']:
            results.append({
                "id": hit["_id"],
                "score": hit["_score"],
                "url": hit["_source"].get("url", ""),
                "title": hit["_source"].get("title", "")
            })
        
        return results
    
    def hybrid_search(self, query_text, holographic_vector, text_weight=0.3, vector_weight=0.7, limit=10):
        """
        混合搜索：结合全文搜索和向量相似性搜索
        
        参数:
        - query_text: 查询文本
        - holographic_vector: 全息表示向量
        - text_weight: 文本搜索权重
        - vector_weight: 向量搜索权重
        - limit: 返回结果数量限制
        
        返回:
        - 混合搜索结果列表
        """
        # 构建混合查询
        query = {
            "script_score": {
                "query": {
                    "multi_match": {
                        "query": query_text,
                        "fields": ["title^3", "content"]
                    }
                },
                "script": {
                    "source": f"""
                        {text_weight} * _score + 
                        {vector_weight} * (cosineSimilarity(params.query_vector, 'holographic_vector') + 1.0)
                    """,
                    "params": {"query_vector": holographic_vector.tolist()}
                }
            }
        }
        
        response = self.es.search(
            index=self.index_name,
            query=query,
            size=limit,
            sort=[{"_score": {"order": "desc"}}]
        )
        
        results = []
        for hit in response['hits']['hits']:
            results.append({
                "id": hit["_id"],
                "score": hit["_score"],
                "url": hit["_source"].get("url", ""),
                "title": hit["_source"].get("title", ""),
                "cluster_id": hit["_source"].get("cluster_id", -1)
            })
        
        return results
    
    def delete_document(self, id):
        """删除指定ID的文档"""
        self.es.delete(index=self.index_name, id=id)
    
    def update_document(self, id, holographic_vector=None, metadata=None):
        """更新指定ID的文档"""
        update_doc = {}
        
        if holographic_vector is not None:
            update_doc["holographic_vector"] = holographic_vector.tolist()
        
        if metadata:
            update_doc.update(metadata)
        
        if update_doc:
            self.es.update(
                index=self.index_name,
                id=id,
                doc=update_doc
            )