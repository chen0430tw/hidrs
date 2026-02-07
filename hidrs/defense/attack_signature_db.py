"""
HIDRS攻击特征库系统
Attack Signature Database with Adaptive State Transition

核心功能：
1. 攻击签名存储和快速匹配
2. 木马payload特征检测
3. 自适应状态转移概率学习
4. IPSec流量识别
5. 性能优化：索引、缓存、并行

By: Claude + 430
"""

import re
import hashlib
import logging
import threading
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import struct

logger = logging.getLogger(__name__)


# ============================================================================
# 攻击签名数据结构
# ============================================================================

@dataclass
class AttackSignature:
    """攻击签名"""
    signature_id: str
    attack_type: str
    severity: int  # 1-10

    # 匹配规则
    port_pattern: Optional[Set[int]] = None
    ip_pattern: Optional[str] = None  # CIDR or regex
    payload_pattern: Optional[bytes] = None  # 字节模式
    payload_regex: Optional[str] = None  # 正则表达式

    # 行为特征
    packet_rate_threshold: Optional[float] = None  # 包/秒
    packet_size_range: Optional[Tuple[int, int]] = None
    protocol: Optional[str] = None  # TCP/UDP/ICMP

    # 元数据
    description: str = ""
    cve_id: Optional[str] = None
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    match_count: int = 0
    false_positive_count: int = 0

    def confidence(self) -> float:
        """计算签名可信度（基于误报率）"""
        if self.match_count == 0:
            return 0.5  # 新签名默认50%
        return 1.0 - (self.false_positive_count / max(1, self.match_count))


@dataclass
class MalwareSignature:
    """木马签名（payload特征）"""
    malware_id: str
    malware_family: str  # 木马家族
    payload_hash: str  # SHA256
    payload_pattern: bytes  # 特征字节串
    offset: int = 0  # payload偏移量

    # 行为特征
    creates_process: bool = False
    modifies_registry: bool = False
    network_callback: Optional[str] = None  # C&C域名/IP

    # 检测统计
    detection_count: int = 0
    last_detected: Optional[datetime] = None


@dataclass
class IPSecSignature:
    """IPSec流量签名"""
    spi: int  # Security Parameters Index
    protocol: str  # ESP or AH
    encryption_algo: Optional[str] = None
    auth_algo: Optional[str] = None
    is_tunnel_mode: bool = True

    # 异常检测
    abnormal_padding: bool = False
    abnormal_sequence: bool = False


# ============================================================================
# 自适应状态转移学习器
# ============================================================================

