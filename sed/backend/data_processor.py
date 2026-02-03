'''
社工库多格式数据处理器
支持处理各种格式的数据文件并导入到Elasticsearch
'''

import os
import re
import csv
import json
import time
import hashlib
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

# 第三方依赖导入
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    import pymysql
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False

try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False

try:
    import pymssql
    MSSQL_AVAILABLE = True
except ImportError:
    MSSQL_AVAILABLE = False

# 导入ES工具
from es_utils import ESClient

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DataProcessor:
    """基础数据处理器"""
    
    def __init__(self, es_client: ESClient = None):
        """初始化处理器"""
        self.es_client = es_client if es_client else ESClient()
        
    def process_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """处理单条记录，添加必要字段"""
        # 复制记录以避免修改原始数据
        processed = record.copy()
        
        # 处理邮箱字段
        if 'email' in processed and isinstance(processed['email'], str):
            parts = processed['email'].split('@')
            if len(parts) > 1:
                processed['user'] = processed.get('user', parts[0])
                processed['suffix_email'] = parts[1].lower()
                
        # 处理用户名字段
        if 'user' in processed and '@' in processed['user'] and 'email' not in processed:
            # 如果用户名看起来像邮箱但没有email字段，则处理它
            parts = processed['user'].split('@')
            if len(parts) > 1:
                processed['email'] = processed['user']
                processed['user'] = parts[0]
                processed['suffix_email'] = parts[1].lower()
        
        # 处理密码哈希
        if 'password' in processed and 'passwordHash' not in processed:
            try:
                password = str(processed['password']).encode('utf-8')
                processed['passwordHash'] = hashlib.md5(password).hexdigest()
            except Exception as e:
                logger.warning(f"无法生成密码哈希: {e}")
        
        # 添加时间字段
        if 'create_time' not in processed:
            processed['create_time'] = time.strftime('%Y/%m/%d %H:%M:%S', time.localtime())
            
        # 添加源字段
        if 'source' not in processed:
            processed['source'] = 'import_script'
            
        # 添加泄露时间字段
        if 'xtime' not in processed:
            processed['xtime'] = time.strftime('%Y%m', time.localtime())
            
        return processed
    
    def process_file(self, file_path: str, config: Dict[str, Any]) -> Tuple[int, int]:
        """
        处理文件并导入到ES
        
        Args:
            file_path: 要处理的文件路径
            config: 处理配置
            
        Returns:
            成功和失败的记录数量
        """
        raise NotImplementedError("子类必须实现此方法")
    
    def bulk_import(self, records: List[Dict[str, Any]]) -> Tuple[int, int]:
        """批量导入处理后的记录"""
        # 处理所有记录
        processed_records = [self.process_record(record) for record in records]
        
        # 批量导入到ES
        return self.es_client.bulk_insert(processed_records)


class TextFileProcessor(DataProcessor):
    """处理文本文件（如.txt）"""
    
    def process_file(self, file_path: str, config: Dict[str, Any]) -> Tuple[int, int]:
        """处理文本文件"""
        split_sign = config.get('split', '----')
        fields = config.get('fields', ['email', 'password'])
        regex_patterns = config.get('regex', {})
        custom_fields = config.get('custom_field', {})
        
        success_count = 0
        error_count = 0
        batch_size = config.get('batch_size', 1000)
        records = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        # 跳过空行
                        line = line.strip()
                        if not line:
                            continue
                            
                        # 分割行
                        parts = line.split(split_sign)
                        
                        # 创建记录
                        record = custom_fields.copy()
                        
                        # 添加字段
                        for i, field in enumerate(fields):
                            if i < len(parts):
                                record[field] = parts[i]
                        
                        # 处理正则表达式
                        for field, pattern_config in regex_patterns.items():
                            target_field = pattern_config.get('target')
                            pattern = pattern_config.get('re')
                            
                            if target_field in record:
                                try:
                                    matches = re.findall(pattern, record[target_field])
                                    if matches:
                                        if isinstance(matches[0], tuple):
                                            record[field] = matches[0][0]
                                        else:
                                            record[field] = matches[0]
                                except Exception as e:
                                    logger.warning(f"正则表达式匹配失败: {e}")
                        
                        # 添加记录到批处理
                        records.append(record)
                        
                        # 达到批处理大小时导入
                        if len(records) >= batch_size:
                            s, e = self.bulk_import(records)
                            success_count += s
                            error_count += e
                            records = []
                            
                            # 输出进度
                            if line_num % (batch_size * 10) == 0:
                                logger.info(f"处理行 {line_num}, 成功: {success_count}, 失败: {error_count}")
                    
                    except Exception as e:
                        error_count += 1
                        logger.error(f"处理第 {line_num} 行出错: {str(e)}")
                
                # 处理剩余的记录
                if records:
                    s, e = self.bulk_import(records)
                    success_count += s
                    error_count += e
        
        except Exception as e:
            logger.error(f"处理文件 {file_path} 失败: {str(e)}")
        
        return success_count, error_count


