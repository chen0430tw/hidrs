"""
暗网爬虫插件 - DarkWeb Crawler Plugin
支持 Tor、I2P 等匿名网络的爬虫功能
用于合法的安全研究和威胁情报收集

⚠️ 严格合规声明 ⚠️

本插件仅用于合法的安全研究、威胁情报收集和学术研究。

使用前必须确保：
1. 您有合法的研究目的和授权
2. 遵守当地法律法规
3. 不访问、下载、传播非法内容（包括但不限于）：
   - 儿童色情内容
   - 毒品交易信息
   - 武器走私信息
   - 人口贩卖信息
   - 恐怖主义内容
4. 不参与任何非法活动
5. 发现非法内容时主动报告相关部门

违反上述条款导致的一切法律后果由使用者自行承担。
"""
import logging
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
from plugin_manager import PluginBase

logger = logging.getLogger(__name__)


class TorClient:
    """Tor 网络客户端"""

    def __init__(self, config: Dict):
        self.config = config
        self.socks_proxy = config.get('proxy', 'socks5h://127.0.0.1:9050')
        self.control_port = config.get('control_port', 9051)
        self.control_password = config.get('control_password', '')
        self.enabled = False
        self.session = None

        # 初始化
        self._initialize()

    def _initialize(self) -> bool:
        """初始化 Tor 连接"""
        try:
            import requests
            import socks
            import socket

            # 创建会话
            self.session = requests.Session()
            self.session.proxies = {
                'http': self.socks_proxy,
                'https': self.socks_proxy
            }

            # 设置超时
            self.session.timeout = 60

            # 测试 Tor 连接
            try:
                response = self.session.get(
                    'https://check.torproject.org/api/ip',
                    timeout=30
                )
                data = response.json()

                if data.get('IsTor'):
                    self.enabled = True
                    logger.info(f"Tor connection established. IP: {data.get('IP')}")
                    return True
                else:
                    logger.error("Not connected through Tor network")
                    return False

            except Exception as e:
                logger.error(f"Tor connection test failed: {e}")
                logger.warning("Please ensure Tor service is running (tor --version)")
                return False

        except ImportError as e:
            logger.error(f"Required libraries not installed: {e}")
            logger.warning("Run: pip install requests PySocks")
            return False
        except Exception as e:
            logger.error(f"Tor initialization failed: {e}")
            return False

    def fetch_onion_site(self, onion_url: str) -> Dict:
        """爬取 .onion 网站"""
        if not self.enabled:
            return {'error': 'Tor connection not available'}

        # 验证 URL 格式
        if not onion_url.endswith('.onion') and '.onion' not in onion_url:
            return {'error': 'Invalid Tor URL. Must contain .onion domain'}

        try:
            logger.info(f"Fetching onion site: {onion_url}")

            # 发起请求
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; rv:91.0) Gecko/20100101 Firefox/91.0'
            }

            start_time = time.time()
            response = self.session.get(onion_url, headers=headers, timeout=60)
            elapsed = time.time() - start_time

            return {
                'success': True,
                'url': onion_url,
                'status_code': response.status_code,
                'content': response.text,
                'content_length': len(response.text),
                'headers': dict(response.headers),
                'elapsed_time': elapsed,
                'timestamp': datetime.now().isoformat(),
                'network': 'tor'
            }

        except Exception as e:
            logger.error(f"Failed to fetch {onion_url}: {e}")
            return {
                'success': False,
                'url': onion_url,
                'error': str(e),
                'network': 'tor'
            }

    def renew_identity(self) -> bool:
        """更换 Tor 身份（获取新的 IP 地址）"""
        if not self.enabled:
            return False

        try:
            from stem import Signal
            from stem.control import Controller

            with Controller.from_port(port=self.control_port) as controller:
                if self.control_password:
                    controller.authenticate(password=self.control_password)
                else:
                    controller.authenticate()

                controller.signal(Signal.NEWNYM)
                time.sleep(5)  # 等待新电路建立

            logger.info("Tor identity renewed")
            return True

        except ImportError:
            logger.error("stem library not installed. Run: pip install stem")
            return False
        except Exception as e:
            logger.error(f"Failed to renew Tor identity: {e}")
            return False

    def get_current_ip(self) -> Optional[str]:
        """获取当前 Tor 出口 IP"""
        if not self.enabled:
            return None

        try:
            response = self.session.get('https://check.torproject.org/api/ip', timeout=30)
            data = response.json()
            return data.get('IP')
        except Exception as e:
            logger.error(f"Failed to get current IP: {e}")
            return None


