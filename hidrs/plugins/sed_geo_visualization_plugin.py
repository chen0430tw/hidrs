"""
SED 地理位置可视化插件
分析数据泄露事件的地理分布，提供威胁情报可视化
"""
import logging
import re
from typing import Dict, List, Any, Optional
from collections import defaultdict
from datetime import datetime
from plugin_manager import PluginBase

logger = logging.getLogger(__name__)


class GeoIPLocator:
    """GeoIP定位器"""

    def __init__(self):
        self.enabled = False
        self.reader = None
        self._init_geoip()

    def _init_geoip(self):
        """初始化GeoIP数据库"""
        try:
            import geoip2.database
            # GeoLite2数据库路径
            db_path = 'data/GeoLite2-City.mmdb'
            self.reader = geoip2.database.Reader(db_path)
            self.enabled = True
            logger.info("GeoIP database loaded")
        except ImportError:
            logger.warning("geoip2 library not installed. Run: pip install geoip2")
        except FileNotFoundError:
            logger.warning("GeoLite2-City.mmdb not found. Download from https://dev.maxmind.com/geoip/geolite2-free-geolocation-data")
        except Exception as e:
            logger.error(f"GeoIP initialization failed: {e}")

    def locate_ip(self, ip: str) -> Optional[Dict]:
        """定位IP地址"""
        if not self.enabled:
            return None

        try:
            response = self.reader.city(ip)
            return {
                'latitude': response.location.latitude,
                'longitude': response.location.longitude,
                'country': response.country.name,
                'country_code': response.country.iso_code,
                'city': response.city.name,
                'postal_code': response.postal.code,
                'timezone': response.location.time_zone
            }
        except Exception as e:
            logger.debug(f"Failed to locate IP {ip}: {e}")
            return None


class EmailDomainAnalyzer:
    """邮箱域名分析器"""

    def __init__(self):
        self.domain_cache = {}

    def extract_domain(self, email: str) -> Optional[str]:
        """提取邮箱域名"""
        if '@' in email:
            return email.split('@')[1].lower()
        return None

    def get_domain_ip(self, domain: str) -> Optional[str]:
        """获取域名IP地址"""
        if domain in self.domain_cache:
            return self.domain_cache[domain]

        try:
            import socket
            ip = socket.gethostbyname(domain)
            self.domain_cache[domain] = ip
            return ip
        except Exception as e:
            logger.debug(f"Failed to resolve domain {domain}: {e}")
            return None


class DataLeakAnalyzer:
    """数据泄露分析器"""

    def __init__(self, geoip_locator: GeoIPLocator, domain_analyzer: EmailDomainAnalyzer):
        self.geoip = geoip_locator
        self.domain_analyzer = domain_analyzer

    def analyze_sources(self, leak_data: List[Dict]) -> Dict:
        """分析数据源的地理分布"""
        source_locations = defaultdict(lambda: {'count': 0, 'locations': []})

        for item in leak_data:
            source = item.get('source', 'Unknown')
            email = item.get('email', '')

            # 提取域名
            domain = self.domain_analyzer.extract_domain(email)
            if domain:
                # 获取域名IP
                ip = self.domain_analyzer.get_domain_ip(domain)
                if ip:
                    # 定位IP
                    location = self.geoip.locate_ip(ip)
                    if location:
                        source_locations[source]['count'] += 1
                        source_locations[source]['locations'].append({
                            'latitude': location['latitude'],
                            'longitude': location['longitude'],
                            'city': location['city'],
                            'country': location['country']
                        })

        return dict(source_locations)

    def generate_heatmap_data(self, leak_data: List[Dict]) -> List[Dict]:
        """生成热力图数据"""
        location_counts = defaultdict(int)

        for item in leak_data:
            email = item.get('email', '')
            domain = self.domain_analyzer.extract_domain(email)

            if domain:
                ip = self.domain_analyzer.get_domain_ip(domain)
                if ip:
                    location = self.geoip.locate_ip(ip)
                    if location:
                        key = (location['latitude'], location['longitude'])
                        location_counts[key] += 1

        # 转换为热力图格式
        heatmap_data = []
        for (lat, lon), count in location_counts.items():
            heatmap_data.append({
                'latitude': lat,
                'longitude': lon,
                'intensity': count
            })

        # 按强度排序
        heatmap_data.sort(key=lambda x: x['intensity'], reverse=True)

        return heatmap_data

    def analyze_timeline(self, leak_data: List[Dict], time_field: str = 'xtime') -> List[Dict]:
        """分析时间轴数据"""
        timeline_data = defaultdict(lambda: {'count': 0, 'locations': []})

        for item in leak_data:
            timestamp = item.get(time_field)
            if not timestamp:
                continue

            # 按月份分组
            try:
                if isinstance(timestamp, str):
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                else:
                    dt = datetime.fromtimestamp(timestamp)

                month_key = dt.strftime('%Y-%m')

                email = item.get('email', '')
                domain = self.domain_analyzer.extract_domain(email)

                if domain:
                    ip = self.domain_analyzer.get_domain_ip(domain)
                    if ip:
                        location = self.geoip.locate_ip(ip)
                        if location:
                            timeline_data[month_key]['count'] += 1
                            timeline_data[month_key]['locations'].append({
                                'latitude': location['latitude'],
                                'longitude': location['longitude']
                            })
            except Exception as e:
                logger.debug(f"Failed to parse timestamp: {e}")
                continue

        # 转换为列表并排序
        timeline_list = [
            {'month': month, 'count': data['count'], 'locations': data['locations']}
            for month, data in timeline_data.items()
        ]
        timeline_list.sort(key=lambda x: x['month'])

        return timeline_list