class CSVProcessor(DataProcessor):
    """处理CSV文件"""
    
    def process_file(self, file_path: str, config: Dict[str, Any]) -> Tuple[int, int]:
        """处理CSV文件"""
        delimiter = config.get('delimiter', ',')
        has_header = config.get('has_header', True)
        fields = config.get('fields', None)  # 如果为None，使用CSV的头部
        custom_fields = config.get('custom_field', {})
        
        success_count = 0
        error_count = 0
        batch_size = config.get('batch_size', 1000)
        records = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                # 创建CSV读取器
                csv_reader = csv.reader(f, delimiter=delimiter)
                
                # 处理头部
                if has_header:
                    header = next(csv_reader)
                    # 如果未提供字段，使用头部
                    if not fields:
                        fields = header
                
                # 处理数据行
                for row_num, row in enumerate(csv_reader, 1):
                    try:
                        # 创建记录
                        record = custom_fields.copy()
                        
                        # 添加字段
                        for i, field in enumerate(fields):
                            if i < len(row):
                                record[field] = row[i]
                        
                        # 添加记录到批处理
                        records.append(record)
                        
                        # 达到批处理大小时导入
                        if len(records) >= batch_size:
                            s, e = self.bulk_import(records)
                            success_count += s
                            error_count += e
                            records = []
                            
                            # 输出进度
                            if row_num % (batch_size * 10) == 0:
                                logger.info(f"处理行 {row_num}, 成功: {success_count}, 失败: {error_count}")
                    
                    except Exception as e:
                        error_count += 1
                        logger.error(f"处理第 {row_num} 行出错: {str(e)}")
                
                # 处理剩余的记录
                if records:
                    s, e = self.bulk_import(records)
                    success_count += s
                    error_count += e
        
        except Exception as e:
            logger.error(f"处理文件 {file_path} 失败: {str(e)}")
        
        return success_count, error_count


class ExcelProcessor(DataProcessor):
    """处理Excel文件"""
    
    def process_file(self, file_path: str, config: Dict[str, Any]) -> Tuple[int, int]:
        """处理Excel文件"""
        if not PANDAS_AVAILABLE:
            logger.error("需要pandas库来处理Excel文件。请安装: pip install pandas openpyxl")
            return 0, 0
        
        sheet_name = config.get('sheet_name', 0)  # 默认为第一个工作表
        custom_fields = config.get('custom_field', {})
        
        success_count = 0
        error_count = 0
        batch_size = config.get('batch_size', 1000)
        
        try:
            # 读取Excel文件
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            
            # 删除全为空的行
            df = df.dropna(how='all')
            
            # 转换为记录列表
            all_records = df.to_dict(orient='records')
            
            # 分批处理
            for i in range(0, len(all_records), batch_size):
                batch = all_records[i:i+batch_size]
                
                # 添加自定义字段
                for record in batch:
                    record.update(custom_fields)
                
                # 批量导入
                s, e = self.bulk_import(batch)
                success_count += s
                error_count += e
                
                # 输出进度
                logger.info(f"处理记录 {i+1}-{i+len(batch)}, 成功: {success_count}, 失败: {error_count}")
        
        except Exception as e:
            logger.error(f"处理Excel文件 {file_path} 失败: {str(e)}")
        
        return success_count, error_count


