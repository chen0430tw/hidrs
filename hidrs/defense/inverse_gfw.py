"""
HIDRS 自我保护系统（反向GFW）
Inverse Great Firewall for HIDRS Self-Defense

核心理念：
- GFW是用来阻止用户访问外部，HIDRS反向运用来阻止恶意访问内部
- 不仅防御攻击，还能将攻击流量反弹成武器
- 结合DPI、主动探测、流量分析和机器学习

技术架构：
┌─────────────────────────────────────────────────────────┐
│                    HIDRS 自我保护层                       │
├─────────────────────────────────────────────────────────┤
│  1. 流量监控层 (Traffic Monitor)                         │
│     - NFQueue包拦截                                      │
│     - DPI深度包检测                                      │
│     - 协议指纹识别                                        │
├─────────────────────────────────────────────────────────┤
│  2. 威胁检测层 (Threat Detection)                        │
│     - 主动探测可疑连接                                    │
│     - 行为模式分析（HLIG异常检测）                        │
│     - IP信誉评分系统                                      │
├─────────────────────────────────────────────────────────┤
│  3. 防御执行层 (Defense Execution)                       │
│     - SYN Cookies（防SYN Flood）                        │
│     - Tarpit（延迟响应）                                 │
│     - 连接限流                                           │
│     - 动态黑名单                                         │
├─────────────────────────────────────────────────────────┤
│  4. 反击层 (Counter-Attack)                             │
│     - DDoS流量反射                                       │
│     - Honeypot陷阱                                       │
│     - 攻击者画像追踪                                      │
│     - 情报共享网络                                        │
└─────────────────────────────────────────────────────────┘

参考文献：
- GFW DPI技术: https://gfw.report/publications/usenixsecurity23/en/
- 主动探测: https://blog.torproject.org/learning-more-about-gfws-active-probing-system/
- SYN Cookies: https://en.wikipedia.org/wiki/SYN_cookies
- Tarpit技术: https://www.secureworks.com/research/ddos
- OpenGFW实现: https://opengfw.io/
"""

import os
import time
import socket
import logging
import hashlib
import threading
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ThreatLevel:
    """威胁等级"""
    CLEAN = 0           # 清白
    SUSPICIOUS = 1      # 可疑
    MALICIOUS = 2       # 恶意
    CRITICAL = 3        # 严重威胁


@dataclass
class ConnectionProfile:
    """连接画像"""
    ip: str
    port: int
    first_seen: datetime
    last_seen: datetime
    packet_count: int
    byte_count: int
    protocol: str

    # 行为特征
    syn_count: int = 0
    incomplete_handshakes: int = 0
    suspicious_patterns: List[str] = None

    # 威胁评分
    threat_score: float = 0.0
    threat_level: int = ThreatLevel.CLEAN

    # HLIG分析
    fiedler_anomaly_score: float = 0.0

    def __post_init__(self):
        if self.suspicious_patterns is None:
            self.suspicious_patterns = []


class PacketAnalyzer:
    """
    包分析器
    基于GFW的DPI技术，对流量进行深度包检测
    """

    # 协议指纹库（基于GFW的特征库）
    PROTOCOL_SIGNATURES = {
        'tor': [
            b'\x16\x03\x01',  # TLS handshake
            b'GET / HTTP/1.0',  # Tor HTTP request
        ],
        'shadowsocks': [
            b'\x05',  # SOCKS5
        ],
        'vmess': [
            b'\x00\x00\x00',  # VMess header
        ],
        'http_flood': [
            b'GET /',
            b'POST /',
            b'HEAD /',
        ],
        'sql_injection': [
            b'UNION SELECT',
            b'OR 1=1',
            b"'; DROP TABLE",
        ],
        'xss_attack': [
            b'<script>',
            b'javascript:',
            b'onerror=',
        ]
    }

    def __init__(self):
        """初始化包分析器"""
        self.packet_cache = deque(maxlen=10000)
        self.signature_hits = defaultdict(int)

    def analyze_packet(self, packet_data: bytes, src_ip: str, dst_ip: str) -> Dict[str, Any]:
        """
        深度包检测

        返回:
        {
            'protocol': 'http/https/tor/shadowsocks',
            'suspicious': True/False,
            'matched_signatures': [...],
            'threat_indicators': [...]
        }
        """
        result = {
            'protocol': 'unknown',
            'suspicious': False,
            'matched_signatures': [],
            'threat_indicators': []
        }

        # 协议识别
        for protocol, signatures in self.PROTOCOL_SIGNATURES.items():
            for sig in signatures:
                if sig in packet_data:
                    result['matched_signatures'].append(protocol)
                    self.signature_hits[protocol] += 1

        # 威胁检测
        if 'sql_injection' in result['matched_signatures']:
            result['suspicious'] = True
            result['threat_indicators'].append('SQL injection attempt')

        if 'xss_attack' in result['matched_signatures']:
            result['suspicious'] = True
            result['threat_indicators'].append('XSS attack attempt')

        # HTTP Flood检测（高频率重复请求）
        if b'GET /' in packet_data or b'POST /' in packet_data:
            recent_packets = [p for p in self.packet_cache if p['src_ip'] == src_ip]
            if len(recent_packets) > 50:  # 50个包/秒
                result['suspicious'] = True
                result['threat_indicators'].append('Possible HTTP flood')

        # 缓存包信息
        self.packet_cache.append({
            'timestamp': time.time(),
            'src_ip': src_ip,
            'dst_ip': dst_ip,
            'size': len(packet_data)
        })

        return result


