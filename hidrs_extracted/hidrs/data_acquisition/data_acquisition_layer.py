"""
数据采集与存储层 - 整合爬虫、端口扫描和数据管理功能
"""
from .distributed_crawler import DistributedCrawler
from .port_scanner import PortScanner
from .data_manager import DataManager


class DataAcquisitionLayer:
    """数据采集与存储层管理类，整合爬虫、端口扫描和数据管理功能"""
    
    def __init__(self):
        self.crawler = DistributedCrawler()
        self.port_scanner = PortScanner()
        self.data_manager = DataManager()
    
    def start(self, crawler_workers=5, scanner_workers=3, seed_urls=None):
        """启动所有服务"""
        # 启动爬虫
        self.crawler.start(num_workers=crawler_workers, seed_urls=seed_urls)
        
        # 启动端口扫描器
        self.port_scanner.start(num_workers=scanner_workers)
        
        # 启动数据管理器
        self.data_manager.start()
        
        print("Data acquisition layer started")
    
    def stop(self):
        """停止所有服务"""
        self.crawler.stop()
        self.port_scanner.stop()
        self.data_manager.stop()
        
        print("Data acquisition layer stopped")