class AdaptiveTransitionMatrix:
    """
    自适应马尔可夫状态转移矩阵

    根据实际攻击统计动态调整转移概率，减少误报率
    """

    def __init__(self, n_states: int = 6):
        self.n_states = n_states

        # 初始转移概率（先验知识）
        self.prior_matrix = self._init_prior_matrix()

        # 观测统计：transition_counts[i][j] = 从状态i到状态j的次数
        self.transition_counts = defaultdict(lambda: defaultdict(int))

        # 每个状态的总转移次数
        self.state_total_counts = defaultdict(int)

        # 误报率统计
        self.false_positive_rate = 0.0
        self.total_alerts = 0
        self.confirmed_attacks = 0
        self.false_positive_count = 0  # 误报次数

        # 学习率（平衡先验和观测）
        self.learning_rate = 0.1

        self._lock = threading.Lock()

    def _init_prior_matrix(self) -> Dict[int, Dict[int, float]]:
        """初始化先验转移概率矩阵"""
        # 基于专家知识的初始概率
        prior = defaultdict(lambda: defaultdict(float))

        # 状态定义：
        # 0:正常流量 1:可疑活动 2:确认攻击 3:攻击升级 4:攻击持续 5:攻击衰退

        # 正常流量 (0)
        prior[0][0] = 0.90  # 保持正常
        prior[0][1] = 0.10  # 变为可疑

        # 可疑活动 (1)
        prior[1][0] = 0.30  # 恢复正常
        prior[1][1] = 0.50  # 保持可疑
        prior[1][2] = 0.20  # 确认攻击

        # 确认攻击 (2)
        prior[2][2] = 0.40  # 保持确认
        prior[2][3] = 0.40  # 攻击升级
        prior[2][5] = 0.20  # 攻击衰退

        # 攻击升级 (3)
        prior[3][3] = 0.30  # 保持升级
        prior[3][4] = 0.50  # 攻击持续
        prior[3][5] = 0.20  # 攻击衰退

        # 攻击持续 (4)
        prior[4][4] = 0.60  # 保持持续
        prior[4][5] = 0.30  # 攻击衰退
        prior[4][3] = 0.10  # 再次升级

        # 攻击衰退 (5)
        prior[5][5] = 0.40  # 保持衰退
        prior[5][1] = 0.30  # 变为可疑
        prior[5][0] = 0.30  # 恢复正常

        return prior

    def update_observation(self, from_state: int, to_state: int, is_false_positive: bool = False):
        """
        更新状态转移观测

        Args:
            from_state: 源状态
            to_state: 目标状态
            is_false_positive: 是否为误报
        """
        with self._lock:
            self.transition_counts[from_state][to_state] += 1
            self.state_total_counts[from_state] += 1

            # 更新误报率
            if to_state >= 2:  # 确认攻击及以上
                self.total_alerts += 1
                if is_false_positive:
                    self.false_positive_count += 1
                else:
                    self.confirmed_attacks += 1

                self.false_positive_rate = self.false_positive_count / max(1, self.total_alerts)

    def get_transition_probability(self, from_state: int, to_state: int) -> float:
        """
        获取当前转移概率（结合先验和观测）

        P_final = (1 - α) × P_prior + α × P_observed
        其中 α = learning_rate，随着观测增加自动调整
        """
        # 获取先验概率
        prior_prob = self.prior_matrix[from_state][to_state]

        # 如果没有观测数据，直接返回先验
        if self.state_total_counts[from_state] == 0:
            return prior_prob

        # 计算观测概率
        observed_prob = self.transition_counts[from_state][to_state] / self.state_total_counts[from_state]

        # 根据误报率调整学习率
        # 高误报率 → 降低学习率（更相信先验）
        adaptive_lr = self.learning_rate * (1.0 - self.false_positive_rate)

        # 贝叶斯融合
        final_prob = (1 - adaptive_lr) * prior_prob + adaptive_lr * observed_prob

        return final_prob

    def get_all_transitions(self, from_state: int) -> Dict[int, float]:
        """获取从某状态出发的所有转移概率"""
        transitions = {}
        for to_state in range(self.n_states):
            prob = self.get_transition_probability(from_state, to_state)
            if prob > 0:
                transitions[to_state] = prob
        return transitions

    def adjust_for_false_positives(self):
        """根据误报率自动调整转移概率（降低敏感度）"""
        if self.false_positive_rate > 0.1:  # 误报率>10%
            # 降低 正常→可疑 的概率
            factor = 1.0 - (self.false_positive_rate - 0.1) * 2
            self.prior_matrix[0][1] *= max(0.5, factor)
            self.prior_matrix[0][0] = 1.0 - self.prior_matrix[0][1]

            # 提高 可疑→正常 的概率
            self.prior_matrix[1][0] *= (1.0 + (self.false_positive_rate - 0.1))

            # 重新归一化
            total = sum(self.prior_matrix[1].values())
            for to_state in self.prior_matrix[1]:
                self.prior_matrix[1][to_state] /= total

            logger.info(f"自动调整状态转移概率：误报率={self.false_positive_rate:.2%}")


# ============================================================================
# 特征库主类
# ============================================================================