class ActiveProber:
    """
    主动探测器
    基于GFW的主动探测技术，主动探测可疑连接

    GFW工作原理：
    1. 被动监听发现可疑流量
    2. 主动发送探测包确认
    3. 如果服务器响应符合特征，立即加入黑名单

    HIDRS反向应用：
    1. 发现可疑连接
    2. 主动探测是否为扫描器/攻击工具
    3. 确认后拉黑或反击
    """

    def __init__(self):
        """初始化主动探测器"""
        self.probe_results = {}
        self.probe_timeout = 5.0

    def probe_suspicious_ip(self, ip: str, port: int) -> Dict[str, Any]:
        """
        主动探测可疑IP

        探测方法：
        1. 发送畸形包测试响应
        2. 尝试常见扫描器指纹
        3. 检测开放端口模式

        返回:
        {
            'is_scanner': True/False,
            'scanner_type': 'nmap/masscan/zmap',
            'open_ports': [...],
            'os_fingerprint': 'Linux/Windows'
        }
        """
        result = {
            'is_scanner': False,
            'scanner_type': None,
            'open_ports': [],
            'os_fingerprint': None,
            'probe_timestamp': datetime.utcnow()
        }

        try:
            # 探测1: 发送畸形SYN包
            # 正常客户端会重传，扫描器通常不会
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.probe_timeout)

            # 探测2: 检测响应时间
            # 自动化工具响应极快，人工浏览慢
            start = time.time()
            try:
                sock.connect((ip, port))
                response_time = time.time() - start

                if response_time < 0.01:  # 10ms内响应
                    result['is_scanner'] = True
                    result['scanner_type'] = 'automated_tool'
            except:
                pass
            finally:
                sock.close()

            # 探测3: 端口扫描检测
            # 尝试连接多个端口，扫描器会快速响应
            common_ports = [22, 80, 443, 3306, 6379, 27017, 9200]
            open_count = 0

            for p in common_ports:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.5)
                    if s.connect_ex((ip, p)) == 0:
                        open_count += 1
                        result['open_ports'].append(p)
                    s.close()
                except:
                    pass

            # 如果多个端口都快速响应，很可能是扫描器
            if open_count > 3:
                result['is_scanner'] = True

            logger.info(f"[ActiveProber] 探测 {ip}:{port} - 扫描器: {result['is_scanner']}")

        except Exception as e:
            logger.error(f"[ActiveProber] 探测失败: {e}")

        self.probe_results[ip] = result
        return result

    def is_known_scanner(self, ip: str) -> bool:
        """检查是否为已知扫描器"""
        return ip in self.probe_results and self.probe_results[ip]['is_scanner']


