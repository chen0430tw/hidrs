#!/usr/bin/env python3
'''
社工库数据处理配置生成器
分析数据文件并生成适合的处理配置
用法: python generate_config.py -f data_file.txt
'''

import os
import re
import json
import csv
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple

# 尝试导入可选依赖
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='社工库数据处理配置生成器')
    
    parser.add_argument('-f', '--file', required=True, help='要分析的数据文件')
    parser.add_argument('-o', '--output', help='输出配置文件路径（默认为[原文件名].config.json）')
    parser.add_argument('-n', '--lines', type=int, default=10, help='分析的行数（默认：10）')
    parser.add_argument('--source', help='指定数据来源名称')
    parser.add_argument('--time', help='指定泄露时间（格式：YYYYMM）')
    
    return parser.parse_args()

def detect_text_format(file_path: str, num_lines: int = 10) -> Dict[str, Any]:
    """检测文本文件格式并生成配置"""
    # 常见分隔符
    separators = ['----', ',', '\t', ':', ';', '|', ' ']
    separator_counts = {sep: 0 for sep in separators}
    
    # 常见模式
    patterns = [
        (r'(.+?)@(.+?)\s*[,;:|]\s*(.+)', ['email', 'password']), # email,password
        (r'(.+?)@(.+?)\s*----\s*(.+)', ['email', 'password']),   # email----password
        (r'(.+?)\s*[,;:|]\s*(.+?)@(.+)', ['user', 'email']),     # user,email
        (r'(.+?)\s*[,;:|]\s*(.+?)\s*[,;:|]\s*(.+?@.+)', ['user', 'password', 'email']) # user,password,email
    ]
    
    pattern_matches = {i: 0 for i in range(len(patterns))}
    
    # 读取样本行
    sample_lines = []
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for _ in range(num_lines):
            line = f.readline().strip()
            if line:
                sample_lines.append(line)
    
    # 统计分隔符
    for line in sample_lines:
        for sep in separators:
            if sep in line:
                separator_counts[sep] += line.count(sep)
    
    # 找出最常见的分隔符
    best_separator = max(separator_counts.items(), key=lambda x: x[1])[0]
    
    # 检查常见模式
    for line in sample_lines:
        for i, (pattern, _) in enumerate(patterns):
            if re.search(pattern, line):
                pattern_matches[i] += 1
    
    # 找出最匹配的模式
    best_pattern_idx = max(pattern_matches.items(), key=lambda x: x[1])[0]
    best_pattern, best_fields = patterns[best_pattern_idx]
    
    # 生成配置
    config = {
        "split": best_separator,
        "fields": best_fields,
        "custom_field": {}
    }
    
    # 添加正则表达式处理
    if 'email' in best_fields:
        config["regex"] = {
            "user": {
                "re": "(.*?)@(.*?)",
                "target": "email"
            },
            "suffix_email": {
                "re": ".*?@(.*)",
                "target": "email"
            }
        }
    
    return config

def detect_csv_format(file_path: str) -> Dict[str, Any]:
    """检测CSV文件格式并生成配置"""
    # 尝试不同的分隔符
    delimiters = [',', ';', '\t', '|']
    best_delimiter = ','
    max_columns = 0
    
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        sample = f.readline()
        
        for delimiter in delimiters:
            fields = sample.split(delimiter)
            if len(fields) > max_columns:
                max_columns = len(fields)
                best_delimiter = delimiter
    
    # 读取头部
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        csv_reader = csv.reader(f, delimiter=best_delimiter)
        header = next(csv_reader)
        
    # 尝试映射字段
    field_mapping = []
    common_fields = {
        'user': ['user', 'username', 'login', 'userid', 'user_name', 'login_name'],
        'email': ['email', 'mail', 'e-mail', 'email_address', 'user_email'],
        'password': ['password', 'pass', 'pwd', 'passwd', 'user_pass'],
        'passwordHash': ['hash', 'passhash', 'password_hash', 'pass_hash', 'md5', 'sha1'],
        'source': ['source', 'src', 'origin', 'leak', 'db_source'],
        'xtime': ['time', 'date', 'leak_time', 'leak_date']
    }
    
    for col in header:
        col_lower = col.lower().strip()
        mapped = False
        
        for field, aliases in common_fields.items():
            if col_lower in aliases or any(alias in col_lower for alias in aliases):
                field_mapping.append(field)
                mapped = True
                break
        
        if not mapped:
            field_mapping.append(col_lower.replace(' ', '_'))
    
    # 生成配置
    config = {
        "delimiter": best_delimiter,
        "has_header": True,
        "fields": field_mapping,
        "custom_field": {}
    }
    
    return config

