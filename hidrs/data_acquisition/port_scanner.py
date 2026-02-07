"""
端口扫描器，用于发现开放的网络服务
"""
import os
import json
import time
import threading
import random
from datetime import datetime
try:
    import nmap
    HAS_NMAP = True
except ImportError:
    HAS_NMAP = False
import pymongo
from kafka import KafkaProducer


class PortScanner:
    """端口扫描器，用于发现开放的网络服务"""
    
    def __init__(self, config_path="config/port_scanner_config.json"):
        # 读取配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # 初始化MongoDB连接
        self.mongo_client = pymongo.MongoClient(self.config['mongodb_uri'])
        self.db = self.mongo_client[self.config['mongodb_db']]
        self.port_scan_collection = self.db[self.config['port_scan_collection']]
        
        # 初始化nmap扫描器
        if not HAS_NMAP:
            raise ImportError("python-nmap 未安装，请运行: pip install python-nmap")
        self.nm = nmap.PortScanner()
        
        # 初始化Kafka生产者
        self.producer = KafkaProducer(
            bootstrap_servers=self.config['kafka_servers'],
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        self.running = False
        self.scanner_threads = []
    
    def _scan_worker(self, ip_range, worker_id):
        """端口扫描工作线程"""
        while self.running:
            try:
                # 对指定IP范围执行端口扫描
                print(f"Worker {worker_id} scanning IP range: {ip_range}")
                
                # 使用nmap进行扫描，指定端口和扫描类型
                self.nm.scan(
                    hosts=ip_range,
                    arguments=f"-p {self.config['ports']} -sV"
                )
                
                # 处理扫描结果
                for host in self.nm.all_hosts():
                    result = {
                        'ip': host,
                        'scan_time': datetime.now(),
                        'ports': {},
                        'worker_id': worker_id
                    }
                    
                    # 提取开放端口和服务信息
                    for proto in self.nm[host].all_protocols():
                        ports = sorted(self.nm[host][proto].keys())
                        for port in ports:
                            service = self.nm[host][proto][port]
                            result['ports'][str(port)] = {
                                'state': service['state'],
                                'service': service['name'],
                                'product': service.get('product', ''),
                                'version': service.get('version', ''),
                                'extrainfo': service.get('extrainfo', '')
                            }
                    
                    # 保存到MongoDB
                    self.port_scan_collection.insert_one(result)
                    
                    # 发送到Kafka
                    kafka_message = {
                        'ip': host,
                        'timestamp': datetime.now().isoformat(),
                        'open_ports': list(result['ports'].keys()),
                        'status': 'scanned'
                    }
                    self.producer.send(
                        self.config['kafka_topic'],
                        kafka_message
                    )
                    
                    print(f"Worker {worker_id} scanned: {host} with {len(result['ports'])} open ports")
                
                # 随机延迟，避免频繁扫描
                time.sleep(random.uniform(
                    self.config['min_scan_interval'],
                    self.config['max_scan_interval']
                ))
                
            except Exception as e:
                print(f"Scanner worker {worker_id} error: {str(e)}")
                time.sleep(30)  # 出错后等待一段时间再继续
    
    def start(self, num_workers=3):
        """启动端口扫描工作线程"""
        self.running = True
        
        # 将IP范围分配给不同工作线程
        ip_ranges = self.config['ip_ranges']
        for i in range(num_workers):
            # 每个线程分配一部分IP范围
            thread_ip_ranges = ip_ranges[i % len(ip_ranges)]
            thread = threading.Thread(
                target=self._scan_worker,
                args=(thread_ip_ranges, i),
                daemon=True
            )
            thread.start()
            self.scanner_threads.append(thread)
            
        print(f"Started {num_workers} port scanner workers")
    
    def stop(self):
        """停止所有扫描线程"""
        self.running = False
        
        # 等待所有线程结束
        for thread in self.scanner_threads:
            thread.join(timeout=10)
        
        # 关闭资源
        self.producer.close()
        self.mongo_client.close()
        
        print("All scanner workers stopped")