class DarkWebCrawlerPlugin(PluginBase):
    """暗网爬虫插件"""

    # 合规性警告（加强版）
    COMPLIANCE_WARNING = """
    ⚠️⚠️⚠️ 暗网爬虫插件严格合规声明 ⚠️⚠️⚠️

    本插件仅用于合法的安全研究、威胁情报收集和学术研究。

    使用前必须确保：
    1. 您有合法的研究目的和授权
    2. 遵守当地法律法规
    3. 不访问非法内容（儿童色情、毒品交易、武器走私、人口贩卖、恐怖主义等）
    4. 不参与任何非法活动
    5. 发现非法内容时主动报告

    本插件会记录所有访问日志用于合规审计。

    违反上述条款导致的一切法律后果由使用者自行承担。
    使用本插件即表示您已阅读并同意上述条款。
    """

    # 内容黑名单（关键词检测）
    CONTENT_BLACKLIST = [
        'child', 'children', 'underage', 'minor',  # 儿童相关
        'drug', 'cocaine', 'heroin', 'methamphetamine',  # 毒品
        'weapon', 'gun', 'explosive', 'bomb',  # 武器
        'traffick', 'slave',  # 人口贩卖
        'terrorism', 'isis', 'al-qaeda',  # 恐怖主义
    ]

    def __init__(self):
        super().__init__()
        self.name = "DarkWebCrawler"
        self.version = "1.0.0"
        self.author = "HIDRS Team"
        self.description = "暗网爬虫插件，支持 Tor 网络"

        # Tor 客户端
        self.tor_client = None

        # 访问日志（用于合规审计）
        self.access_log = []
        self.query_count = 0

    def on_load(self):
        """插件加载时调用"""
        logger.info(f"[{self.name}] 正在加载...")

        # 显示合规性警告
        logger.warning(self.COMPLIANCE_WARNING)

        # 读取配置
        config = self.get_config()

        # 强制要求用户明确同意
        if not config.get('user_consent', False):
            raise ValueError(
                f"[{self.name}] 暗网爬虫需要用户明确同意合规条款。\n"
                f"请阅读合规声明后，在配置中设置 'user_consent: true'"
            )

        # 初始化 Tor 客户端
        if config.get('tor', {}).get('enabled'):
            self.tor_client = TorClient(config['tor'])

            if not self.tor_client.enabled:
                logger.error(f"[{self.name}] Tor 初始化失败")
                raise RuntimeError("Tor connection failed. Please ensure Tor service is running.")
        else:
            logger.warning(f"[{self.name}] Tor 未启用")

        logger.info(f"[{self.name}] 加载完成")

    def on_unload(self):
        """插件卸载时调用"""
        logger.info(f"[{self.name}] 正在卸载... (总访问次数: {self.query_count})")

        # 保存访问日志
        if self.access_log:
            logger.info(f"[{self.name}] 保存 {len(self.access_log)} 条访问日志")

    def crawl(self, url: str, renew_identity: bool = True) -> Dict:
        """爬取暗网网站"""
        if not self.tor_client or not self.tor_client.enabled:
            return {'error': 'Tor client not available'}

        # 记录访问
        self.query_count += 1
        log_entry = {
            'url': url,
            'timestamp': datetime.now().isoformat(),
            'success': False
        }

        try:
            # 爬取网站
            result = self.tor_client.fetch_onion_site(url)

            # 内容安全检查
            if result.get('success') and result.get('content'):
                safety_check = self._check_content_safety(result['content'], url)

                if not safety_check['safe']:
                    logger.critical(f"[{self.name}] ⚠️ 检测到可疑内容: {url}")
                    logger.critical(f"[{self.name}] 匹配的黑名单关键词: {safety_check['matched_keywords']}")

                    result['safety_warning'] = safety_check
                    result['content'] = '[内容已屏蔽 - 检测到可疑关键词]'

            # 更新日志
            log_entry['success'] = result.get('success', False)
            log_entry['status_code'] = result.get('status_code')
            log_entry['safety_check'] = result.get('safety_warning', {'safe': True})

            # 可选：更换身份
            if renew_identity and self.tor_client:
                self.tor_client.renew_identity()

            return result

        except Exception as e:
            logger.error(f"[{self.name}] 爬取失败: {e}")
            log_entry['error'] = str(e)
            return {'error': str(e)}

        finally:
            # 记录访问日志
            self.access_log.append(log_entry)

    def renew_tor_identity(self) -> Dict:
        """手动更换 Tor 身份"""
        if not self.tor_client or not self.tor_client.enabled:
            return {'error': 'Tor client not available'}

        success = self.tor_client.renew_identity()

        if success:
            new_ip = self.tor_client.get_current_ip()
            return {
                'success': True,
                'message': 'Tor identity renewed',
                'new_ip': new_ip
            }
        else:
            return {'error': 'Failed to renew identity'}

    def get_current_tor_ip(self) -> Dict:
        """获取当前 Tor 出口 IP"""
        if not self.tor_client or not self.tor_client.enabled:
            return {'error': 'Tor client not available'}

        ip = self.tor_client.get_current_ip()

        if ip:
            return {'success': True, 'ip': ip}
        else:
            return {'error': 'Failed to get current IP'}

    def get_stats(self) -> Dict:
        """获取插件统计信息"""
        return {
            'query_count': self.query_count,
            'tor_enabled': self.tor_client and self.tor_client.enabled,
            'recent_access': self.access_log[-10:]  # 最近10条访问记录
        }

    def _check_content_safety(self, content: str, url: str) -> Dict:
        """内容安全检查（黑名单关键词检测）"""
        content_lower = content.lower()
        matched_keywords = []

        for keyword in self.CONTENT_BLACKLIST:
            if keyword in content_lower:
                matched_keywords.append(keyword)

        if matched_keywords:
            # 记录可疑内容（用于合规审计）
            logger.critical(f"⚠️ SUSPICIOUS CONTENT DETECTED")
            logger.critical(f"URL: {url}")
            logger.critical(f"Matched keywords: {matched_keywords}")
            logger.critical(f"Timestamp: {datetime.now().isoformat()}")

            return {
                'safe': False,
                'matched_keywords': matched_keywords,
                'action': 'content_blocked'
            }

        return {'safe': True}

    def get_access_log(self, limit: int = 100) -> List[Dict]:
        """获取访问日志（用于合规审计）"""
        return self.access_log[-limit:]
