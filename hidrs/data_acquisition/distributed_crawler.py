"""
分布式爬虫管理类，负责爬虫的分发和协调
"""
import os
import time
import json
import threading
import queue
import random
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import pymongo
from kafka import KafkaProducer


class DistributedCrawler:
    """分布式爬虫管理类，负责爬虫的分发和协调"""
    
    def __init__(self, config_path="config/crawler_config.json"):
        # 读取配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # 初始化URL队列
        self.url_queue = queue.Queue()
        
        # 初始化MongoDB连接
        self.mongo_client = pymongo.MongoClient(self.config['mongodb_uri'])
        self.db = self.mongo_client[self.config['mongodb_db']]
        self.raw_data_collection = self.db[self.config['raw_data_collection']]
        
        # 初始化Kafka生产者，用于实时数据流
        self.producer = KafkaProducer(
            bootstrap_servers=self.config['kafka_servers'],
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        # 爬虫线程池
        self.crawler_threads = []
        self.running = False
        
        # 已访问URL集合，避免重复抓取
        self.visited_urls = set()
    
    def add_urls(self, urls):
        """添加URL到队列中"""
        for url in urls:
            if url not in self.visited_urls:
                self.url_queue.put(url)
    
    def _crawl_worker(self, worker_id):
        """爬虫工作线程"""
        while self.running:
            try:
                # 获取一个URL进行抓取，设置超时以便线程可以定期检查running状态
                try:
                    url = self.url_queue.get(timeout=5)
                except queue.Empty:
                    continue
                
                if url in self.visited_urls:
                    self.url_queue.task_done()
                    continue
                
                # 添加到已访问集合
                self.visited_urls.add(url)
                
                # 抓取网页内容
                headers = {'User-Agent': random.choice(self.config['user_agents'])}
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    # 解析网页内容
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # 提取标题、内容、链接等信息
                    title = soup.title.string if soup.title else url
                    text_content = ' '.join([p.text for p in soup.find_all('p')])
                    links = [a.get('href') for a in soup.find_all('a', href=True)]
                    
                    # 处理相对链接
                    absolute_links = []
                    for link in links:
                        if link.startswith('http'):
                            absolute_links.append(link)
                        elif link.startswith('/'):
                            base_url = '/'.join(url.split('/')[:3])  # 提取域名
                            absolute_links.append(f"{base_url}{link}")
                    
                    # 保存到MongoDB
                    document = {
                        'url': url,
                        'title': title,
                        'content': text_content,
                        'links': absolute_links,
                        'crawl_time': datetime.now(),
                        'status_code': response.status_code,
                        'content_type': response.headers.get('Content-Type', ''),
                        'worker_id': worker_id
                    }
                    self.raw_data_collection.insert_one(document)
                    
                    # 发送到Kafka，用于实时处理
                    kafka_message = {
                        'url': url,
                        'title': title,
                        'timestamp': datetime.now().isoformat(),
                        'status': 'success'
                    }
                    self.producer.send(
                        self.config['kafka_topic'],
                        kafka_message
                    )
                    
                    # 添加新发现的链接到队列中
                    self.add_urls(absolute_links[:self.config['max_links_per_page']])
                    
                    print(f"Worker {worker_id} crawled: {url} - {title}")
                else:
                    print(f"Worker {worker_id} failed: {url} - Status {response.status_code}")
                
                # 标记任务完成
                self.url_queue.task_done()
                
                # 随机延迟，避免频繁请求
                time.sleep(random.uniform(
                    self.config['min_crawl_delay'],
                    self.config['max_crawl_delay']
                ))
                
            except Exception as e:
                print(f"Worker {worker_id} error: {str(e)}")
                # 标记任务完成
                try:
                    self.url_queue.task_done()
                except:
                    pass
    
    def start(self, num_workers=5, seed_urls=None):
        """启动爬虫工作线程"""
        self.running = True
        
        # 添加种子URL
        if seed_urls:
            self.add_urls(seed_urls)
        else:
            self.add_urls(self.config['seed_urls'])
        
        # 创建并启动工作线程
        for i in range(num_workers):
            thread = threading.Thread(
                target=self._crawl_worker,
                args=(i,),
                daemon=True
            )
            thread.start()
            self.crawler_threads.append(thread)
            
        print(f"Started {num_workers} crawler workers")
    
    def stop(self):
        """停止所有爬虫线程"""
        self.running = False
        
        # 等待所有线程结束
        for thread in self.crawler_threads:
            thread.join(timeout=10)
        
        # 关闭资源
        self.producer.close()
        self.mongo_client.close()
        
        print("All crawler workers stopped")