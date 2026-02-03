'''
重构后的数据导入脚本，支持直接导入到Elasticsearch
使用方式: python import.py -f data_file.csv -c config.json
'''

import os
import sys
import re
import getopt
import json
import time
import datetime
import hashlib
import logging
import csv
from concurrent.futures import ThreadPoolExecutor

# 导入ES工具类
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

def usage():
    """打印使用说明"""
    print('import.py USAGE:')
    print('-h, --help:\t打印帮助信息')
    print('-f, --file:\t导入单个数据文件')
    print('-c, --config:\t指定格式配置文件(JSON)')
    print('-d, --directory:\t导入目录下的所有文件')
    print('-b, --batch:\t批量导入大小 (默认: 1000)')
    print('示例:\npython import.py -f ./test.csv -c ./format.json -b 2000')

def check_opts(argv):
    '''检查参数完整性'''
    try:
        opts, args = getopt.getopt(
            argv[1:], 
            'hf:c:d:b:', 
            ['help', 'file=', 'config=', 'directory=', 'batch=']
        )
        
        if not opts:
            usage()
            sys.exit(0)
            
    except getopt.GetoptError as err:
        print(f"[!] {err}")
        usage()
        sys.exit(2)

    data_file = ''
    config_file = ''
    data_dir = ''
    batch_size = ElasticConfig.BULK_SIZE
    
    for o, a in opts:
        if o in ('-h', '--help'):
            usage()
            sys.exit(0)
        elif o in ('-f', '--file'):
            data_file = a
        elif o in ('-c', '--config'):
            config_file = a
        elif o in ('-d', '--directory'):
            data_dir = a
        elif o in ('-b', '--batch'):
            try:
                batch_size = int(a)
            except ValueError:
                print(f"[!] 批量大小必须是整数: {a}")
                sys.exit(1)
        else:
            print('[!] 未处理的选项')
            usage()
            sys.exit(3)
            
    if not config_file:
        print('[!] 必须指定格式配置文件')
        usage()
        sys.exit(1)
        
    if not (data_file or data_dir):
        print('[!] 必须指定数据文件或数据目录')
        usage()
        sys.exit(1)
        
    return data_file, config_file, data_dir, batch_size

def parse_line(line, split_sign, regex, custom_field, id_fields):
    """解析单行数据"""
    try:
        # 初始化数据对象
        data = {}
        
        # 添加自定义字段
        data.update(custom_field)
        
        # 分割行数据
        line = line.strip()
        parts = line.split(split_sign)
        
        # 确保分割后的数据数量与ID字段匹配
        if len(parts) < len(id_fields):
            raise ValueError(f"数据字段不足: 期望 {len(id_fields)} 个字段，实际 {len(parts)} 个字段")
            
        # 映射数据到字段
        for i, field_name in enumerate(id_fields):
            data[field_name] = parts[i]
            
        # 处理邮箱特殊字段
        if 'email' in data:
            email_parts = data['email'].split('@')
            if len(email_parts) > 1:
                data['suffix_email'] = email_parts[1].lower()
                data['user'] = email_parts[0]
                
        # 处理密码哈希
        if 'password' in data and 'passwordHash' not in data:
            data['passwordHash'] = hashlib.md5(data['password'].encode('utf-8')).hexdigest()
            
        # 处理正则表达式提取
        for field, config in regex.items():
            pattern = config["re"]
            target_field = config["target"]
            
            if target_field in data:
                matches = re.findall(pattern, data[target_field])
                if matches:
                    # 处理正则表达式结果
                    if isinstance(matches[0], tuple):
                        data[field] = matches[0][0]
                    else:
                        data[field] = matches[0]
        
        # 添加创建时间
        data['create_time'] = time.strftime('%Y/%m/%d %H:%M:%S', time.localtime())
        
        return data
    except Exception as e:
        logger.error(f"解析行失败: {line}: {str(e)}")
        return None

