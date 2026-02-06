"""
百度搜索适配器 - 使用百度搜索API或网页抓取

降级层实现 - Priority 3
当HIDRS Core和Google都不可用时的备选方案
"""
import logging
import requests
from typing import List, Dict, Optional
from datetime import datetime
from urllib.parse import quote
from bs4 import BeautifulSoup
from .base_adapter import SearchAdapter, AdapterType

logger = logging.getLogger(__name__)


class BaiduSearchAdapter(SearchAdapter):
    """百度搜索适配器 - 降级层"""

    def __init__(self, use_api: bool = False, api_key: Optional[str] = None):
        """
        初始化百度搜索适配器

        参数:
        - use_api: 是否使用百度API（默认False，使用网页抓取）
        - api_key: 百度API密钥（如果使用API）

        注意:
        - 百度没有公开的搜索API，主要通过网页抓取实现
        - 抓取可能受到反爬虫机制限制
        - 需要注意User-Agent和请求频率
        """
        super().__init__(
            name="百度搜索",
            adapter_type=AdapterType.FALLBACK,
            priority=3  # 降级层第二优先级
        )

        self.use_api = use_api
        self.api_key = api_key
        self.base_url = "https://www.baidu.com/s"

        # 模拟浏览器请求头
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Referer': 'https://www.baidu.com/'
        }

        self._request_count = 0
        self._rate_limit_delay = 2  # 请求间隔（秒）

        logger.info(f"[BaiduSearchAdapter] 初始化完成: 模式={'API' if use_api else '网页抓取'}")

    def search(self, query: str, limit: int = 10, **kwargs) -> List[Dict]:
        """
        执行百度搜索

        参数:
        - query: 搜索查询
        - limit: 返回结果数量
        - **kwargs: 额外参数
          - time_filter: 时间过滤 ('day', 'week', 'month', 'year')

        返回:
        - 结果列表，每个结果包含: title, url, snippet, source, timestamp, score, metadata
        """
        if not self.is_available():
            logger.warning("[BaiduSearchAdapter] 适配器不可用")
            return []

        try:
            logger.info(f"[BaiduSearchAdapter] 搜索: '{query}' (limit={limit})")

            if self.use_api and self.api_key:
                return self._search_via_api(query, limit, **kwargs)
            else:
                return self._search_via_scraping(query, limit, **kwargs)

        except Exception as e:
            logger.error(f"[BaiduSearchAdapter] 搜索失败: {e}")
            return []

    def _search_via_scraping(self, query: str, limit: int, **kwargs) -> List[Dict]:
        """通过网页抓取搜索"""
        try:
            # 构建搜索URL
            params = {
                'wd': query,
                'rn': min(limit, 50)  # 百度单页最多50个结果
            }

            # 时间过滤
            time_filter = kwargs.get('time_filter')
            if time_filter == 'day':
                params['gpc'] = 'stf=0,1|stftype=1'
            elif time_filter == 'week':
                params['gpc'] = 'stf=0,7|stftype=1'
            elif time_filter == 'month':
                params['gpc'] = 'stf=0,30|stftype=1'
            elif time_filter == 'year':
                params['gpc'] = 'stf=0,365|stftype=1'

            # 发送请求
            response = requests.get(
                self.base_url,
                params=params,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            response.encoding = 'utf-8'

            self._request_count += 1

            # 解析HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []

            # 查找搜索结果容器
            # 百度搜索结果的class可能会变化，需要适配多种情况
            result_containers = soup.find_all('div', class_='result')
            if not result_containers:
                result_containers = soup.find_all('div', class_='c-container')

            for idx, container in enumerate(result_containers[:limit]):
                try:
                    # 提取标题
                    title_elem = container.find('h3') or container.find('a')
                    title = title_elem.get_text(strip=True) if title_elem else ''

                    # 提取URL
                    link_elem = container.find('a')
                    url = link_elem.get('href', '') if link_elem else ''

                    # 百度搜索结果URL是重定向链接，需要提取真实URL
                    # 这里简化处理，直接使用百度的跳转链接
                    if url and url.startswith('http://www.baidu.com/link'):
                        # 可以添加提取真实URL的逻辑，但会增加请求次数
                        pass

                    # 提取摘要
                    snippet_elem = container.find('div', class_='c-abstract')
                    if not snippet_elem:
                        snippet_elem = container.find('div', class_='c-span-last')
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''

                    # 过滤无效结果
                    if not title or not url:
                        continue

                    result = {
                        'title': title,
                        'url': url,
                        'snippet': snippet,
                        'source': self.name,
                        'timestamp': datetime.now().isoformat(),
                        'score': 1.0 - (idx * 0.05),  # 简单的位置衰减得分
                        'metadata': {
                            'adapter': self.name,
                            'adapter_type': self.adapter_type.name,
                            'priority': self.priority,
                            'position': idx + 1,
                            'is_baidu_redirect': url.startswith('http://www.baidu.com/link')
                        }
                    }

                    results.append(result)

                except Exception as e:
                    logger.warning(f"[BaiduSearchAdapter] 解析结果失败: {e}")
                    continue

            logger.info(f"[BaiduSearchAdapter] 返回 {len(results)} 个结果")
            return results

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                logger.error("[BaiduSearchAdapter] 被百度反爬虫机制拦截")
                self._available = False
            else:
                logger.error(f"[BaiduSearchAdapter] HTTP错误: {e}")
            return []

        except requests.exceptions.Timeout:
            logger.error("[BaiduSearchAdapter] 请求超时")
            return []

        except Exception as e:
            logger.error(f"[BaiduSearchAdapter] 抓取失败: {e}")
            return []

    def _search_via_api(self, query: str, limit: int, **kwargs) -> List[Dict]:
        """通过API搜索（如果百度提供API）"""
        logger.warning("[BaiduSearchAdapter] 百度API模式尚未实现，回退到网页抓取")
        return self._search_via_scraping(query, limit, **kwargs)

    def is_available(self) -> bool:
        """检查适配器是否可用"""
        return self._available

    def is_core(self) -> bool:
        """是否为核心适配器"""
        return False  # 百度是降级层

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'name': self.name,
            'type': self.adapter_type.name,
            'priority': self.priority,
            'available': self.is_available(),
            'request_count': self._request_count,
            'mode': 'API' if self.use_api else 'Scraping'
        }
