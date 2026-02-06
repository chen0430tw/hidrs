"""
SpiderFoot模块整合
将HIDRS封装为SpiderFoot OSINT模块

SpiderFoot模块开发文档：
https://github.com/smicallef/spiderfoot/wiki/Developing-modules

安装方式：
1. 将此文件复制到SpiderFoot的modules目录
2. 重启SpiderFoot
3. 在配置中启用sfp_hidrs模块

模块功能：
- 实时搜索HIDRS索引
- 查询Common Crawl历史数据
- 网络拓扑分析
- HLIG相似度分析
"""

import logging
from typing import List, Dict, Any

# SpiderFoot基类导入
# 注意：这些类在SpiderFoot环境中才能导入
try:
    from spiderfoot import SpiderFootEvent, SpiderFootPlugin
    SPIDERFOOT_AVAILABLE = True
except ImportError:
    SPIDERFOOT_AVAILABLE = False
    # 定义占位类供测试
    class SpiderFootPlugin:
        pass
    class SpiderFootEvent:
        pass


class sfp_hidrs(SpiderFootPlugin):
    """
    HIDRS OSINT模块

    使用HIDRS的全息拉普拉斯互联网图谱进行深度情报收集
    """

    # 模块元数据
    meta = {
        'name': 'HIDRS - Holographic Internet Discovery & Retrieval System',
        'summary': '使用HLIG理论进行高级OSINT搜索和网络拓扑分析',
        'flags': ['apikey'],  # 如果需要API密钥
        'useCases': ['Footprint', 'Investigate', 'Passive'],
        'categories': ['Search Engines', 'Content Analysis'],
        'dataSource': {
            'website': 'https://github.com/your-repo/hidrs',
            'model': 'FREE_NOAUTH_LIMITED',  # 或 'COMMERCIAL_ONLY'
            'references': [
                'https://hidrs-docs.example.com',
            ],
            'description': 'HIDRS使用拉普拉斯矩阵谱分析和全息映射进行互联网信息检索。'
        }
    }

    # 配置选项
    opts = {
        'hidrs_api_url': 'http://localhost:5000',
        'hidrs_api_key': '',  # 如果启用了API认证
        'search_limit': 50,
        'enable_commoncrawl': True,
        'enable_topology': True,
        'min_fiedler_score': 0.3,  # 最小Fiedler得分阈值
        'timeout': 30
    }

    # 配置选项描述
    optdescs = {
        'hidrs_api_url': 'HIDRS API服务器地址',
        'hidrs_api_key': 'HIDRS API密钥（如果需要）',
        'search_limit': '每次搜索的最大结果数量',
        'enable_commoncrawl': '启用Common Crawl历史数据搜索',
        'enable_topology': '启用网络拓扑分析',
        'min_fiedler_score': '最小Fiedler得分阈值（0-1）',
        'timeout': '请求超时时间（秒）'
    }

    # 模块生成的事件类型
    results = None

    def setup(self, sfc, userOpts=None):
        """初始化模块"""
        self.sf = sfc
        self.results = self.tempStorage()

        # 合并用户选项
        if userOpts:
            self.opts.update(userOpts)

        # 初始化日志
        self.logger = logging.getLogger(f"spiderfoot.{self.__class__.__name__}")

    def watchedEvents(self):
        """
        返回此模块关注的事件类型

        当SpiderFoot扫描中出现这些事件时，会调用handleEvent()
        """
        return [
            'DOMAIN_NAME',
            'EMAILADDR',
            'IP_ADDRESS',
            'PHONE_NUMBER',
            'HUMAN_NAME',
            'USERNAME',
            'AFFILIATE_DOMAIN_NAME',
            'LINKED_URL_INTERNAL'
        ]

    def producedEvents(self):
        """返回此模块可能产生的事件类型"""
        return [
            'RAW_RIR_DATA',
            'SIMILAR_DOMAIN',
            'LINKED_URL_EXTERNAL',
            'SEARCH_ENGINE_WEB_CONTENT',
            'WEBSERVER_HTTPHEADERS',
            'PROVIDER_DNS',
            'MALICIOUS_IPADDR',
            'MALICIOUS_HOSTNAME'
        ]

    def handleEvent(self, event: 'SpiderFootEvent'):
        """
        处理事件

        参数:
        - event: SpiderFoot事件对象
        """
        eventName = event.eventType
        srcModuleName = event.module
        eventData = event.data

        # 检查是否已经处理过此数据
        if eventData in self.results:
            self.logger.debug(f"跳过已处理的数据: {eventData}")
            return

        self.results[eventData] = True

        self.logger.info(f"收到事件: {eventName} ({eventData})")

        try:
            # 根据事件类型执行不同的HIDRS查询
            if eventName in ['DOMAIN_NAME', 'AFFILIATE_DOMAIN_NAME']:
                self._search_domain(eventData, event)
            elif eventName == 'EMAILADDR':
                self._search_email(eventData, event)
            elif eventName == 'IP_ADDRESS':
                self._search_ip(eventData, event)
            elif eventName in ['HUMAN_NAME', 'USERNAME']:
                self._search_person(eventData, event)
            elif eventName == 'LINKED_URL_INTERNAL':
                self._analyze_url(eventData, event)

        except Exception as e:
            self.logger.error(f"处理事件失败: {e}", exc_info=True)

    def _search_domain(self, domain: str, source_event: 'SpiderFootEvent'):
        """搜索域名相关信息"""
        try:
            # 1. HIDRS实时搜索
            results = self._hidrs_search(f'domain:{domain}')

            for result in results:
                # 发现的URL
                if 'url' in result:
                    evt = SpiderFootEvent(
                        'LINKED_URL_EXTERNAL',
                        result['url'],
                        self.__name__,
                        source_event
                    )
                    self.notifyListeners(evt)

                # 网页内容
                if 'text' in result:
                    evt = SpiderFootEvent(
                        'SEARCH_ENGINE_WEB_CONTENT',
                        result['text'][:500],  # 限制长度
                        self.__name__,
                        source_event
                    )
                    self.notifyListeners(evt)

            # 2. Common Crawl历史搜索
            if self.opts['enable_commoncrawl']:
                cc_results = self._commoncrawl_search(domain)
                for result in cc_results:
                    evt = SpiderFootEvent(
                        'RAW_RIR_DATA',
                        f"Common Crawl: {result.get('title', 'N/A')} - {result.get('url', 'N/A')}",
                        self.__name__,
                        source_event
                    )
                    self.notifyListeners(evt)

            # 3. 网络拓扑分析
            if self.opts['enable_topology']:
                topology = self._topology_analysis(domain)
                if topology:
                    evt = SpiderFootEvent(
                        'RAW_RIR_DATA',
                        f"HIDRS Topology: Fiedler={topology.get('fiedler_value', 'N/A')}",
                        self.__name__,
                        source_event
                    )
                    self.notifyListeners(evt)

        except Exception as e:
            self.logger.error(f"域名搜索失败: {e}")

    def _search_email(self, email: str, source_event: 'SpiderFootEvent'):
        """搜索邮箱地址"""
        results = self._hidrs_search(f'email:{email}')

        for result in results:
            if result.get('url'):
                evt = SpiderFootEvent(
                    'LINKED_URL_EXTERNAL',
                    result['url'],
                    self.__name__,
                    source_event
                )
                self.notifyListeners(evt)

    def _search_ip(self, ip: str, source_event: 'SpiderFootEvent'):
        """搜索IP地址"""
        results = self._hidrs_search(f'ip:{ip}')

        for result in results:
            # 检查是否有恶意标记
            if result.get('metadata', {}).get('malicious'):
                evt = SpiderFootEvent(
                    'MALICIOUS_IPADDR',
                    ip,
                    self.__name__,
                    source_event
                )
                self.notifyListeners(evt)

    def _search_person(self, name: str, source_event: 'SpiderFootEvent'):
        """搜索人名"""
        results = self._hidrs_search(name)

        # 这里可以提取社交媒体账号、邮箱等信息
        for result in results:
            # 提取邮箱
            import re
            emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                              result.get('text', ''))
            for email in emails:
                evt = SpiderFootEvent(
                    'EMAILADDR',
                    email,
                    self.__name__,
                    source_event
                )
                self.notifyListeners(evt)

    def _analyze_url(self, url: str, source_event: 'SpiderFootEvent'):
        """分析URL"""
        # 使用HLIG相似度查找相似页面
        results = self._hidrs_search(f'url:{url}')

        for result in results:
            fiedler_score = result.get('metadata', {}).get('fiedler_score', 0)

            # 只返回高相似度的结果
            if fiedler_score >= self.opts['min_fiedler_score']:
                evt = SpiderFootEvent(
                    'SIMILAR_DOMAIN',
                    result.get('url', ''),
                    self.__name__,
                    source_event
                )
                self.notifyListeners(evt)

    def _hidrs_search(self, query: str) -> List[Dict]:
        """调用HIDRS搜索API"""
        try:
            import requests

            url = f"{self.opts['hidrs_api_url']}/api/search"
            params = {
                'q': query,
                'limit': self.opts['search_limit']
            }

            headers = {}
            if self.opts['hidrs_api_key']:
                headers['Authorization'] = f"Bearer {self.opts['hidrs_api_key']}"

            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=self.opts['timeout']
            )

            if response.status_code == 200:
                data = response.json()
                return data.get('results', [])
            else:
                self.logger.error(f"HIDRS API错误: {response.status_code}")
                return []

        except Exception as e:
            self.logger.error(f"HIDRS搜索失败: {e}")
            return []

    def _commoncrawl_search(self, query: str) -> List[Dict]:
        """调用HIDRS Common Crawl API"""
        try:
            import requests

            url = f"{self.opts['hidrs_api_url']}/api/commoncrawl/search"
            params = {
                'keywords': query,
                'limit': min(self.opts['search_limit'], 30)
            }

            response = requests.get(url, params=params, timeout=self.opts['timeout'])

            if response.status_code == 200:
                data = response.json()
                return data.get('results', [])
            else:
                return []

        except Exception as e:
            self.logger.error(f"Common Crawl搜索失败: {e}")
            return []

    def _topology_analysis(self, target: str) -> Dict:
        """网络拓扑分析"""
        try:
            import requests

            url = f"{self.opts['hidrs_api_url']}/api/network/metrics"
            response = requests.get(url, timeout=self.opts['timeout'])

            if response.status_code == 200:
                return response.json()
            else:
                return {}

        except Exception as e:
            self.logger.error(f"拓扑分析失败: {e}")
            return {}


# 测试代码
if __name__ == '__main__':
    print("HIDRS SpiderFoot模块")
    print("=" * 50)
    print(f"模块名称: {sfp_hidrs.meta['name']}")
    print(f"描述: {sfp_hidrs.meta['summary']}")
    print(f"监听事件: {', '.join(sfp_hidrs().watchedEvents())}")
    print(f"生成事件: {', '.join(sfp_hidrs().producedEvents())}")
    print("\n安装方式:")
    print("1. 复制此文件到SpiderFoot的modules/目录")
    print("2. 文件名必须以 sfp_ 开头，如 sfp_hidrs.py")
    print("3. 重启SpiderFoot")
    print("4. 在Web界面的Modules设置中启用HIDRS模块")
