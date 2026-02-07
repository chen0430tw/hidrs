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
        """
        使用boto3直连S3搜索（备用）

        Common Crawl索引存储在S3上：
        - Bucket: commoncrawl (公开，无需认证)
        - 索引路径: cc-index/collections/{crawl}/indexes/
        - 索引格式: CDX集群索引 (cluster.idx) + 分片CDX文件

        流程：
        1. 从cluster.idx找到URL对应的CDX分片
        2. 下载对应分片的CDX数据
        3. 在分片中查找匹配的URL记录
        """
        logger.info("使用boto3 S3直连")

        import gzip
        import io
        from bisect import bisect_left, bisect_right

        # 无需认证即可访问commoncrawl公开bucket
        s3 = self.boto3.client(
            's3',
            config=self.boto3.session.Config(signature_version='UNSIGNED')
        )
        bucket = 'commoncrawl'

        if not crawls:
            crawls = self.available_crawls[:3]

        # SURT格式转换：将URL转为排序友好的反转域名格式
        # 例如: example.com/page → com,example)/page
        search_key = self._url_to_surt(url_pattern)

        results = []

        for crawl in crawls:
            if len(results) >= limit:
                break

            try:
                # 步骤1: 下载cluster.idx（CDX分片索引）
                cluster_idx_key = f"cc-index/collections/{crawl}/indexes/cluster.idx"
                logger.debug(f"下载cluster.idx: {cluster_idx_key}")

                cluster_response = s3.get_object(Bucket=bucket, Key=cluster_idx_key)
                cluster_data = cluster_response['Body'].read().decode('utf-8')
                cluster_lines = cluster_data.strip().split('\n')

                # 步骤2: 二分查找定位CDX分片
                # cluster.idx每行格式: SURT_KEY\tCDX_SHARD_NUM\tOFFSET\tLENGTH
                shard_nums = self._find_cdx_shards(cluster_lines, search_key)

                if not shard_nums:
                    logger.debug(f"crawl {crawl} 中未找到匹配的CDX分片")
                    continue

                # 步骤3: 下载并搜索CDX分片
                for shard_num in shard_nums:
                    if len(results) >= limit:
                        break

                    cdx_key = f"cc-index/collections/{crawl}/indexes/cdx-{shard_num:05d}.gz"
                    logger.debug(f"下载CDX分片: {cdx_key}")

                    try:
                        cdx_response = s3.get_object(Bucket=bucket, Key=cdx_key)
                        compressed = cdx_response['Body'].read()

                        # 解压gzip
                        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as f:
                            cdx_text = f.read().decode('utf-8')

                        # 逐行搜索匹配记录
                        for line in cdx_text.split('\n'):
                            if not line.strip():
                                continue

                            # CDX行格式: SURT_KEY TIMESTAMP JSON_DATA
                            parts = line.split(' ', 2)
                            if len(parts) < 3:
                                continue

                            surt_key = parts[0]
                            timestamp = parts[1]

                            # URL匹配检查
                            if not self._surt_matches(surt_key, search_key, url_pattern):
                                continue

                            # 解析JSON部分
                            try:
                                record = json.loads(parts[2])
                            except json.JSONDecodeError:
                                continue

                            # 应用时间过滤
                            if from_date and timestamp < from_date:
                                continue
                            if to_date and timestamp > to_date:
                                continue

                            # 应用状态码过滤
                            status_code = int(record.get('status', 0))
                            if filter_status and status_code not in filter_status:
                                continue

                            record['timestamp'] = timestamp
                            results.append(self._normalize_result(record))

                            if len(results) >= limit:
                                break

                    except Exception as e:
                        logger.warning(f"CDX分片 {cdx_key} 读取失败: {e}")
                        continue

            except Exception as e:
                logger.warning(f"crawl {crawl} S3搜索失败: {e}")
                continue

        logger.info(f"boto3 S3返回 {len(results)} 个结果")
        return results

    def _url_to_surt(self, url: str) -> str:
        """
        将URL转换为SURT（Sort-friendly URI Rewriting Transform）格式

        SURT是Common Crawl索引的排序键格式：
        - 反转域名部分，用逗号分隔
        - 例如: http://www.example.com/page → com,example,www)/page
        - 通配符*保留用于前缀匹配
        """
        # 去掉协议前缀
        url_clean = url
        for prefix in ['https://', 'http://']:
            if url_clean.startswith(prefix):
                url_clean = url_clean[len(prefix):]
                break

        # 分离域名和路径
        if '/' in url_clean:
            domain, path = url_clean.split('/', 1)
            path = '/' + path
        else:
            domain = url_clean
            path = ''

        # 处理通配符
        if domain.startswith('*.'):
            domain = domain[2:]
            # 通配符域名：返回反转的基础域名作为前缀搜索键
            parts = domain.split('.')
            parts.reverse()
            return ','.join(parts) + ','

        # 去掉端口号
        if ':' in domain:
            domain = domain.split(':')[0]

        # 反转域名
        parts = domain.split('.')
        parts.reverse()
        surt = ','.join(parts) + ')'

        if path and path != '/*':
            surt += path.rstrip('*')

        return surt

    def _find_cdx_shards(self, cluster_lines: List[str], search_key: str) -> List[int]:
        """
        从cluster.idx中定位包含搜索键的CDX分片编号

        cluster.idx每行格式: SURT_KEY \\t CDX_SHARD_PATH \\t OFFSET \\t LENGTH \\t CDX_SHARD_NUM
        使用二分查找定位目标分片范围
        """
        # 提取所有SURT键用于二分查找
        keys = []
        shard_info = []
        for line in cluster_lines:
            parts = line.split('\t')
            if len(parts) >= 2:
                keys.append(parts[0])
                shard_info.append(parts)

        if not keys:
            return []

        # 二分查找：找到search_key可能落入的分片范围
        idx = bisect_left(keys, search_key)

        # 取前后各1个分片以确保覆盖（SURT前缀匹配可能跨分片）
        shard_nums = set()
        for i in range(max(0, idx - 1), min(len(shard_info), idx + 2)):
            try:
                # 分片编号从路径中提取: cdx-NNNNN.gz
                shard_path = shard_info[i][1] if len(shard_info[i]) > 1 else ''
                if 'cdx-' in shard_path:
                    num_str = shard_path.split('cdx-')[1].split('.')[0]
                    shard_nums.add(int(num_str))
                else:
                    # 有些cluster.idx格式直接是数字
                    shard_nums.add(i)
            except (ValueError, IndexError):
                shard_nums.add(i)

        return sorted(shard_nums)

    def _surt_matches(self, surt_key: str, search_surt: str, original_pattern: str) -> bool:
        """
        检查CDX记录的SURT键是否匹配搜索模式

        支持:
        - 精确匹配
        - 前缀匹配（通配符*）
        - 域名匹配
        """
        # 通配符模式：前缀匹配
        if '*' in original_pattern:
            return surt_key.startswith(search_surt)

        # 精确或前缀匹配
        return surt_key.startswith(search_surt)

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
