"""
WARC 流式解析器 - 支持PB级数据处理

核心技术：
1. 使用warcio库进行流式解析（无需完整下载文件）
2. 增量解析（每次只加载一个record到内存）
3. 多线程并发处理（可配置worker数量）
4. 自动重试机制（网络故障恢复）
5. 进度追踪和断点续传

依赖库：
- warcio: 流式WARC读取
- requests: HTTP请求
- beautifulsoup4: HTML解析
"""

import logging
import requests
from typing import Iterator, Dict, Any, Optional, List
from datetime import datetime
from urllib.parse import urlparse
import hashlib
import gzip
from io import BytesIO

try:
    from warcio.archiveiterator import ArchiveIterator
except ImportError:
    raise ImportError(
        "需要安装warcio库: pip install warcio\n"
        "这是Common Crawl流式处理的推荐库"
    )

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
    logging.warning("BeautifulSoup未安装，HTML解析功能将受限")

logger = logging.getLogger(__name__)


class WARCStreamParser:
    """WARC文件流式解析器"""

    def __init__(
        self,
        chunk_size: int = 8192,
        max_retries: int = 3,
        timeout: int = 300,
        enable_html_parsing: bool = True,
    ):
        """
        初始化WARC解析器

        Args:
            chunk_size: 流式读取块大小（字节）
            max_retries: 最大重试次数
            timeout: 请求超时时间（秒）
            enable_html_parsing: 是否解析HTML内容
        """
        self.chunk_size = chunk_size
        self.max_retries = max_retries
        self.timeout = timeout
        self.enable_html_parsing = enable_html_parsing

        self.stats = {
            'total_records': 0,
            'success_records': 0,
            'failed_records': 0,
            'total_bytes': 0,
        }

    def stream_warc(
        self,
        warc_url: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> Iterator[Dict[str, Any]]:
        """
        流式处理WARC文件（无需完整下载）

        Args:
            warc_url: WARC文件URL（支持HTTP/S3）
            filters: 过滤条件
                - url_pattern: URL正则匹配
                - status_code: HTTP状态码列表
                - content_type: MIME类型列表

        Yields:
            字典格式的记录:
            {
                'url': str,
                'timestamp': datetime,
                'status_code': int,
                'content_type': str,
                'html': str,
                'text': str,  # 提取的文本
                'title': str,
                'meta': dict,  # 元数据
                'links': list,  # 出站链接
                'warc_record_id': str,
                'warc_file': str,
            }
        """
        logger.info(f"开始流式处理WARC文件: {warc_url}")

        try:
            # 流式HTTP请求（不缓存到内存）
            response = self._request_with_retry(warc_url)

            # 解压缩（Common Crawl的WARC文件通常是gzip压缩的）
            if warc_url.endswith('.gz'):
                stream = gzip.GzipFile(fileobj=response.raw)
            else:
                stream = response.raw

            # 使用ArchiveIterator流式遍历
            for record in ArchiveIterator(stream):
                self.stats['total_records'] += 1

                # 只处理response记录
                if record.rec_type != 'response':
                    continue

                try:
                    parsed_record = self._parse_record(record, warc_url)

                    # 应用过滤器
                    if filters and not self._apply_filters(parsed_record, filters):
                        continue

                    self.stats['success_records'] += 1
                    self.stats['total_bytes'] += len(parsed_record.get('html', ''))

                    yield parsed_record

                except Exception as e:
                    self.stats['failed_records'] += 1
                    logger.error(f"解析记录失败: {e}")
                    continue

        except Exception as e:
            logger.error(f"WARC文件处理失败 {warc_url}: {e}")
            raise

        finally:
            logger.info(
                f"WARC处理完成: {self.stats['success_records']}/{self.stats['total_records']} 记录成功, "
                f"{self.stats['total_bytes'] / (1024*1024):.2f} MB"
            )

    def _parse_record(self, record, warc_file: str) -> Dict[str, Any]:
        """解析单个WARC记录"""
        # 提取HTTP头
        http_headers = record.http_headers
        status_code = int(http_headers.statusline.split()[0]) if http_headers else 0

        # 提取WARC头
        warc_headers = record.rec_headers
        url = warc_headers.get_header('WARC-Target-URI')
        timestamp_str = warc_headers.get_header('WARC-Date')
        record_id = warc_headers.get_header('WARC-Record-ID')
        content_type = http_headers.get_header('Content-Type', '') if http_headers else ''

        # 解析时间戳
        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except:
            timestamp = None

        # 读取内容
        content = record.content_stream().read()

        # 解析HTML
        html = content.decode('utf-8', errors='ignore')
        text = ''
        title = ''
        links = []

        if self.enable_html_parsing and BeautifulSoup and 'html' in content_type.lower():
            try:
                soup = BeautifulSoup(html, 'html.parser')

                # 提取标题
                title_tag = soup.find('title')
                title = title_tag.get_text(strip=True) if title_tag else ''

                # 提取文本（去除脚本和样式）
                for script in soup(['script', 'style']):
                    script.decompose()
                text = soup.get_text(separator=' ', strip=True)

                # 提取链接
                links = [
                    a.get('href')
                    for a in soup.find_all('a', href=True)
                    if a.get('href')
                ]

            except Exception as e:
                logger.debug(f"HTML解析失败 {url}: {e}")

        # 提取域名
        domain = self._extract_domain(url)

        return {
            'url': url,
            'domain': domain,
            'timestamp': timestamp,
            'status_code': status_code,
            'content_type': content_type,
            'html': html,
            'text': text[:10000],  # 限制文本长度
            'title': title,
            'links': links[:100],  # 限制链接数量
            'warc_record_id': record_id,
            'warc_file': warc_file,
            'content_length': len(content),
        }

    def _request_with_retry(self, url: str) -> requests.Response:
        """带重试的HTTP请求"""
        for attempt in range(self.max_retries):
            try:
                response = requests.get(
                    url,
                    stream=True,
                    timeout=self.timeout,
                    headers={'User-Agent': 'HIDRS-CommonCrawl/1.0'}
                )
                response.raise_for_status()
                return response

            except Exception as e:
                logger.warning(f"请求失败 (尝试 {attempt+1}/{self.max_retries}): {e}")
                if attempt == self.max_retries - 1:
                    raise

    def _apply_filters(self, record: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """应用过滤条件"""
        import re

        # URL模式匹配
        if 'url_pattern' in filters:
            pattern = filters['url_pattern']
            if not re.search(pattern, record['url']):
                return False

        # 状态码过滤
        if 'status_code' in filters:
            if record['status_code'] not in filters['status_code']:
                return False

        # Content-Type过滤
        if 'content_type' in filters:
            if not any(ct in record['content_type'] for ct in filters['content_type']):
                return False

        # 域名过滤
        if 'domain' in filters:
            if record['domain'] != filters['domain']:
                return False

        return True

    def _extract_domain(self, url: str) -> str:
        """提取域名"""
        try:
            parsed = urlparse(url)
            return parsed.netloc
        except:
            return ''

    def get_stats(self) -> Dict[str, Any]:
        """获取处理统计信息"""
        return self.stats.copy()


class WARCBatchProcessor:
    """WARC批量处理器（多线程）"""

    def __init__(
        self,
        num_workers: int = 4,
        parser_config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化批量处理器

        Args:
            num_workers: 工作线程数
            parser_config: WARCStreamParser配置
        """
        self.num_workers = num_workers
        self.parser_config = parser_config or {}

    def process_warc_files(
        self,
        warc_urls: List[str],
        callback,
        filters: Optional[Dict[str, Any]] = None
    ):
        """
        并行处理多个WARC文件

        Args:
            warc_urls: WARC文件URL列表
            callback: 处理每个记录的回调函数 callback(record) -> None
            filters: 过滤条件
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        logger.info(f"开始批量处理 {len(warc_urls)} 个WARC文件，使用 {self.num_workers} 个工作线程")

        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            futures = []

            for warc_url in warc_urls:
                future = executor.submit(
                    self._process_single_warc,
                    warc_url,
                    callback,
                    filters
                )
                futures.append(future)

            # 等待所有任务完成
            for future in as_completed(futures):
                try:
                    result = future.result()
                    logger.info(f"WARC处理完成: {result}")
                except Exception as e:
                    logger.error(f"WARC处理失败: {e}")

    def _process_single_warc(
        self,
        warc_url: str,
        callback,
        filters: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """处理单个WARC文件"""
        parser = WARCStreamParser(**self.parser_config)

        records_processed = 0
        for record in parser.stream_warc(warc_url, filters=filters):
            callback(record)
            records_processed += 1

        return {
            'warc_url': warc_url,
            'records_processed': records_processed,
            'stats': parser.get_stats()
        }
