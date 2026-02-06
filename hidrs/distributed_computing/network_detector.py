"""
网络检测器 - 自动检测网络连接状态

功能：
1. 检测网络接口状态（WiFi/以太网）
2. 检测互联网连通性
3. 检测IP地址变化
4. 检测网络类型（家庭/企业/数据中心）
5. 触发连接/断开事件

检测策略：
- 快速检测：检查本地网络接口（0.1秒）
- 中等检测：Ping网关（1秒）
- 深度检测：HTTP请求公网服务（3-5秒）

触发场景：
- 笔记本从睡眠唤醒 → 检测到网络 → 自动加入HIDRS
- 手机切换WiFi → 检测到新网络 → 重新广播位置
- 服务器重启 → 检测到网络恢复 → 重新注册
"""
import logging
import socket
import threading
import time
import requests
from typing import Optional, Callable, Dict, List
from datetime import datetime
from enum import Enum
import netifaces

logger = logging.getLogger(__name__)


class NetworkStatus(Enum):
    """网络状态"""
    DISCONNECTED = "disconnected"  # 断开
    LOCAL_ONLY = "local_only"      # 仅本地网络
    INTERNET = "internet"          # 已连接互联网
    UNKNOWN = "unknown"            # 未知


class NetworkType(Enum):
    """网络类型"""
    UNKNOWN = "unknown"
    HOME = "home"              # 家庭网络
    WORK = "work"              # 企业网络
    DATACENTER = "datacenter"  # 数据中心
    MOBILE = "mobile"          # 移动网络
    PUBLIC = "public"          # 公共WiFi