class SQLDumpProcessor(DataProcessor):
    """处理SQL转储文件"""
    
    def process_file(self, file_path: str, config: Dict[str, Any]) -> Tuple[int, int]:
        """处理SQL文件"""
        if not MYSQL_AVAILABLE:
            logger.error("需要pymysql库来处理SQL转储文件。请安装: pip install pymysql")
            return 0, 0
        
        # 数据库连接配置
        db_config = config.get('db_config', {
            'host': 'localhost',
            'user': 'root',
            'password': '',
            'db': 'temp_db'
        })
        
        # 导入配置
        table_name = config.get('table_name', 'imported_data')
        fields_mapping = config.get('fields_mapping', {})  # 数据库字段到ES字段的映射
        custom_fields = config.get('custom_field', {})
        query = config.get('query', f"SELECT * FROM {table_name}")
        
        success_count = 0
        error_count = 0
        batch_size = config.get('batch_size', 1000)
        
        # 创建临时数据库
        try:
            # 连接到MySQL
            conn = pymysql.connect(
                host=db_config['host'],
                user=db_config['user'],
                password=db_config['password']
            )
            
            with conn.cursor() as cursor:
                # 创建临时数据库
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_config['db']}")
                cursor.execute(f"USE {db_config['db']}")
                
                # 导入SQL文件
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    sql_content = f.read()
                    
                    # 分割SQL语句并执行
                    for statement in sql_content.split(';'):
                        if statement.strip():
                            try:
                                cursor.execute(statement)
                            except Exception as e:
                                logger.warning(f"执行SQL语句失败: {e}")
                
                conn.commit()
                
                # 查询数据
                cursor.execute(query)
                columns = [col[0] for col in cursor.description]
                
                # 分批获取和处理记录
                while True:
                    batch = cursor.fetchmany(batch_size)
                    if not batch:
                        break
                    
                    records = []
                    for row in batch:
                        # 创建记录
                        record = {columns[i]: value for i, value in enumerate(row)}
                        
                        # 应用字段映射
                        mapped_record = {}
                        for db_field, es_field in fields_mapping.items():
                            if db_field in record:
                                mapped_record[es_field] = record[db_field]
                        
                        # 如果没有映射，使用原始记录
                        if not mapped_record and not fields_mapping:
                            mapped_record = record
                        
                        # 添加自定义字段
                        mapped_record.update(custom_fields)
                        
                        records.append(mapped_record)
                    
                    # 批量导入
                    s, e = self.bulk_import(records)
                    success_count += s
                    error_count += e
                    
                    # 输出进度
                    logger.info(f"处理批次, 成功: {success_count}, 失败: {error_count}")
            
            # 清理：删除临时数据库
            if config.get('cleanup', True):
                with conn.cursor() as cursor:
                    cursor.execute(f"DROP DATABASE IF EXISTS {db_config['db']}")
                conn.commit()
            
            conn.close()
        
        except Exception as e:
            logger.error(f"处理SQL文件 {file_path} 失败: {str(e)}")
        
        return success_count, error_count