def process_file(file_path, format_config, batch_size):
    """处理单个文件导入到ES"""
    es_client = ESClient()
    
    # 从配置中获取参数
    split_sign = format_config.get("split", ",")
    skip_header = format_config.get("strip_csv_tilte", False)
    regex_patterns = format_config.get("regex", {})
    custom_fields = format_config.get("custom_field", {})
    
    # 获取ID字段映射
    id_mapping = format_config.get("id", {})
    id_fields = [id_mapping[k] for k in sorted(id_mapping.keys())]
    
    start_time = datetime.datetime.now()
    error_count = 0
    success_count = 0
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            # 如果需要跳过CSV头部
            if skip_header:
                next(f)
                
            batch = []
            
            for line_num, line in enumerate(f, 1):
                try:
                    # 解析行数据
                    doc = parse_line(line, split_sign, regex_patterns, custom_fields, id_fields)
                    
                    if doc:
                        batch.append(doc)
                        
                        # 达到批量大小，执行批量导入
                        if len(batch) >= batch_size:
                            success, failed = es_client.bulk_insert(batch)
                            success_count += success
                            error_count += len(failed) if isinstance(failed, list) else 0
                            batch = []
                            
                            # 输出进度
                            if line_num % (batch_size * 10) == 0:
                                logger.info(f"已处理 {line_num} 行，成功: {success_count}，失败: {error_count}")
                                
                except Exception as e:
                    error_count += 1
                    logger.error(f"处理第 {line_num} 行出错: {str(e)}")
                    
            # 处理剩余的批次
            if batch:
                success, failed = es_client.bulk_insert(batch)
                success_count += success
                error_count += len(failed) if isinstance(failed, list) else 0
                
    except Exception as e:
        logger.error(f"处理文件 {file_path} 失败: {str(e)}")
        
    end_time = datetime.datetime.now()
    
    logger.info(f"导入完成: {file_path}")
    logger.info(f"总用时: {end_time - start_time}")
    logger.info(f"成功导入: {success_count} 条")
    logger.info(f"失败: {error_count} 条")
    
    return success_count, error_count

def process_directory(directory, format_config, batch_size):
    """处理目录下的所有文件"""
    total_success = 0
    total_error = 0
    
    # 确保目录存在
    if not os.path.isdir(directory):
        logger.error(f"目录不存在: {directory}")
        return 0, 0
        
    # 获取目录下的所有文件
    files = [
        os.path.join(directory, f) for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f))
    ]
    
    logger.info(f"找到 {len(files)} 个文件待处理")
    
    # 使用线程池处理多个文件
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(process_file, file_path, format_config, batch_size): file_path
            for file_path in files
        }
        
        for future in futures:
            file_path = futures[future]
            try:
                success, error = future.result()
                total_success += success
                total_error += error
                logger.info(f"完成文件 {file_path}: 成功 {success}，失败 {error}")
            except Exception as e:
                logger.error(f"处理文件 {file_path} 异常: {str(e)}")
                total_error += 1
                
    return total_success, total_error

def main(argv):
    """主函数"""
    data_file, config_file, data_dir, batch_size = check_opts(argv)
    
    # 读取格式配置
    try:
        with open(config_file, 'r') as f:
            format_config = json.load(f)
    except Exception as e:
        logger.error(f"读取配置文件失败: {str(e)}")
        sys.exit(1)
        
    # 启动导入过程
    start_time = datetime.datetime.now()
    
    if data_file:
        # 处理单个文件
        success, error = process_file(data_file, format_config, batch_size)
        logger.info(f"单文件导入完成: 成功 {success}，失败 {error}")
    elif data_dir:
        # 处理目录下的所有文件
        success, error = process_directory(data_dir, format_config, batch_size)
        logger.info(f"目录导入完成: 成功 {success}，失败 {error}")
        
    end_time = datetime.datetime.now()
    logger.info(f"总耗时: {end_time - start_time}")

if __name__ == '__main__':
    main(sys.argv)