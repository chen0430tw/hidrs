#!/usr/bin/env python3
"""
全息互联网动态实时搜索系统（HIDRS）主程序
整合所有层并提供统一的启动和管理功能
"""
import os
import time
import json
import argparse
import logging
import threading
import signal
import sys
from datetime import datetime


# 配置日志
def setup_logging(log_dir="logs", log_level=logging.INFO):
    """配置日志系统"""
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, f"hidrs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    
    # 创建日志格式化器
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # 创建文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    return root_logger


# 导入各层模块
def import_modules():
    """导入系统各层模块"""
    # 确保当前目录在路径中
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    # 导入各层模块
    try:
        # 导入数据采集与存储层
        from data_acquisition import DataAcquisitionLayer
        
        # 导入数据处理与特征抽取层
        from data_processing import DataProcessingLayer
        
        # 导入网络拓扑构建与谱分析层
        from network_topology import NetworkTopologyLayer
        
        # 导入全息映射与索引构建层
        from holographic_mapping import HolographicMappingLayer
        
        # 导入实时搜索与决策反馈层
        from realtime_search import RealtimeSearchLayer
        
        # 导入用户交互与展示层
        from user_interface import UserInterfaceLayer
        
        return {
            'data_acquisition': DataAcquisitionLayer,
            'data_processing': DataProcessingLayer,
            'network_topology': NetworkTopologyLayer,
            'holographic_mapping': HolographicMappingLayer,
            'realtime_search': RealtimeSearchLayer,
            'user_interface': UserInterfaceLayer
        }
    
    except ImportError as e:
        logging.error(f"模块导入失败: {str(e)}")
        logging.error("请确保所有必要的模块已正确安装")
        sys.exit(1)


class HIDRSSystem:
    """全息互联网动态实时搜索系统主类"""
    
    def __init__(self, config_path="config/system_config.json"):
        """初始化HIDRS系统"""
        # 读取系统配置
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            logging.warning(f"配置文件 {config_path} 不存在，使用默认配置")
            self.config = {
                "enabled_layers": ["data_acquisition", "data_processing", "network_topology", 
                                   "holographic_mapping", "realtime_search", "user_interface"],
                "ui_host": "0.0.0.0",
                "ui_port": 5000,
                "debug_mode": False,
                "startup_delay": {
                    "data_acquisition": 0,
                    "data_processing": 5,
                    "network_topology": 10,
                    "holographic_mapping": 15,
                    "realtime_search": 20,
                    "user_interface": 25
                }
            }
            
            # 保存默认配置
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
        
        # 导入模块
        self.modules = import_modules()
        
        # 初始化各层实例
        self.layers = {}
        self.layer_threads = {}
        
        # 运行标志
        self.running = False
        
        # 导入层实例
        self._load_layers()
    
    def _load_layers(self):
        """加载并初始化各层实例"""
        for layer_name in self.config["enabled_layers"]:
            if layer_name in self.modules:
                try:
                    logging.info(f"初始化 {layer_name} 层")
                    self.layers[layer_name] = self.modules[layer_name]()
                except Exception as e:
                    logging.error(f"初始化 {layer_name} 层失败: {str(e)}")
    
    def _start_layer(self, layer_name):
        """启动指定层"""
        if layer_name not in self.layers:
            logging.error(f"层 {layer_name} 未加载")
            return False
        
        try:
            # 获取层实例
            layer = self.layers[layer_name]
            
            # 特殊处理用户交互层
            if layer_name == "user_interface":
                layer.start(
                    host=self.config.get("ui_host", "0.0.0.0"),
                    port=self.config.get("ui_port", 5000),
                    debug=self.config.get("debug_mode", False)
                )
            else:
                layer.start()
            
            logging.info(f"层 {layer_name} 已启动")
            return True
        
        except Exception as e:
            logging.error(f"启动层 {layer_name} 失败: {str(e)}")
            return False
    
    def _start_layer_with_delay(self, layer_name):
        """启动层并应用配置的延迟"""
        # 获取启动延迟（秒）
        delay = self.config.get("startup_delay", {}).get(layer_name, 0)
        
        if delay > 0:
            logging.info(f"层 {layer_name} 将在 {delay} 秒后启动")
            time.sleep(delay)
        
        return self._start_layer(layer_name)
    
    def start(self):
        """启动HIDRS系统的所有层"""
        if self.running:
            logging.warning("系统已经在运行")
            return
        
        self.running = True
        logging.info("启动HIDRS系统...")
        
        # 按顺序启动各层（创建线程以非阻塞方式启动）
        for layer_name in self.config["enabled_layers"]:
            if layer_name in self.layers:
                # 创建线程启动层
                thread = threading.Thread(
                    target=self._start_layer_with_delay,
                    args=(layer_name,),
                    name=f"{layer_name}_starter"
                )
                self.layer_threads[layer_name] = thread
                thread.start()
        
        logging.info("所有层已开始启动过程")
    
    def stop(self):
        """停止HIDRS系统的所有层"""
        if not self.running:
            logging.warning("系统尚未运行")
            return
        
        self.running = False
        logging.info("关闭HIDRS系统...")
        
        # 按相反顺序停止各层
        for layer_name in reversed(self.config["enabled_layers"]):
            if layer_name in self.layers:
                try:
                    self.layers[layer_name].stop()
                    logging.info(f"层 {layer_name} 已停止")
                except Exception as e:
                    logging.error(f"停止层 {layer_name} 失败: {str(e)}")
        
        # 等待所有线程结束
        for name, thread in self.layer_threads.items():
            thread.join(timeout=10)
            if thread.is_alive():
                logging.warning(f"线程 {name} 未能在超时内结束")
        
        logging.info("HIDRS系统已关闭")
    
    def get_status(self):
        """获取系统状态"""
        status = {
            "running": self.running,
            "layers": {}
        }
        
        for layer_name in self.config["enabled_layers"]:
            if layer_name in self.layers:
                layer_thread = self.layer_threads.get(layer_name)
                status["layers"][layer_name] = {
                    "loaded": True,
                    "starting": layer_thread.is_alive() if layer_thread else False
                }
            else:
                status["layers"][layer_name] = {
                    "loaded": False,
                    "starting": False
                }
        
        return status