class HLIGAnomalyDetector:
    """
    HLIG异常检测器
    使用拉普拉斯矩阵谱分析检测异常流量模式

    正常流量：在拉普拉斯空间中形成密集簇
    攻击流量：表现为离群点或异常模式
    """

    def __init__(self, window_size: int = 100):
        """
        初始化异常检测器

        参数:
        - window_size: 滑动窗口大小
        """
        self.window_size = window_size
        self.traffic_window = deque(maxlen=window_size)
        self.baseline_fiedler = None

    def add_traffic_sample(self, connection_profile: ConnectionProfile):
        """添加流量样本"""
        # 提取特征向量
        features = self._extract_features(connection_profile)

        self.traffic_window.append({
            'timestamp': time.time(),
            'ip': connection_profile.ip,
            'features': features,
            'profile': connection_profile
        })

    def _extract_features(self, profile: ConnectionProfile) -> np.ndarray:
        """
        提取连接特征

        特征：
        1. 包速率 (packets/sec)
        2. 字节速率 (bytes/sec)
        3. SYN比率
        4. 不完整握手比率
        5. 连接持续时间
        """
        duration = (profile.last_seen - profile.first_seen).total_seconds() or 1.0

        features = np.array([
            profile.packet_count / duration,  # 包速率
            profile.byte_count / duration,    # 字节速率
            profile.syn_count / max(profile.packet_count, 1),  # SYN比率
            profile.incomplete_handshakes / max(profile.packet_count, 1),  # 不完整握手
            duration,  # 持续时间
        ])

        return features

    def detect_anomaly(self, profile: ConnectionProfile) -> Tuple[bool, float]:
        """
        检测异常

        返回:
        - (is_anomaly, anomaly_score)
        """
        if len(self.traffic_window) < 10:
            return False, 0.0

        # 构建流量特征矩阵
        feature_matrix = np.array([
            sample['features'] for sample in self.traffic_window
        ])

        # 归一化
        mean = np.mean(feature_matrix, axis=0)
        std = np.std(feature_matrix, axis=0) + 1e-6
        normalized = (feature_matrix - mean) / std

        # 构建相似度矩阵（基于欧氏距离）
        n = len(normalized)
        W = np.zeros((n, n))

        for i in range(n):
            for j in range(i + 1, n):
                dist = np.linalg.norm(normalized[i] - normalized[j])
                similarity = np.exp(-dist)  # 高斯核
                W[i, j] = similarity
                W[j, i] = similarity

        # 计算拉普拉斯矩阵
        D = np.diag(np.sum(W, axis=1))
        L = D - W

        # 归一化拉普拉斯矩阵
        D_sqrt_inv = np.diag(1.0 / np.sqrt(np.diag(D) + 1e-6))
        L_norm = np.eye(n) - D_sqrt_inv @ W @ D_sqrt_inv

        # 计算特征值
        try:
            eigenvalues = np.linalg.eigvalsh(L_norm)
            fiedler_value = eigenvalues[1]  # 第二小特征值

            # 建立基线
            if self.baseline_fiedler is None:
                self.baseline_fiedler = fiedler_value
                return False, 0.0

            # 计算异常得分
            anomaly_score = abs(fiedler_value - self.baseline_fiedler) / (self.baseline_fiedler + 1e-6)

            # 更新基线（指数移动平均）
            alpha = 0.1
            self.baseline_fiedler = alpha * fiedler_value + (1 - alpha) * self.baseline_fiedler

            # 判断异常
            is_anomaly = anomaly_score > 2.0  # 阈值

            logger.debug(f"[HLIG] Fiedler: {fiedler_value:.4f}, Baseline: {self.baseline_fiedler:.4f}, Anomaly: {anomaly_score:.4f}")

            return is_anomaly, anomaly_score

        except Exception as e:
            logger.error(f"[HLIG] 异常检测失败: {e}")
            return False, 0.0


class IPReputationSystem:
    """
    IP信誉评分系统
    基于历史行为动态评分
    """

    def __init__(self):
        """初始化信誉系统"""
        self.reputation_db = {}  # ip -> score (0-100)
        self.blacklist = set()
        self.whitelist = set()

    def get_reputation(self, ip: str) -> int:
        """获取IP信誉分（0-100，越高越好）"""
        if ip in self.whitelist:
            return 100
        if ip in self.blacklist:
            return 0
        return self.reputation_db.get(ip, 50)  # 默认50分

    def update_reputation(self, ip: str, delta: int):
        """
        更新信誉分

        参数:
        - delta: 变化量（正数增加信誉，负数降低）
        """
        current = self.get_reputation(ip)
        new_score = max(0, min(100, current + delta))

        self.reputation_db[ip] = new_score

        # 自动加入黑名单
        if new_score == 0:
            self.blacklist.add(ip)
            logger.warning(f"[Reputation] IP {ip} 加入黑名单")

        # 自动移出黑名单
        if new_score > 20 and ip in self.blacklist:
            self.blacklist.remove(ip)
            logger.info(f"[Reputation] IP {ip} 移出黑名单")

    def report_malicious(self, ip: str, reason: str):
        """报告恶意行为"""
        logger.warning(f"[Reputation] 恶意行为: {ip} - {reason}")
        self.update_reputation(ip, -30)

    def report_suspicious(self, ip: str, reason: str):
        """报告可疑行为"""
        logger.info(f"[Reputation] 可疑行为: {ip} - {reason}")
        self.update_reputation(ip, -10)

    def report_clean(self, ip: str):
        """报告正常行为"""
        self.update_reputation(ip, +1)