class MDBProcessor(DataProcessor):
    """处理Access数据库文件"""
    
    def process_file(self, file_path: str, config: Dict[str, Any]) -> Tuple[int, int]:
        """处理MDB文件"""
        if not PYODBC_AVAILABLE:
            logger.error("需要pyodbc库来处理Access数据库文件。请安装: pip install pyodbc")
            return 0, 0
        
        # 表和字段配置
        table_name = config.get('table_name', None)
        fields_mapping = config.get('fields_mapping', {})
        custom_fields = config.get('custom_field', {})
        
        success_count = 0
        error_count = 0
        batch_size = config.get('batch_size', 1000)
        
        try:
            # 连接到Access数据库
            conn_str = f"Driver={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={file_path}"
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()
            
            # 如果未指定表名，获取所有表并处理第一个
            if not table_name:
                tables = cursor.tables(tableType='TABLE')
                for table_info in tables:
                    table_name = table_info.table_name
                    break
            
            if not table_name:
                logger.error("未找到表")
                return 0, 0
            
            # 查询数据
            cursor.execute(f"SELECT * FROM [{table_name}]")
            columns = [column[0] for column in cursor.description]
            
            # 分批获取和处理记录
            records = []
            row = cursor.fetchone()
            row_count = 0
            
            while row:
                row_count += 1
                
                # 创建记录
                record = {columns[i]: value for i, value in enumerate(row)}
                
                # 应用字段映射
                mapped_record = {}
                for db_field, es_field in fields_mapping.items():
                    if db_field in record:
                        mapped_record[es_field] = record[db_field]
                
                # 如果没有映射，使用原始记录
                if not mapped_record and not fields_mapping:
                    mapped_record = record
                
                # 添加自定义字段
                mapped_record.update(custom_fields)
                
                records.append(mapped_record)
                
                # 达到批处理大小时导入
                if len(records) >= batch_size:
                    s, e = self.bulk_import(records)
                    success_count += s
                    error_count += e
                    records = []
                    
                    # 输出进度
                    logger.info(f"处理行 {row_count}, 成功: {success_count}, 失败: {error_count}")
                
                # 获取下一行
                row = cursor.fetchone()
            
            # 处理剩余的记录
            if records:
                s, e = self.bulk_import(records)
                success_count += s
                error_count += e
            
            cursor.close()
            conn.close()
        
        except Exception as e:
            logger.error(f"处理MDB文件 {file_path} 失败: {str(e)}")
        
        return success_count, error_count


class LogFileProcessor(DataProcessor):
    """处理日志文件"""
    
    def process_file(self, file_path: str, config: Dict[str, Any]) -> Tuple[int, int]:
        """处理日志文件"""
        # 正则表达式配置
        patterns = config.get('patterns', [
            # 默认尝试匹配email:password格式
            r'(?P<email>[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})[:：\s]+(?P<password>[^\s]+)',
            # 尝试匹配用户名和密码
            r'(?P<user>[a-zA-Z0-9._-]+)[:：\s]+(?P<password>[^\s]+)'
        ])
        custom_fields = config.get('custom_field', {})
        
        success_count = 0
        error_count = 0
        batch_size = config.get('batch_size', 1000)
        records = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        line = line.strip()
                        if not line:
                            continue
                        
                        # 尝试所有模式匹配
                        record = None
                        for pattern in patterns:
                            match = re.search(pattern, line)
                            if match:
                                record = match.groupdict()
                                break
                        
                        # 如果找到匹配项
                        if record:
                            # 添加自定义字段
                            record.update(custom_fields)
                            
                            # 添加记录到批处理
                            records.append(record)
                            
                            # 达到批处理大小时导入
                            if len(records) >= batch_size:
                                s, e = self.bulk_import(records)
                                success_count += s
                                error_count += e
                                records = []
                                
                                # 输出进度
                                if line_num % (batch_size * 10) == 0:
                                    logger.info(f"处理行 {line_num}, 成功: {success_count}, 失败: {error_count}")
                    
                    except Exception as e:
                        error_count += 1
                        logger.error(f"处理第 {line_num} 行出错: {str(e)}")
                
                # 处理剩余的记录
                if records:
                    s, e = self.bulk_import(records)
                    success_count += s
                    error_count += e
        
        except Exception as e:
            logger.error(f"处理日志文件 {file_path} 失败: {str(e)}")
        
        return success_count, error_count


