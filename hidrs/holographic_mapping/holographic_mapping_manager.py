"""
全息映射管理类，管理局部拉普拉斯矩阵到全息表示的映射和索引构建
"""
import os
import json
import time
import threading
import numpy as np
from datetime import datetime
from pymongo import MongoClient
from kafka import KafkaConsumer, KafkaProducer

from .holographic_mapper import HolographicMapper
from .holographic_index import HolographicIndex


class HolographicMappingManager:
    """全息映射管理类，管理局部拉普拉斯矩阵到全息表示的映射和索引构建"""
    
    def __init__(self, config_path="config/holographic_mapping_manager_config.json"):
        """初始化全息映射管理器"""
        # 读取配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # 初始化MongoDB连接
        self.mongo_client = MongoClient(self.config['mongodb_uri'])
        self.db = self.mongo_client[self.config['mongodb_db']]
        self.topology_collection = self.db[self.config['topology_collection']]
        self.holographic_collection = self.db[self.config['holographic_collection']]
        
        # 初始化Kafka消费者，用于接收拓扑分析结果
        self.consumer = KafkaConsumer(
            self.config['kafka_input_topic'],
            bootstrap_servers=self.config['kafka_servers'],
            auto_offset_reset='latest',
            group_id='holographic_mapping_group',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        
        # 初始化Kafka生产者，用于发送全息映射结果
        self.producer = KafkaProducer(
            bootstrap_servers=self.config['kafka_servers'],
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        # 初始化全息映射器
        self.mapper = HolographicMapper(
            config_path=self.config['holographic_mapper_config_path']
        )
        
        # 初始化全息索引
        self.index = HolographicIndex(
            config_path=self.config['holographic_index_config_path']
        )
        
        # 缓存全局Fiedler向量
        self.global_fiedler_vector = None
        
        # 映射线程
        self.mapping_thread = None
        self.running = False
    
    def _mapping_worker(self):
        """全息映射线程，从拓扑分析结果生成全息表示并构建索引"""
        while self.running:
            try:
                # 从Kafka消费拓扑分析结果
                for message in self.consumer:
                    if not self.running:
                        break
                    
                    try:
                        # 获取拓扑分析数据
                        topology_data = message.value
                        
                        # 从MongoDB获取完整的拓扑信息
                        topology_id = topology_data.get('_id') or topology_data.get('id')
                        if topology_id:
                            topology_doc = self.topology_collection.find_one({"_id": topology_id})
                            if topology_doc:
                                topology_data = topology_doc
                        
                        # 提取全局Fiedler向量
                        if 'fiedler_vector' in topology_data:
                            self.global_fiedler_vector = np.array(topology_data['fiedler_vector'])
                        
                        # 获取局部拉普拉斯矩阵
                        if 'local_laplacian_matrices' in topology_data:
                            local_matrices = topology_data['local_laplacian_matrices']
                            
                            # 处理多尺度全息映射
                            for loc_id, matrices in local_matrices.items():
                                # 转换为NumPy数组
                                laplacian_matrices = [np.array(matrix) for matrix in matrices]
                                
                                # 执行多尺度全息映射
                                holographic_rep = self.mapper.map_multi_scale(
                                    laplacian_matrices,
                                    self.global_fiedler_vector
                                )
                                
                                # 获取节点元数据
                                metadata = topology_data.get('nodes_metadata', {}).get(loc_id, {})
                                
                                # 添加聚类信息
                                cluster_id = topology_data.get('cluster_labels', {}).get(loc_id, -1)
                                if 'cluster_id' not in metadata:
                                    metadata['cluster_id'] = cluster_id
                                
                                # 索引全息表示
                                self.index.index_holographic_representation(
                                    loc_id,
                                    holographic_rep,
                                    metadata
                                )
                                
                                # 保存到MongoDB
                                holographic_doc = {
                                    'node_id': loc_id,
                                    'holographic_representation': holographic_rep.tolist(),
                                    'metadata': metadata,
                                    'topology_id': topology_id,
                                    'creation_time': datetime.now()
                                }
                                self.holographic_collection.insert_one(holographic_doc)
                                
                                # 发送到Kafka
                                self.producer.send(
                                    self.config['kafka_output_topic'],
                                    {
                                        'node_id': loc_id,
                                        'holographic_vector_length': len(holographic_rep),
                                        'cluster_id': cluster_id,
                                        'mapping_time': datetime.now().isoformat()
                                    }
                                )
                    
                    except Exception as e:
                        print(f"Error processing topology data: {str(e)}")
            
            except Exception as e:
                print(f"Holographic mapping error: {str(e)}")
                time.sleep(10)  # 出错后等待一段时间再继续
    
    def start(self):
        """启动全息映射服务"""
        self.running = True
        
        # 启动映射线程
        self.mapping_thread = threading.Thread(
            target=self._mapping_worker,
            daemon=True
        )
        self.mapping_thread.start()
        
        print("Holographic mapping manager started")
    
    def stop(self):
        """停止全息映射服务"""
        self.running = False
        
        # 等待线程结束
        if self.mapping_thread:
            self.mapping_thread.join(timeout=10)
        
        # 关闭资源
        self.mongo_client.close()
        self.consumer.close()
        self.producer.close()
        
        print("Holographic mapping manager stopped")
    
    def map_local_laplacian(self, local_laplacian, metadata=None):
        """
        手动执行局部拉普拉斯矩阵到全息表示的映射
        
        参数:
        - local_laplacian: 局部拉普拉斯矩阵
        - metadata: 节点元数据
        
        返回:
        - holographic_representation: 全息表示向量
        """
        # 执行全息映射
        holographic_rep = self.mapper.map_local_to_global(
            local_laplacian,
            self.global_fiedler_vector
        )
        
        # 如果提供了元数据和ID，索引全息表示
        if metadata and 'id' in metadata:
            self.index.index_holographic_representation(
                metadata['id'],
                holographic_rep,
                metadata
            )
            
            # 保存到MongoDB
            holographic_doc = {
                'node_id': metadata['id'],
                'holographic_representation': holographic_rep.tolist(),
                'metadata': metadata,
                'creation_time': datetime.now()
            }
            self.holographic_collection.insert_one(holographic_doc)
        
        return holographic_rep
    
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
        # 如果提供了局部拉普拉斯矩阵但没有全息向量，先进行映射
        if local_laplacian is not None and holographic_vector is None:
            holographic_vector = self.mapper.map_local_to_global(
                local_laplacian,
                self.global_fiedler_vector
            )
        
        # 执行搜索
        if holographic_vector is not None and query_text:
            # 混合搜索
            return self.index.hybrid_search(
                query_text,
                holographic_vector,
                text_weight=self.config['text_search_weight'],
                vector_weight=self.config['vector_search_weight'],
                limit=limit
            )
        elif holographic_vector is not None:
            # 向量相似性搜索
            return self.index.search_similar(holographic_vector, limit=limit)
        elif query_text:
            # 全文搜索
            return self.index.full_text_search(query_text, limit=limit)
        else:
            # 未提供搜索条件
            return []