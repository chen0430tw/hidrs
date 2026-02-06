"""
Common Crawl 索引客户端

功能：
1. 搜索Common Crawl索引（CDX API）
2. 多备用接口（comcrawl / CDX API / boto3）
3. 自动降级策略
4. 缓存优化

支持的搜索方式：
- URL精确匹配: example.com/page.html
- URL通配符: *.example.com/*
- 域名搜索: domain:example.com
- 时间范围: from=20240101&to=20240131
"""

import logging
import requests
from typing import List, Dict, Any, Optional, Iterator
from datetime import datetime
from urllib.parse import quote
import json

logger = logging.getLogger(__name__)


class CommonCrawlIndexClient:
    """Common Crawl索引搜索客户端（支持多备用接口）"""

    # Common Crawl CDX API端点
    CDX_API_URL = "https://index.commoncrawl.org"

    def __init__(
        self,
        use_comcrawl: bool = True,
        use_cdx_api: bool = True,
        use_boto3: bool = False,
        cache_enabled: bool = True,
    ):
        """
        初始化索引客户端

        Args:
            use_comcrawl: 使用comcrawl库（推荐，最简单）
            use_cdx_api: 使用CDX API（备用，无需额外依赖）
            use_boto3: 使用boto3直连S3（备用，适合大规模）
            cache_enabled: 启用本地缓存
        """
        self.use_comcrawl = use_comcrawl
        self.use_cdx_api = use_cdx_api
        self.use_boto3 = use_boto3
        self.cache_enabled = cache_enabled

        # 尝试导入comcrawl
        self.comcrawl_available = False
        if self.use_comcrawl:
            try:
                from comcrawl import IndexClient
                self.IndexClient = IndexClient
                self.comcrawl_available = True
                logger.info("✅ comcrawl库可用（推荐）")
            except ImportError:
                logger.warning(
                    "⚠️ comcrawl库未安装，将使用CDX API备用接口\n"
                    "安装: pip install comcrawl"
                )

        # 尝试导入boto3
        self.boto3_available = False
        if self.use_boto3:
            try:
                import boto3
                self.boto3 = boto3
                self.boto3_available = True
                logger.info("✅ boto3库可用（备用）")
            except ImportError:
                logger.warning("boto3未安装，S3直连功能不可用")

        # 获取可用的crawl列表
        self.available_crawls = self._get_available_crawls()
        logger.info(f"发现 {len(self.available_crawls)} 个可用的crawl")

    def search(
        self,
        url_pattern: str,
        limit: int = 1000,
        crawls: Optional[List[str]] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        filter_status: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        """
        搜索Common Crawl索引

        Args:
            url_pattern: URL模式（支持通配符*）
                - 精确: https://example.com/page.html
                - 通配符: *.example.com/*
                - 前缀: example.com/*
            limit: 最大结果数
            crawls: 指定crawl列表（如['CC-MAIN-2024-10']），None=最新
            from_date: 开始日期 YYYYMMDD
            to_date: 结束日期 YYYYMMDD
            filter_status: HTTP状态码过滤 [200, 301, 302]

        Returns:
            结果列表:
            [
                {
                    'url': str,
                    'timestamp': str,  # ISO格式
                    'status_code': int,
                    'mime_type': str,
                    'filename': str,  # WARC文件名
                    'offset': int,    # WARC文件偏移
                    'length': int,    # 记录长度
                    'digest': str,    # 内容哈希
                }
            ]
        """
        logger.info(f"搜索索引: {url_pattern}, limit={limit}")

        # 策略1: 使用comcrawl（优先，最简单）
        if self.comcrawl_available:
            try:
                return self._search_with_comcrawl(
                    url_pattern, limit, crawls, from_date, to_date, filter_status
                )
            except Exception as e:
                logger.warning(f"comcrawl搜索失败: {e}，降级到CDX API")

        # 策略2: 使用CDX API（备用）
        if self.use_cdx_api:
            try:
                return self._search_with_cdx_api(
                    url_pattern, limit, crawls, from_date, to_date, filter_status
                )
            except Exception as e:
                logger.warning(f"CDX API搜索失败: {e}")

        # 策略3: 使用boto3直连S3（最后备用）
        if self.boto3_available:
            try:
                return self._search_with_boto3(
                    url_pattern, limit, crawls, from_date, to_date, filter_status
                )
            except Exception as e:
                logger.error(f"boto3搜索失败: {e}")

        raise RuntimeError("所有搜索接口均不可用")

    def _search_with_comcrawl(
        self,
        url_pattern: str,
        limit: int,
        crawls: Optional[List[str]],
        from_date: Optional[str],
        to_date: Optional[str],
        filter_status: Optional[List[int]],
    ) -> List[Dict[str, Any]]:
        """使用comcrawl库搜索（推荐）"""
        logger.info("使用comcrawl接口")

        # 使用最新的crawls
        if not crawls:
            crawls = self.available_crawls[:3]  # 最近3个月

        client = self.IndexClient(crawls)

        # 执行搜索
        results = []
        for result in client.search(url_pattern):
            # 应用过滤
            if filter_status and result.get('status') not in filter_status:
                continue

            # 应用时间过滤
            if from_date or to_date:
                timestamp = result.get('timestamp', '')
                if from_date and timestamp < from_date:
                    continue
                if to_date and timestamp > to_date:
                    continue

            # 标准化结果格式
            results.append(self._normalize_result(result))

            if len(results) >= limit:
                break

        logger.info(f"comcrawl返回 {len(results)} 个结果")
        return results

    def _search_with_cdx_api(
        self,
        url_pattern: str,
        limit: int,
        crawls: Optional[List[str]],
        from_date: Optional[str],
        to_date: Optional[str],
        filter_status: Optional[List[int]],
    ) -> List[Dict[str, Any]]:
        """使用CDX API搜索（备用）"""
        logger.info("使用CDX API接口")

        # 构建查询参数
        params = {
            'url': url_pattern,
            'output': 'json',
            'limit': limit,
        }

        if from_date:
            params['from'] = from_date
        if to_date:
            params['to'] = to_date
        if filter_status:
            params['filter'] = f"status:{','.join(map(str, filter_status))}"

        # 请求CDX API
        response = requests.get(
            f"{self.CDX_API_URL}/search",
            params=params,
            timeout=60
        )
        response.raise_for_status()

        # 解析结果
        results = []
        for line in response.text.strip().split('\n'):
            if not line:
                continue

            try:
                result = json.loads(line)
                results.append(self._normalize_result(result))
            except json.JSONDecodeError:
                continue

        logger.info(f"CDX API返回 {len(results)} 个结果")
        return results

    def _search_with_boto3(
        self,
        url_pattern: str,
        limit: int,
        crawls: Optional[List[str]],
        from_date: Optional[str],
        to_date: Optional[str],
        filter_status: Optional[List[int]],
    ) -> List[Dict[str, Any]]:
        """使用boto3直连S3搜索（备用）"""
        logger.info("使用boto3 S3直连")

        # TODO: 实现S3直连逻辑
        # 这需要直接读取S3上的索引文件
        raise NotImplementedError("boto3 S3直连功能待实现")

    def _normalize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """标准化不同来源的结果格式"""
        # comcrawl格式
        if 'urlkey' in result:
            return {
                'url': result.get('url', ''),
                'timestamp': self._parse_timestamp(result.get('timestamp', '')),
                'status_code': int(result.get('status', 0)),
                'mime_type': result.get('mime', ''),
                'filename': result.get('filename', ''),
                'offset': int(result.get('offset', 0)),
                'length': int(result.get('length', 0)),
                'digest': result.get('digest', ''),
            }

        # CDX API格式（类似）
        return {
            'url': result.get('url', ''),
            'timestamp': self._parse_timestamp(result.get('timestamp', '')),
            'status_code': int(result.get('status', 0)),
            'mime_type': result.get('mime-type', result.get('mime', '')),
            'filename': result.get('filename', ''),
            'offset': int(result.get('offset', 0)),
            'length': int(result.get('length', 0)),
            'digest': result.get('digest', ''),
        }

    def _parse_timestamp(self, timestamp_str: str) -> str:
        """解析时间戳为ISO格式"""
        try:
            # Common Crawl格式: YYYYMMDDHHmmss
            if len(timestamp_str) == 14:
                dt = datetime.strptime(timestamp_str, '%Y%m%d%H%M%S')
                return dt.isoformat()
        except:
            pass
        return timestamp_str

    def _get_available_crawls(self) -> List[str]:
        """获取可用的crawl列表（倒序，最新在前）"""
        try:
            response = requests.get(
                f"{self.CDX_API_URL}/collinfo.json",
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            # 提取crawl ID并倒序
            crawls = [item['id'] for item in data if 'id' in item]
            crawls.reverse()

            return crawls

        except Exception as e:
            logger.error(f"获取crawl列表失败: {e}")
            # 返回最近几个月的默认列表
            return [
                'CC-MAIN-2026-02',
                'CC-MAIN-2026-01',
                'CC-MAIN-2025-12',
            ]

    def get_warc_url(self, filename: str) -> str:
        """获取WARC文件的完整URL"""
        return f"https://data.commoncrawl.org/{filename}"

    def stream_results(
        self,
        url_pattern: str,
        crawls: Optional[List[str]] = None,
        batch_size: int = 100,
    ) -> Iterator[List[Dict[str, Any]]]:
        """
        流式返回搜索结果（适合大量结果）

        Args:
            url_pattern: URL模式
            crawls: crawl列表
            batch_size: 每批返回的结果数

        Yields:
            每批结果列表
        """
        logger.info(f"流式搜索: {url_pattern}")

        if not crawls:
            crawls = self.available_crawls[:3]

        for crawl in crawls:
            logger.info(f"搜索crawl: {crawl}")

            try:
                results = self.search(
                    url_pattern,
                    limit=batch_size,
                    crawls=[crawl]
                )

                if results:
                    yield results

            except Exception as e:
                logger.error(f"搜索crawl {crawl} 失败: {e}")
                continue
