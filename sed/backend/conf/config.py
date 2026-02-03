import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class ElasticConfig:
    # Elasticsearch配置
    ES_HOST = os.getenv('ES_HOST', 'localhost')
    ES_PORT = int(os.getenv('ES_PORT', 9200))
    ES_INDEX = os.getenv('ES_INDEX', 'socialdb')
    ES_USERNAME = os.getenv('ES_USERNAME', '')
    ES_PASSWORD = os.getenv('ES_PASSWORD', '')
    
    # 索引映射定义
    ES_MAPPING = {
        "settings": {
            "number_of_shards": 5,
            "number_of_replicas": 0,
            "index.codec": "best_compression",
            "index.refresh_interval": "30s"
        },
        "mappings": {
            "properties": {
                "user": {"type": "keyword", "doc_values": False},
                "email": {"type": "keyword", "doc_values": False},
                "password": {"type": "keyword", "doc_values": False, "index": True},
                "passwordHash": {"type": "keyword", "doc_values": False},
                "source": {"type": "keyword"},
                "xtime": {"type": "keyword"},
                "suffix_email": {"type": "keyword"},
                "create_time": {"type": "date", "format": "yyyy/MM/dd HH:mm:ss||yyyy/MM/dd||epoch_millis"},
                "reference": {
                    "properties": {
                        "file": {"type": "keyword"},
                        "line": {"type": "integer"}
                    }
                }
            }
        }
    }
    
    # 批量操作配置
    BULK_SIZE = 1000

class StorageConfig:
    # 存储模式：'duplicate'（复制全部数据）或 'reference'（仅索引关键字段）
    STORAGE_MODE = os.getenv('STORAGE_MODE', 'reference') 
    # 源数据文件目录
    SOURCE_DATA_DIR = os.getenv('SOURCE_DATA_DIR', 'data')
    # 是否压缩索引
    COMPRESS_INDEX = True
    # 是否使用数据分区
    USE_PARTITIONING = os.getenv('USE_PARTITIONING', 'False').lower() in ('true', '1', 't')
    # 分区策略 (source, time, or both)
    PARTITION_STRATEGY = os.getenv('PARTITION_STRATEGY', 'source')

class LogstashConfig:
    # Logstash配置
    LS_HOST = os.getenv('LS_HOST', 'localhost')
    LS_PORT = int(os.getenv('LS_PORT', 5044))
    LS_CONFIG_PATH = os.getenv('LS_CONFIG_PATH', 'logstash/socialdb.conf')

class AppConfig:
    # 应用通用配置
    DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 5000))
    
    # 数据文件配置
    DATA_DIR = os.getenv('DATA_DIR', 'data')
    ERROR_LOG_FILE = os.getenv('ERROR_LOG_FILE', 'logs/error.log')
    ALLOWED_EXTENSIONS = ['txt', 'csv', 'xls', 'xlsx', 'sql', 'mdb', 'log', 'bak']