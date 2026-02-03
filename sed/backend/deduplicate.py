#!/usr/bin/env python3
'''
社工库数据去重工具
用于处理大量数据文件，去除重复记录
用法: python deduplicate.py -i input_file.txt -o output_file.txt -c config.json
      python deduplicate.py -d input_directory -o output_directory -c config.json
'''

import os
import sys
import json
import hashlib
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, Set
from record_parser import parse_line
from conf.config import AppConfig

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
    parser = argparse.ArgumentParser(description='社工库数据去重工具')
    
    # 定义互斥组：文件和目录不能同时指定
    group_in = parser.add_mutually_exclusive_group(required=True)
    group_in.add_argument('-i', '--input', help='输入文件')
    group_in.add_argument('-d', '--directory', help='输入目录')
    
    # 其他选项
    parser.add_argument('-o', '--output', required=True, help='输出文件或目录')
    parser.add_argument('-c', '--config', required=True, help='处理配置文件(JSON)')
    parser.add_argument('-k', '--key', default='email', 
                      help='去重依据的字段(默认: email，可选: user, email, combine)')
    parser.add_argument('--combine-fields', default='user,email', 
                      help='当key=combine时，组合字段，用逗号分隔')
    
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

def get_record_key(record: Dict[str, Any], key_field: str, combine_fields: str = None) -> str:
    """获取记录的唯一键"""
    if key_field == 'combine' and combine_fields:
        # 使用多个字段组合作为键
        fields = combine_fields.split(',')
        values = []
        for field in fields:
            field = field.strip()
            values.append(str(record.get(field, '')).lower())
        
        return '|'.join(values)
    else:
        # 使用单个字段作为键
        return str(record.get(key_field, '')).lower()

def deduplicate_file(input_file: str, output_file: str, config: Dict[str, Any], 
                   key_field: str, combine_fields: str, seen_keys: Set[str]) -> tuple:
    """去除文件中的重复记录"""
    split_sign = config.get('split', '----')
    fields = config.get('fields', ['email', 'password'])
    regex_patterns = config.get('regex', {})
    custom_fields = config.get('custom_field', {})
    
    total_count = 0
    unique_count = 0
    
    try:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(input_file, 'r', encoding='utf-8', errors='ignore') as in_f, \
             open(output_file, 'w', encoding='utf-8') as out_f:
            
            for line_num, line in enumerate(in_f, 1):
                total_count += 1
                
                try:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 解析记录
                    record = parse_line(line, split_sign, fields, regex_patterns, custom_fields)
                    if not record:
                        continue
                    
                    # 获取记录键
                    record_key = get_record_key(record, key_field, combine_fields)
                    
                    # 检查是否重复
                    if record_key and record_key not in seen_keys:
                        seen_keys.add(record_key)
                        out_f.write(line + '\n')
                        unique_count += 1
                        
                except Exception as e:
                    logger.error(f"处理第 {line_num} 行出错: {str(e)}")
                
                # 输出进度
                if line_num % 100000 == 0:
                    logger.info(f"已处理 {line_num} 行, 发现 {unique_count} 条唯一记录")
    
    except Exception as e:
        logger.error(f"处理文件失败: {str(e)}")
    
    return total_count, unique_count

def main():
    """主函数"""
    # 解析命令行参数
    args = parse_args()
    
    # 加载配置
    config = load_config(args.config)
    
    # 记录已见过的键
    seen_keys = set()
    
    # 统计
    total_records = 0
    unique_records = 0
    
    # 处理单个文件
    if args.input:
        input_file = args.input
        output_file = args.output
        
        logger.info(f"开始处理文件: {input_file}")
        
        # 检查文件是否存在
        if not os.path.isfile(input_file):
            logger.error(f"文件不存在: {input_file}")
            sys.exit(1)
        
        # 去重
        total, unique = deduplicate_file(
            input_file, output_file, config, 
            args.key, args.combine_fields, seen_keys
        )
        
        total_records += total
        unique_records += unique
        
        logger.info(f"文件处理完成: {input_file}")
        logger.info(f"总记录数: {total}, 唯一记录数: {unique}, 重复率: {(total-unique)/total*100:.2f}%")
    
    # 处理目录
    elif args.directory:
        input_dir = args.directory
        output_dir = args.output
        
        logger.info(f"开始处理目录: {input_dir}")
        
        # 检查目录是否存在
        if not os.path.isdir(input_dir):
            logger.error(f"目录不存在: {input_dir}")
            sys.exit(1)
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 获取目录中的所有文件
        file_patterns = config.get('file_patterns', ['*.txt'])
        input_files = []
        for pattern in file_patterns:
            input_files.extend(Path(input_dir).glob(pattern))
        
        # 处理每个文件
        for input_file in input_files:
            # 构建输出文件路径
            rel_path = input_file.relative_to(input_dir)
            output_file = os.path.join(output_dir, rel_path)
            
            logger.info(f"处理文件: {input_file}")
            
            # 去重
            total, unique = deduplicate_file(
                str(input_file), str(output_file), config, 
                args.key, args.combine_fields, seen_keys
            )
            
            total_records += total
            unique_records += unique
            
            logger.info(f"文件处理完成: {input_file}")
            logger.info(f"总记录数: {total}, 唯一记录数: {unique}, 重复率: {(total-unique)/total*100:.2f}%")
    
    # 打印总结
    logger.info("=" * 50)
    logger.info("去重过程完成")
    logger.info(f"总记录数: {total_records}")
    logger.info(f"唯一记录数: {unique_records}")
    if total_records > 0:
        logger.info(f"总重复率: {(total_records-unique_records)/total_records*100:.2f}%")
    logger.info(f"节省空间: {(total_records-unique_records)/1000000:.2f} 百万条记录")
    logger.info("=" * 50)

if __name__ == '__main__':
    main()