class MySQLFilesProcessor(DataProcessor):
    """处理MySQL数据文件(.frm, .MYD, .MYI)"""
    
    def process_file(self, directory_path: str, config: Dict[str, Any]) -> Tuple[int, int]:
        """
        处理MySQL数据文件
        
        注意：这个方法需要MySQL服务器访问权限，并且需要将文件放在MySQL数据目录中
        """
        if not MYSQL_AVAILABLE:
            logger.error("需要pymysql库来处理MySQL数据文件。请安装: pip install pymysql")
            return 0, 0
        
        # MySQL连接配置
        mysql_config = config.get('mysql_config', {
            'host': 'localhost',
            'user': 'root',
            'password': '',
            'port': 3306
        })
        
        data_dir = config.get('data_dir', '/var/lib/mysql')
        db_name = config.get('db_name', 'imported_db')
        table_name = config.get('table_name', None)
        fields_mapping = config.get('fields_mapping', {})
        custom_fields = config.get('custom_field', {})
        
        success_count = 0
        error_count = 0
        batch_size = config.get('batch_size', 1000)
        
        # 验证目录中是否包含.frm, .MYD, .MYI文件
        directory = Path(directory_path)
        frm_files = list(directory.glob('*.frm'))
        
        if not frm_files:
            logger.error(f"目录 {directory_path} 中未找到.frm文件")
            return 0, 0
        
        # 如果未指定表名，使用第一个.frm文件的名称
        if not table_name:
            table_name = frm_files[0].stem
        
        try:
            # 尝试复制文件到MySQL数据目录
            target_dir = Path(data_dir) / db_name
            
            # 创建目标目录
            os.makedirs(target_dir, exist_ok=True)
            
            # 复制所有相关文件
            for ext in ['.frm', '.MYD', '.MYI']:
                source_file = directory / f"{table_name}{ext}"
                if source_file.exists():
                    import shutil
                    shutil.copy(source_file, target_dir)
            
            # 连接到MySQL并查询数据
            conn = pymysql.connect(
                host=mysql_config['host'],
                user=mysql_config['user'],
                password=mysql_config['password'],
                port=mysql_config['port']
            )
            
            with conn.cursor() as cursor:
                # 创建数据库（如果不存在）
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
                cursor.execute(f"USE {db_name}")
                
                # 查询表结构
                cursor.execute(f"SHOW COLUMNS FROM {table_name}")
                columns = [row[0] for row in cursor.fetchall()]
                
                # 分批查询数据
                cursor.execute(f"SELECT * FROM {table_name}")
                
                while True:
                    batch = cursor.fetchmany(batch_size)
                    if not batch:
                        break
                    
                    records = []
                    for row in batch:
                        # 创建记录
                        record = {columns[i]: value for i, value in enumerate(row)}
                        
                        # 应用字段映射
                        mapped_record = {}
                        for db_field, es_field in fields_mapping.items():
                            if db_field in record:
                                mapped_record[es_field] = record[db_field]
                        
                        # 如果没有映射，使用原始记录
                        if not mapped_record and not fields_mapping:
                            mapped_record = record
                        
                        # 添加自定义字段
                        mapped_record.update(custom_fields)
                        
                        records.append(mapped_record)
                    
                    # 批量导入
                    s, e = self.bulk_import(records)
                    success_count += s
                    error_count += e
                    
                    # 输出进度
                    logger.info(f"处理批次, 成功: {success_count}, 失败: {error_count}")
            
            # 清理：删除临时数据库
            if config.get('cleanup', True):
                with conn.cursor() as cursor:
                    cursor.execute(f"DROP DATABASE IF EXISTS {db_name}")
                conn.commit()
            
            conn.close()
            
            # 删除复制的文件
            if config.get('cleanup', True):
                for file in target_dir.glob(f"{table_name}*"):
                    file.unlink()
                
                # 尝试删除目录
                try:
                    target_dir.rmdir()
                except:
                    pass
        
        except Exception as e:
            logger.error(f"处理MySQL数据文件失败: {str(e)}")
        
        return success_count, error_count