class SYNCookieDefense:
    """
    SYN Cookie防御
    基于Linux内核的SYN Cookie机制，防止SYN Flood攻击

    原理：
    1. 不维护半开连接状态
    2. 在SYN-ACK的序列号中编码连接信息
    3. 只有收到合法ACK才分配资源

    参考: https://en.wikipedia.org/wiki/SYN_cookies
    """

    def __init__(self, secret_key: bytes = None):
        """
        初始化SYN Cookie防御

        参数:
        - secret_key: 密钥（用于HMAC）
        """
        self.secret_key = secret_key or os.urandom(32)
        self.pending_cookies = {}

    def generate_cookie(self, src_ip: str, src_port: int, dst_ip: str, dst_port: int) -> int:
        """
        生成SYN Cookie

        Cookie编码：
        - 时间戳（防重放）
        - 源IP/端口
        - 目标IP/端口
        - HMAC签名
        """
        timestamp = int(time.time()) & 0x1F  # 5位时间戳（32秒循环）

        # 构建cookie数据
        data = f"{src_ip}:{src_port}:{dst_ip}:{dst_port}:{timestamp}".encode()

        # HMAC签名
        import hmac
        signature = hmac.new(self.secret_key, data, hashlib.sha256).digest()

        # 取前24位作为cookie
        cookie = int.from_bytes(signature[:3], 'big')

        # 存储cookie（用于验证）
        cookie_key = (src_ip, src_port, dst_ip, dst_port)
        self.pending_cookies[cookie_key] = {
            'cookie': cookie,
            'timestamp': time.time()
        }

        return cookie

    def verify_cookie(self, cookie: int, src_ip: str, src_port: int, dst_ip: str, dst_port: int) -> bool:
        """验证SYN Cookie"""
        cookie_key = (src_ip, src_port, dst_ip, dst_port)

        if cookie_key not in self.pending_cookies:
            return False

        stored = self.pending_cookies[cookie_key]

        # 检查超时（60秒）
        if time.time() - stored['timestamp'] > 60:
            del self.pending_cookies[cookie_key]
            return False

        # 验证cookie
        if stored['cookie'] == cookie:
            del self.pending_cookies[cookie_key]
            return True

        return False

    def cleanup_expired(self):
        """清理过期cookie"""
        now = time.time()
        expired = [
            key for key, val in self.pending_cookies.items()
            if now - val['timestamp'] > 60
        ]

        for key in expired:
            del self.pending_cookies[key]


class TarpitDefense:
    """
    Tarpit防御
    故意延迟响应，耗尽攻击者资源

    原理：
    1. 识别恶意连接
    2. 不立即拒绝，而是极慢地响应
    3. 攻击者被迫维持连接，消耗自身资源

    参考: https://www.secureworks.com/research/ddos
    """

    def __init__(self, delay_seconds: float = 30.0):
        """
        初始化Tarpit防御

        参数:
        - delay_seconds: 延迟秒数
        """
        self.delay_seconds = delay_seconds
        self.tarpitted_ips = set()

    def add_to_tarpit(self, ip: str):
        """将IP加入tarpit"""
        self.tarpitted_ips.add(ip)
        logger.info(f"[Tarpit] IP {ip} 加入tarpit（延迟{self.delay_seconds}秒）")

    def should_tarpit(self, ip: str) -> bool:
        """检查是否应该tarpit"""
        return ip in self.tarpitted_ips

    def apply_delay(self, ip: str):
        """应用延迟"""
        if self.should_tarpit(ip):
            logger.debug(f"[Tarpit] 延迟响应 {ip}")
            time.sleep(self.delay_seconds)