class AttackSignatureDatabase:
    """
    攻击特征库

    功能：
    1. 快速签名匹配（索引优化）
    2. 木马payload检测
    3. IPSec流量识别
    4. 自适应学习
    """

    def __init__(self):
        # 签名存储
        self.attack_signatures: Dict[str, AttackSignature] = {}
        self.malware_signatures: Dict[str, MalwareSignature] = {}
        self.ipsec_signatures: Dict[int, IPSecSignature] = {}

        # 快速索引
        self.port_index: Dict[int, Set[str]] = defaultdict(set)  # port -> signature_ids
        self.attack_type_index: Dict[str, Set[str]] = defaultdict(set)  # type -> signature_ids
        self.payload_hash_index: Dict[str, str] = {}  # hash -> malware_id

        # 自适应转移矩阵
        self.adaptive_matrix = AdaptiveTransitionMatrix()

        # 缓存（性能优化）
        self._match_cache: Dict[str, Optional[str]] = {}  # packet_hash -> signature_id
        self._cache_max_size = 10000

        self._lock = threading.Lock()

        # 加载预定义签名
        self._load_builtin_signatures()

    def _load_builtin_signatures(self):
        """加载内置攻击签名"""

        # ========== DDoS签名 ==========
        self.add_signature(AttackSignature(
            signature_id="ddos_syn_flood",
            attack_type="SYN_FLOOD",
            severity=8,
            protocol="TCP",
            packet_rate_threshold=1000.0,
            packet_size_range=(40, 60),
            description="TCP SYN洪水攻击",
        ))

        self.add_signature(AttackSignature(
            signature_id="ddos_udp_flood",
            attack_type="UDP_FLOOD",
            severity=7,
            protocol="UDP",
            packet_rate_threshold=5000.0,
            description="UDP洪水攻击",
        ))

        self.add_signature(AttackSignature(
            signature_id="ddos_icmp_flood",
            attack_type="ICMP_FLOOD",
            severity=6,
            protocol="ICMP",
            packet_rate_threshold=500.0,
            description="ICMP洪水攻击（Ping flood）",
        ))

        # ========== DNS攻击签名 ==========
        self.add_signature(AttackSignature(
            signature_id="dns_amplification",
            attack_type="DNS_AMPLIFICATION",
            severity=9,
            port_pattern={53},
            protocol="UDP",
            packet_size_range=(500, 4096),
            description="DNS放大攻击",
        ))

        self.add_signature(AttackSignature(
            signature_id="dns_tunneling",
            attack_type="DNS_TUNNELING",
            severity=7,
            port_pattern={53},
            payload_regex=r"[a-f0-9]{32,}",  # 长域名hex编码
            description="DNS隧道（数据泄露）",
        ))

        # ========== 端口扫描签名 ==========
        self.add_signature(AttackSignature(
            signature_id="port_scan_tcp",
            attack_type="PORT_SCAN",
            severity=5,
            packet_rate_threshold=50.0,
            description="TCP端口扫描",
        ))

        # ========== Web攻击签名 ==========
        self.add_signature(AttackSignature(
            signature_id="sql_injection",
            attack_type="SQL_INJECTION",
            severity=10,
            port_pattern={80, 443, 8080},
            payload_regex=r"(union.*select|or.*1.*=.*1|drop.*table)",
            description="SQL注入攻击",
        ))

        self.add_signature(AttackSignature(
            signature_id="xss_attack",
            attack_type="XSS",
            severity=8,
            port_pattern={80, 443},
            payload_regex=r"(<script|javascript:|onerror=|onload=)",
            description="跨站脚本攻击",
        ))

        # ========== 木马签名 ==========

        # Metasploit reverse shell特征
        self.add_malware_signature(MalwareSignature(
            malware_id="metasploit_reverse_tcp",
            malware_family="Metasploit",
            payload_hash=hashlib.sha256(b"meterpreter").hexdigest(),
            payload_pattern=b"\x4d\x5a\x90\x00",  # PE文件头
            creates_process=True,
            network_callback="*",  # 任意C&C
        ))

        # Cobalt Strike Beacon
        self.add_malware_signature(MalwareSignature(
            malware_id="cobaltstrike_beacon",
            malware_family="CobaltStrike",
            payload_hash=hashlib.sha256(b"beacon").hexdigest(),
            payload_pattern=b"\x00\x00\x00\x01\x00\x00\x00\x01",
            creates_process=True,
            network_callback="*.cloudfront.net",
        ))

        # Webshell特征（中国菜刀）
        self.add_malware_signature(MalwareSignature(
            malware_id="webshell_chopper",
            malware_family="Webshell",
            payload_hash=hashlib.sha256(b"chopper").hexdigest(),
            payload_pattern=b"eval(base64_decode(",
        ))

        logger.info(f"已加载 {len(self.attack_signatures)} 个攻击签名和 {len(self.malware_signatures)} 个木马签名")

    def add_signature(self, sig: AttackSignature):
        """添加攻击签名并建立索引"""
        with self._lock:
            self.attack_signatures[sig.signature_id] = sig

            # 建立端口索引
            if sig.port_pattern:
                for port in sig.port_pattern:
                    self.port_index[port].add(sig.signature_id)

            # 建立攻击类型索引
            self.attack_type_index[sig.attack_type].add(sig.signature_id)

    def add_malware_signature(self, sig: MalwareSignature):
        """添加木马签名"""
        with self._lock:
            self.malware_signatures[sig.malware_id] = sig
            self.payload_hash_index[sig.payload_hash] = sig.malware_id

    def match_packet(self,
                     src_ip: str,
                     dst_ip: str,
                     src_port: int,
                     dst_port: int,
                     protocol: str,
                     payload: bytes,
                     packet_rate: float = 0.0,
                     packet_size: int = 0) -> Optional[AttackSignature]:
        """
        匹配数据包

        使用索引优化，优先匹配高概率签名
        """
        # 生成包特征哈希（缓存用）
        packet_hash = hashlib.md5(
            f"{src_ip}:{src_port}->{dst_ip}:{dst_port}:{protocol}".encode()
        ).hexdigest()

        # 检查缓存
        if packet_hash in self._match_cache:
            cached_id = self._match_cache[packet_hash]
            return self.attack_signatures.get(cached_id) if cached_id else None

        # 候选签名集合（基于索引快速筛选）
        candidates: Set[str] = set()

        # 1. 通过目标端口索引筛选
        if dst_port in self.port_index:
            candidates.update(self.port_index[dst_port])

        # 2. 如果没有端口匹配，检查所有签名（较慢）
        if not candidates:
            candidates = set(self.attack_signatures.keys())

        # 3. 逐个匹配候选签名
        for sig_id in candidates:
            sig = self.attack_signatures[sig_id]

            # 协议匹配
            if sig.protocol and sig.protocol != protocol:
                continue

            # 端口匹配
            if sig.port_pattern and dst_port not in sig.port_pattern:
                continue

            # 包速率阈值
            if sig.packet_rate_threshold and packet_rate < sig.packet_rate_threshold:
                continue

            # 包大小范围
            if sig.packet_size_range:
                min_size, max_size = sig.packet_size_range
                if not (min_size <= packet_size <= max_size):
                    continue

            # Payload模式匹配
            if sig.payload_pattern and sig.payload_pattern not in payload:
                continue

            # Payload正则匹配
            if sig.payload_regex:
                try:
                    if not re.search(sig.payload_regex.encode(), payload, re.IGNORECASE):
                        continue
                except:
                    continue

            # 匹配成功
            sig.match_count += 1
            sig.last_seen = datetime.now()

            # 更新缓存
            if len(self._match_cache) < self._cache_max_size:
                self._match_cache[packet_hash] = sig_id

            return sig

        # 未匹配
        if len(self._match_cache) < self._cache_max_size:
            self._match_cache[packet_hash] = None

        return None

    def detect_malware_payload(self, payload: bytes) -> Optional[MalwareSignature]:
        """
        检测木马payload

        使用哈希+模式匹配双重检测
        """
        if len(payload) < 4:
            return None

        # 1. 快速哈希匹配（完整payload）
        payload_hash = hashlib.sha256(payload).hexdigest()
        if payload_hash in self.payload_hash_index:
            malware_id = self.payload_hash_index[payload_hash]
            sig = self.malware_signatures[malware_id]
            sig.detection_count += 1
            sig.last_detected = datetime.now()
            return sig

        # 2. 模式匹配（特征字节串）
        for malware_id, sig in self.malware_signatures.items():
            if sig.payload_pattern in payload:
                sig.detection_count += 1
                sig.last_detected = datetime.now()
                return sig

        return None

    def parse_ipsec_packet(self, payload: bytes) -> Optional[IPSecSignature]:
        """
        解析IPSec数据包

        识别ESP和AH协议
        """
        if len(payload) < 8:
            return None

        try:
            # 尝试解析ESP头部
            # ESP格式: SPI(4字节) + Sequence(4字节) + Payload(变长)
            spi, sequence = struct.unpack('!II', payload[:8])

            # 检查SPI是否在已知范围（0是保留值）
            if spi == 0:
                return None

            # 检查是否已存在
            if spi in self.ipsec_signatures:
                return self.ipsec_signatures[spi]

            # 创建新签名
            sig = IPSecSignature(
                spi=spi,
                protocol="ESP",  # 假设为ESP（最常见）
                is_tunnel_mode=True,
            )

            # 检测异常
            # 异常1：序列号跳跃过大（可能重放攻击）
            if spi in self.ipsec_signatures:
                prev_sig = self.ipsec_signatures[spi]
                # 这里需要追踪序列号，暂时省略

            # 异常2：异常padding（payload末尾）
            if len(payload) > 8:
                # ESP trailer在末尾，检查padding长度
                pad_length = payload[-2] if len(payload) >= 2 else 0
                if pad_length > 255:
                    sig.abnormal_padding = True

            self.ipsec_signatures[spi] = sig
            return sig

        except struct.error:
            return None

    def report_false_positive(self, signature_id: str):
        """报告误报"""
        if signature_id in self.attack_signatures:
            sig = self.attack_signatures[signature_id]
            sig.false_positive_count += 1
            logger.warning(f"签名 {signature_id} 误报，当前可信度={sig.confidence():.2%}")

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_signatures": len(self.attack_signatures),
            "total_malware_signatures": len(self.malware_signatures),
            "total_ipsec_sessions": len(self.ipsec_signatures),
            "cache_size": len(self._match_cache),
            "false_positive_rate": self.adaptive_matrix.false_positive_rate,
            "top_matched_signatures": sorted(
                [(sig_id, sig.match_count) for sig_id, sig in self.attack_signatures.items()],
                key=lambda x: x[1],
                reverse=True
            )[:10]
        }


