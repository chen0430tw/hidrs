"""
HIDRS Common Crawl 数据接入模块

功能：
1. 流式WARC文件解析（支持PB级数据）
2. Common Crawl索引搜索
3. MongoDB流式写入
4. HLIG谱分析集成
5. 多备用接口（comcrawl/boto3/S3直连）

使用示例：
    from hidrs.commoncrawl import CommonCrawlIndexClient, WARCStreamParser

    # 搜索索引
    client = CommonCrawlIndexClient()
    results = client.search('*.example.com', limit=1000)

    # 流式处理WARC文件
    parser = WARCStreamParser()
    for record in parser.stream_warc(warc_url):
        print(record['url'], record['html'])
"""

from .index_client import CommonCrawlIndexClient
from .warc_stream_parser import WARCStreamParser
from .data_importer import CommonCrawlImporter
from .query_engine import CommonCrawlQueryEngine

__all__ = [
    'CommonCrawlIndexClient',
    'WARCStreamParser',
    'CommonCrawlImporter',
    'CommonCrawlQueryEngine',
]

__version__ = '1.0.0'