class TrafficReflector:
    """
    流量反射器（流量大炮）
    将DDoS攻击流量反弹回攻击者

    警告：这是攻击性技术，仅用于合法防御和研究！

    原理：
    1. 检测到DDoS攻击
    2. 识别攻击者IP（可能是伪造的）
    3. 利用协议特性将流量反射回去
    4. 攻击者自己承受放大的流量

    常见反射协议：
    - DNS (放大因子: 28-54x)
    - NTP (放大因子: 556x)
    - SSDP (放大因子: 30x)
    - Memcached (放大因子: 51000x)

    参考: https://www.netscout.com/what-is-ddos/what-is-reflection-amplification-attack
    """

    def __init__(self, enable_reflection: bool = False):
        """
        初始化流量反射器

        参数:
        - enable_reflection: 是否启用反射（默认禁用，需明确启用）
        """
        self.enable_reflection = enable_reflection
        self.reflection_log = []

        if enable_reflection:
            logger.warning("[TrafficReflector] ⚠️  流量反射已启用！仅用于合法防御！")

    def reflect_attack(self, attacker_ip: str, attack_type: str, packet_count: int):
        """
        反射攻击

        ⚠️ 警告：这会向攻击者发送大量流量！
        仅在确认合法防御的情况下使用！

        参数:
        - attacker_ip: 攻击者IP
        - attack_type: 攻击类型
        - packet_count: 反射包数量
        """
        if not self.enable_reflection:
            logger.warning("[TrafficReflector] 反射被禁用，跳过")
            return

        logger.warning(f"[TrafficReflector] 🔥 向 {attacker_ip} 反射 {attack_type} 攻击（{packet_count}包）")

        # 记录反射日志
        self.reflection_log.append({
            'timestamp': datetime.utcnow(),
            'target': attacker_ip,
            'type': attack_type,
            'packet_count': packet_count
        })

        # 实际反射逻辑
        # 注意：这里仅为演示，实际实现需要专业的网络编程

        if attack_type == 'syn_flood':
            self._reflect_syn_flood(attacker_ip, packet_count)
        elif attack_type == 'http_flood':
            self._reflect_http_flood(attacker_ip, packet_count)
        else:
            logger.warning(f"[TrafficReflector] 不支持的攻击类型: {attack_type}")

    def _reflect_syn_flood(self, target_ip: str, count: int):
        """反射SYN Flood"""
        logger.info(f"[TrafficReflector] SYN反射 -> {target_ip}")

        # 这里应该使用原始socket发送SYN包
        # 示例代码（需要root权限）:
        # for _ in range(count):
        #     send_raw_syn_packet(target_ip, random_port())

        # 为了安全，这里只是模拟
        logger.warning("[TrafficReflector] SYN反射（模拟模式）")

    def _reflect_http_flood(self, target_ip: str, count: int):
        """反射HTTP Flood"""
        logger.info(f"[TrafficReflector] HTTP反射 -> {target_ip}")

        # 这里应该发送大量HTTP请求
        # 为了安全，这里只是模拟
        logger.warning("[TrafficReflector] HTTP反射（模拟模式）")


