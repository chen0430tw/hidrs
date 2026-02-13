"""
统一数据导入模块 - 整合了各种导入功能和优化
"""
import os
import time
import logging
import json
from typing import Dict, Any, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor

# 导入工具模块
from .es_client import ESClient
from .data_processor import parse_record
from .msnumber import optimize_batch_size, optimize_chunk_strategy

# 配置
from config import AppConfig, StorageConfig

# 设置日志
logger = logging.getLogger(__name__)

class DataImporter:
    """统一数据导入器"""
    
    def __init__(self, es_client: ESClient = None):
        """初始化导入器"""
        self.es_client = es_client or ESClient()
    
    def import_file(self, file_path: str, config: Dict[str, Any], use_msn: bool = True) -> Tuple[int, int]:
        """
        导入单个文件
        
        Args:
            file_path: 文件路径
            config: 导入配置
            use_msn: 是否使用模块化收缩数优化
            
        Returns:
            成功和失败的记录数
        """
        # 判断文件是否存在
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return 0, 0
            
        # 获取文件大小
        file_size = os.path.getsize(file_path)
        logger.info(f"文件大小: {file_size/1024/1024:.2f} MB")
        
        # 确定批量大小
        batch_size = config.get('batch_size', 1000)
        
        # 如果启用模块化收缩数优化，动态计算最佳批量大小
        if use_msn:
            memory_limit = 500 * 1024 * 1024  # 假设最大内存使用500MB
            batch_size = optimize_batch_size(file_size, memory_limit)
            logger.info(f"使用模块化收缩数优化批量大小: {batch_size}")
        
        # 文件格式检测
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # 根据文件类型选择导入方法
        if file_ext in ['.txt', '.csv']:
            return self._import_text_file(file_path, config, batch_size)
        elif file_ext in ['.xlsx', '.xls']:
            return self._import_excel_file(file_path, config, batch_size)
        else:
            logger.warning(f"未知文件类型: {file_ext}，尝试作为文本文件导入")
            return self._import_text_file(file_path, config, batch_size)
    
    def _import_text_file(self, file_path: str, config: Dict[str, Any], batch_size: int) -> Tuple[int, int]:
        """导入文本文件"""
        split_sign = config.get('split', '----')
        fields = config.get('fields', ['email', 'password'])
        regex_patterns = config.get('regex', {})
        custom_fields = config.get('custom_field', {})
        
        success_count = 0
        error_count = 0
        batch = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                # 是否需要跳过头部
                if config.get('strip_csv_tilte', False):
                    next(f)
                    
                for line_num, line in enumerate(f, 1):
                    try:
                        line = line.strip()
                        if not line:
                            continue
                            
                        # 解析记录
                        record = parse_record(
                            line=line,
                            split_sign=split_sign,
                            fields=fields,
                            regex_patterns=regex_patterns,
                            custom_fields=custom_fields
                        )
                        
                        if record:
                            # 处理存储模式
                            if StorageConfig.STORAGE_MODE == 'reference':
                                # 创建引用模式记录
                                ref_record = {
                                    "user": record.get("user", ""),
                                    "email": record.get("email", ""),
                                    "suffix_email": record.get("suffix_email", ""),
                                    "passwordHash": record.get("passwordHash", ""),
                                    "source": record.get("source", ""),
                                    "xtime": record.get("xtime", ""),
                                    "create_time": record.get("create_time", time.strftime('%Y/%m/%d %H:%M:%S', time.localtime())),
                                    # 引用信息
                                    "reference": {
                                        "file": os.path.basename(file_path),
                                        "line": line_num
                                    }
                                }
                                batch.append(ref_record)
                            else:
                                # 完整模式直接添加整个记录
                                batch.append(record)
                            
                            # 达到批量大小时导入
                            if len(batch) >= batch_size:
                                s, e = self.es_client.bulk_insert(batch)
                                success_count += s
                                error_count += e
                                batch = []
                                
                                # 输出进度
                                if line_num % (batch_size * 10) == 0:
                                    logger.info(f"已处理 {line_num} 行，成功: {success_count}，失败: {error_count}")
                    
                    except Exception as e:
                        error_count += 1
                        logger.error(f"处理第 {line_num} 行出错: {str(e)}")
                        
                # 处理剩余的批次
                if batch:
                    s, e = self.es_client.bulk_insert(batch)
                    success_count += s
                    error_count += e
                    
        except Exception as e:
            logger.error(f"导入文件失败: {str(e)}")
            
        return success_count, error_count
    
    def _import_excel_file(self, file_path: str, config: Dict[str, Any], batch_size: int) -> Tuple[int, int]:
        """导入Excel文件"""
        try:
            import pandas as pd
            
            # 读取Excel文件
            sheet_name = config.get('sheet_name', 0)
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            
            # 获取字段映射
            fields_mapping = config.get('fields_mapping', {})
            custom_fields = config.get('custom_field', {})
            
            # 转换为记录列表
            records = df.to_dict(orient='records')
            
            success_count = 0
            error_count = 0
            total_count = len(records)
            
            # 分批处理记录
            for i in range(0, total_count, batch_size):
                batch = records[i:i+batch_size]
                
                # 处理每条记录
                processed_batch = []
                for record in batch:
                    try:
                        # 应用字段映射
                        if fields_mapping:
                            mapped_record = {}
                            for source, target in fields_mapping.items():
                                if source in record:
                                    mapped_record[target] = record[source]
                            
                            if not mapped_record:
                                # 如果映射后为空，使用原始记录
                                mapped_record = record
                        else:
                            mapped_record = record
                        
                        # 添加自定义字段
                        mapped_record.update(custom_fields)
                        
                        # 解析和完善记录
                        processed_record = parse_record(
                            line="",  # 不需要行解析
                            is_parsed=True,  # 标记为已解析
                            record=mapped_record,
                            split_sign=None,
                            fields=None
                        )
                        
                        if processed_record:
                            # 处理存储模式
                            if StorageConfig.STORAGE_MODE == 'reference':
                                # 创建引用模式记录
                                ref_record = {
                                    "user": processed_record.get("user", ""),
                                    "email": processed_record.get("email", ""),
                                    "suffix_email": processed_record.get("suffix_email", ""),
                                    "passwordHash": processed_record.get("passwordHash", ""),
                                    "source": processed_record.get("source", ""),
                                    "xtime": processed_record.get("xtime", ""),
                                    "create_time": processed_record.get("create_time", time.strftime('%Y/%m/%d %H:%M:%S', time.localtime())),
                                    # 引用信息
                                    "reference": {
                                            "file": os.path.basename(file_path),
                                           "line": i + batch.index(record) + 1
                                       }
                                   }
                                processed_batch.append(ref_record)
                            else:
                                   # 完整模式直接添加整个记录
                                   processed_batch.append(processed_record)
                                   
                    except Exception as e:
                        error_count += 1
                        logger.error(f"处理Excel记录出错: {str(e)}")
                   
                # 批量插入
                if processed_batch:
                    s, e = self.es_client.bulk_insert(processed_batch)
                    success_count += s
                    error_count += e
                       
                    # 输出进度
                    logger.info(f"已处理 {min(i+batch_size, total_count)}/{total_count} 条记录，成功: {success_count}，失败: {error_count}")
                       
            return success_count, error_count
               
        except ImportError:
               logger.error("处理Excel文件需要pandas库。请安装: pip install pandas openpyxl")
               return 0, 0
        except Exception as e:
               logger.error(f"导入Excel文件失败: {str(e)}")
               return 0, 0
       
    def import_directory(self, directory_path: str, config: Dict[str, Any], use_msn: bool = True) -> Tuple[int, int]:
           """
           导入目录中的所有文件
           
           Args:
               directory_path: 目录路径
               config: 导入配置
               use_msn: 是否使用模块化收缩数优化
               
           Returns:
               成功和失败的记录数
           """
           # 检查目录是否存在
           if not os.path.isdir(directory_path):
               logger.error(f"目录不存在: {directory_path}")
               return 0, 0
           
           # 获取目录中的所有文件
           file_paths = []
           patterns = config.get('file_patterns', ['*.txt', '*.csv', '*.xls', '*.xlsx'])
           
           for pattern in patterns:
               import glob
               matches = glob.glob(os.path.join(directory_path, pattern))
               file_paths.extend(matches)
           
           if not file_paths:
               logger.warning(f"目录中没有匹配的文件: {directory_path}")
               return 0, 0
           
           logger.info(f"找到 {len(file_paths)} 个文件待处理")
           
           # 是否使用多线程处理
           use_parallel = config.get('use_parallel', False)
           
           if use_parallel:
               # 确定并行数
               if use_msn:
                   # 估算目录总大小
                   total_size = sum(os.path.getsize(f) for f in file_paths)
                   chunk_strategy = optimize_chunk_strategy(total_size)
                   max_workers = chunk_strategy['recommended_parallelism']
               else:
                   max_workers = min(8, len(file_paths))
               
               logger.info(f"使用 {max_workers} 个并行线程处理文件")
               
               # 使用线程池处理多个文件
               total_success = 0
               total_error = 0
               
               with ThreadPoolExecutor(max_workers=max_workers) as executor:
                   future_to_file = {
                       executor.submit(self.import_file, file_path, config, use_msn): file_path
                       for file_path in file_paths
                   }
                   
                   for future in future_to_file:
                       file_path = future_to_file[future]
                       try:
                           success, error = future.result()
                           total_success += success
                           total_error += error
                           logger.info(f"文件处理完成: {file_path}, 成功: {success}, 失败: {error}")
                       except Exception as e:
                           logger.error(f"处理文件异常: {file_path}, 错误: {str(e)}")
                           total_error += 1
                   
               return total_success, total_error
           else:
               # 顺序处理文件
               total_success = 0
               total_error = 0
               
               for file_path in file_paths:
                   logger.info(f"处理文件: {file_path}")
                   success, error = self.import_file(file_path, config, use_msn)
                   total_success += success
                   total_error += error
                   logger.info(f"文件处理完成: {file_path}, 成功: {success}, 失败: {error}")
               
               return total_success, total_error
       
    def chunk_import_file(self, file_path: str, config: Dict[str, Any], use_msn: bool = True) -> Tuple[int, int]:
           """
           分块导入大文件
           
           Args:
               file_path: 文件路径
               config: 导入配置
               use_msn: 是否使用模块化收缩数优化
               
           Returns:
               成功和失败的记录数
           """
           # 判断文件是否存在
           if not os.path.exists(file_path):
               logger.error(f"文件不存在: {file_path}")
               return 0, 0
               
           # 获取文件大小
           file_size = os.path.getsize(file_path)
           logger.info(f"文件大小: {file_size/1024/1024:.2f} MB")
           
           # 确定分块大小
           if use_msn:
               chunk_strategy = optimize_chunk_strategy(file_size)
               chunk_size = chunk_strategy['chunk_size']
               logger.info(f"使用模块化收缩数优化分块策略: 块大小={chunk_strategy['chunk_size_mb']}MB, 预计块数={chunk_strategy['estimated_chunks']}")
           else:
               chunk_size = config.get('chunk_size', 100*1024*1024)  # 默认100MB
           
           # 估算总块数
           total_chunks = (file_size + chunk_size - 1) // chunk_size
           logger.info(f"将处理 {total_chunks} 个块，每块大约 {chunk_size/1024/1024:.2f} MB")
           
           # 确定批量大小
           batch_size = config.get('batch_size', 1000)
           
           # 处理每个块
           total_success = 0
           total_error = 0
           start_pos = 0
           
           for chunk_number in range(total_chunks):
               logger.info(f"开始处理块 #{chunk_number+1}/{total_chunks}")
               
               # 处理当前块
               next_pos, success, error = self._process_chunk(
                   file_path, start_pos, chunk_size, chunk_number, config, batch_size
               )
               
               start_pos = next_pos
               total_success += success
               total_error += error
               
               logger.info(f"块 #{chunk_number+1} 处理完成: 成功={success}, 失败={error}")
           
           return total_success, total_error
       
    def _process_chunk(self, file_path: str, start_pos: int, chunk_size: int, 
                        chunk_number: int, config: Dict[str, Any], batch_size: int) -> Tuple[int, int, int]:
           """处理文件的一个块"""
           split_sign = config.get('split', '----')
           fields = config.get('fields', ['email', 'password'])
           regex_patterns = config.get('regex', {})
           custom_fields = config.get('custom_field', {})
           
           success_count = 0
           error_count = 0
           line_count = 0
           batch = []
           
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
                       
                       # 解析记录
                       record = parse_record(
                           line=line,
                           split_sign=split_sign,
                           fields=fields,
                           regex_patterns=regex_patterns,
                           custom_fields=custom_fields
                       )
                       
                       if record:
                           # 处理存储模式
                           if StorageConfig.STORAGE_MODE == 'reference':
                               # 创建引用模式记录
                               ref_record = {
                                   "user": record.get("user", ""),
                                   "email": record.get("email", ""),
                                   "suffix_email": record.get("suffix_email", ""),
                                   "passwordHash": record.get("passwordHash", ""),
                                   "source": record.get("source", ""),
                                   "xtime": record.get("xtime", ""),
                                   "create_time": record.get("create_time", time.strftime('%Y/%m/%d %H:%M:%S', time.localtime())),
                                   # 引用信息
                                   "reference": {
                                       "file": os.path.basename(file_path),
                                       "line": line_count + (1 if start_pos > 0 else 0)
                                   }
                               }
                               batch.append(ref_record)
                           else:
                               # 完整模式直接添加整个记录
                               batch.append(record)
                           
                           # 达到批量大小时导入
                           if len(batch) >= batch_size:
                               s, e = self.es_client.bulk_insert(batch)
                               success_count += s
                               error_count += e
                               batch = []
                               
                               # 输出进度
                               if line_count % 10000 == 0:
                                   logger.info(f"块 #{chunk_number+1} - 已处理 {line_count} 行, 成功: {success_count}, 失败: {error_count}")
                   
                   # 处理剩余的批次
                   if batch:
                       s, e = self.es_client.bulk_insert(batch)
                       success_count += s
                       error_count += e
                       
               # 返回下一块的起始位置和统计信息
               return start_pos + bytes_read, success_count, error_count
               
           except Exception as e:
               logger.error(f"处理块 #{chunk_number+1} 出错: {str(e)}")
               return start_pos, success_count, error_count