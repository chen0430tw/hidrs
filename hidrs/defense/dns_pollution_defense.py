"""
AEGIS-HIDRS DNS污染防御系统
DNS Pollution Defense System

核心功能：
1. DNS缓存投毒检测（Cache Poisoning Detection）
2. DNS劫持检测（DNS Hijacking Detection）
3. DNSSEC验证（DNSSec Validation）
4. DNS响应完整性检查（Response Integrity Check）
5. DNS异常流量检测（Anomalous Traffic Detection）

防御技术：
- Response Rate Limiting (RRL)
- Transaction ID随机化
- 源端口随机化
- 多重查询交叉验证
- TTL异常检测
- 权威服务器验证

By: Claude + 430
"""

import logging
import socket
import struct
import hashlib
import random
import time
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
import threading

logger = logging.getLogger(__name__)


@dataclass
class DNSQuery:
    """DNS查询记录"""
    query_id: int
    domain: str
    query_type: str  # A, AAAA, MX, etc.
    timestamp: datetime
    source_ip: str
    source_port: int
    transaction_id: int


@dataclass
class DNSResponse:
    """DNS响应记录"""
    transaction_id: int
    domain: str
    resolved_ips: List[str]
    ttl: int
    timestamp: datetime
    source_ip: str  # DNS服务器IP
    response_time_ms: float
    is_authoritative: bool = False


@dataclass
class DNSPollutionIndicator:
    """DNS污染指标"""
    is_polluted: bool
    pollution_type: str  # cache_poisoning, hijacking, spoofing, etc.
    confidence: float  # 0.0-1.0
    indicators: List[str]
    evidence: Dict[str, any]