def detect_excel_format(file_path: str) -> Dict[str, Any]:
    """检测Excel文件格式并生成配置"""
    if not PANDAS_AVAILABLE:
        logger.warning("未安装pandas库，无法分析Excel文件。建议安装: pip install pandas openpyxl")
        # 返回基本配置
        return {
            "sheet_name": 0,
            "custom_field": {}
        }
    
    # 读取Excel文件头部
    try:
        df = pd.read_excel(file_path, nrows=1)
        columns = df.columns.tolist()
        
        # 尝试映射字段
        field_mapping = {}
        common_fields = {
            'user': ['user', 'username', 'login', 'userid', 'user_name', 'login_name'],
            'email': ['email', 'mail', 'e-mail', 'email_address', 'user_email'],
            'password': ['password', 'pass', 'pwd', 'passwd', 'user_pass'],
            'passwordHash': ['hash', 'passhash', 'password_hash', 'pass_hash', 'md5', 'sha1'],
            'source': ['source', 'src', 'origin', 'leak', 'db_source'],
            'xtime': ['time', 'date', 'leak_time', 'leak_date']
        }
        
        for col in columns:
            col_lower = str(col).lower().strip()
            
            for field, aliases in common_fields.items():
                if col_lower in aliases or any(alias in col_lower for alias in aliases):
                    field_mapping[col] = field
                    break
        
        # 生成配置
        config = {
            "sheet_name": 0,
            "fields_mapping": field_mapping,
            "custom_field": {}
        }
        
        return config
    
    except Exception as e:
        logger.error(f"Excel分析失败: {str(e)}")
        # 返回基本配置
        return {
            "sheet_name": 0,
            "custom_field": {}
        }

def detect_file_format(file_path: str, num_lines: int = 10) -> Dict[str, Any]:
    """检测文件格式并生成相应配置"""
    # 获取文件扩展名
    _, ext = os.path.splitext(file_path.lower())
    
    if ext == '.txt':
        return detect_text_format(file_path, num_lines)
    elif ext == '.csv':
        return detect_csv_format(file_path)
    elif ext in ['.xls', '.xlsx']:
        return detect_excel_format(file_path)
    elif ext == '.sql':
        # 基本SQL配置
        return {
            "db_config": {
                "host": "localhost",
                "user": "root",
                "password": "",
                "db": "temp_db"
            },
            "custom_field": {}
        }
    elif ext == '.mdb':
        # 基本Access配置
        return {
            "custom_field": {}
        }
    elif ext == '.log':
        # 基本日志配置
        return {
            "patterns": [
                r'(?P<email>[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})[:：\s]+(?P<password>[^\s]+)',
                r'(?P<user>[a-zA-Z0-9._-]+)[:：\s]+(?P<password>[^\s]+)'
            ],
            "custom_field": {}
        }
    elif ext == '.bak':
        # 基本MSSQL备份配置
        return {
            "mssql_config": {
                "server": "localhost",
                "user": "sa",
                "password": "",
                "database": "master"
            },
            "restore_db": "restored_db",
            "custom_field": {}
        }
    else:
        # 默认配置
        return {
            "custom_field": {}
        }

def main():
    """主函数"""
    # 解析命令行参数
    args = parse_args()
    
    # 检查文件是否存在
    if not os.path.isfile(args.file):
        logger.error(f"文件不存在: {args.file}")
        return
    
    # 检测文件格式
    logger.info(f"分析文件: {args.file}")
    config = detect_file_format(args.file, args.lines)
    
    # 添加自定义字段
    if args.source:
        config["custom_field"]["source"] = args.source
    else:
        # 从文件名中猜测来源
        filename = os.path.basename(args.file)
        name_parts = re.split(r'[_\-.]', filename)
        if len(name_parts) > 1:
            config["custom_field"]["source"] = name_parts[0].lower()
    
    if args.time:
        config["custom_field"]["xtime"] = args.time
    
    # 确定输出文件路径
    if args.output:
        output_path = args.output
    else:
        base_name = os.path.basename(args.file)
        name, _ = os.path.splitext(base_name)
        output_path = f"{name}.config.json"
    
    # 保存配置
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    logger.info(f"配置已保存到: {output_path}")
    logger.info("配置预览:")
    print(json.dumps(config, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()