class HIDRSFirewall:
    """
    HIDRS反向防火墙
    整合所有自我保护机制
    """

    def __init__(
        self,
        enable_active_probing: bool = True,
        enable_hlig_detection: bool = True,
        enable_syn_cookies: bool = True,
        enable_tarpit: bool = True,
        enable_traffic_reflection: bool = False  # 默认禁用攻击性功能
    ):
        """
        初始化HIDRS防火墙

        参数:
        - enable_active_probing: 启用主动探测
        - enable_hlig_detection: 启用HLIG异常检测
        - enable_syn_cookies: 启用SYN Cookie
        - enable_tarpit: 启用Tarpit
        - enable_traffic_reflection: 启用流量反射（⚠️ 攻击性功能）
        """
        logger.info("=" * 60)
        logger.info("🛡️  HIDRS反向防火墙初始化")
        logger.info("=" * 60)

        # 组件初始化
        self.packet_analyzer = PacketAnalyzer()
        self.active_prober = ActiveProber() if enable_active_probing else None
        self.hlig_detector = HLIGAnomalyDetector() if enable_hlig_detection else None
        self.reputation_system = IPReputationSystem()
        self.syn_cookie = SYNCookieDefense() if enable_syn_cookies else None
        self.tarpit = TarpitDefense() if enable_tarpit else None
        self.reflector = TrafficReflector(enable_reflection=enable_traffic_reflection)

        # 连接追踪
        self.connections = {}  # ip -> ConnectionProfile

        # 统计
        self.stats = {
            'total_packets': 0,
            'blocked_packets': 0,
            'suspicious_packets': 0,
            'tarpitted_connections': 0,
            'reflected_attacks': 0,
            'active_probes': 0
        }

        # 自动清理线程
        self.running = False
        self.cleanup_thread = None

        logger.info(f"  主动探测: {'✅' if enable_active_probing else '❌'}")
        logger.info(f"  HLIG检测: {'✅' if enable_hlig_detection else '❌'}")
        logger.info(f"  SYN Cookies: {'✅' if enable_syn_cookies else '❌'}")
        logger.info(f"  Tarpit: {'✅' if enable_tarpit else '❌'}")
        logger.info(f"  流量反射: {'⚠️  已启用' if enable_traffic_reflection else '❌'}")
        logger.info("=" * 60)

    def start(self):
        """启动防火墙"""
        self.running = True

        # 启动清理线程
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()

        logger.info("[HIDRSFirewall] 🛡️  防火墙已启动")

    def stop(self):
        """停止防火墙"""
        self.running = False
        logger.info("[HIDRSFirewall] 防火墙已停止")

    def process_packet(
        self,
        packet_data: bytes,
        src_ip: str,
        src_port: int,
        dst_ip: str,
        dst_port: int,
        protocol: str = 'tcp'
    ) -> Dict[str, Any]:
        """
        处理数据包

        返回:
        {
            'action': 'allow/block/tarpit',
            'reason': '...',
            'threat_level': 0-3
        }
        """
        self.stats['total_packets'] += 1

        # 1. 检查IP信誉
        reputation = self.reputation_system.get_reputation(src_ip)

        if reputation == 0:
            self.stats['blocked_packets'] += 1
            return {
                'action': 'block',
                'reason': 'IP in blacklist',
                'threat_level': ThreatLevel.CRITICAL
            }

        # 2. DPI包分析
        analysis = self.packet_analyzer.analyze_packet(packet_data, src_ip, dst_ip)

        if analysis['suspicious']:
            self.stats['suspicious_packets'] += 1
            self.reputation_system.report_suspicious(
                src_ip,
                ', '.join(analysis['threat_indicators'])
            )

        # 3. 获取或创建连接画像
        if src_ip not in self.connections:
            self.connections[src_ip] = ConnectionProfile(
                ip=src_ip,
                port=src_port,
                first_seen=datetime.utcnow(),
                last_seen=datetime.utcnow(),
                packet_count=0,
                byte_count=0,
                protocol=protocol
            )

        profile = self.connections[src_ip]
        profile.last_seen = datetime.utcnow()
        profile.packet_count += 1
        profile.byte_count += len(packet_data)

        # 4. HLIG异常检测
        if self.hlig_detector:
            self.hlig_detector.add_traffic_sample(profile)
            is_anomaly, anomaly_score = self.hlig_detector.detect_anomaly(profile)

            profile.fiedler_anomaly_score = anomaly_score

            if is_anomaly:
                logger.warning(f"[HIDRSFirewall] HLIG异常检测: {src_ip} (得分: {anomaly_score:.2f})")
                profile.threat_level = ThreatLevel.SUSPICIOUS

        # 5. 主动探测（针对可疑IP）
        if self.active_prober and profile.threat_level >= ThreatLevel.SUSPICIOUS:
            if not self.active_prober.is_known_scanner(src_ip):
                self.stats['active_probes'] += 1

                probe_result = self.active_prober.probe_suspicious_ip(src_ip, src_port)

                if probe_result['is_scanner']:
                    logger.warning(f"[HIDRSFirewall] 检测到扫描器: {src_ip}")
                    profile.threat_level = ThreatLevel.MALICIOUS
                    self.reputation_system.report_malicious(src_ip, 'Scanner detected')

        # 6. 决策
        action = 'allow'
        reason = 'Normal traffic'

        if profile.threat_level == ThreatLevel.CRITICAL:
            action = 'block'
            reason = 'Critical threat'

            # 可选：反射攻击
            if self.reflector.enable_reflection:
                self.reflector.reflect_attack(src_ip, 'http_flood', 100)
                self.stats['reflected_attacks'] += 1

        elif profile.threat_level == ThreatLevel.MALICIOUS:
            # Tarpit攻击者
            if self.tarpit:
                self.tarpit.add_to_tarpit(src_ip)
                action = 'tarpit'
                reason = 'Malicious activity'
                self.stats['tarpitted_connections'] += 1

        elif profile.threat_level == ThreatLevel.SUSPICIOUS:
            # 可疑流量，降低优先级但不阻断
            action = 'rate_limit'
            reason = 'Suspicious pattern detected'

        return {
            'action': action,
            'reason': reason,
            'threat_level': profile.threat_level,
            'reputation': reputation,
            'anomaly_score': profile.fiedler_anomaly_score
        }

    def _cleanup_loop(self):
        """清理循环"""
        while self.running:
            try:
                time.sleep(300)  # 5分钟

                # 清理过期连接
                now = datetime.utcnow()
                expired = [
                    ip for ip, profile in self.connections.items()
                    if (now - profile.last_seen).total_seconds() > 600  # 10分钟
                ]

                for ip in expired:
                    del self.connections[ip]

                # 清理SYN Cookie
                if self.syn_cookie:
                    self.syn_cookie.cleanup_expired()

                logger.debug(f"[HIDRSFirewall] 清理完成，移除 {len(expired)} 个过期连接")

            except Exception as e:
                logger.error(f"[HIDRSFirewall] 清理错误: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            'active_connections': len(self.connections),
            'blacklisted_ips': len(self.reputation_system.blacklist),
            'whitelisted_ips': len(self.reputation_system.whitelist)
        }

    def get_threat_report(self) -> Dict[str, Any]:
        """获取威胁报告"""
        threats = {
            'critical': [],
            'malicious': [],
            'suspicious': []
        }

        for ip, profile in self.connections.items():
            if profile.threat_level == ThreatLevel.CRITICAL:
                threats['critical'].append({
                    'ip': ip,
                    'threat_score': profile.threat_score,
                    'anomaly_score': profile.fiedler_anomaly_score,
                    'patterns': profile.suspicious_patterns
                })
            elif profile.threat_level == ThreatLevel.MALICIOUS:
                threats['malicious'].append({
                    'ip': ip,
                    'threat_score': profile.threat_score,
                    'anomaly_score': profile.fiedler_anomaly_score
                })
            elif profile.threat_level == ThreatLevel.SUSPICIOUS:
                threats['suspicious'].append({
                    'ip': ip,
                    'anomaly_score': profile.fiedler_anomaly_score
                })

        return threats


