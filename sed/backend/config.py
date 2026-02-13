"""
统一配置模块 - 替代原配置目录
"""
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class AppConfig:
    """应用配置"""
    DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 5000))
    DATA_DIR = os.getenv('DATA_DIR', 'data')
    ERROR_LOG_FILE = os.getenv('ERROR_LOG_FILE', 'logs/error.log')
    
    # 文件格式设置
    ALLOWED_EXTENSIONS = ['txt', 'csv', 'xls', 'xlsx', 'sql', 'mdb', 'log', 'bak']

class StorageConfig:
    """存储配置"""
    # 存储模式：'duplicate'（复制全部数据）或 'reference'（仅索引关键字段）
    STORAGE_MODE = os.getenv('STORAGE_MODE', 'reference')
    
    # 源数据文件目录
    SOURCE_DATA_DIR = os.getenv('DATA_DIR', 'data')
    
    # 是否压缩索引
    COMPRESS_INDEX = os.getenv('COMPRESS_INDEX', 'True').lower() in ('true', '1', 't')
    
    # 是否使用数据分区
    USE_PARTITIONING = os.getenv('USE_PARTITIONING', 'False').lower() in ('true', '1', 't')
    
    # 分区策略 (source, time, both)
    PARTITION_STRATEGY = os.getenv('PARTITION_STRATEGY', 'source')

class ElasticConfig:
    """Elasticsearch配置"""
    ES_HOST = os.getenv('ES_HOST', 'elasticsearch')
    ES_PORT = int(os.getenv('ES_PORT', 9200))
    ES_INDEX = os.getenv('ES_INDEX', 'socialdb')
    ES_USERNAME = os.getenv('ES_USERNAME', '')
    ES_PASSWORD = os.getenv('ES_PASSWORD', '')
    
    # 批量操作配置
    BULK_SIZE = int(os.getenv('BULK_SIZE', 1000))

class LogstashConfig:
    """Logstash配置"""
    LS_HOST = os.getenv('LS_HOST', 'logstash')
    LS_PORT = int(os.getenv('LS_PORT', 5044))
    LS_CONFIG_PATH = os.getenv('LS_CONFIG_PATH', 'logstash/pipeline/unified.conf')

class RedisConfig:
    """Redis配置"""
    REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
    CACHE_TTL = int(os.getenv('CACHE_TTL', 3600))  # 缓存过期时间(秒)