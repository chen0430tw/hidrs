#!/usr/bin/env python3
'''
社工库多格式数据导入工具 - 优化版
支持导入多种格式的数据文件到Elasticsearch，使用引用模式减少存储空间
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
from es_utils import ESClient
from data_processor import DataProcessorFactory
from record_parser import parse_line
from conf.config import ElasticConfig, AppConfig, StorageConfig

# 配置日志
os.makedirs(os.path.dirname(AppConfig.ERROR_LOG_FILE), exist_ok=True)
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
    parser.add_argument('--storage-mode', choices=['duplicate', 'reference'], 
                      default=StorageConfig.STORAGE_MODE, help='存储模式')
    parser.add_argument('--skip-existing', action='store_true', help='跳过已存在的记录')
    parser.add_argument('--update-mode', action='store_true', help='仅导入新数据')
    
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

def process_file_reference_mode(file_path: str, config: Dict[str, Any], es_client: ESClient) -> tuple:
    """在引用模式下处理文件"""
    split_sign = config.get('split', '----')
    fields = config.get('fields', ['email', 'password'])
    regex_patterns = config.get('regex', {})
    custom_fields = config.get('custom_field', {})
    batch_size = config.get('batch_size', 1000)
    
    success_count = 0
    error_count = 0
    batch = []
    
    try:
        logger.info(f"以引用模式处理文件: {file_path}")
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 基本解析记录
                    record = parse_line(line, split_sign, fields, regex_patterns, custom_fields)
                    if record:
                        # 创建简化版本的记录（仅包含搜索所需的字段）
                        ref_record = {
                            "user": record.get("user", ""),
                            "email": record.get("email", ""),
                            "suffix_email": record.get("suffix_email", ""),
                            "password": record.get("password", ""),
                            "passwordHash": record.get("passwordHash", ""),
                            "source": record.get("source", ""),
                            "xtime": record.get("xtime", ""),
                            "create_time": record.get("create_time", time.strftime('%Y/%m/%d %H:%M:%S', time.localtime())),
                            # 添加引用信息
                            "reference": {
                                "file": os.path.basename(file_path),
                                "line": line_num
                            }
                        }
                        
                        batch.append(ref_record)
                        
                        # 达到批处理大小时导入
                        if len(batch) >= batch_size:
                            s, e = es_client.bulk_insert(batch)
                            success_count += s
                            error_count += e
                            batch = []
                            
                            # 输出进度
                            if line_num % (batch_size * 10) == 0:
                                logger.info(f"处理行 {line_num}, 成功: {success_count}, 失败: {error_count}")
                                
                except Exception as e:
                    error_count += 1
                    logger.error(f"处理第 {line_num} 行出错: {str(e)}")
            
            # 处理剩余的批次
            if batch:
                s, e = es_client.bulk_insert(batch)
                success_count += s
                error_count += e
                
    except Exception as e:
        logger.error(f"处理文件失败: {str(e)}")
                
    return success_count, error_count

def main():
    """主函数"""
    # 解析命令行参数
    args = parse_args()
    
    # 设置存储模式
    if args.storage_mode:
        StorageConfig.STORAGE_MODE = args.storage_mode
    
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
            
            # 根据存储模式选择处理方法
            if StorageConfig.STORAGE_MODE == 'reference':
                success, error = process_file_reference_mode(file_path, config, es_client)
            else:
                # 使用常规处理器处理文件
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
            
            # 获取目录中的所有文件
            file_paths = []
            file_patterns = config.get('file_patterns', ['*.txt', '*.csv', '*.sql', '*.xls', '*.xlsx', '*.mdb', '*.log', '*.bak'])
            for pattern in file_patterns:
                file_paths.extend(Path(directory_path).glob(pattern))
            
            # 处理每个文件
            for file_path in file_paths:
                logger.info(f"处理文件: {file_path}")
                
                # 根据存储模式选择处理方法
                if StorageConfig.STORAGE_MODE == 'reference':
                    success, error = process_file_reference_mode(str(file_path), config, es_client)
                else:
                    # 使用常规处理器处理文件
                    success, error = DataProcessorFactory.process_file(str(file_path), config, es_client)
                    
                total_success += success
                total_error += error
                
                logger.info(f"文件处理完成: {file_path}, 成功: {success}, 失败: {error}")
            
    except KeyboardInterrupt:
        logger.warning("用户中断导入过程")
    except Exception as e:
        logger.error(f"处理过程出错: {str(e)}")
    
    # 记录结束时间
    end_time = datetime.datetime.now()
    duration = end_time - start_time
    
    # 获取ES统计信息
    try:
        index_name = args.index
        if StorageConfig.USE_PARTITIONING:
            index_name = f"{args.index}*"
            
        stats = es_client.es.indices.stats(index=index_name)
        index_size_bytes = stats.get('_all', {}).get('total', {}).get('store', {}).get('size_in_bytes', 0)
        index_size_mb = round(index_size_bytes / (1024 * 1024), 2)
    except:
        index_size_mb = "未知"
    
    # 打印总结
    logger.info("=" * 50)
    logger.info("导入过程完成")
    logger.info(f"存储模式: {StorageConfig.STORAGE_MODE}")
    logger.info(f"总时间: {duration}")
    logger.info(f"成功导入记录: {total_success}")
    logger.info(f"失败记录: {total_error}")
    logger.info(f"索引大小: {index_size_mb} MB")
    logger.info("=" * 50)

if __name__ == '__main__':
    main()