class MSSQLBackupProcessor(DataProcessor):
    """处理MSSQL备份文件(.bak)"""
    
    def process_file(self, file_path: str, config: Dict[str, Any]) -> Tuple[int, int]:
        """处理MSSQL备份文件"""
        if not MSSQL_AVAILABLE:
            logger.error("需要pymssql库来处理MSSQL备份文件。请安装: pip install pymssql")
            return 0, 0
        
        # MSSQL连接配置
        mssql_config = config.get('mssql_config', {
            'server': 'localhost',
            'user': 'sa',
            'password': '',
            'database': 'master'
        })
        
        # MSSQL还原配置
        restore_db = config.get('restore_db', 'restored_db')
        table_name = config.get('table_name', None)
        fields_mapping = config.get('fields_mapping', {})
        custom_fields = config.get('custom_field', {})
        
        success_count = 0
        error_count = 0
        batch_size = config.get('batch_size', 1000)
        
        try:
            # 连接到MSSQL
            conn = pymssql.connect(
                server=mssql_config['server'],
                user=mssql_config['user'],
                password=mssql_config['password'],
                database=mssql_config['database']
            )
            
            # 创建临时目录存放恢复的数据
            import tempfile
            temp_dir = tempfile.mkdtemp()
            
            # 构建完整的备份文件路径
            full_path = os.path.abspath(file_path)
            
            with conn.cursor() as cursor:
                # 先删除可能存在的数据库
                cursor.execute(f"IF DB_ID('{restore_db}') IS NOT NULL BEGIN ALTER DATABASE [{restore_db}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{restore_db}]; END")
                
                # 恢复备份
                restore_query = f"""
                RESTORE DATABASE [{restore_db}] FROM DISK = '{full_path}'
                WITH MOVE 'data' TO '{temp_dir}\\{restore_db}_data.mdf',
                MOVE 'log' TO '{temp_dir}\\{restore_db}_log.ldf',
                REPLACE
                """
                cursor.execute(restore_query)
                
                # 如果未指定表名，获取第一个表
                if not table_name:
                    cursor.execute(f"USE [{restore_db}]; SELECT name FROM sys.tables")
                    result = cursor.fetchone()
                    if result:
                        table_name = result[0]
                    else:
                        logger.error("未找到表")
                        return 0, 0
                
                # 分批查询数据
                cursor.execute(f"USE [{restore_db}]; SELECT * FROM [{table_name}]")
                columns = [column[0] for column in cursor.description]
                
                # 分批获取和处理记录
                while True:
                    batch = cursor.fetchmany(batch_size)
                    if not batch:
                        break
                    
                    records = []
                    for row in batch:
                        # 创建记录
                        record = {columns[i]: value for i, value in enumerate(row)}
                        
                        # 应用字段映射
                        mapped_record = {}
                        for db_field, es_field in fields_mapping.items():
                            if db_field in record:
                                mapped_record[es_field] = record[db_field]
                        
                        # 如果没有映射，使用原始记录
                        if not mapped_record and not fields_mapping:
                            mapped_record = record
                        
                        # 添加自定义字段
                        mapped_record.update(custom_fields)
                        
                        records.append(mapped_record)
                    
                    # 批量导入
                    s, e = self.bulk_import(records)
                    success_count += s
                    error_count += e
                    
                    # 输出进度
                    logger.info(f"处理批次, 成功: {success_count}, 失败: {error_count}")
                
                # 清理：删除恢复的数据库
                if config.get('cleanup', True):
                    cursor.execute(f"ALTER DATABASE [{restore_db}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{restore_db}]")
            
            # 清理临时目录
            if config.get('cleanup', True):
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            
            conn.close()
        
        except Exception as e:
            logger.error(f"处理MSSQL备份文件 {file_path} 失败: {str(e)}")
        
        return success_count, error_count


