"""
数据处理与特征抽取层 - 整合预处理、特征提取和降维功能
"""
import os
import json
import time
import threading
import numpy as np
from datetime import datetime
from pymongo import MongoClient
from kafka import KafkaConsumer, KafkaProducer

from .text_preprocessor import TextPreprocessor
from .feature_extractor import FeatureExtractor
from .dimensionality_reducer import DimensionalityReducer


class DataProcessingLayer:
    """数据处理与特征抽取层，整合预处理、特征提取和降维功能"""
    
    def __init__(self, config_path="config/data_processing_config.json"):
        # 读取配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # 初始化MongoDB连接
        self.mongo_client = MongoClient(self.config['mongodb_uri'])
        self.db = self.mongo_client[self.config['mongodb_db']]
        self.raw_data_collection = self.db[self.config['raw_data_collection']]
        self.processed_data_collection = self.db[self.config['processed_data_collection']]
        self.feature_vectors_collection = self.db[self.config['feature_vectors_collection']]
        
        # 初始化Kafka消费者，用于接收实时数据
        self.consumer = KafkaConsumer(
            self.config['kafka_input_topic'],
            bootstrap_servers=self.config['kafka_servers'],
            auto_offset_reset='latest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        
        # 初始化Kafka生产者，用于发送处理后的数据
        self.producer = KafkaProducer(
            bootstrap_servers=self.config['kafka_servers'],
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        # 初始化组件
        self.text_preprocessor = TextPreprocessor()
        self.feature_extractor = FeatureExtractor(
            model_type=self.config['feature_extractor_model'],
            config_path=self.config['feature_extractor_config_path']
        )
        self.dimension_reducer = DimensionalityReducer(
            method=self.config['dimension_reduction_method'],
            config_path=self.config['dimension_reducer_config_path']
        )
        
        # 处理线程
        self.batch_processing_thread = None
        self.stream_processing_thread = None
        self.running = False
        
        # 数据缓存
        self.feature_vectors_cache = []
    
    def _batch_processing_worker(self):
        """批处理工作线程，处理MongoDB中的历史数据"""
        while self.running:
            try:
                # 获取未处理的数据
                unprocessed_docs = self.raw_data_collection.find({
                    'processed': {'$ne': True}
                }).limit(self.config['batch_size'])
                
                docs_count = 0
                feature_vectors = []
                
                for doc in unprocessed_docs:
                    docs_count += 1
                    doc_id = doc['_id']
                    
                    # 提取内容
                    content = doc.get('content', '')
                    
                    # 预处理文本
                    cleaned_text = self.text_preprocessor.clean_text(content)
                    
                    # 提取特征向量
                    feature_vector = self.feature_extractor.extract_features(cleaned_text)
                    
                    # 保存处理后的数据
                    self.processed_data_collection.insert_one({
                        'original_id': doc_id,
                        'url': doc.get('url', ''),
                        'title': doc.get('title', ''),
                        'cleaned_text': cleaned_text,
                        'processing_time': datetime.now()
                    })
                    
                    # 保存特征向量
                    self.feature_vectors_collection.insert_one({
                        'original_id': doc_id,
                        'url': doc.get('url', ''),
                        'title': doc.get('title', ''),
                        'feature_vector': feature_vector.tolist(),
                        'extraction_time': datetime.now()
                    })
                    
                    # 缓存特征向量用于降维
                    feature_vectors.append(feature_vector)
                    
                    # 标记原始数据为已处理
                    self.raw_data_collection.update_one(
                        {'_id': doc_id},
                        {'$set': {'processed': True}}
                    )
                
                # 更新缓存
                if feature_vectors:
                    self.feature_vectors_cache.extend(feature_vectors)
                    
                    # 如果缓存足够大，进行降维训练
                    if len(self.feature_vectors_cache) >= self.config['min_samples_for_reduction']:
                        # 使用所有缓存的特征向量进行降维训练
                        data_array = np.array(self.feature_vectors_cache)
                        try:
                            # 尝试训练或更新降维模型
                            if not self.dimension_reducer.fitted:
                                self.dimension_reducer.fit(data_array)
                                # 保存模型
                                self.dimension_reducer.save_model(self.config['reducer_model_path'])
                            else:
                                # 增量更新（如果支持）或重新训练
                                if hasattr(self.dimension_reducer.reducer, 'partial_fit'):
                                    # 部分模型支持增量学习
                                    self.dimension_reducer.reducer.partial_fit(data_array)
                                else:
                                    # 不支持增量学习时，重新训练
                                    self.dimension_reducer.fit(data_array)
                                # 更新保存的模型
                                self.dimension_reducer.save_model(self.config['reducer_model_path'])
                        except Exception as e:
                            print(f"Error during dimension reduction: {str(e)}")
                        
                        # 清空缓存
                        self.feature_vectors_cache = []
                
                if docs_count == 0:
                    # 没有新数据，等待一段时间
                    time.sleep(self.config['batch_processing_interval'])
                else:
                    print(f"Batch processed {docs_count} documents")
            
            except Exception as e:
                print(f"Batch processing error: {str(e)}")
                time.sleep(60)  # 出错后等待一段时间再继续
    
    def _stream_processing_worker(self):
        """流处理工作线程，实时处理Kafka中的数据"""
        while self.running:
            try:
                # 消费消息
                for message in self.consumer:
                    if not self.running:
                        break
                    
                    try:
                        # 获取消息值
                        data = message.value
                        
                        # 检查消息是否包含必要字段
                        if 'url' not in data or 'title' not in data:
                            continue
                        
                        # 获取MongoDB中对应的原始数据
                        doc = self.raw_data_collection.find_one({'url': data['url']})
                        
                        if doc and 'content' in doc:
                            # 预处理文本
                            cleaned_text = self.text_preprocessor.clean_text(doc['content'])
                            
                            # 提取特征向量
                            feature_vector = self.feature_extractor.extract_features(cleaned_text)
                            
                            # 如果降维模型已经训练好，应用降维
                            if self.dimension_reducer.fitted:
                                # 将特征向量转换为二维数组（必须是二维的，即使只有一个样本）
                                reshaped_vector = feature_vector.reshape(1, -1)
                                reduced_vector = self.dimension_reducer.transform(reshaped_vector)
                                reduced_vector = reduced_vector[0]  # 取出降维后的向量
                            else:
                                reduced_vector = None
                            
                            # 将处理结果发送到Kafka
                            result = {
                                'url': data['url'],
                                'title': data['title'],
                                'feature_vector_dim': len(feature_vector),
                                'processing_time': datetime.now().isoformat()
                            }
                            
                            if reduced_vector is not None:
                                result['reduced_vector'] = reduced_vector.tolist()
                            
                            self.producer.send(
                                self.config['kafka_output_topic'],
                                result
                            )
                            
                            print(f"Stream processed: {data['url']}")
                    
                    except Exception as e:
                        print(f"Error processing message: {str(e)}")
            
            except Exception as e:
                print(f"Stream processing error: {str(e)}")
                time.sleep(10)  # 出错后等待一段时间再继续
    
    def start(self):
        """启动数据处理服务"""
        self.running = True
        
        # 尝试加载已训练的降维模型
        if os.path.exists(self.config['reducer_model_path']):
            try:
                self.dimension_reducer.load_model(self.config['reducer_model_path'])
                print("Loaded existing dimension reducer model")
            except Exception as e:
                print(f"Error loading dimension reducer model: {str(e)}")
        
        # 启动批处理线程
        self.batch_processing_thread = threading.Thread(
            target=self._batch_processing_worker,
            daemon=True
        )
        self.batch_processing_thread.start()
        
        # 启动流处理线程
        self.stream_processing_thread = threading.Thread(
            target=self._stream_processing_worker,
            daemon=True
        )
        self.stream_processing_thread.start()
        
        print("Data processing layer started")
    
    def stop(self):
        """停止数据处理服务"""
        self.running = False
        
        # 等待线程结束
        if self.batch_processing_thread:
            self.batch_processing_thread.join(timeout=10)
        if self.stream_processing_thread:
            self.stream_processing_thread.join(timeout=10)
        
        # 关闭资源
        self.mongo_client.close()
        self.consumer.close()
        self.producer.close()
        
        print("Data processing layer stopped")