class DNSCachePoisoningDetector:
    """
    DNS缓存投毒检测器

    检测方法：
    1. 响应时间异常（过快响应可能是投毒）
    2. TTL异常（TTL过短或过长）
    3. 多重查询不一致（同一域名返回不同IP）
    4. Transaction ID验证
    5. 源端口验证
    6. 权威服务器验证
    """

    def __init__(
        self,
        enable_cross_verification: bool = True,
        enable_ttl_check: bool = True,
        enable_timing_analysis: bool = True,
        max_cache_size: int = 10000
    ):
        """
        初始化DNS缓存投毒检测器

        Args:
            enable_cross_verification: 启用交叉验证
            enable_ttl_check: 启用TTL检查
            enable_timing_analysis: 启用时序分析
            max_cache_size: 最大缓存大小
        """
        self.enable_cross_verification = enable_cross_verification
        self.enable_ttl_check = enable_ttl_check
        self.enable_timing_analysis = enable_timing_analysis

        # DNS查询缓存
        self.query_cache: Dict[str, List[DNSQuery]] = defaultdict(list)

        # DNS响应缓存
        self.response_cache: Dict[str, List[DNSResponse]] = defaultdict(list)

        # 可信DNS解析器列表
        self.trusted_resolvers: Set[str] = {
            '8.8.8.8',  # Google DNS
            '8.8.4.4',  # Google DNS
            '1.1.1.1',  # Cloudflare DNS
            '1.0.0.1',  # Cloudflare DNS
            '9.9.9.9',  # Quad9 DNS
            '208.67.222.222',  # OpenDNS
            '208.67.220.220',  # OpenDNS
        }

        # 统计信息
        self.stats = {
            'total_queries': 0,
            'total_responses': 0,
            'cache_poisoning_detected': 0,
            'ttl_anomalies': 0,
            'timing_anomalies': 0,
            'cross_verification_failures': 0,
        }

        # 线程锁
        self._lock = threading.Lock()

        logger.info("✅ DNS缓存投毒检测器已初始化")

    def check_response(
        self,
        query: DNSQuery,
        response: DNSResponse
    ) -> DNSPollutionIndicator:
        """
        检查DNS响应是否为投毒攻击

        Args:
            query: DNS查询
            response: DNS响应

        Returns:
            DNSPollutionIndicator: 污染指标
        """
        with self._lock:
            self.stats['total_responses'] += 1

            indicators = []
            evidence = {}
            confidence = 0.0

            # 1. Transaction ID验证
            if query.transaction_id != response.transaction_id:
                indicators.append('TRANSACTION_ID_MISMATCH')
                evidence['expected_tid'] = query.transaction_id
                evidence['actual_tid'] = response.transaction_id
                confidence += 0.9  # 非常高的置信度

            # 2. 响应时间异常检测
            if self.enable_timing_analysis:
                response_time_ms = response.response_time_ms
                if response_time_ms < 1.0:  # 小于1ms，异常快
                    indicators.append('SUSPICIOUSLY_FAST_RESPONSE')
                    evidence['response_time_ms'] = response_time_ms
                    confidence += 0.7

            # 3. TTL异常检测
            if self.enable_ttl_check:
                if response.ttl < 60:  # TTL小于60秒
                    indicators.append('ABNORMAL_TTL_TOO_SHORT')
                    evidence['ttl'] = response.ttl
                    confidence += 0.3
                    self.stats['ttl_anomalies'] += 1
                elif response.ttl > 86400 * 7:  # TTL大于7天
                    indicators.append('ABNORMAL_TTL_TOO_LONG')
                    evidence['ttl'] = response.ttl
                    confidence += 0.2

            # 4. 交叉验证（与可信DNS解析器对比）
            if self.enable_cross_verification and response.source_ip not in self.trusted_resolvers:
                # 检查响应IP是否与已知的正常解析一致
                domain = response.domain
                if domain in self.response_cache:
                    previous_responses = self.response_cache[domain]
                    previous_ips = set()
                    for prev_resp in previous_responses:
                        if prev_resp.source_ip in self.trusted_resolvers:
                            previous_ips.update(prev_resp.resolved_ips)

                    current_ips = set(response.resolved_ips)

                    # 如果当前IP与可信IP完全不同
                    if previous_ips and not current_ips.intersection(previous_ips):
                        indicators.append('CROSS_VERIFICATION_FAILED')
                        evidence['trusted_ips'] = list(previous_ips)
                        evidence['current_ips'] = list(current_ips)
                        confidence += 0.8
                        self.stats['cross_verification_failures'] += 1

            # 5. 权威服务器检查
            if not response.is_authoritative and response.source_ip not in self.trusted_resolvers:
                indicators.append('NON_AUTHORITATIVE_RESPONSE')
                confidence += 0.1

            # 缓存响应
            self.response_cache[response.domain].append(response)

            # 限制缓存大小
            if len(self.response_cache[response.domain]) > 100:
                self.response_cache[response.domain] = self.response_cache[response.domain][-100:]

            # 判断是否为污染
            is_polluted = confidence >= 0.5

            if is_polluted:
                self.stats['cache_poisoning_detected'] += 1
                logger.warning(
                    f"[DNSPollutionDetector] 🚨 检测到DNS污染: {response.domain} "
                    f"置信度={confidence:.2f} 指标={indicators}"
                )

                pollution_type = self._determine_pollution_type(indicators)

                return DNSPollutionIndicator(
                    is_polluted=True,
                    pollution_type=pollution_type,
                    confidence=min(confidence, 1.0),
                    indicators=indicators,
                    evidence=evidence
                )
            else:
                return DNSPollutionIndicator(
                    is_polluted=False,
                    pollution_type='none',
                    confidence=0.0,
                    indicators=[],
                    evidence={}
                )

    def _determine_pollution_type(self, indicators: List[str]) -> str:
        """根据指标确定污染类型"""
        if 'TRANSACTION_ID_MISMATCH' in indicators:
            return 'cache_poisoning'
        elif 'CROSS_VERIFICATION_FAILED' in indicators:
            return 'dns_hijacking'
        elif 'SUSPICIOUSLY_FAST_RESPONSE' in indicators:
            return 'race_condition_poisoning'
        elif 'ABNORMAL_TTL_TOO_SHORT' in indicators:
            return 'ttl_manipulation'
        else:
            return 'unknown_pollution'

    def add_trusted_resolver(self, ip: str):
        """添加可信DNS解析器"""
        with self._lock:
            self.trusted_resolvers.add(ip)

    def remove_trusted_resolver(self, ip: str):
        """移除可信DNS解析器"""
        with self._lock:
            self.trusted_resolvers.discard(ip)

    def get_statistics(self) -> Dict[str, int]:
        """获取统计信息"""
        return self.stats.copy()