# ============================================================================
# 轻量级特征提取器（混合模型组件）
# ============================================================================

class LightweightFeatureExtractor:
    """
    轻量级流量特征提取器

    不使用深度学习，仅统计特征 + 启发式规则
    推理时间 < 10ms
    """

    @staticmethod
    def extract_packet_features(payload: bytes, protocol: str, packet_size: int) -> Dict[str, float]:
        """
        提取数据包特征向量

        返回归一化的特征字典，供SOSA使用
        """
        features = {}

        # 1. 熵（随机性）
        if len(payload) > 0:
            byte_counts = [payload.count(bytes([i])) for i in range(256)]
            total = sum(byte_counts)
            entropy = 0.0
            for count in byte_counts:
                if count > 0:
                    p = count / total
                    entropy -= p * (p ** 0.5)  # 简化版香农熵
            features['entropy'] = min(1.0, entropy / 8.0)  # 归一化到[0,1]
        else:
            features['entropy'] = 0.0

        # 2. ASCII比例（文本 vs 二进制）
        if len(payload) > 0:
            ascii_count = sum(1 for b in payload if 32 <= b <= 126)
            features['ascii_ratio'] = ascii_count / len(payload)
        else:
            features['ascii_ratio'] = 0.0

        # 3. NULL字节比例
        if len(payload) > 0:
            null_count = payload.count(b'\x00')
            features['null_ratio'] = null_count / len(payload)
        else:
            features['null_ratio'] = 0.0

        # 4. 包大小（归一化）
        features['packet_size_norm'] = min(1.0, packet_size / 1500.0)  # MTU=1500

        # 5. 协议编码
        protocol_map = {'TCP': 0.33, 'UDP': 0.66, 'ICMP': 1.0}
        features['protocol_encoded'] = protocol_map.get(protocol, 0.0)

        # 6. Payload前4字节魔术数（常见协议识别）
        if len(payload) >= 4:
            magic = payload[:4]
            # HTTP
            if magic.startswith(b'HTTP') or magic.startswith(b'GET ') or magic.startswith(b'POST'):
                features['is_http'] = 1.0
            # TLS/SSL
            elif magic[0] in [0x16, 0x14, 0x15, 0x17]:
                features['is_tls'] = 1.0
            # DNS
            elif protocol == 'UDP' and len(payload) >= 12:
                features['is_dns'] = 1.0
            else:
                features['is_http'] = 0.0
                features['is_tls'] = 0.0
                features['is_dns'] = 0.0
        else:
            features['is_http'] = 0.0
            features['is_tls'] = 0.0
            features['is_dns'] = 0.0

        return features

    @staticmethod
    def is_suspicious(features: Dict[str, float]) -> Tuple[bool, float]:
        """
        启发式规则判断是否可疑

        Returns:
            (is_suspicious, suspicion_score)
        """
        score = 0.0

        # 规则1：高熵 + 二进制内容 → 可能加密或shellcode
        if features['entropy'] > 0.7 and features['ascii_ratio'] < 0.3:
            score += 0.3

        # 规则2：大量NULL字节 → 可能padding攻击或缓冲区溢出
        if features['null_ratio'] > 0.5:
            score += 0.2

        # 规则3：小包高熵 → 可能扫描探测
        if features['packet_size_norm'] < 0.1 and features['entropy'] > 0.6:
            score += 0.2

        # 规则4：非标准协议（不是HTTP/TLS/DNS）
        if features['is_http'] == 0 and features['is_tls'] == 0 and features['is_dns'] == 0:
            score += 0.15

        # 规则5：ICMP大包 → 可能ICMP隧道
        if features['protocol_encoded'] == 1.0 and features['packet_size_norm'] > 0.5:
            score += 0.25

        return score > 0.4, score


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=== HIDRS攻击特征库测试 ===\n")

    # 创建数据库
    db = AttackSignatureDatabase()

    # 测试1：DDoS检测
    print("测试1：SYN Flood检测")
    sig = db.match_packet(
        src_ip="192.168.1.100",
        dst_ip="10.0.0.1",
        src_port=12345,
        dst_port=80,
        protocol="TCP",
        payload=b"\x00\x00\x00\x00",
        packet_rate=1500.0,  # 超过阈值
        packet_size=52
    )
    if sig:
        print(f"✓ 检测到攻击: {sig.attack_type} (严重度={sig.severity})")
    else:
        print("✗ 未检测到攻击")

    # 测试2：SQL注入检测
    print("\n测试2：SQL注入检测")
    sig = db.match_packet(
        src_ip="1.2.3.4",
        dst_ip="10.0.0.1",
        src_port=54321,
        dst_port=443,
        protocol="TCP",
        payload=b"GET /login.php?id=1' OR 1=1-- HTTP/1.1",
        packet_rate=1.0,
        packet_size=200
    )
    if sig:
        print(f"✓ 检测到攻击: {sig.attack_type} (严重度={sig.severity})")
    else:
        print("✗ 未检测到攻击")

    # 测试3：木马payload检测
    print("\n测试3：木马payload检测")
    malware = db.detect_malware_payload(b"eval(base64_decode('malicious_code'))")
    if malware:
        print(f"✓ 检测到木马: {malware.malware_family} (ID={malware.malware_id})")
    else:
        print("✗ 未检测到木马")

    # 测试4：IPSec解析
    print("\n测试4：IPSec数据包解析")
    ipsec_payload = struct.pack('!II', 0x12345678, 100) + b"\x00" * 64
    ipsec_sig = db.parse_ipsec_packet(ipsec_payload)
    if ipsec_sig:
        print(f"✓ 检测到IPSec: SPI=0x{ipsec_sig.spi:08x}, 协议={ipsec_sig.protocol}")
    else:
        print("✗ 未检测到IPSec")

    # 测试5：轻量级特征提取
    print("\n测试5：轻量级特征提取")
    extractor = LightweightFeatureExtractor()
    features = extractor.extract_packet_features(
        payload=b"\x90" * 100,  # NOP sled (shellcode特征)
        protocol="TCP",
        packet_size=128
    )
    is_sus, score = extractor.is_suspicious(features)
    print(f"可疑分数: {score:.2f}")
    print(f"特征: 熵={features['entropy']:.2f}, ASCII比={features['ascii_ratio']:.2f}")
    if is_sus:
        print("✓ 判定为可疑流量")
    else:
        print("✗ 判定为正常流量")

    # 测试6：自适应转移矩阵
    print("\n测试6：自适应状态转移学习")
    matrix = db.adaptive_matrix

    # 模拟观测
    matrix.update_observation(0, 1, is_false_positive=False)  # 正常→可疑
    matrix.update_observation(1, 2, is_false_positive=False)  # 可疑→确认
    matrix.update_observation(1, 0, is_false_positive=True)   # 可疑→正常（误报）

    prob_01 = matrix.get_transition_probability(0, 1)
    prob_10 = matrix.get_transition_probability(1, 0)
    print(f"P(正常→可疑) = {prob_01:.3f}")
    print(f"P(可疑→正常) = {prob_10:.3f}")
    print(f"当前误报率: {matrix.false_positive_rate:.2%}")

    # 统计
    print("\n=== 特征库统计 ===")
    stats = db.get_statistics()
    print(f"攻击签名总数: {stats['total_signatures']}")
    print(f"木马签名总数: {stats['total_malware_signatures']}")
    print(f"缓存大小: {stats['cache_size']}")
    print(f"Top 3匹配签名:")
    for sig_id, count in stats['top_matched_signatures'][:3]:
        print(f"  - {sig_id}: {count} 次")