class DataProcessorFactory:
    """数据处理器工厂类，根据文件类型创建合适的处理器"""
    
    @staticmethod
    def get_processor(file_path: str, es_client: ESClient = None) -> Optional[DataProcessor]:
        """
        根据文件类型返回合适的处理器
        
        Args:
            file_path: 文件路径
            es_client: 可选的ES客户端实例
            
        Returns:
            对应类型的数据处理器实例，如果不支持则返回None
        """
        # 获取文件扩展名（小写）
        _, ext = os.path.splitext(file_path.lower())
        
        # 创建ES客户端（如果未提供）
        if not es_client:
            es_client = ESClient()
        
        # 根据扩展名选择处理器
        if ext == '.txt':
            return TextFileProcessor(es_client)
        elif ext == '.csv':
            return CSVProcessor(es_client)
        elif ext in ['.xls', '.xlsx']:
            return ExcelProcessor(es_client)
        elif ext == '.sql':
            return SQLDumpProcessor(es_client)
        elif ext == '.mdb':
            return MDBProcessor(es_client)
        elif ext == '.log':
            return LogFileProcessor(es_client)
        elif ext == '.bak':
            return MSSQLBackupProcessor(es_client)
        else:
            # 对于不能通过扩展名识别的特殊情况（如MySQL数据文件）
            # 需要单独处理
            logger.warning(f"不支持的文件类型: {ext}")
            return None
    
    @staticmethod
    def process_file(file_path: str, config: Dict[str, Any], es_client: ESClient = None) -> Tuple[int, int]:
        """
        处理单个文件
        
        Args:
            file_path: 文件路径
            config: 处理配置
            es_client: 可选的ES客户端实例
            
        Returns:
            成功和失败的记录数量
        """
        # 获取处理器
        processor = DataProcessorFactory.get_processor(file_path, es_client)
        
        if processor:
            # 处理文件
            return processor.process_file(file_path, config)
        else:
            # 尝试自动识别文件类型
            magic_number = DataProcessorFactory._get_magic_number(file_path)
            
            # 根据文件内容判断
            if magic_number.startswith(b'PK'):
                # 可能是Office 2007+文档(Excel, Word等)
                return ExcelProcessor(es_client).process_file(file_path, config)
            elif magic_number.startswith(b'\xD0\xCF\x11\xE0'):
                # 可能是Office 97-2003文档(Excel, Word等)或Access数据库
                if file_path.lower().endswith('.mdb'):
                    return MDBProcessor(es_client).process_file(file_path, config)
                else:
                    return ExcelProcessor(es_client).process_file(file_path, config)
            else:
                # 默认作为文本文件处理
                logger.warning(f"未知文件类型，尝试作为文本文件处理: {file_path}")
                return TextFileProcessor(es_client).process_file(file_path, config)
    
    @staticmethod
    def _get_magic_number(file_path: str, bytes_count: int = 8) -> bytes:
        """获取文件的魔数（文件头部的字节）"""
        try:
            with open(file_path, 'rb') as f:
                return f.read(bytes_count)
        except Exception:
            return b''
    
    @staticmethod
    def process_directory(directory_path: str, config: Dict[str, Any], es_client: ESClient = None) -> Tuple[int, int]:
        """
        处理目录中的所有文件
        
        Args:
            directory_path: 目录路径
            config: 处理配置
            es_client: 可选的ES客户端实例
            
        Returns:
            成功和失败的记录数量
        """
        # 创建ES客户端（如果未提供）
        if not es_client:
            es_client = ESClient()
        
        # 设置文件过滤
        file_patterns = config.get('file_patterns', ['*.txt', '*.csv', '*.sql', '*.xls', '*.xlsx', '*.mdb', '*.log', '*.bak'])
        
        # 获取所有匹配的文件
        all_files = []
        for pattern in file_patterns:
            all_files.extend(Path(directory_path).glob(pattern))
        
        # 检查是否有MySQL数据文件
        mysql_files = list(Path(directory_path).glob('*.frm'))
        if mysql_files:
            logger.info(f"发现MySQL数据文件，将使用MySQLFilesProcessor处理")
            return MySQLFilesProcessor(es_client).process_file(directory_path, config)
        
        # 处理每个文件
        total_success = 0
        total_error = 0
        
        for file_path in all_files:
            try:
                logger.info(f"处理文件: {file_path}")
                success, error = DataProcessorFactory.process_file(str(file_path), config, es_client)
                total_success += success
                total_error += error
                logger.info(f"文件 {file_path} 处理完成: 成功 {success}, 失败 {error}")
            except Exception as e:
                logger.error(f"处理文件 {file_path} 时出错: {str(e)}")
                total_error += 1
        
        return total_success, total_error