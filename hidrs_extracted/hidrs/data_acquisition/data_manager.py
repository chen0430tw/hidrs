"""
数据管理类，负责数据存储、备份和同步
"""
import os
import json
import time
import threading
from datetime import datetime
import pymongo
from elasticsearch import Elasticsearch


class DataManager:
    """数据管理类，负责数据存储、备份和同步"""
    
    def __init__(self, config_path="config/data_manager_config.json"):
        # 读取配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # 初始化MongoDB连接
        self.mongo_client = pymongo.MongoClient(self.config['mongodb_uri'])
        self.db = self.mongo_client[self.config['mongodb_db']]
        
        # 初始化Elasticsearch连接，用于搜索
        self.es = Elasticsearch(self.config['elasticsearch_hosts'])
        
        # 确保索引存在
        if not self.es.indices.exists(index=self.config['es_index']):
            self.es.indices.create(
                index=self.config['es_index'],
                body=self.config['es_index_settings']
            )
        
        # 备份与同步线程
        self.backup_thread = None
        self.sync_thread = None
        self.running = False
    
    def _backup_worker(self):
        """数据备份工作线程"""
        while self.running:
            try:
                # 执行数据备份
                backup_dir = os.path.join(
                    self.config['backup_path'],
                    datetime.now().strftime('%Y%m%d_%H%M%S')
                )
                os.makedirs(backup_dir, exist_ok=True)
                
                # 备份每个集合
                for collection_name in self.config['collections_to_backup']:
                    collection = self.db[collection_name]
                    documents = list(collection.find({}, {'_id': 0}))
                    
                    if documents:
                        backup_file = os.path.join(backup_dir, f"{collection_name}.json")
                        with open(backup_file, 'w', encoding='utf-8') as f:
                            json.dump(documents, f, ensure_ascii=False, default=str)
                        
                        print(f"Backed up {len(documents)} documents from {collection_name}")
                
                # 按照配置间隔执行备份
                time.sleep(self.config['backup_interval'])
                
            except Exception as e:
                print(f"Backup worker error: {str(e)}")
                time.sleep(300)  # 出错后等待一段时间再继续
    
    def _sync_worker(self):
        """数据同步工作线程，将MongoDB数据同步到Elasticsearch"""
        last_sync_time = datetime.now()
        
        while self.running:
            try:
                # 获取上次同步后的新数据
                raw_data_collection = self.db[self.config['raw_data_collection']]
                new_documents = raw_data_collection.find({
                    'crawl_time': {'$gt': last_sync_time}
                })
                
                # 批量插入Elasticsearch
                bulk_data = []
                for doc in new_documents:
                    # 转换MongoDB文档ID为字符串
                    doc_id = str(doc.pop('_id'))
                    
                    # 准备ES索引操作
                    action = {
                        "index": {
                            "_index": self.config['es_index'],
                            "_id": doc_id
                        }
                    }
                    
                    # 转换日期类型为字符串
                    if 'crawl_time' in doc:
                        doc['crawl_time'] = doc['crawl_time'].isoformat()
                    
                    bulk_data.append(action)
                    bulk_data.append(doc)
                
                if bulk_data:
                    # 执行批量操作
                    self.es.bulk(body=bulk_data, refresh=True)
                    print(f"Synced {len(bulk_data)//2} documents to Elasticsearch")
                
                # 更新同步时间
                last_sync_time = datetime.now()
                
                # 按照配置间隔执行同步
                time.sleep(self.config['sync_interval'])
                
            except Exception as e:
                print(f"Sync worker error: {str(e)}")
                time.sleep(60)  # 出错后等待一段时间再继续
    
    def start(self):
        """启动数据管理服务"""
        self.running = True
        
        # 启动备份线程
        self.backup_thread = threading.Thread(
            target=self._backup_worker,
            daemon=True
        )
        self.backup_thread.start()
        
        # 启动同步线程
        self.sync_thread = threading.Thread(
            target=self._sync_worker,
            daemon=True
        )
        self.sync_thread.start()
        
        print("Data manager started")
    
    def stop(self):
        """停止数据管理服务"""
        self.running = False
        
        # 等待线程结束
        if self.backup_thread:
            self.backup_thread.join(timeout=10)
        if self.sync_thread:
            self.sync_thread.join(timeout=10)
        
        # 关闭资源
        self.mongo_client.close()
        
        print("Data manager stopped")