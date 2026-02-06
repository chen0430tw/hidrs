"""
设备扫描插件 - Device Scanner Plugin
集成 Shodan、Censys、ZoomEye 等设备搜索引擎 API
提供互联网设备扫描和漏洞情报收集功能

合规声明：
本插件仅用于合法的安全研究、渗透测试和威胁情报收集。
使用前请确保：
1. 您有合法的研究目的
2. 遵守当地法律法规
3. 不进行未授权的扫描活动
4. 遵守 API 提供商的服务条款
"""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from plugin_manager import PluginBase

logger = logging.getLogger(__name__)


class ShodanClient:
    """Shodan API 客户端"""

    def __init__(self, api_key: str):
        try:
            import shodan
            self.api = shodan.Shodan(api_key)
            self.enabled = True
            logger.info("Shodan API initialized")
        except ImportError:
            logger.warning("shodan library not installed. Run: pip install shodan")
            self.enabled = False
        except Exception as e:
            logger.error(f"Shodan initialization failed: {e}")
            self.enabled = False

    def search(self, query: str, limit: int = 100) -> List[Dict]:
        """执行 Shodan 搜索"""
        if not self.enabled:
            return []

        try:
            results = self.api.search(query, limit=limit)
            devices = []

            for result in results['matches']:
                devices.append({
                    'ip': result.get('ip_str'),
                    'port': result.get('port'),
                    'organization': result.get('org', 'Unknown'),
                    'os': result.get('os'),
                    'hostnames': result.get('hostnames', []),
                    'location': {
                        'country': result.get('location', {}).get('country_name'),
                        'country_code': result.get('location', {}).get('country_code'),
                        'city': result.get('location', {}).get('city'),
                        'latitude': result.get('location', {}).get('latitude'),
                        'longitude': result.get('location', {}).get('longitude'),
                    },
                    'vulnerabilities': result.get('vulns', []),
                    'services': result.get('data', ''),
                    'timestamp': result.get('timestamp'),
                    'asn': result.get('asn'),
                    'isp': result.get('isp'),
                    'domains': result.get('domains', []),
                    'source': 'shodan'
                })

            logger.info(f"Shodan search returned {len(devices)} results")
            return devices

        except Exception as e:
            logger.error(f"Shodan search error: {e}")
            return []

    def host_info(self, ip: str) -> Optional[Dict]:
        """获取主机详细信息"""
        if not self.enabled:
            return None

        try:
            info = self.api.host(ip)
            return {
                'ip': info.get('ip_str'),
                'organization': info.get('org'),
                'os': info.get('os'),
                'ports': info.get('ports', []),
                'hostnames': info.get('hostnames', []),
                'location': info.get('location'),
                'vulnerabilities': info.get('vulns', []),
                'last_update': info.get('last_update'),
                'source': 'shodan'
            }
        except Exception as e:
            logger.error(f"Shodan host lookup error: {e}")
            return None


class CensysClient:
    """Censys API 客户端（支持新旧两个版本）"""

    def __init__(self, api_id: str = None, api_secret: str = None, access_token: str = None):
        self.enabled = False
        self.client = None
        self.version = None

        # 优先使用新版 API (censys-platform)
        if access_token:
            try:
                from censys.search import CensysHosts
                self.client = CensysHosts(api_key=access_token)
                self.enabled = True
                self.version = 'new'
                logger.info("Censys API (new platform) initialized")
                return
            except ImportError:
                logger.warning("censys library not installed. Run: pip install censys")
            except Exception as e:
                logger.error(f"Censys new API initialization failed: {e}")

        # 回退到旧版 API
        if api_id and api_secret:
            try:
                from censys.search import CensysHosts
                self.client = CensysHosts(api_id=api_id, api_secret=api_secret)
                self.enabled = True
                self.version = 'legacy'
                logger.info("Censys API (legacy) initialized")
            except ImportError:
                logger.warning("censys library not installed")
            except Exception as e:
                logger.error(f"Censys legacy API initialization failed: {e}")

    def search(self, query: str, limit: int = 100) -> List[Dict]:
        """执行 Censys 搜索"""
        if not self.enabled:
            return []

        try:
            results = []
            count = 0

            for page in self.client.search(query, per_page=min(limit, 100), pages=1):
                for host in page:
                    if count >= limit:
                        break

                    results.append({
                        'ip': host.get('ip'),
                        'services': host.get('services', []),
                        'protocols': host.get('protocols', []),
                        'location': {
                            'country': host.get('location', {}).get('country'),
                            'country_code': host.get('location', {}).get('country_code'),
                            'city': host.get('location', {}).get('city'),
                            'coordinates': host.get('location', {}).get('coordinates'),
                        },
                        'autonomous_system': {
                            'asn': host.get('autonomous_system', {}).get('asn'),
                            'name': host.get('autonomous_system', {}).get('name'),
                            'organization': host.get('autonomous_system', {}).get('organization'),
                        },
                        'last_updated': host.get('last_updated_at'),
                        'source': 'censys'
                    })
                    count += 1

            logger.info(f"Censys search returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Censys search error: {e}")
            return []


