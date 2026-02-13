"""工具模块初始化"""
from .data_processor import parse_record
from .es_client import ESClient
from .importer import DataImporter
from .msnumber import ModularShrinkingNumber, optimize_batch_size, optimize_chunk_strategy
