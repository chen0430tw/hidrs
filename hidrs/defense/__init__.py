"""
HIDRS自我保护模块
Self-Defense System for HIDRS

基于GFW技术的反向应用，保护HIDRS免受攻击
包含DNS劫持防御和反劫持系统（物理攻击无效化）
"""

from .inverse_gfw import (
    HIDRSFirewall,
    PacketAnalyzer,
    ActiveProber,
    HLIGAnomalyDetector,
    IPReputationSystem,
    SYNCookieDefense,
    TarpitDefense,
    TrafficReflector,
    ThreatLevel,
    ConnectionProfile
)

from .dns_defense import (
    HIDRSDNSDefense,
    DNSSECValidator,
    TrustedDNSPool,
    DNSCache,
    DNSHijackingDetector,
    ReverseDNSHijacker,
    DNSRecord,
    DNSAnomalySignature
)

__all__ = [
    # 反向GFW防火墙
    'HIDRSFirewall',
    'PacketAnalyzer',
    'ActiveProber',
    'HLIGAnomalyDetector',
    'IPReputationSystem',
    'SYNCookieDefense',
    'TarpitDefense',
    'TrafficReflector',
    'ThreatLevel',
    'ConnectionProfile',

    # DNS防御系统
    'HIDRSDNSDefense',
    'DNSSECValidator',
    'TrustedDNSPool',
    'DNSCache',
    'DNSHijackingDetector',
    'ReverseDNSHijacker',
    'DNSRecord',
    'DNSAnomalySignature'
]