class NetworkDetector:
    """网络检测器 - 自动检测网络连接"""

    def __init__(
        self,
        check_interval: int = 10,
        enable_auto_check: bool = True,
        check_urls: Optional[List[str]] = None
    ):
        """
        初始化网络检测器

        参数:
        - check_interval: 检测间隔（秒）
        - enable_auto_check: 是否启用自动检测
        - check_urls: 用于检测互联网连通性的URL列表
        """
        self.check_interval = check_interval
        self.enable_auto_check = enable_auto_check
        self.check_urls = check_urls or [
            "https://www.google.com",
            "https://www.cloudflare.com",
            "https://1.1.1.1"
        ]

        # 当前状态
        self.current_status = NetworkStatus.UNKNOWN
        self.current_ip: Optional[str] = None
        self.current_gateway: Optional[str] = None
        self.current_network_type = NetworkType.UNKNOWN

        # 历史记录
        self.last_check_time: Optional[datetime] = None
        self.last_status_change: Optional[datetime] = None
        self.connection_history: List[Dict] = []

        # 事件回调
        self.on_connected: Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None
        self.on_ip_changed: Optional[Callable] = None

        # 检测线程
        self._check_thread: Optional[threading.Thread] = None
        self._running = False

        logger.info("[NetworkDetector] 初始化完成")
        logger.info(f"  检测间隔: {check_interval}秒")
        logger.info(f"  自动检测: {'启用' if enable_auto_check else '禁用'}")

    def start(self):
        """启动自动检测"""
        if self._running:
            logger.warning("[NetworkDetector] 已在运行")
            return

        if not self.enable_auto_check:
            logger.info("[NetworkDetector] 自动检测被禁用")
            return

        self._running = True
        self._check_thread = threading.Thread(target=self._check_loop, daemon=True)
        self._check_thread.start()

        logger.info("[NetworkDetector] 自动检测已启动")

        # 立即执行一次检测
        self.check_network()

    def stop(self):
        """停止自动检测"""
        self._running = False
        logger.info("[NetworkDetector] 已停止")

    def _check_loop(self):
        """检测循环"""
        while self._running:
            try:
                self.check_network()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"[NetworkDetector] 检测循环错误: {e}")

    def check_network(self) -> NetworkStatus:
        """
        执行网络检测

        返回:
        - NetworkStatus: 当前网络状态
        """
        logger.debug("[NetworkDetector] 开始网络检测")

        previous_status = self.current_status
        previous_ip = self.current_ip

        # 1. 快速检测：本地网络接口
        has_interface = self._check_network_interface()

        if not has_interface:
            self._update_status(NetworkStatus.DISCONNECTED)
            return self.current_status

        # 2. 中等检测：获取IP和网关
        local_ip = self._get_local_ip()
        gateway = self._get_gateway()

        if not local_ip:
            self._update_status(NetworkStatus.DISCONNECTED)
            return self.current_status

        # 更新IP信息
        self.current_ip = local_ip
        self.current_gateway = gateway

        # 3. 深度检测：互联网连通性
        has_internet = self._check_internet_connectivity()

        if has_internet:
            self._update_status(NetworkStatus.INTERNET)
        else:
            self._update_status(NetworkStatus.LOCAL_ONLY)

        # 4. 检测网络类型
        self.current_network_type = self._detect_network_type()

        # 5. 触发事件
        if previous_status != self.current_status:
            self._on_status_changed(previous_status, self.current_status)

        if previous_ip != self.current_ip and previous_ip is not None:
            self._on_ip_changed_event(previous_ip, self.current_ip)

        self.last_check_time = datetime.now()

        logger.info(f"[NetworkDetector] 检测完成: {self.current_status.value}")
        logger.info(f"  IP: {self.current_ip}")
        logger.info(f"  网关: {self.current_gateway}")
        logger.info(f"  类型: {self.current_network_type.value}")

        return self.current_status

    def _check_network_interface(self) -> bool:
        """检查网络接口是否存在"""
        try:
            interfaces = netifaces.interfaces()
            # 排除回环接口
            active_interfaces = [iface for iface in interfaces if iface != 'lo']
            return len(active_interfaces) > 0
        except Exception as e:
            logger.debug(f"[NetworkDetector] 网络接口检查失败: {e}")
            return False

    def _get_local_ip(self) -> Optional[str]:
        """获取本地IP地址"""
        try:
            # 方法1：连接外部地址（不实际发送数据）
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            pass

        try:
            # 方法2：遍历网络接口
            for interface in netifaces.interfaces():
                if interface == 'lo':  # 跳过回环
                    continue

                addrs = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addrs:
                    for addr_info in addrs[netifaces.AF_INET]:
                        ip = addr_info.get('addr')
                        if ip and not ip.startswith('127.'):
                            return ip
        except Exception as e:
            logger.debug(f"[NetworkDetector] 获取本地IP失败: {e}")

        return None

    def _get_gateway(self) -> Optional[str]:
        """获取默认网关"""
        try:
            gws = netifaces.gateways()
            default_gateway = gws.get('default', {}).get(netifaces.AF_INET)
            if default_gateway:
                return default_gateway[0]
        except Exception as e:
            logger.debug(f"[NetworkDetector] 获取网关失败: {e}")

        return None

    def _check_internet_connectivity(self) -> bool:
        """检查互联网连通性"""
        for url in self.check_urls:
            try:
                response = requests.get(url, timeout=3)
                if response.status_code == 200:
                    logger.debug(f"[NetworkDetector] 互联网连通（{url}）")
                    return True
            except Exception:
                continue

        logger.debug("[NetworkDetector] 互联网不可达")
        return False

    def _detect_network_type(self) -> NetworkType:
        """
        检测网络类型

        简化版检测逻辑：
        - 数据中心：IP在云服务商范围内
        - 企业：IP在企业网段
        - 家庭：IP在家庭网段
        - 移动：通过网关特征判断
        """
        if not self.current_ip:
            return NetworkType.UNKNOWN

        # 简化：根据IP段判断
        if self.current_ip.startswith('192.168.'):
            return NetworkType.HOME  # 典型家庭网络
        elif self.current_ip.startswith('10.'):
            return NetworkType.WORK  # 典型企业网络
        elif self.current_ip.startswith('172.'):
            # 172.16-31是私有地址
            octets = self.current_ip.split('.')
            if len(octets) >= 2:
                second = int(octets[1])
                if 16 <= second <= 31:
                    return NetworkType.WORK

        # TODO: 更精确的检测（查询IP数据库、ASN等）
        return NetworkType.UNKNOWN

    def _update_status(self, new_status: NetworkStatus):
        """更新状态"""
        if new_status != self.current_status:
            self.last_status_change = datetime.now()

            # 记录历史
            self.connection_history.append({
                'timestamp': self.last_status_change.isoformat(),
                'old_status': self.current_status.value,
                'new_status': new_status.value,
                'ip': self.current_ip,
                'gateway': self.current_gateway
            })

            # 保持历史记录在合理范围
            if len(self.connection_history) > 100:
                self.connection_history = self.connection_history[-100:]

        self.current_status = new_status

    def _on_status_changed(self, old_status: NetworkStatus, new_status: NetworkStatus):
        """状态变化事件"""
        logger.info(f"[NetworkDetector] 网络状态变化: {old_status.value} → {new_status.value}")

        if new_status == NetworkStatus.INTERNET and old_status in [NetworkStatus.DISCONNECTED, NetworkStatus.UNKNOWN]:
            # 网络已连接
            if self.on_connected:
                logger.info("[NetworkDetector] 触发连接事件")
                threading.Thread(target=self.on_connected, daemon=True).start()

        elif new_status == NetworkStatus.DISCONNECTED and old_status in [NetworkStatus.INTERNET, NetworkStatus.LOCAL_ONLY]:
            # 网络已断开
            if self.on_disconnected:
                logger.info("[NetworkDetector] 触发断开事件")
                threading.Thread(target=self.on_disconnected, daemon=True).start()

    def _on_ip_changed_event(self, old_ip: str, new_ip: str):
        """IP变化事件"""
        logger.info(f"[NetworkDetector] IP地址变化: {old_ip} → {new_ip}")

        if self.on_ip_changed:
            threading.Thread(target=lambda: self.on_ip_changed(old_ip, new_ip), daemon=True).start()

    def is_connected(self) -> bool:
        """是否已连接互联网"""
        return self.current_status == NetworkStatus.INTERNET

    def is_local_network(self) -> bool:
        """是否仅本地网络"""
        return self.current_status == NetworkStatus.LOCAL_ONLY

    def is_disconnected(self) -> bool:
        """是否断开连接"""
        return self.current_status == NetworkStatus.DISCONNECTED

    def get_public_ip(self) -> Optional[str]:
        """
        获取公网IP地址

        通过第三方服务查询
        """
        services = [
            "https://api.ipify.org",
            "https://icanhazip.com",
            "https://ifconfig.me/ip"
        ]

        for service in services:
            try:
                response = requests.get(service, timeout=5)
                if response.status_code == 200:
                    public_ip = response.text.strip()
                    logger.info(f"[NetworkDetector] 公网IP: {public_ip}")
                    return public_ip
            except Exception:
                continue

        logger.warning("[NetworkDetector] 无法获取公网IP")
        return None

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'current_status': self.current_status.value,
            'current_ip': self.current_ip,
            'current_gateway': self.current_gateway,
            'network_type': self.current_network_type.value,
            'last_check_time': self.last_check_time.isoformat() if self.last_check_time else None,
            'last_status_change': self.last_status_change.isoformat() if self.last_status_change else None,
            'connection_history_count': len(self.connection_history),
            'is_connected': self.is_connected()
        }


# 便捷函数
def quick_check_network() -> bool:
    """快速检查网络是否连通"""
    detector = NetworkDetector(enable_auto_check=False)
    status = detector.check_network()
    return status == NetworkStatus.INTERNET
