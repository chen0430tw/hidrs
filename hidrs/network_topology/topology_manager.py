"""
拓扑管理类，管理网络拓扑的构建、更新和分析
"""
import os
import json
import time
import threading
from datetime import datetime
import numpy as np
import networkx as nx
from pymongo import MongoClient
from kafka import KafkaConsumer, KafkaProducer

from .topology_builder import TopologyBuilder


class TopologyManager:
    """拓扑管理类，管理网络拓扑的构建、更新和分析"""
    
    def __init__(self, config_path="config/topology_manager_config.json"):
        """初始化拓扑管理器"""
        # 读取配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # 初始化MongoDB连接
        self.mongo_client = MongoClient(self.config['mongodb_uri'])
        self.db = self.mongo_client[self.config['mongodb_db']]
        self.feature_vectors_collection = self.db[self.config['feature_vectors_collection']]
        self.topology_collection = self.db[self.config['topology_collection']]
        
        # 初始化Kafka消费者，用于接收处理后的特征向量
        self.consumer = KafkaConsumer(
            self.config['kafka_input_topic'],
            bootstrap_servers=self.config['kafka_servers'],
            auto_offset_reset='latest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        
        # 初始化Kafka生产者，用于发送拓扑分析结果
        self.producer = KafkaProducer(
            bootstrap_servers=self.config['kafka_servers'],
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        # 初始化拓扑构建器
        self.topology_builder = TopologyBuilder(
            config_path=self.config['topology_builder_config_path']
        )
        
        # 拓扑更新线程
        self.update_thread = None
        self.running = False
        
        # 最近一次更新时间
        self.last_update_time = None
    
    def _update_worker(self):
        """拓扑更新线程，从MongoDB和Kafka获取数据更新拓扑"""
        while self.running:
            try:
                # 1. 从MongoDB获取特征向量
                if not self.last_update_time:
                    # 首次运行，获取所有特征向量
                    cursor = self.feature_vectors_collection.find({})
                else:
                    # 获取上次更新后的新特征向量
                    cursor = self.feature_vectors_collection.find({
                        'extraction_time': {'$gt': self.last_update_time}
                    })
                
                # 收集新的特征向量和节点ID
                new_feature_vectors = []
                new_node_ids = []
                new_node_urls = []
                
                for doc in cursor:
                    if 'feature_vector' in doc and 'original_id' in doc:
                        new_feature_vectors.append(np.array(doc['feature_vector']))
                        new_node_ids.append(str(doc['original_id']))
                        new_node_urls.append(doc.get('url', str(doc['original_id'])))
                
                # 2. 从Kafka消费消息
                for _ in range(self.config['max_kafka_messages_per_update']):
                    try:
                        # 非阻塞轮询
                        msg = next(self.consumer, None)
                        if msg is None:
                            break
                        
                        data = msg.value
                        if 'feature_vector' in data and 'url' in data:
                            new_feature_vectors.append(np.array(data['feature_vector']))
                            # 使用URL作为节点ID
                            new_node_ids.append(data['url'])
                            new_node_urls.append(data['url'])
                    except StopIteration:
                        break
                
                # 3. 更新拓扑
                if new_feature_vectors:
                    if not self.topology_builder.node_ids:
                        # 首次构建拓扑
                        self.topology_builder.build_topology_from_features(
                            new_feature_vectors, new_node_ids, new_node_urls
                        )
                    else:
                        # 更新现有拓扑
                        self.topology_builder.update_topology(
                            new_feature_vectors, new_node_ids, new_node_urls
                        )
                    
                    # 检测异常
                    is_anomaly, anomaly_info = self.topology_builder.detect_anomalies(
                        threshold=self.config['anomaly_threshold']
                    )
                    
                    # 保存分析结果到MongoDB
                    topology_info = {
                        'time': datetime.now(),
                        'node_count': len(self.topology_builder.node_ids),
                        'edge_count': self.topology_builder.graph.number_of_edges(),
                        'fiedler_value': self.topology_builder.fiedler_value,
                        'spectral_gap': self.topology_builder.spectral_gap,
                        'is_anomaly': is_anomaly,
                        'anomaly_info': anomaly_info,
                        'community_count': len(self.topology_builder.get_community_structure())
                    }
                    self.topology_collection.insert_one(topology_info)
                    
                    # 发送分析结果到Kafka
                    self.producer.send(
                        self.config['kafka_output_topic'],
                        topology_info
                    )
                    
                    # 如果检测到异常，发送警报
                    if is_anomaly:
                        alert_info = {
                            'time': datetime.now().isoformat(),
                            'type': 'topology_anomaly',
                            'fiedler_change': anomaly_info['fiedler_change'],
                            'current_fiedler': anomaly_info['current_fiedler'],
                            'threshold': anomaly_info['threshold'],
                            'node_count': topology_info['node_count'],
                            'severity': 'high' if anomaly_info['fiedler_change'] > 2*self.config['anomaly_threshold'] else 'medium'
                        }
                        self.producer.send(
                            self.config['kafka_alert_topic'],
                            alert_info
                        )
                        print(f"Anomaly detected! Fiedler change: {anomaly_info['fiedler_change']:.4f}")
                    
                    # 定期保存拓扑结构
                    if not hasattr(self, 'last_save_time') or \
                       (datetime.now() - self.last_save_time).total_seconds() > self.config['save_interval']:
                        self.topology_builder.save_topology(self.config['topology_save_path'])
                        self.last_save_time = datetime.now()
                    
                    # 更新最后更新时间
                    self.last_update_time = datetime.now()
                    
                    print(f"Updated topology: {topology_info['node_count']} nodes, Fiedler value: {topology_info['fiedler_value']:.6f}")
                
                # 等待下一次更新
                time.sleep(self.config['update_interval'])
                
            except Exception as e:
                print(f"Topology update error: {str(e)}")
                time.sleep(10)  # 出错后等待一段时间再继续
    
    def start(self):
        """启动拓扑管理服务"""
        self.running = True
        
        # 尝试加载已保存的拓扑结构
        if os.path.exists(self.config['topology_save_path']):
            try:
                self.topology_builder.load_topology(self.config['topology_save_path'])
                print("Loaded existing topology structure")
            except Exception as e:
                print(f"Error loading topology structure: {str(e)}")
        
        # 启动更新线程
        self.update_thread = threading.Thread(
            target=self._update_worker,
            daemon=True
        )
        self.update_thread.start()
        
        print("Topology manager started")
    
    def stop(self):
        """停止拓扑管理服务"""
        self.running = False
        
        # 等待线程结束
        if self.update_thread:
            self.update_thread.join(timeout=10)
        
        # 保存拓扑结构
        self.topology_builder.save_topology(self.config['topology_save_path'])
        
        # 关闭资源
        self.mongo_client.close()
        self.consumer.close()
        self.producer.close()
        
        print("Topology manager stopped")
    
    def get_topology_info(self):
        """获取当前拓扑信息"""
        return self.topology_builder.get_spectral_info()
    
    def get_community_structure(self):
        """获取社区结构"""
        return self.topology_builder.get_community_structure()
    
    def get_graph(self):
        """获取NetworkX图对象"""
        return self.topology_builder.graph