class SEDGeoVisualizationPlugin(PluginBase):
    """SED地理可视化插件"""

    def __init__(self):
        super().__init__()
        self.name = "SEDGeoVisualization"
        self.version = "1.0.0"
        self.author = "HIDRS Team"
        self.description = "数据泄露事件地理分布可视化"

        # 核心组件
        self.geoip_locator = None
        self.domain_analyzer = None
        self.leak_analyzer = None

        # 数据存储（支持真实数据输入和演示mock数据）
        self.data = []
        self._demo_mode = False

    def on_load(self):
        """插件加载时调用"""
        logger.info(f"[{self.name}] 正在加载...")

        # 初始化组件
        self.geoip_locator = GeoIPLocator()
        self.domain_analyzer = EmailDomainAnalyzer()
        self.leak_analyzer = DataLeakAnalyzer(self.geoip_locator, self.domain_analyzer)

        # 如果没有外部数据，使用演示数据
        if not self.data:
            self._generate_mock_data()
            self._demo_mode = True
            logger.warning(f"[{self.name}] 使用演示数据（调用ingest_data()导入真实数据）")

        logger.info(f"[{self.name}] 加载完成")

    def ingest_data(self, records: list):
        """
        导入真实泄露数据

        参数:
        - records: 记录列表，每条记录应包含:
            {'email': str, 'source': str, 'xtime': str(ISO格式), ...}

        调用后会替换演示数据，切换到真实数据模式。
        """
        self.data = records
        self._demo_mode = False
        logger.info(f"[{self.name}] 已导入 {len(records)} 条真实数据")

    def on_unload(self):
        """插件卸载时调用"""
        logger.info(f"[{self.name}] 正在卸载...")

        # 关闭GeoIP数据库
        if self.geoip_locator and self.geoip_locator.reader:
            self.geoip_locator.reader.close()

        logger.info(f"[{self.name}] 卸载完成")

    def _generate_mock_data(self):
        """生成模拟数据（用于演示）"""
        # 模拟一些常见的数据泄露事件
        self.data = [
            {
                'email': 'user1@qq.com',
                'source': 'QQ数据库泄露',
                'xtime': '2023-01-15T10:30:00Z'
            },
            {
                'email': 'user2@gmail.com',
                'source': 'Gmail账号泄露',
                'xtime': '2023-02-20T14:25:00Z'
            },
            {
                'email': 'user3@163.com',
                'source': '网易邮箱泄露',
                'xtime': '2023-03-10T09:15:00Z'
            },
            {
                'email': 'user4@outlook.com',
                'source': 'Outlook泄露',
                'xtime': '2023-04-05T16:40:00Z'
            },
            {
                'email': 'user5@sina.com',
                'source': '新浪微博泄露',
                'xtime': '2023-05-12T11:20:00Z'
            },
            # 更多模拟数据...
        ] * 10  # 复制10次增加数据量

    def get_source_distribution(self) -> Dict:
        """获取数据源地理分布"""
        try:
            result = self.leak_analyzer.analyze_sources(self.data)
            return {
                'success': True,
                'data': result
            }
        except Exception as e:
            logger.error(f"Failed to analyze sources: {e}")
            return {'error': str(e)}

    def get_heatmap_data(self) -> Dict:
        """获取热力图数据"""
        try:
            heatmap = self.leak_analyzer.generate_heatmap_data(self.data)
            return {
                'success': True,
                'data': heatmap,
                'count': len(heatmap)
            }
        except Exception as e:
            logger.error(f"Failed to generate heatmap: {e}")
            return {'error': str(e)}

    def get_timeline_data(self) -> Dict:
        """获取时间轴数据"""
        try:
            timeline = self.leak_analyzer.analyze_timeline(self.data)
            return {
                'success': True,
                'data': timeline
            }
        except Exception as e:
            logger.error(f"Failed to analyze timeline: {e}")
            return {'error': str(e)}

    def get_region_data(self, region_name: str) -> Dict:
        """获取指定地区的数据"""
        try:
            # 过滤指定地区的数据
            region_data = []

            for item in self.data:
                email = item.get('email', '')
                domain = self.domain_analyzer.extract_domain(email)

                if domain:
                    ip = self.domain_analyzer.get_domain_ip(domain)
                    if ip:
                        location = self.geoip_locator.locate_ip(ip)
                        if location and (
                            region_name.lower() in (location.get('country', '')).lower() or
                            region_name.lower() in (location.get('city', '') or '').lower()
                        ):
                            region_data.append({
                                **item,
                                'location': location
                            })

            return {
                'success': True,
                'region': region_name,
                'count': len(region_data),
                'data': region_data[:100]  # 限制返回数量
            }
        except Exception as e:
            logger.error(f"Failed to get region data: {e}")
            return {'error': str(e)}

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'total_records': len(self.data),
            'geoip_enabled': self.geoip_locator.enabled if self.geoip_locator else False,
            'unique_sources': len(set(item.get('source') for item in self.data)),
            'unique_domains': len(set(
                self.domain_analyzer.extract_domain(item.get('email', ''))
                for item in self.data
                if self.domain_analyzer.extract_domain(item.get('email', ''))
            ))
        }