class ZoomEyeClient:
    """ZoomEye API 客户端"""

    def __init__(self, api_key: str):
        try:
            import zoomeye
            self.zm = zoomeye.ZoomEye(api_key=api_key)
            self.enabled = True
            logger.info("ZoomEye API initialized")
        except ImportError:
            logger.warning("zoomeye library not installed. Run: pip install zoomeye")
            self.enabled = False
        except Exception as e:
            logger.error(f"ZoomEye initialization failed: {e}")
            self.enabled = False

    def search(self, query: str, search_type: str = 'host', limit: int = 100) -> List[Dict]:
        """执行 ZoomEye 搜索"""
        if not self.enabled:
            return []

        try:
            # ZoomEye 搜索
            data = self.zm.dork_search(query, resource=search_type, page=1)

            results = []
            for item in data.get('matches', [])[:limit]:
                if search_type == 'host':
                    results.append({
                        'ip': item.get('ip'),
                        'port': item.get('portinfo', {}).get('port'),
                        'service': item.get('portinfo', {}).get('service'),
                        'organization': item.get('geoinfo', {}).get('organization'),
                        'location': {
                            'country': item.get('geoinfo', {}).get('country', {}).get('names', {}).get('zh-CN'),
                            'city': item.get('geoinfo', {}).get('city', {}).get('names', {}).get('zh-CN'),
                        },
                        'timestamp': item.get('timestamp'),
                        'source': 'zoomeye'
                    })
                elif search_type == 'web':
                    results.append({
                        'site': item.get('site'),
                        'title': item.get('title'),
                        'ip': item.get('ip', []),
                        'location': {
                            'country': item.get('geoinfo', {}).get('country', {}).get('names', {}).get('zh-CN'),
                        },
                        'source': 'zoomeye'
                    })

            logger.info(f"ZoomEye search returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"ZoomEye search error: {e}")
            return []


class DeviceScannerPlugin(PluginBase):
    """设备扫描插件"""

    # 合规性警告
    COMPLIANCE_WARNING = """
    ⚠️ 设备扫描插件合规声明

    使用本插件前，请确保：
    1. 您有合法的安全研究或渗透测试授权
    2. 遵守当地法律法规
    3. 不进行未授权的扫描活动
    4. 遵守 API 提供商的服务条款
    5. 记录所有查询用于审计

    使用本插件即表示您同意上述条款并对使用后果负全部责任。
    """

    def __init__(self):
        super().__init__()
        self.name = "DeviceScanner"
        self.version = "1.0.0"
        self.author = "HIDRS Team"
        self.description = "设备扫描插件，集成 Shodan、Censys、ZoomEye API"

        # API 客户端
        self.shodan_client = None
        self.censys_client = None
        self.zoomeye_client = None

        # 使用统计
        self.query_count = 0
        self.query_log = []

    def on_load(self):
        """插件加载时调用"""
        logger.info(f"[{self.name}] 正在加载...")

        # 显示合规性警告
        logger.warning(self.COMPLIANCE_WARNING)

        # 读取配置
        config = self.get_config()

        # 检查用户同意
        if not config.get('user_consent', False):
            raise ValueError(
                f"[{self.name}] 需要用户明确同意合规条款。"
                "请在配置中设置 'user_consent: true'"
            )

        # 初始化 Shodan
        if config.get('shodan', {}).get('api_key'):
            self.shodan_client = ShodanClient(config['shodan']['api_key'])

        # 初始化 Censys
        censys_config = config.get('censys', {})
        if censys_config.get('access_token'):
            self.censys_client = CensysClient(access_token=censys_config['access_token'])
        elif censys_config.get('api_id') and censys_config.get('api_secret'):
            self.censys_client = CensysClient(
                api_id=censys_config['api_id'],
                api_secret=censys_config['api_secret']
            )

        # 初始化 ZoomEye
        if config.get('zoomeye', {}).get('api_key'):
            self.zoomeye_client = ZoomEyeClient(config['zoomeye']['api_key'])

        # 检查至少有一个 API 可用
        if not any([
            self.shodan_client and self.shodan_client.enabled,
            self.censys_client and self.censys_client.enabled,
            self.zoomeye_client and self.zoomeye_client.enabled
        ]):
            logger.warning(f"[{self.name}] 没有可用的 API 客户端")

        logger.info(f"[{self.name}] 加载完成")

    def on_unload(self):
        """插件卸载时调用"""
        logger.info(f"[{self.name}] 正在卸载... (总查询次数: {self.query_count})")

    def search(self, query: str, source: str = 'shodan', limit: int = 100) -> Dict:
        """执行设备搜索"""
        # 记录查询
        self.query_count += 1
        self.query_log.append({
            'query': query,
            'source': source,
            'timestamp': datetime.now().isoformat()
        })

        logger.info(f"[{self.name}] 搜索查询: {query} (来源: {source})")

        results = []

        if source == 'shodan' and self.shodan_client and self.shodan_client.enabled:
            results = self.shodan_client.search(query, limit)
        elif source == 'censys' and self.censys_client and self.censys_client.enabled:
            results = self.censys_client.search(query, limit)
        elif source == 'zoomeye' and self.zoomeye_client and self.zoomeye_client.enabled:
            results = self.zoomeye_client.search(query, limit=limit)
        else:
            return {
                'error': f'数据源 {source} 不可用或未配置',
                'available_sources': self.get_available_sources()
            }

        # 标准化结果
        normalized_results = self._normalize_results(results)

        return {
            'success': True,
            'query': query,
            'source': source,
            'count': len(normalized_results),
            'results': normalized_results
        }

    def host_lookup(self, ip: str, source: str = 'shodan') -> Dict:
        """查询主机详细信息"""
        logger.info(f"[{self.name}] 主机查询: {ip} (来源: {source})")

        if source == 'shodan' and self.shodan_client and self.shodan_client.enabled:
            info = self.shodan_client.host_info(ip)
            if info:
                return {'success': True, 'host': info}
            else:
                return {'error': '主机信息查询失败'}
        else:
            return {'error': f'数据源 {source} 不支持主机查询或未配置'}

    def get_available_sources(self) -> List[str]:
        """获取可用的数据源"""
        sources = []

        if self.shodan_client and self.shodan_client.enabled:
            sources.append('shodan')
        if self.censys_client and self.censys_client.enabled:
            sources.append('censys')
        if self.zoomeye_client and self.zoomeye_client.enabled:
            sources.append('zoomeye')

        return sources

    def get_stats(self) -> Dict:
        """获取插件统计信息"""
        return {
            'query_count': self.query_count,
            'available_sources': self.get_available_sources(),
            'recent_queries': self.query_log[-10:]  # 最近10条查询
        }

    def _normalize_results(self, results: List[Dict]) -> List[Dict]:
        """标准化不同 API 的结果格式"""
        normalized = []

        for result in results:
            source = result.get('source')

            # 提取通用字段
            normalized_item = {
                'ip': result.get('ip'),
                'port': result.get('port'),
                'organization': result.get('organization') or result.get('autonomous_system', {}).get('organization'),
                'location': result.get('location', {}),
                'source': source,
                'timestamp': result.get('timestamp') or result.get('last_updated'),
                'raw_data': result  # 保留原始数据
            }

            # Shodan 特有字段
            if source == 'shodan':
                normalized_item.update({
                    'vulnerabilities': result.get('vulnerabilities', []),
                    'os': result.get('os'),
                    'hostnames': result.get('hostnames', []),
                    'asn': result.get('asn'),
                    'isp': result.get('isp'),
                })

            # Censys 特有字段
            elif source == 'censys':
                normalized_item.update({
                    'services': result.get('services', []),
                    'protocols': result.get('protocols', []),
                    'asn': result.get('autonomous_system', {}).get('asn'),
                })

            # ZoomEye 特有字段
            elif source == 'zoomeye':
                normalized_item.update({
                    'service': result.get('service'),
                    'site': result.get('site'),
                    'title': result.get('title'),
                })

            normalized.append(normalized_item)

        return normalized
