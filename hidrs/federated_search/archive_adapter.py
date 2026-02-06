"""
Internet Archive适配器 - 使用Archive.org API

降级层实现 - Priority 4
用于搜索历史文档和存档内容
"""
import logging
import requests
from typing import List, Dict, Optional
from datetime import datetime
from .base_adapter import SearchAdapter, AdapterType

logger = logging.getLogger(__name__)


class ArchiveSearchAdapter(SearchAdapter):
    """Internet Archive搜索适配器 - 降级层"""

    def __init__(self):
        """
        初始化Archive搜索适配器

        注意:
        - Internet Archive提供免费的搜索API
        - 无需API密钥
        - 文档: https://archive.org/services/docs/api/
        """
        super().__init__(
            name="Internet Archive",
            adapter_type=AdapterType.FALLBACK,
            priority=4  # 降级层第三优先级
        )

        self.base_url = "https://archive.org/advancedsearch.php"
        self.details_url = "https://archive.org/metadata"

        # Archive.org支持的媒体类型
        self.media_types = [
            'texts',        # 文本/书籍
            'movies',       # 视频
            'audio',        # 音频
            'software',     # 软件
            'image',        # 图片
            'web',          # 网页存档
            'collection',   # 集合
            'account'       # 账户
        ]

        self._request_count = 0

        logger.info("[ArchiveSearchAdapter] 初始化完成")

    def search(self, query: str, limit: int = 10, **kwargs) -> List[Dict]:
        """
        执行Archive搜索

        参数:
        - query: 搜索查询
        - limit: 返回结果数量
        - **kwargs: 额外参数
          - media_type: 媒体类型 (默认: 'texts')
          - sort: 排序方式 ('relevance', 'date', 'downloads', 'createdate')

        返回:
        - 结果列表，每个结果包含: title, url, snippet, source, timestamp, score, metadata
        """
        if not self.is_available():
            logger.warning("[ArchiveSearchAdapter] 适配器不可用")
            return []

        try:
            logger.info(f"[ArchiveSearchAdapter] 搜索: '{query}' (limit={limit})")

            # 媒体类型过滤
            media_type = kwargs.get('media_type', 'texts')
            if media_type not in self.media_types:
                media_type = 'texts'

            # 排序方式
            sort_options = {
                'relevance': 'score desc',
                'date': 'date desc',
                'downloads': 'downloads desc',
                'createdate': 'createdate desc'
            }
            sort = kwargs.get('sort', 'relevance')
            sort_param = sort_options.get(sort, 'score desc')

            # 构建搜索查询
            # Archive.org使用Lucene查询语法
            search_query = f"({query}) AND mediatype:({media_type})"

            # 构建请求参数
            params = {
                'q': search_query,
                'fl[]': [  # 返回字段
                    'identifier',     # 唯一标识符
                    'title',          # 标题
                    'description',    # 描述
                    'mediatype',      # 媒体类型
                    'collection',     # 所属集合
                    'creator',        # 创建者
                    'date',           # 日期
                    'year',           # 年份
                    'downloads',      # 下载次数
                    'item_size',      # 大小
                    'format'          # 格式
                ],
                'sort[]': sort_param,
                'rows': limit,
                'page': 1,
                'output': 'json'
            }

            # 发送请求
            response = requests.get(
                self.base_url,
                params=params,
                timeout=15
            )
            response.raise_for_status()

            self._request_count += 1
            data = response.json()

            # 解析结果
            results = []
            docs = data.get('response', {}).get('docs', [])
            num_found = data.get('response', {}).get('numFound', 0)

            logger.info(f"[ArchiveSearchAdapter] 找到 {num_found} 个结果")

            for idx, doc in enumerate(docs):
                identifier = doc.get('identifier', '')
                title = doc.get('title', '')
                description = doc.get('description', '')

                # 处理description（可能是数组）
                if isinstance(description, list):
                    description = ' '.join(description)

                # 构建Archive.org URL
                url = f"https://archive.org/details/{identifier}"

                # 计算得分
                downloads = doc.get('downloads', 0)
                if isinstance(downloads, (int, float)):
                    # 基于下载次数的得分（对数缩放）
                    import math
                    download_score = math.log10(downloads + 1) / 10.0
                else:
                    download_score = 0.0

                # 位置衰减 + 下载次数
                position_score = 1.0 - (idx * 0.05)
                final_score = 0.7 * position_score + 0.3 * download_score

                result = {
                    'title': title if isinstance(title, str) else str(title),
                    'url': url,
                    'snippet': description[:300] if description else '',  # 限制长度
                    'source': self.name,
                    'timestamp': datetime.now().isoformat(),
                    'score': final_score,
                    'metadata': {
                        'adapter': self.name,
                        'adapter_type': self.adapter_type.name,
                        'priority': self.priority,
                        'identifier': identifier,
                        'mediatype': doc.get('mediatype', ''),
                        'collection': doc.get('collection', []),
                        'creator': doc.get('creator', ''),
                        'date': doc.get('date', ''),
                        'year': doc.get('year', ''),
                        'downloads': downloads,
                        'format': doc.get('format', []),
                        'item_size': doc.get('item_size', 0)
                    }
                }

                results.append(result)

            logger.info(f"[ArchiveSearchAdapter] 返回 {len(results)} 个结果")
            return results

        except requests.exceptions.HTTPError as e:
            logger.error(f"[ArchiveSearchAdapter] HTTP错误: {e}")
            return []

        except requests.exceptions.Timeout:
            logger.error("[ArchiveSearchAdapter] 请求超时")
            return []

        except Exception as e:
            logger.error(f"[ArchiveSearchAdapter] 搜索失败: {e}")
            return []

    def search_wayback(self, url: str, timestamp: Optional[str] = None) -> Optional[Dict]:
        """
        搜索Wayback Machine存档

        参数:
        - url: 要查询的URL
        - timestamp: 时间戳（格式: YYYYMMDDhhmmss，可选）

        返回:
        - 存档信息字典，如果没有找到则返回None
        """
        try:
            # Wayback Machine CDX API
            cdx_url = "https://web.archive.org/cdx/search/cdx"
            params = {
                'url': url,
                'output': 'json',
                'limit': 1
            }

            if timestamp:
                params['closest'] = timestamp

            response = requests.get(cdx_url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            if len(data) > 1:  # 第一行是标题
                fields = data[0]
                values = data[1]
                archive_info = dict(zip(fields, values))

                # 构建Wayback URL
                wayback_url = f"https://web.archive.org/web/{archive_info['timestamp']}/{archive_info['original']}"

                return {
                    'wayback_url': wayback_url,
                    'timestamp': archive_info['timestamp'],
                    'original_url': archive_info['original'],
                    'mimetype': archive_info.get('mimetype', ''),
                    'statuscode': archive_info.get('statuscode', ''),
                    'digest': archive_info.get('digest', '')
                }

            return None

        except Exception as e:
            logger.error(f"[ArchiveSearchAdapter] Wayback查询失败: {e}")
            return None

    def is_available(self) -> bool:
        """检查适配器是否可用"""
        return self._available

    def is_core(self) -> bool:
        """是否为核心适配器"""
        return False  # Archive是降级层

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'name': self.name,
            'type': self.adapter_type.name,
            'priority': self.priority,
            'available': self.is_available(),
            'request_count': self._request_count,
            'supported_media_types': self.media_types
        }
