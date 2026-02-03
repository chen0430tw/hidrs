# 创建文件 backend/chunk_import.py
import os
import sys
import json
import time
import logging
import argparse
import hashlib
from datetime import datetime
from es_utils import ESClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def parse_line(line, split_sign, fields, custom_fields):
    """解析单行数据"""
    try:
        line = line.strip()
        if not line:
            return None
            
        parts = line.split(split_sign)
        if len(parts) < len(fields):
            return None
            
        record = custom_fields.copy()
        
        for i, field in enumerate(fields):
            record[field] = parts[i].strip()
            
        # 处理邮箱
        if 'email' in record:
            email_parts = record['email'].split('@')
            if len(email_parts) > 1:
                record['user'] = record.get('user', email_parts[0])
                record['suffix_email'] = email_parts[1].lower()
                
        # 处理密码哈希
        if 'password' in record and 'passwordHash' not in record:
            record['passwordHash'] = hashlib.md5(record['password'].encode('utf-8')).hexdigest()
            
        # 添加时间戳
        record['create_time'] = time.strftime('%Y/%m/%d %H:%M:%S', time.localtime())
        
        return record
    except Exception as e:
        return None

def process_chunk(file_path, start_pos, chunk_size, chunk_number, config, es_client):
    """处理文件的一个块"""
    split_sign = config.get('split', '----')
    fields = config.get('fields', ['email', 'password'])
    custom_fields = config.get('custom_field', {})
    batch_size = 1000
    
    success_count = 0
    error_count = 0
    line_count = 0
    batch = []
    
    logger.info(f"开始处理块 #{chunk_number} - 起始位置: {start_pos}, 大小: {chunk_size} 字节")
    start_time = datetime.now()
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            # 移动到起始位置
            f.seek(start_pos)
            
            # 如果不是文件开头，读取并丢弃第一行(可能是不完整的)
            if start_pos > 0:
                f.readline()
            
            # 读取数据直到达到块大小
            bytes_read = 0
            while bytes_read < chunk_size:
                line = f.readline()
                if not line:  # 文件结束
                    break
                    
                bytes_read += len(line.encode('utf-8'))
                line_count += 1
                
                record = parse_line(line, split_sign, fields, custom_fields)
                if not record:
                    continue
                
                # 创建引用记录
                ref_record = {
                    "user": record.get("user", ""),
                    "email": record.get("email", ""),
                    "suffix_email": record.get("suffix_email", ""),
                    "passwordHash": record.get("passwordHash", ""),
                    "source": record.get("source", ""),
                    "xtime": record.get("xtime", ""),
                    "create_time": record.get("create_time", ""),
                    # 引用信息
                    "reference": {
                        "file": os.path.basename(file_path),
                        "line": line_count + (start_pos > 0)
                    }
                }
                
                batch.append(ref_record)
                
                # 批量导入
                if len(batch) >= batch_size:
                    s, e = es_client.bulk_insert(batch)
                    success_count += s
                    error_count += e
                    batch = []
                    
                    # 输出进度
                    if line_count % 10000 == 0:
                        elapsed = datetime.now() - start_time
                        rate = line_count / elapsed.total_seconds() if elapsed.total_seconds() > 0 else 0
                        logger.info(f"块 #{chunk_number} - 已处理 {line_count} 行, 成功: {success_count}, 速度: {rate:.2f} 行/秒")
            
            # 处理剩余数据
            if batch:
                s, e = es_client.bulk_insert(batch)
                success_count += s
                error_count += e
        
        # 输出块处理结果
        elapsed = datetime.now() - start_time
        rate = line_count / elapsed.total_seconds() if elapsed.total_seconds() > 0 else 0
        logger.info(f"块 #{chunk_number} 处理完成 - 行数: {line_count}, 成功: {success_count}, 失败: {error_count}, 时间: {elapsed}, 速度: {rate:.2f} 行/秒")
        
        # 返回下一块的起始位置
        return start_pos + bytes_read, success_count, error_count
    
    except Exception as e:
        logger.error(f"处理块 #{chunk_number} 时出错: {str(e)}")
        return start_pos, success_count, error_count

def main():
    parser = argparse.ArgumentParser(description='大文件分块导入工具')
    parser.add_argument('-f', '--file', required=True, help='要导入的大文件')
    parser.add_argument('-c', '--config', required=True, help='配置文件')
    parser.add_argument('--chunk-size', type=int, default=100*1024*1024, help='块大小(字节), 默认100MB')
    parser.add_argument('--start-chunk', type=int, default=0, help='起始块编号(从0开始)')
    parser.add_argument('--max-chunks', type=int, default=0, help='最大处理块数量(0表示全部)')
    parser.add_argument('--create-index', action='store_true', help='创建索引')
    args = parser.parse_args()
    
    # 检查文件
    if not os.path.isfile(args.file):
        logger.error(f"文件不存在: {args.file}")
        return
    
    # 获取文件大小
    file_size = os.path.getsize(args.file)
    logger.info(f"文件大小: {file_size/1024/1024:.2f} MB")
    
    # 加载配置
    try:
        with open(args.config, 'r', encoding='utf-8') as f:
            config = json.load(f)
            logger.info(f"成功加载配置文件: {args.config}")
    except Exception as e:
        logger.error(f"加载配置文件失败: {str(e)}")
        return
    
    # 创建ES客户端
    es_client = ESClient()
    
    # 创建索引
    if args.create_index:
        es_client.create_index_if_not_exists()
        logger.info("索引创建成功")
    
    # 计算块数
    total_chunks = (file_size + args.chunk_size - 1) // args.chunk_size
    max_chunks = args.max_chunks if args.max_chunks > 0 else total_chunks
    chunks_to_process = min(max_chunks, total_chunks - args.start_chunk)
    
    logger.info(f"将处理 {chunks_to_process} 个块, 每块 {args.chunk_size/1024/1024:.2f} MB")
    
    # 处理块
    start_pos = args.start_chunk * args.chunk_size
    total_success = 0
    total_error = 0
    
    start_time = datetime.now()
    
    for i in range(chunks_to_process):
        chunk_number = args.start_chunk + i
        next_pos, success, error = process_chunk(args.file, start_pos, args.chunk_size, chunk_number, config, es_client)
        
        start_pos = next_pos
        total_success += success
        total_error += error
    
    # 输出总结
    elapsed = datetime.now() - start_time
    logger.info("=" * 60)
    logger.info(f"分块导入完成")
    logger.info(f"总共处理 {chunks_to_process} 个块")
    logger.info(f"成功导入: {total_success} 条记录")
    logger.info(f"失败: {total_error} 条记录")
    logger.info(f"总耗时: {elapsed}")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()