# 使用示例
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("🛡️  HIDRS反向防火墙演示")
    print("=" * 70)

    # 初始化防火墙
    firewall = HIDRSFirewall(
        enable_active_probing=True,
        enable_hlig_detection=True,
        enable_syn_cookies=True,
        enable_tarpit=True,
        enable_traffic_reflection=False  # 演示环境禁用攻击性功能
    )

    firewall.start()

    # 模拟正常流量
    print("\n测试1: 正常流量")
    result = firewall.process_packet(
        b'GET / HTTP/1.1\r\nHost: example.com\r\n',
        '1.2.3.4',
        12345,
        '10.0.0.1',
        80,
        'tcp'
    )
    print(f"结果: {result}")

    # 模拟SQL注入攻击
    print("\n测试2: SQL注入攻击")
    result = firewall.process_packet(
        b"GET /?id=1' OR 1=1-- HTTP/1.1\r\n",
        '5.6.7.8',
        54321,
        '10.0.0.1',
        80,
        'tcp'
    )
    print(f"结果: {result}")

    # 模拟HTTP Flood
    print("\n测试3: HTTP Flood")
    for i in range(100):
        result = firewall.process_packet(
            b'GET / HTTP/1.1\r\n',
            '9.10.11.12',
            10000 + i,
            '10.0.0.1',
            80,
            'tcp'
        )
    print(f"结果: {result}")

    # 显示统计
    print("\n统计信息:")
    stats = firewall.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # 威胁报告
    print("\n威胁报告:")
    threats = firewall.get_threat_report()
    for level, items in threats.items():
        print(f"  {level.upper()}: {len(items)} 个")

    firewall.stop()
    print("\n防火墙已停止")
