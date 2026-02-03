#!/usr/bin/env python3
'''
社工库多格式数据导入工具
支持导入多种格式的数据文件到Elasticsearch
用法: python import_all.py -f data_file.txt -c config.json
      python import_all.py -d data_directory -c config.json
'''

import os
import sys
import json
import time
import logging
import argparse
import datetime
from pathlib import Path
from typing import Dict, Any

# 导入数据处理器和ES工具
from data_processor import DataProcessorFactory
from es_utils import ESClient
from conf.config import ElasticConfig, AppConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(AppConfig.ERROR_LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='社工库多格式数据导入工具')
    
    # 定义互斥组：文件和目录不能同时指定
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-f', '--file', help='要导入的数据文件')
    group.add_argument('-d', '--directory', help='包含数据文件的目录')
    
    # 其他选项
    parser.add_argument('-c', '--config', required=True, help='处理配置文件(JSON)')
    parser.add_argument('-b', '--batch', type=int, default=1000, help='批处理大小(默认: 1000)')
    parser.add_argument('-i', '--index', default=ElasticConfig.ES_INDEX, help=f'ES索引名称(默认: {ElasticConfig.ES_INDEX})')
    parser.add_argument('--create-index', action='store_true', help='如果索引不存在则创建')
    parser.add_argument('--overwrite-index', action='store_true', help='覆盖现有索引')
    parser.add_argument('--format', help='强制指定文件格式(txt, csv, excel, sql, mdb, log, bak)')
    
    return parser.parse_args()

def load_config(config_file: str) -> Dict[str, Any]:
    """加载配置文件"""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        logger.info(f"成功加载配置文件: {config_file}")
        return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {str(e)}")
        sys.exit(1)

def setup_elasticsearch(args):
    """设置Elasticsearch客户端和索引"""
    try:
        # 创建ES客户端
        es_client = ESClient()
        
        # 检查是否需要创建或覆盖索引
        if args.overwrite_index:
            if es_client.es.indices.exists(index=args.index):
                es_client.es.indices.delete(index=args.index)
                logger.info(f"已删除现有索引: {args.index}")
            
            es_client.es.indices.create(index=args.index, body=ElasticConfig.ES_MAPPING)
            logger.info(f"已创建新索引: {args.index}")
        elif args.create_index:
            if not es_client.es.indices.exists(index=args.index):
                es_client.es.indices.create(index=args.index, body=ElasticConfig.ES_MAPPING)
                logger.info(f"已创建索引: {args.index}")
        
        return es_client
    except Exception as e:
        logger.error(f"设置Elasticsearch失败: {str(e)}")
        sys.exit(1)

def main():
    """主函数"""
    # 解析命令行参数
    args = parse_args()
    
    # 加载配置
    config = load_config(args.config)
    
    # 添加批处理大小
    config['batch_size'] = args.batch
    
    # 设置Elasticsearch
    es_client = setup_elasticsearch(args)
    
    # 记录开始时间
    start_time = datetime.datetime.now()
    
    total_success = 0
    total_error = 0
    
    try:
        # 处理单个文件
        if args.file:
            file_path = args.file
            logger.info(f"开始处理文件: {file_path}")
            
            # 检查文件是否存在
            if not os.path.isfile(file_path):
                logger.error(f"文件不存在: {file_path}")
                sys.exit(1)
            
            # 处理文件
            success, error = DataProcessorFactory.process_file(file_path, config, es_client)
            total_success += success
            total_error += error
            
            logger.info(f"文件处理完成: {file_path}, 成功: {success}, 失败: {error}")
        
        # 处理目录
        elif args.directory:
            directory_path = args.directory
            logger.info(f"开始处理目录: {directory_path}")
            
            # 检查目录是否存在
            if not os.path.isdir(directory_path):
                logger.error(f"目录不存在: {directory_path}")
                sys.exit(1)
            
            # 处理目录
            success, error = DataProcessorFactory.process_directory(directory_path, config, es_client)
            total_success += success
            total_error += error
            
            logger.info(f"目录处理完成: {directory_path}, 成功: {success}, 失败: {error}")
    
    except KeyboardInterrupt:
        logger.warning("用户中断导入过程")
    except Exception as e:
        logger.error(f"处理过程出错: {str(e)}")
    
    # 记录结束时间
    end_time = datetime.datetime.now()
    duration = end_time - start_time
    
    # 打印总结
    logger.info("=" * 50)
    logger.info("导入过程完成")
    logger.info(f"总时间: {duration}")
    logger.info(f"成功导入记录: {total_success}")
    logger.info(f"失败记录: {total_error}")
    logger.info("=" * 50)

if __name__ == '__main__':
    main()