"""
Google搜索适配器 - 使用Google Custom Search API

降级层实现 - Priority 2
当HIDRS Core不可用时的备选方案
"""
import os
import logging
import requests
from typing import List, Dict, Optional
from datetime import datetime
from .base_adapter import SearchAdapter, AdapterType

logger = logging.getLogger(__name__)


class GoogleSearchAdapter(SearchAdapter):
    """Google搜索适配器 - 降级层"""

    def __init__(self, api_key: Optional[str] = None, search_engine_id: Optional[str] = None):
        """
        初始化Google搜索适配器

        参数:
        - api_key: Google Custom Search API密钥
        - search_engine_id: 搜索引擎ID（CX）

        注意:
        - 需要在Google Cloud Console创建Custom Search API凭证
        - 免费额度: 100次/天
        - 文档: https://developers.google.com/custom-search/v1/overview
        """
        super().__init__(
            name="Google搜索",
            adapter_type=AdapterType.FALLBACK,
            priority=2  # 降级层第一优先级
        )

        self.api_key = api_key or os.getenv('GOOGLE_SEARCH_API_KEY')
        self.search_engine_id = search_engine_id or os.getenv('GOOGLE_SEARCH_ENGINE_ID')

        if not self.api_key or not self.search_engine_id:
            logger.warning("[GoogleSearchAdapter] API密钥或搜索引擎ID未配置")
            self._available = False

        self.base_url = "https://www.googleapis.com/customsearch/v1"
        self._request_count = 0
        self._daily_limit = 100

        logger.info(f"[GoogleSearchAdapter] 初始化完成: {'可用' if self._available else '不可用'}")

    def search(self, query: str, limit: int = 10, **kwargs) -> List[Dict]:
        """
        执行Google搜索

        参数:
        - query: 搜索查询
        - limit: 返回结果数量（最大10）
        - **kwargs: 额外参数
          - lang: 语言 (默认: None)
          - safe: 安全搜索 (默认: 'off')

        返回:
        - 结果列表，每个结果包含: title, url, snippet, source, timestamp, score, metadata
        """
        if not self.is_available():
            logger.warning("[GoogleSearchAdapter] 适配器不可用")
            return []

        if self._request_count >= self._daily_limit:
            logger.warning("[GoogleSearchAdapter] 达到每日请求限制")
            self._available = False
            return []

        try:
            logger.info(f"[GoogleSearchAdapter] 搜索: '{query}' (limit={limit})")

            # 构建请求参数
            params = {
                'key': self.api_key,
                'cx': self.search_engine_id,
                'q': query,
                'num': min(limit, 10),  # Google API单次最多返回10个结果
                'safe': kwargs.get('safe', 'off')
            }

            # 语言过滤
            if 'lang' in kwargs:
                params['lr'] = f"lang_{kwargs['lang']}"

            # 发送请求
            response = requests.get(
                self.base_url,
                params=params,
                timeout=10
            )
            response.raise_for_status()

            self._request_count += 1
            data = response.json()

            # 解析结果
            results = []
            items = data.get('items', [])

            for idx, item in enumerate(items):
                result = {
                    'title': item.get('title', ''),
                    'url': item.get('link', ''),
                    'snippet': item.get('snippet', ''),
                    'source': self.name,
                    'timestamp': datetime.now().isoformat(),
                    'score': 1.0 - (idx * 0.05),  # 简单的位置衰减得分
                    'metadata': {
                        'adapter': self.name,
                        'adapter_type': self.adapter_type.name,
                        'priority': self.priority,
                        'display_link': item.get('displayLink', ''),
                        'formatted_url': item.get('formattedUrl', ''),
                        'html_snippet': item.get('htmlSnippet', ''),
                        'kind': item.get('kind', '')
                    }
                }

                # 添加图片信息（如果有）
                if 'pagemap' in item and 'cse_image' in item['pagemap']:
                    images = item['pagemap']['cse_image']
                    if images:
                        result['metadata']['image'] = images[0].get('src', '')

                results.append(result)

            logger.info(f"[GoogleSearchAdapter] 返回 {len(results)} 个结果")
            return results

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                logger.error("[GoogleSearchAdapter] API密钥无效或已超出配额")
                self._available = False
            else:
                logger.error(f"[GoogleSearchAdapter] HTTP错误: {e}")
            return []

        except requests.exceptions.Timeout:
            logger.error("[GoogleSearchAdapter] 请求超时")
            return []

        except Exception as e:
            logger.error(f"[GoogleSearchAdapter] 搜索失败: {e}")
            return []

    def is_available(self) -> bool:
        """检查适配器是否可用"""
        return self._available and self.api_key and self.search_engine_id

    def is_core(self) -> bool:
        """是否为核心适配器"""
        return False  # Google是降级层

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'name': self.name,
            'type': self.adapter_type.name,
            'priority': self.priority,
            'available': self.is_available(),
            'request_count': self._request_count,
            'daily_limit': self._daily_limit,
            'remaining_quota': self._daily_limit - self._request_count
        }

    def reset_daily_counter(self):
        """重置每日计数器（用于定时任务）"""
        logger.info(f"[GoogleSearchAdapter] 重置计数器: {self._request_count} -> 0")
        self._request_count = 0
        if self.api_key and self.search_engine_id:
            self._available = True