def handle_signal(signum, frame):
    """处理信号（如Ctrl+C）"""
    logging.info(f"接收到信号 {signum}，开始关闭系统...")
    if 'system' in globals() and isinstance(system, HIDRSSystem):
        system.stop()
    sys.exit(0)


def init_directories():
    """初始化系统所需的目录结构"""
    # 创建主要目录
    dirs = [
        "config",               # 配置文件目录
        "data",                 # 数据目录
        "data/raw",             # 原始数据
        "data/processed",       # 处理后的数据
        "data/backups",         # 备份
        "data/topology",        # 拓扑数据
        "logs",                 # 日志目录
        "models",               # 模型目录
        "static",               # 静态文件目录
        "templates"             # 模板目录
    ]
    
    for dir_path in dirs:
        os.makedirs(dir_path, exist_ok=True)
        logging.debug(f"目录 {dir_path} 已创建或已存在")


def create_module_structure():
    """创建模块结构（在开发时使用）"""
    modules = [
        "data_acquisition",
        "data_processing",
        "network_topology",
        "holographic_mapping",
        "realtime_search",
        "user_interface"
    ]
    
    for module in modules:
        module_dir = module.replace(".", "/")
        os.makedirs(module_dir, exist_ok=True)
        
        # 创建__init__.py文件
        init_file = os.path.join(module_dir, "__init__.py")
        if not os.path.exists(init_file):
            with open(init_file, 'w', encoding='utf-8') as f:
                f.write(f"# {module} 模块初始化\n")
        
        logging.debug(f"模块 {module} 目录结构已创建")


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="全息互联网动态实时搜索系统 (HIDRS)")
    
    parser.add_argument("--config", "-c", type=str, default="config/system_config.json",
                        help="系统配置文件路径")
    
    parser.add_argument("--log-level", "-l", type=str, default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="日志级别")
    
    parser.add_argument("--init-only", action="store_true",
                        help="仅初始化目录结构，不启动系统")
    
    parser.add_argument("--create-modules", action="store_true",
                        help="创建模块目录结构（开发用）")
    
    return parser.parse_args()


def main():
    """主函数"""
    # 解析命令行参数
    args = parse_arguments()
    
    # 设置日志级别
    log_level = getattr(logging, args.log_level)
    logger = setup_logging(log_level=log_level)
    
    # 初始化目录结构
    init_directories()
    
    # 如果需要，创建模块结构
    if args.create_modules:
        create_module_structure()
    
    # 如果是仅初始化模式，到此结束
    if args.init_only:
        logger.info("目录结构初始化完成，程序退出")
        return
    
    # 设置信号处理
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    # 创建并启动系统
    global system
    system = HIDRSSystem(config_path=args.config)
    system.start()
    
    # 主线程保持运行
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("接收到键盘中断，关闭系统...")
        system.stop()


if __name__ == "__main__":
    main()