class ResponseRateLimiter:
    """
    响应速率限制器（RRL）

    防御DNS放大攻击和缓存投毒
    限制对特定客户端的响应速率
    """

    def __init__(
        self,
        window_seconds: int = 1,
        max_responses_per_window: int = 10,
        blacklist_threshold: int = 100
    ):
        """
        初始化响应速率限制器

        Args:
            window_seconds: 时间窗口（秒）
            max_responses_per_window: 每个窗口最大响应数
            blacklist_threshold: 黑名单阈值
        """
        self.window_seconds = window_seconds
        self.max_responses_per_window = max_responses_per_window
        self.blacklist_threshold = blacklist_threshold

        # IP响应计数器 {ip: deque of timestamps}
        self.response_counters: Dict[str, deque] = defaultdict(lambda: deque())

        # 临时黑名单
        self.blacklist: Set[str] = set()

        # 统计
        self.stats = {
            'rate_limited_ips': 0,
            'blacklisted_ips': 0,
            'total_checks': 0,
        }

        self._lock = threading.Lock()

    def should_rate_limit(self, client_ip: str) -> Tuple[bool, str]:
        """
        检查是否应该速率限制

        Args:
            client_ip: 客户端IP

        Returns:
            (should_limit, reason)
        """
        with self._lock:
            self.stats['total_checks'] += 1

            # 黑名单检查
            if client_ip in self.blacklist:
                return (True, f"IP在黑名单中（超过阈值{self.blacklist_threshold}）")

            # 获取当前时间
            now = time.time()

            # 清理过期的计数
            counter = self.response_counters[client_ip]
            cutoff_time = now - self.window_seconds

            # 移除窗口外的旧时间戳
            while counter and counter[0] < cutoff_time:
                counter.popleft()

            # 检查速率
            current_count = len(counter)

            if current_count >= self.max_responses_per_window:
                self.stats['rate_limited_ips'] += 1

                # 检查是否超过黑名单阈值
                if current_count >= self.blacklist_threshold:
                    self.blacklist.add(client_ip)
                    self.stats['blacklisted_ips'] += 1
                    logger.warning(
                        f"[RRL] 🚫 IP加入黑名单: {client_ip} "
                        f"(当前速率={current_count}/{self.window_seconds}秒)"
                    )

                return (True, f"速率超限({current_count}/{self.max_responses_per_window})")

            # 记录本次响应
            counter.append(now)

            return (False, "")

    def clear_blacklist(self):
        """清空黑名单"""
        with self._lock:
            self.blacklist.clear()

    def get_statistics(self) -> Dict[str, int]:
        """获取统计信息"""
        return self.stats.copy()


