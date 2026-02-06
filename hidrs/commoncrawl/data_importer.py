"""
Common Crawl 数据导入器

功能：
1. 流式导入MongoDB（批量写入优化）
2. 集成HLIG拉普拉斯谱分析
3. 自动提取关键词和实体
4. 进度追踪和断点续传
5. 多线程并发导入

优化策略：
- 批量插入（batch_size=1000）
- 异步写入队列
- 重复数据去重（URL+timestamp哈希）
- 自动索引创建
"""

import logging
from typing import Dict, Any, List, Optional, Iterator
from datetime import datetime
from urllib.parse import urlparse
import hashlib
import time
from queue import Queue
from threading import Thread, Event

try:
    from pymongo import MongoClient, UpdateOne
    from pymongo.errors import BulkWriteError
except ImportError:
    raise ImportError(
        "需要安装pymongo: pip install pymongo\n"
        "用于MongoDB数据存储"
    )

from .index_client import CommonCrawlIndexClient
from .warc_stream_parser import WARCStreamParser

logger = logging.getLogger(__name__)


class CommonCrawlImporter:
    """Common Crawl数据导入器"""

    def __init__(
        self,
        mongo_uri: str = 'mongodb://localhost:27017/',
        database: str = 'hidrs_commoncrawl',
        collection: str = 'web_pages',
        batch_size: int = 1000,
        enable_hlig_analysis: bool = True,
        num_workers: int = 4,
    ):
        """
        初始化导入器

        Args:
            mongo_uri: MongoDB连接URI
            database: 数据库名
            collection: 集合名
            batch_size: 批量写入大小
            enable_hlig_analysis: 启用HLIG分析
            num_workers: 工作线程数
        """
        self.batch_size = batch_size
        self.enable_hlig_analysis = enable_hlig_analysis
        self.num_workers = num_workers

        # 连接MongoDB
        try:
            self.client = MongoClient(mongo_uri)
            self.db = self.client[database]
            self.collection = self.db[collection]
            logger.info(f"✅ MongoDB已连接: {database}.{collection}")
        except Exception as e:
            logger.error(f"MongoDB连接失败: {e}")
            raise

        # 创建索引
        self._create_indexes()

        # 初始化组件
        self.index_client = CommonCrawlIndexClient()
        self.warc_parser = WARCStreamParser()

        # 尝试导入HLIG分析器
        self.hlig_analyzer = None
        if self.enable_hlig_analysis:
            try:
                from hidrs.hlig import HLIGAnalyzer
                self.hlig_analyzer = HLIGAnalyzer(output_dim=256)
                logger.info("✅ HLIG分析器已加载")
            except ImportError as e:
                logger.warning(f"⚠️ HLIG分析器导入失败: {e}，将跳过谱分析")
                self.enable_hlig_analysis = False

        # 统计信息
        self.stats = {
            'total_records': 0,
            'inserted': 0,
            'skipped': 0,
            'failed': 0,
            'start_time': None,
            'end_time': None,
        }

        # 写入队列（异步批量写入）
        self.write_queue = Queue(maxsize=batch_size * 10)
        self.shutdown_event = Event()

    def _create_indexes(self):
        """创建MongoDB索引（加速查询）"""
        logger.info("创建MongoDB索引...")

        indexes = [
            ('url', 1),
            ('domain', 1),
            ('timestamp', -1),
            ('crawl_id', 1),
            [('keywords', 'text'), ('title', 'text')],  # 全文索引
        ]

        for index in indexes:
            try:
                if isinstance(index, list):
                    self.collection.create_index(index)
                else:
                    self.collection.create_index([index])
            except Exception as e:
                logger.debug(f"索引创建跳过: {e}")

        logger.info("✅ 索引创建完成")

    def import_from_url_pattern(
        self,
        url_pattern: str,
        limit: int = 10000,
        crawls: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        从URL模式导入数据

        Args:
            url_pattern: URL模式（支持通配符）
            limit: 最大导入数量
            crawls: 指定crawl列表
            filters: WARC记录过滤条件

        Returns:
            导入统计信息
        """
        logger.info(f"开始导入: {url_pattern}, limit={limit}")
        self.stats['start_time'] = time.time()

        try:
            # 1. 搜索索引
            logger.info("步骤1: 搜索Common Crawl索引...")
            index_results = self.index_client.search(
                url_pattern,
                limit=limit,
                crawls=crawls
            )
            logger.info(f"找到 {len(index_results)} 个索引记录")

            # 2. 按WARC文件分组（优化：减少HTTP请求）
            warc_groups = self._group_by_warc(index_results)
            logger.info(f"分组为 {len(warc_groups)} 个WARC文件")

            # 3. 启动异步写入线程
            writer_thread = Thread(target=self._batch_writer, daemon=True)
            writer_thread.start()

            # 4. 流式处理每个WARC文件
            for warc_file, records in warc_groups.items():
                logger.info(f"处理WARC文件: {warc_file} ({len(records)} 条记录)")

                warc_url = self.index_client.get_warc_url(warc_file)

                try:
                    # 流式解析WARC
                    for parsed_record in self.warc_parser.stream_warc(warc_url, filters=filters):
                        # 增强数据
                        enhanced_record = self._enhance_record(parsed_record)

                        # 加入写入队列
                        self.write_queue.put(enhanced_record)
                        self.stats['total_records'] += 1

                except Exception as e:
                    logger.error(f"WARC处理失败 {warc_file}: {e}")
                    continue

            # 5. 等待写入完成
            logger.info("等待所有数据写入完成...")
            self.shutdown_event.set()
            writer_thread.join(timeout=300)

        finally:
            self.stats['end_time'] = time.time()

        # 返回统计信息
        return self._get_import_stats()

    def _group_by_warc(
        self,
        index_results: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """按WARC文件名分组"""
        groups = {}

        for result in index_results:
            filename = result.get('filename', '')
            if filename not in groups:
                groups[filename] = []
            groups[filename].append(result)

        return groups

    def _enhance_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """增强记录（添加HLIG分析、关键词提取等）"""
        # 基础字段
        enhanced = {
            'url': record['url'],
            'domain': record.get('domain', ''),
            'title': record.get('title', ''),
            'text': record.get('text', ''),
            'html': record.get('html', ''),  # 可选：存储HTML（占用大量空间）
            'links': record.get('links', []),
            'timestamp': record.get('timestamp'),
            'status_code': record.get('status_code', 0),
            'content_type': record.get('content_type', ''),
            'content_length': record.get('content_length', 0),
            'warc_record_id': record.get('warc_record_id', ''),
            'warc_file': record.get('warc_file', ''),
            'imported_at': datetime.utcnow(),
        }

        # 生成唯一标识（用于去重）
        enhanced['record_hash'] = self._compute_record_hash(
            record['url'],
            record.get('timestamp', '')
        )

        # 提取关键词和向量（如果启用HLIG分析）
        if self.enable_hlig_analysis and self.hlig_analyzer:
            try:
                text = record.get('text', '')
                if text:
                    # 提取关键词
                    keywords = self.hlig_analyzer.extract_keywords(text, top_n=20)
                    enhanced['keywords'] = keywords

                    # 计算文档向量（可选，根据需求选择方法）
                    # tfidf_vector = self.hlig_analyzer.compute_document_vector(text, method='tfidf')
                    # enhanced['tfidf_vector'] = tfidf_vector.tolist()

                    # 计算拉普拉斯向量（可选，计算密集）
                    # laplacian_vector = self.hlig_analyzer.compute_document_vector(text, method='laplacian')
                    # enhanced['laplacian_vector'] = laplacian_vector.tolist()

                    # 计算全息向量（可选，最复杂）
                    # holographic_vector = self.hlig_analyzer.compute_document_vector(text, method='holographic')
                    # enhanced['holographic_vector'] = holographic_vector.tolist()

            except Exception as e:
                logger.debug(f"HLIG分析失败: {e}")

        return enhanced

    def _compute_record_hash(self, url: str, timestamp: str) -> str:
        """计算记录哈希（用于去重）"""
        content = f"{url}|{timestamp}"
        return hashlib.md5(content.encode()).hexdigest()

    def _batch_writer(self):
        """异步批量写入线程"""
        batch = []

        while not self.shutdown_event.is_set() or not self.write_queue.empty():
            try:
                # 从队列获取记录
                record = self.write_queue.get(timeout=1)
                batch.append(record)

                # 达到batch_size或队列为空时写入
                if len(batch) >= self.batch_size or self.write_queue.empty():
                    if batch:
                        self._write_batch(batch)
                        batch = []

            except Exception:
                # 超时或队列为空，尝试写入剩余数据
                if batch:
                    self._write_batch(batch)
                    batch = []

        # 写入剩余数据
        if batch:
            self._write_batch(batch)

    def _write_batch(self, batch: List[Dict[str, Any]]):
        """批量写入MongoDB"""
        if not batch:
            return

        try:
            # 使用upsert避免重复（基于record_hash）
            operations = [
                UpdateOne(
                    {'record_hash': record['record_hash']},
                    {'$set': record},
                    upsert=True
                )
                for record in batch
            ]

            result = self.collection.bulk_write(operations, ordered=False)

            self.stats['inserted'] += result.upserted_count + result.modified_count
            self.stats['skipped'] += len(batch) - result.upserted_count - result.modified_count

            logger.info(
                f"批量写入完成: 插入={result.upserted_count}, "
                f"更新={result.modified_count}, 跳过={len(batch) - result.upserted_count - result.modified_count}"
            )

        except BulkWriteError as e:
            logger.error(f"批量写入部分失败: {e.details}")
            self.stats['failed'] += len(e.details.get('writeErrors', []))

        except Exception as e:
            logger.error(f"批量写入失败: {e}")
            self.stats['failed'] += len(batch)

    def _get_import_stats(self) -> Dict[str, Any]:
        """获取导入统计信息"""
        duration = 0
        if self.stats['start_time'] and self.stats['end_time']:
            duration = self.stats['end_time'] - self.stats['start_time']

        records_per_sec = 0
        if duration > 0:
            records_per_sec = self.stats['total_records'] / duration

        return {
            'total_records': self.stats['total_records'],
            'inserted': self.stats['inserted'],
            'skipped': self.stats['skipped'],
            'failed': self.stats['failed'],
            'duration_seconds': duration,
            'records_per_second': records_per_sec,
        }

    def get_collection_stats(self) -> Dict[str, Any]:
        """获取MongoDB集合统计"""
        return {
            'total_documents': self.collection.count_documents({}),
            'unique_domains': len(self.collection.distinct('domain')),
            'unique_warc_files': len(self.collection.distinct('warc_file')),
            'storage_size_mb': self.db.command('collstats', self.collection.name)['size'] / (1024 * 1024),
        }

    def close(self):
        """关闭连接"""
        if self.client:
            self.client.close()
            logger.info("MongoDB连接已关闭")