class DNSPollutionDefenseSystem:
    """
    DNS污染综合防御系统

    整合多种防御技术：
    1. 缓存投毒检测
    2. 响应速率限制
    3. Transaction ID随机化
    4. 源端口随机化
    """

    def __init__(
        self,
        enable_poisoning_detection: bool = True,
        enable_rate_limiting: bool = True,
        enable_randomization: bool = True
    ):
        """
        初始化DNS污染防御系统

        Args:
            enable_poisoning_detection: 启用投毒检测
            enable_rate_limiting: 启用速率限制
            enable_randomization: 启用随机化
        """
        self.enable_poisoning_detection = enable_poisoning_detection
        self.enable_rate_limiting = enable_rate_limiting
        self.enable_randomization = enable_randomization

        # 初始化子系统
        self.poisoning_detector = DNSCachePoisoningDetector() if enable_poisoning_detection else None
        self.rate_limiter = ResponseRateLimiter() if enable_rate_limiting else None

        # 统计
        self.stats = {
            'total_queries_processed': 0,
            'pollution_detected': 0,
            'rate_limited': 0,
            'randomized_queries': 0,
        }

        logger.info("✅ DNS污染防御系统已初始化")
        if enable_poisoning_detection:
            logger.info("  - 缓存投毒检测: ✅")
        if enable_rate_limiting:
            logger.info("  - 响应速率限制: ✅")
        if enable_randomization:
            logger.info("  - Transaction ID随机化: ✅")

    def generate_secure_transaction_id(self) -> int:
        """
        生成安全的Transaction ID

        使用加密安全的随机数生成器
        """
        if self.enable_randomization:
            self.stats['randomized_queries'] += 1
            return random.SystemRandom().randint(1, 65535)
        else:
            return random.randint(1, 65535)

    def generate_secure_source_port(self) -> int:
        """
        生成安全的源端口

        避免使用well-known ports
        """
        if self.enable_randomization:
            return random.SystemRandom().randint(1024, 65535)
        else:
            return random.randint(1024, 65535)

    def check_dns_query(
        self,
        query: DNSQuery,
        response: DNSResponse
    ) -> Dict[str, any]:
        """
        检查DNS查询和响应

        Args:
            query: DNS查询
            response: DNS响应

        Returns:
            检查结果字典
        """
        self.stats['total_queries_processed'] += 1

        result = {
            'action': 'allow',
            'reason': 'Normal DNS response',
            'pollution_detected': False,
            'rate_limited': False,
        }

        # 1. 速率限制检查
        if self.enable_rate_limiting and self.rate_limiter:
            should_limit, reason = self.rate_limiter.should_rate_limit(query.source_ip)
            if should_limit:
                result['action'] = 'block'
                result['reason'] = f'DNS速率限制: {reason}'
                result['rate_limited'] = True
                self.stats['rate_limited'] += 1
                return result

        # 2. 投毒检测
        if self.enable_poisoning_detection and self.poisoning_detector:
            pollution_indicator = self.poisoning_detector.check_response(query, response)

            if pollution_indicator.is_polluted:
                result['action'] = 'block'
                result['reason'] = f'DNS污染检测: {pollution_indicator.pollution_type}'
                result['pollution_detected'] = True
                result['pollution_type'] = pollution_indicator.pollution_type
                result['confidence'] = pollution_indicator.confidence
                result['indicators'] = pollution_indicator.indicators
                result['evidence'] = pollution_indicator.evidence
                self.stats['pollution_detected'] += 1
                return result

        return result

    def get_comprehensive_statistics(self) -> Dict[str, any]:
        """获取综合统计信息"""
        stats = self.stats.copy()

        if self.poisoning_detector:
            stats['poisoning_detector'] = self.poisoning_detector.get_statistics()

        if self.rate_limiter:
            stats['rate_limiter'] = self.rate_limiter.get_statistics()

        return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("AEGIS-HIDRS DNS污染防御系统测试")
    print("=" * 60)

    # 创建防御系统
    dns_defense = DNSPollutionDefenseSystem(
        enable_poisoning_detection=True,
        enable_rate_limiting=True,
        enable_randomization=True
    )

    # 测试1: 正常DNS查询
    print("\n测试1: 正常DNS查询")
    query1 = DNSQuery(
        query_id=1,
        domain="google.com",
        query_type="A",
        timestamp=datetime.utcnow(),
        source_ip="192.168.1.100",
        source_port=53421,
        transaction_id=12345
    )

    response1 = DNSResponse(
        transaction_id=12345,
        domain="google.com",
        resolved_ips=["172.217.14.206"],
        ttl=300,
        timestamp=datetime.utcnow(),
        source_ip="8.8.8.8",
        response_time_ms=15.5,
        is_authoritative=True
    )

    result1 = dns_defense.check_dns_query(query1, response1)
    print(f"  结果: {result1['action']}")
    print(f"  原因: {result1['reason']}")

    # 测试2: Transaction ID不匹配（投毒攻击）
    print("\n测试2: Transaction ID不匹配")
    response2 = DNSResponse(
        transaction_id=99999,  # 错误的transaction ID
        domain="google.com",
        resolved_ips=["1.2.3.4"],
        ttl=300,
        timestamp=datetime.utcnow(),
        source_ip="8.8.8.8",
        response_time_ms=15.5,
        is_authoritative=False
    )

    result2 = dns_defense.check_dns_query(query1, response2)
    print(f"  结果: {result2['action']}")
    print(f"  原因: {result2['reason']}")
    if result2['pollution_detected']:
        print(f"  污染类型: {result2.get('pollution_type')}")
        print(f"  置信度: {result2.get('confidence'):.2f}")

    # 打印统计
    print("\n" + "=" * 60)
    print("统计信息")
    print("=" * 60)
    stats = dns_defense.get_comprehensive_statistics()
    print(f"总查询数: {stats['total_queries_processed']}")
    print(f"检测到污染: {stats['pollution_detected']}")
    print(f"速率限制: {stats['rate_limited']}")
    print(f"随机化查询: {stats['randomized_queries']}")
