"""
HIDRS快速过滤清单系统
Fast Filter Lists for Quick Packet Filtering

核心功能：
1. 关键词黑名单/白名单（Trie树）
2. DNS域名过滤（哈希表+通配符）
3. IP/IPv6地址过滤（CIDR范围匹配）
4. SSL证书指纹过滤
5. Tunnel协议检测
6. VoIP协议标记
7. 性能优化：O(1)查表，减少记忆检索负担

By: Claude + 430
"""

import logging
import ipaddress
import re
import hashlib
import socket
from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
import threading

logger = logging.getLogger(__name__)


# ============================================================================
# Trie树（前缀树）用于关键词快速匹配
# ============================================================================

class TrieNode:
    """Trie树节点"""
    def __init__(self):
        self.children: Dict[str, 'TrieNode'] = {}
        self.is_end_of_word = False
        self.keyword = None


class KeywordTrie:
    """
    关键词Trie树（前缀树）

    用于快速匹配HTTP/DNS/Payload中的敏感关键词
    时间复杂度：O(m)，m为关键词长度
    """

    def __init__(self):
        self.root = TrieNode()
        self.keyword_count = 0

    def insert(self, keyword: str):
        """插入关键词"""
        node = self.root
        for char in keyword.lower():
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]

        node.is_end_of_word = True
        node.keyword = keyword
        self.keyword_count += 1

    def search(self, text: str) -> Optional[str]:
        """
        在文本中搜索关键词

        返回第一个匹配的关键词，如果没有则返回None
        """
        text_lower = text.lower()
        for i in range(len(text_lower)):
            node = self.root
            j = i
            while j < len(text_lower) and text_lower[j] in node.children:
                node = node.children[text_lower[j]]
                if node.is_end_of_word:
                    return node.keyword
                j += 1
        return None

    def search_all(self, text: str) -> List[str]:
        """
        在文本中搜索所有关键词

        返回所有匹配的关键词列表
        """
        matches = []
        text_lower = text.lower()
        for i in range(len(text_lower)):
            node = self.root
            j = i
            while j < len(text_lower) and text_lower[j] in node.children:
                node = node.children[text_lower[j]]
                if node.is_end_of_word:
                    matches.append(node.keyword)
                j += 1
        return matches


# ============================================================================
# 快速过滤清单数据结构
# ============================================================================

@dataclass
class FilterListEntry:
    """过滤清单条目"""
    value: str                          # 值（IP/域名/关键词等）
    list_type: str                      # 类型（blacklist/whitelist）
    category: str                       # 分类（ip/dns/keyword/ssl等）
    reason: str = ""                    # 原因
    added_time: datetime = field(default_factory=datetime.utcnow)
    hit_count: int = 0                  # 命中次数
    last_hit: Optional[datetime] = None


@dataclass
class SSLFingerprint:
    """SSL证书指纹"""
    sha256: str                         # SHA256指纹
    issuer: str = ""                    # 颁发者
    subject: str = ""                   # 主题
    is_trusted: bool = False            # 是否可信


@dataclass
class TunnelSignature:
    """隧道协议签名"""
    protocol: str                       # 协议名（Shadowsocks/V2Ray/Tor等）
    port_pattern: Set[int]              # 常见端口
    payload_pattern: bytes              # Payload特征
    description: str = ""


@dataclass
class VoIPSignature:
    """VoIP协议签名"""
    protocol: str                       # 协议名（SIP/RTP/H.323等）
    port_pattern: Set[int]              # 常见端口
    codec: str = ""                     # 编解码器
    description: str = ""


@dataclass
class SpamhausResult:
    """Spamhaus查询结果"""
    is_listed: bool                     # 是否被列入黑名单
    lists: List[str]                    # 列入的清单（SBL/XBL/PBL等）
    return_codes: List[str]             # 返回码
    severity: str = "low"               # 严重性（low/medium/high/critical）
    description: str = ""               # 描述


# ============================================================================
# 邮件安全常量
# ============================================================================

# 邮件相关端口
EMAIL_PORTS = {
    25: 'SMTP (Server-to-Server)',
    465: 'SMTPS (Implicit TLS)',
    587: 'SMTP Submission (STARTTLS)',
    993: 'IMAPS (Secure IMAP)',
    995: 'POP3S (Secure POP3)',
    110: 'POP3 (Insecure)',
    143: 'IMAP (Insecure)',
}

# 钓鱼邮件常见发件人伪装
PHISHING_SENDER_PATTERNS = [
    'noreply@paypal',  # 伪装PayPal
    'security@apple',  # 伪装Apple
    'support@amazon',  # 伪装Amazon
    'admin@microsoft',  # 伪装Microsoft
    'verify@facebook',  # 伪装Facebook
    'security@google',  # 伪装Google
    'support@netflix',  # 伪装Netflix
    'no-reply@bank',  # 伪装银行
    'admin@irs.gov',  # 伪装IRS（美国国税局）
    'agent@fbi.gov',  # 伪装FBI
]

# 钓鱼邮件常见主题行关键词
PHISHING_SUBJECT_KEYWORDS = [
    'urgent action required',
    '紧急行动',
    'verify your account',
    '验证您的账户',
    'suspended account',
    '账户已暂停',
    'unusual activity',
    '异常活动',
    'confirm your identity',
    '确认您的身份',
    'update payment',
    '更新付款',
    'tax refund',
    '税收退款',
    'prize winner',
    '中奖',
    'inheritance',
    '遗产',
    'claim your reward',
    '领取奖励',
]

# FBI/执法机构伪装特征
FBI_IMPERSONATION_PATTERNS = [
    '@fbi.gov',  # 假FBI域名
    '@ic3.gov',  # 假IC3（FBI网络犯罪投诉中心）
    '@justice.gov',  # 假司法部
    '@dhs.gov',  # 假国土安全部
    '@irs.gov',  # 假IRS
    'special agent',  # 自称特工
    'federal investigation',  # 联邦调查
    'legal action against you',  # 针对你的法律行动
    'warrant for your arrest',  # 逮捕令
    'suspended social security',  # SSN暂停
]


# ============================================================================
# Spamhaus集成
# ============================================================================

class SpamhausChecker:
    """
    Spamhaus DNSBL检查器

    使用zen.spamhaus.org进行IP信誉检查
    免费用于非商业低流量使用
    """

    # Spamhaus返回码解析
    RETURN_CODE_MAP = {
        '127.0.0.2': ('SBL', 'high', 'Spamhaus SBL - 垃圾邮件源'),
        '127.0.0.3': ('CSS', 'medium', 'Spamhaus CSS - 低信誉发件人'),
        '127.0.0.4': ('XBL', 'critical', 'Spamhaus XBL - 恶意软件/僵尸网络'),
        '127.0.0.9': ('DROP', 'critical', 'Spamhaus DROP - 防弹主机/流氓实体'),
        '127.0.0.10': ('PBL_ISP', 'low', 'Spamhaus PBL - 动态IP（ISP维护）'),
        '127.0.0.11': ('PBL_SH', 'low', 'Spamhaus PBL - 动态IP（Spamhaus维护）'),
        '127.255.255.254': ('ERROR', 'none', '查询错误 - 公共DNS解析器'),
        '127.255.255.255': ('BLOCKED', 'none', '查询被阻断 - 超出查询限制'),
    }

    def __init__(self, zone: str = 'zen.spamhaus.org', timeout: float = 2.0, enable_cache: bool = True):
        """
        初始化Spamhaus检查器

        Args:
            zone: DNSBL区域（默认zen.spamhaus.org）
            timeout: DNS查询超时时间（秒）
            enable_cache: 是否启用缓存
        """
        self.zone = zone
        self.timeout = timeout
        self.enable_cache = enable_cache
        self._cache: Dict[str, SpamhausResult] = {}
        self._cache_lock = threading.Lock()

    def check_ip(self, ip: str) -> SpamhausResult:
        """
        检查IP是否在Spamhaus黑名单中

        Args:
            ip: IP地址（IPv4）

        Returns:
            SpamhausResult对象
        """
        # 缓存检查
        if self.enable_cache and ip in self._cache:
            return self._cache[ip]

        # 验证IP格式
        try:
            ipaddress.IPv4Address(ip)
        except ValueError:
            return SpamhausResult(
                is_listed=False,
                lists=[],
                return_codes=[],
                severity='none',
                description='无效的IPv4地址'
            )

        # 反转IP地址
        reversed_ip = '.'.join(reversed(ip.split('.')))
        query_host = f"{reversed_ip}.{self.zone}"

        try:
            # DNS查询
            socket.setdefaulttimeout(self.timeout)
            answers = socket.gethostbyname_ex(query_host)

            # 解析返回码
            return_codes = answers[2] if len(answers) > 2 else []

            if not return_codes:
                # 未列入黑名单
                result = SpamhausResult(
                    is_listed=False,
                    lists=[],
                    return_codes=[],
                    severity='none',
                    description='未列入Spamhaus黑名单'
                )
            else:
                # 解析返回码
                lists = []
                descriptions = []
                max_severity = 'low'
                severity_order = {'none': 0, 'low': 1, 'medium': 2, 'high': 3, 'critical': 4}

                for code in return_codes:
                    if code in self.RETURN_CODE_MAP:
                        list_name, severity, desc = self.RETURN_CODE_MAP[code]
                        lists.append(list_name)
                        descriptions.append(desc)

                        # 更新最高严重性
                        if severity_order.get(severity, 0) > severity_order.get(max_severity, 0):
                            max_severity = severity

                result = SpamhausResult(
                    is_listed=True,
                    lists=lists,
                    return_codes=return_codes,
                    severity=max_severity,
                    description=' | '.join(descriptions) if descriptions else '列入Spamhaus黑名单'
                )

            # 更新缓存
            if self.enable_cache:
                with self._cache_lock:
                    self._cache[ip] = result

            return result

        except socket.gaierror:
            # NXDOMAIN - 未列入黑名单
            result = SpamhausResult(
                is_listed=False,
                lists=[],
                return_codes=[],
                severity='none',
                description='未列入Spamhaus黑名单'
            )

            # 缓存负面结果
            if self.enable_cache:
                with self._cache_lock:
                    self._cache[ip] = result

            return result

        except socket.timeout:
            # 查询超时
            return SpamhausResult(
                is_listed=False,
                lists=[],
                return_codes=[],
                severity='none',
                description='Spamhaus查询超时'
            )
        except Exception as e:
            # 其他错误
            logger.warning(f"Spamhaus查询失败 ({ip}): {e}")
            return SpamhausResult(
                is_listed=False,
                lists=[],
                return_codes=[],
                severity='none',
                description=f'Spamhaus查询失败: {str(e)}'
            )

    def clear_cache(self):
        """清空缓存"""
        with self._cache_lock:
            self._cache.clear()

    def get_cache_size(self) -> int:
        """获取缓存大小"""
        return len(self._cache)


# ============================================================================
# 快速过滤清单系统
# ============================================================================

class FastFilterLists:
    """
    快速过滤清单系统

    性能优化：
    - IP地址：哈希表 O(1) + CIDR范围匹配
    - DNS域名：哈希表 O(1) + 通配符
    - 关键词：Trie树 O(m)
    - SSL指纹：哈希表 O(1)

    优先级：
    1. 白名单优先（立即放行）
    2. 黑名单次之（立即阻断）
    3. 未命中则继续深度检测
    """

    def __init__(self):
        # ========== IP地址过滤 ==========
        self.ip_blacklist: Set[str] = set()                     # IP黑名单（精确匹配）
        self.ip_whitelist: Set[str] = set()                     # IP白名单
        self.ip_greylist: Set[str] = set()                      # IP灰名单（需额外验证）
        self.ip_blacklist_networks: List[ipaddress.IPv4Network] = []  # CIDR黑名单
        self.ip_whitelist_networks: List[ipaddress.IPv4Network] = []  # CIDR白名单
        self.ip_greylist_networks: List[ipaddress.IPv4Network] = []   # CIDR灰名单

        # IPv6支持
        self.ipv6_blacklist: Set[str] = set()
        self.ipv6_whitelist: Set[str] = set()
        self.ipv6_greylist: Set[str] = set()
        self.ipv6_blacklist_networks: List[ipaddress.IPv6Network] = []
        self.ipv6_whitelist_networks: List[ipaddress.IPv6Network] = []
        self.ipv6_greylist_networks: List[ipaddress.IPv6Network] = []

        # ========== DNS域名过滤 ==========
        self.dns_blacklist: Set[str] = set()                    # 域名黑名单
        self.dns_whitelist: Set[str] = set()                    # 域名白名单
        self.dns_greylist: Set[str] = set()                     # 域名灰名单（可疑域名）
        self.dns_wildcard_blacklist: List[str] = []             # 通配符黑名单（*.example.com）
        self.dns_wildcard_whitelist: List[str] = []             # 通配符白名单
        self.dns_wildcard_greylist: List[str] = []              # 通配符灰名单

        # ========== 关键词过滤 ==========
        self.keyword_blacklist_trie = KeywordTrie()             # 关键词黑名单（Trie树）
        self.keyword_whitelist_trie = KeywordTrie()             # 关键词白名单
        self.keyword_greylist_trie = KeywordTrie()              # 关键词灰名单（需深度检测）

        # ========== SSL证书指纹 ==========
        self.ssl_blacklist: Dict[str, SSLFingerprint] = {}      # SSL黑名单（SHA256 -> 指纹）
        self.ssl_whitelist: Dict[str, SSLFingerprint] = {}      # SSL白名单
        self.ssl_greylist: Dict[str, SSLFingerprint] = {}       # SSL灰名单（可疑证书）

        # ========== Tunnel检测 ==========
        self.tunnel_signatures: Dict[str, TunnelSignature] = {} # Tunnel签名

        # ========== VoIP协议 ==========
        self.voip_signatures: Dict[str, VoIPSignature] = {}     # VoIP签名

        # ========== Spamhaus集成 ==========
        self.spamhaus_enabled = True
        try:
            self.spamhaus = SpamhausChecker(timeout=2.0, enable_cache=True)
        except Exception as e:
            logger.warning(f"Spamhaus初始化失败: {e}，已禁用")
            self.spamhaus_enabled = False
            self.spamhaus = None

        # ========== 邮件安全 ==========
        self.email_phishing_patterns = PHISHING_SENDER_PATTERNS
        self.email_subject_keywords = PHISHING_SUBJECT_KEYWORDS
        self.fbi_patterns = FBI_IMPERSONATION_PATTERNS

        # ========== 灰名单策略配置 ==========
        self.greylist_actions = {
            'captcha': 'CAPTCHA验证',              # CAPTCHA人机验证
            'rate_limit': '限速访问',              # 降低速率限制
            'deep_inspect': '深度DPI检测',         # 启用深度包检测
            'dns_verify': 'DNS额外验证',          # 额外DNS验证
            'ssl_inspect': 'SSL证书深度检查',     # SSL证书详细检查
            'tarpit': 'Tarpit延迟',              # Tarpit延迟响应
            'monitor': '监控观察',                 # 仅记录，不阻断
        }

        # ========== 统计信息 ==========
        self.stats = {
            'ip_blacklist_hits': 0,
            'ip_whitelist_hits': 0,
            'ip_greylist_hits': 0,
            'dns_blacklist_hits': 0,
            'dns_whitelist_hits': 0,
            'dns_greylist_hits': 0,
            'keyword_blacklist_hits': 0,
            'keyword_whitelist_hits': 0,
            'keyword_greylist_hits': 0,
            'ssl_blacklist_hits': 0,
            'ssl_whitelist_hits': 0,
            'ssl_greylist_hits': 0,
            'tunnel_detections': 0,
            'voip_detections': 0,
            'total_checks': 0,
            'phishing_prevented': 0,  # 防止的钓鱼攻击数
            'spamhaus_hits': 0,  # Spamhaus黑名单命中
            'email_phishing_prevented': 0,  # 邮件钓鱼阻止数
            'fbi_impersonation_blocked': 0,  # FBI伪装阻止数
        }

        # 线程锁
        self._lock = threading.Lock()

        # 加载预定义规则
        self._load_builtin_rules()

        logger.info("✅ FastFilterLists 初始化完成")
        if self.spamhaus_enabled:
            logger.info("  - Spamhaus DNSBL: 已启用")

    def _load_builtin_rules(self):
        """加载内置规则"""

        # ========== 内置IP黑名单 ==========
        # 私有地址段（测试用）
        self.add_ip_blacklist("0.0.0.0/8", reason="保留地址")
        self.add_ip_blacklist("127.0.0.0/8", reason="回环地址")
        self.add_ip_blacklist("169.254.0.0/16", reason="链路本地地址")

        # 已知恶意IP示例（实际应从威胁情报获取）
        self.add_ip_blacklist("192.0.2.0/24", reason="文档示例（TEST-NET-1）")

        # ========== 内置DNS黑名单 ==========
        # 恶意域名示例
        self.add_dns_blacklist("malware.example.com", reason="已知恶意域名")
        self.add_dns_blacklist("phishing.example.org", reason="钓鱼网站")

        # 通配符黑名单
        self.add_dns_wildcard_blacklist("*.malicious.com", reason="恶意域名家族")

        # ========== 内置关键词黑名单 ==========
        # SQL注入关键词
        for keyword in ["union select", "drop table", "' or '1'='1", "exec(", "base64_decode"]:
            self.add_keyword_blacklist(keyword, reason="SQL注入/代码执行")

        # Webshell关键词
        for keyword in ["eval(", "assert(", "system(", "exec(", "passthru("]:
            self.add_keyword_blacklist(keyword, reason="Webshell特征")

        # ========== Tunnel签名 ==========
        # Shadowsocks
        self.tunnel_signatures['shadowsocks'] = TunnelSignature(
            protocol='Shadowsocks',
            port_pattern={8388, 8389, 1080, 1081},
            payload_pattern=b'\x05\x01',  # SOCKS5握手
            description='Shadowsocks代理'
        )

        # V2Ray/VMess
        self.tunnel_signatures['v2ray'] = TunnelSignature(
            protocol='V2Ray',
            port_pattern={10086, 8080, 443},
            payload_pattern=b'',  # VMess使用加密，无明显特征
            description='V2Ray/VMess代理'
        )

        # Tor
        self.tunnel_signatures['tor'] = TunnelSignature(
            protocol='Tor',
            port_pattern={9001, 9030, 9050, 9051},
            payload_pattern=b'\x16\x03',  # TLS握手
            description='Tor洋葱网络'
        )

        # SSH Tunnel
        self.tunnel_signatures['ssh_tunnel'] = TunnelSignature(
            protocol='SSH Tunnel',
            port_pattern={22, 2222},
            payload_pattern=b'SSH-',
            description='SSH隧道'
        )

        # ========== VoIP签名 ==========
        # SIP (Session Initiation Protocol)
        self.voip_signatures['sip'] = VoIPSignature(
            protocol='SIP',
            port_pattern={5060, 5061},
            codec='G.711/G.729',
            description='SIP信令协议'
        )

        # RTP (Real-time Transport Protocol)
        self.voip_signatures['rtp'] = VoIPSignature(
            protocol='RTP',
            port_pattern=set(range(10000, 20000)),  # RTP动态端口范围
            codec='PCMU/PCMA',
            description='RTP媒体流'
        )

        # H.323
        self.voip_signatures['h323'] = VoIPSignature(
            protocol='H.323',
            port_pattern={1720, 1503},
            codec='H.264',
            description='H.323视频会议'
        )

        logger.info(f"  - IP黑名单: {len(self.ip_blacklist)} 条 + {len(self.ip_blacklist_networks)} 个网段")
        logger.info(f"  - DNS黑名单: {len(self.dns_blacklist)} 条 + {len(self.dns_wildcard_blacklist)} 个通配符")
        logger.info(f"  - 关键词黑名单: {self.keyword_blacklist_trie.keyword_count} 个")
        logger.info(f"  - Tunnel签名: {len(self.tunnel_signatures)} 个")
        logger.info(f"  - VoIP签名: {len(self.voip_signatures)} 个")

    # ========================================================================
    # 灰名单管理（中间态策略）
    # ========================================================================

    def add_ip_greylist(self, ip_or_cidr: str, action: str = 'monitor', reason: str = ""):
        """
        添加IP灰名单

        Args:
            ip_or_cidr: IP地址或CIDR
            action: 灰名单动作（captcha/rate_limit/deep_inspect/monitor等）
            reason: 原因
        """
        with self._lock:
            try:
                network = ipaddress.ip_network(ip_or_cidr, strict=False)
                if isinstance(network, ipaddress.IPv4Network):
                    if network.num_addresses == 1:
                        self.ip_greylist.add(str(network.network_address))
                    else:
                        self.ip_greylist_networks.append(network)
                elif isinstance(network, ipaddress.IPv6Network):
                    if network.num_addresses == 1:
                        self.ipv6_greylist.add(str(network.network_address))
                    else:
                        self.ipv6_greylist_networks.append(network)
            except ValueError:
                self.ip_greylist.add(ip_or_cidr)

    def add_dns_greylist(self, domain: str, action: str = 'dns_verify', reason: str = ""):
        """添加DNS灰名单"""
        with self._lock:
            self.dns_greylist.add(domain.lower())

    def add_dns_wildcard_greylist(self, pattern: str, action: str = 'dns_verify', reason: str = ""):
        """添加DNS通配符灰名单"""
        with self._lock:
            self.dns_wildcard_greylist.append(pattern.lower())

    def add_keyword_greylist(self, keyword: str, action: str = 'deep_inspect', reason: str = ""):
        """添加关键词灰名单"""
        with self._lock:
            self.keyword_greylist_trie.insert(keyword)

    def add_ssl_greylist(self, sha256: str, action: str = 'ssl_inspect', issuer: str = "", subject: str = ""):
        """添加SSL灰名单"""
        with self._lock:
            self.ssl_greylist[sha256] = SSLFingerprint(
                sha256=sha256,
                issuer=issuer,
                subject=subject,
                is_trusted=False  # 灰名单证书不确定是否可信
            )

    def check_phishing(self, domain: str, ip: str = "") -> Tuple[bool, str]:
        """
        钓鱼检测

        检测钓鱼攻击的常见特征：
        1. 域名相似性（typosquatting）
        2. 同形字攻击（homograph attack）
        3. IP地址不匹配
        4. 可疑TLD
        5. 长域名（>50字符）

        返回：
        - (True, reason) 如果疑似钓鱼
        - (False, reason) 如果正常
        """
        domain_lower = domain.lower()

        # 1. 检查可疑TLD
        suspicious_tlds = ['.tk', '.ml', '.ga', '.cf', '.gq', '.xyz', '.top', '.wang']
        for tld in suspicious_tlds:
            if domain_lower.endswith(tld):
                self.stats['phishing_prevented'] += 1
                return (True, f"可疑TLD: {tld}")

        # 2. 检查域名长度
        if len(domain) > 50:
            self.stats['phishing_prevented'] += 1
            return (True, "域名过长（>50字符）")

        # 3. 检查同形字（常见钓鱼技巧）
        # 例如：paypa1.com (l→1)，goog1e.com (l→1)
        confusables = {
            '0': ['o', 'O'],
            '1': ['l', 'I'],
            'rn': ['m'],
            'vv': ['w'],
        }
        for char, similar in confusables.items():
            if char in domain_lower:
                # 简单检测：如果域名包含容易混淆的字符
                if any(s in domain_lower for s in similar):
                    self.stats['phishing_prevented'] += 1
                    return (True, f"可能的同形字攻击（{char}）")

        # 4. 检查typosquatting（常见品牌）
        famous_brands = ['google', 'facebook', 'amazon', 'apple', 'microsoft', 'paypal', 'netflix']
        for brand in famous_brands:
            # 简单编辑距离检测
            if brand in domain_lower and brand != domain_lower.split('.')[0]:
                # 域名包含品牌但不完全匹配
                self.stats['phishing_prevented'] += 1
                return (True, f"可能的品牌钓鱼（{brand}）")

        return (False, "")

    # ========================================================================
    # Spamhaus检查
    # ========================================================================

    def check_spamhaus(self, ip: str) -> Tuple[bool, str, str]:
        """
        检查IP是否在Spamhaus黑名单中

        返回：
        - (is_listed, severity, description)
        """
        if not self.spamhaus_enabled or not self.spamhaus:
            return (False, "none", "Spamhaus未启用")

        result = self.spamhaus.check_ip(ip)

        if result.is_listed:
            self.stats['spamhaus_hits'] += 1
            lists_str = ', '.join(result.lists)
            return (True, result.severity, f"Spamhaus: {lists_str} - {result.description}")

        return (False, "none", "未列入Spamhaus黑名单")

    # ========================================================================
    # 邮件安全检查
    # ========================================================================

    def check_email_phishing(
        self,
        email_from: str = "",
        subject: str = "",
        body: str = ""
    ) -> Tuple[bool, str]:
        """
        检测邮件钓鱼

        检测:
        1. 发件人伪装（PayPal/Apple/Amazon/FBI等）
        2. 主题行钓鱼关键词
        3. 邮件正文中的可疑内容

        返回：
        - (True, reason) 如果疑似钓鱼
        - (False, "") 如果正常
        """
        email_from_lower = email_from.lower()
        subject_lower = subject.lower()
        body_lower = body.lower()

        # 1. 检查发件人伪装
        for pattern in self.email_phishing_patterns:
            if pattern in email_from_lower:
                self.stats['email_phishing_prevented'] += 1
                return (True, f"疑似钓鱼邮件: 伪装发件人（{pattern}）")

        # 2. 检查主题行关键词
        for keyword in self.email_subject_keywords:
            if keyword.lower() in subject_lower:
                self.stats['email_phishing_prevented'] += 1
                return (True, f"疑似钓鱼邮件: 可疑主题（{keyword}）")

        # 3. 检查邮件正文（简化版）
        # 检测多个紧急关键词同时出现
        urgent_keywords = ['urgent', 'immediate', 'suspended', 'verify', 'confirm', 'update']
        urgent_count = sum(1 for kw in urgent_keywords if kw in body_lower)
        if urgent_count >= 3:
            self.stats['email_phishing_prevented'] += 1
            return (True, f"疑似钓鱼邮件: 过多紧急关键词（{urgent_count}个）")

        return (False, "")

    def detect_fbi_impersonation(self, email_from: str = "", body: str = "") -> Tuple[bool, str]:
        """
        检测FBI/执法机构伪装

        检测:
        1. 假冒FBI/司法部/国土安全部等域名
        2. 自称特工/联邦调查等关键词
        3. 逮捕令/法律行动等威胁性语言

        返回：
        - (True, reason) 如果疑似FBI伪装
        - (False, "") 如果正常
        """
        email_from_lower = email_from.lower()
        body_lower = body.lower()

        # 1. 检查发件人域名
        for pattern in self.fbi_patterns:
            if '@' in pattern:
                # 域名模式
                if pattern in email_from_lower:
                    # 额外验证：真正的gov域名应该有正确的DNS记录
                    # 这里简化处理，直接标记为可疑
                    self.stats['fbi_impersonation_blocked'] += 1
                    return (True, f"疑似FBI伪装: 假冒政府域名（{pattern}）")

        # 2. 检查正文中的伪装关键词
        for pattern in self.fbi_patterns:
            if '@' not in pattern:
                # 关键词模式
                if pattern in body_lower:
                    self.stats['fbi_impersonation_blocked'] += 1
                    return (True, f"疑似FBI伪装: 威胁性语言（{pattern}）")

        return (False, "")

    def check_email_headers(self, headers: Dict[str, str]) -> Tuple[bool, str]:
        """
        检查邮件头的真实性（SPF/DKIM/DMARC简化检测）

        这是简化版本，真实环境需要DNS查询验证SPF/DKIM/DMARC

        返回：
        - (True, reason) 如果疑似假封包
        - (False, "") 如果正常
        """
        # 1. 检查Return-Path与From是否匹配
        return_path = headers.get('Return-Path', '').lower()
        from_addr = headers.get('From', '').lower()

        if return_path and from_addr:
            # 提取域名
            return_domain = return_path.split('@')[-1].strip('>')
            from_domain = from_addr.split('@')[-1].strip('>')

            if return_domain and from_domain and return_domain != from_domain:
                return (True, f"Return-Path域名不匹配From域名（{return_domain} vs {from_domain}）")

        # 2. 检查Received头
        received = headers.get('Received', '')
        if not received:
            return (True, "缺少Received头（可疑）")

        # 3. 检查Authentication-Results (SPF/DKIM/DMARC)
        auth_results = headers.get('Authentication-Results', '').lower()
        if auth_results:
            if 'spf=fail' in auth_results:
                return (True, "SPF验证失败")
            if 'dkim=fail' in auth_results:
                return (True, "DKIM验证失败")
            if 'dmarc=fail' in auth_results:
                return (True, "DMARC验证失败")

        return (False, "")

    # ========================================================================
    # IP地址过滤
    # ========================================================================

    def add_ip_blacklist(self, ip_or_cidr: str, reason: str = ""):
        """添加IP黑名单（支持CIDR）"""
        with self._lock:
            try:
                # 尝试解析为网络
                network = ipaddress.ip_network(ip_or_cidr, strict=False)
                if isinstance(network, ipaddress.IPv4Network):
                    if network.num_addresses == 1:
                        # 单个IP
                        self.ip_blacklist.add(str(network.network_address))
                    else:
                        # CIDR范围
                        self.ip_blacklist_networks.append(network)
                elif isinstance(network, ipaddress.IPv6Network):
                    if network.num_addresses == 1:
                        self.ipv6_blacklist.add(str(network.network_address))
                    else:
                        self.ipv6_blacklist_networks.append(network)
            except ValueError:
                # 直接作为字符串添加
                self.ip_blacklist.add(ip_or_cidr)

    def add_ip_whitelist(self, ip_or_cidr: str, reason: str = ""):
        """添加IP白名单（支持CIDR）"""
        with self._lock:
            try:
                network = ipaddress.ip_network(ip_or_cidr, strict=False)
                if isinstance(network, ipaddress.IPv4Network):
                    if network.num_addresses == 1:
                        self.ip_whitelist.add(str(network.network_address))
                    else:
                        self.ip_whitelist_networks.append(network)
                elif isinstance(network, ipaddress.IPv6Network):
                    if network.num_addresses == 1:
                        self.ipv6_whitelist.add(str(network.network_address))
                    else:
                        self.ipv6_whitelist_networks.append(network)
            except ValueError:
                self.ip_whitelist.add(ip_or_cidr)

    def check_ip(self, ip: str) -> Tuple[str, Optional[str]]:
        """
        检查IP是否在黑名单/白名单/灰名单

        返回：
        - ("whitelist", reason) 如果在白名单（立即放行）
        - ("greylist", reason) 如果在灰名单（需额外验证）
        - ("blacklist", reason) 如果在黑名单（立即阻断）
        - ("pass", None) 如果都不在
        """
        self.stats['total_checks'] += 1

        try:
            ip_obj = ipaddress.ip_address(ip)
        except ValueError:
            return ("pass", None)

        # 优先级1：白名单（立即放行）
        if isinstance(ip_obj, ipaddress.IPv4Address):
            if ip in self.ip_whitelist:
                self.stats['ip_whitelist_hits'] += 1
                return ("whitelist", "精确匹配白名单")

            for network in self.ip_whitelist_networks:
                if ip_obj in network:
                    self.stats['ip_whitelist_hits'] += 1
                    return ("whitelist", f"CIDR白名单: {network}")

            # 优先级2：灰名单（需额外验证）
            if ip in self.ip_greylist:
                self.stats['ip_greylist_hits'] += 1
                return ("greylist", "精确匹配灰名单")

            for network in self.ip_greylist_networks:
                if ip_obj in network:
                    self.stats['ip_greylist_hits'] += 1
                    return ("greylist", f"CIDR灰名单: {network}")

            # 优先级3：黑名单（立即阻断）
            if ip in self.ip_blacklist:
                self.stats['ip_blacklist_hits'] += 1
                return ("blacklist", "精确匹配黑名单")

            for network in self.ip_blacklist_networks:
                if ip_obj in network:
                    self.stats['ip_blacklist_hits'] += 1
                    return ("blacklist", f"CIDR黑名单: {network}")

        elif isinstance(ip_obj, ipaddress.IPv6Address):
            if ip in self.ipv6_whitelist:
                self.stats['ip_whitelist_hits'] += 1
                return ("whitelist", "IPv6白名单")

            for network in self.ipv6_whitelist_networks:
                if ip_obj in network:
                    self.stats['ip_whitelist_hits'] += 1
                    return ("whitelist", f"IPv6 CIDR白名单: {network}")

            if ip in self.ipv6_greylist:
                self.stats['ip_greylist_hits'] += 1
                return ("greylist", "IPv6灰名单")

            for network in self.ipv6_greylist_networks:
                if ip_obj in network:
                    self.stats['ip_greylist_hits'] += 1
                    return ("greylist", f"IPv6 CIDR灰名单: {network}")

            if ip in self.ipv6_blacklist:
                self.stats['ip_blacklist_hits'] += 1
                return ("blacklist", "IPv6黑名单")

            for network in self.ipv6_blacklist_networks:
                if ip_obj in network:
                    self.stats['ip_blacklist_hits'] += 1
                    return ("blacklist", f"IPv6 CIDR黑名单: {network}")

        return ("pass", None)

    # ========================================================================
    # DNS域名过滤
    # ========================================================================

    def add_dns_blacklist(self, domain: str, reason: str = ""):
        """添加DNS黑名单"""
        with self._lock:
            self.dns_blacklist.add(domain.lower())

    def add_dns_whitelist(self, domain: str, reason: str = ""):
        """添加DNS白名单"""
        with self._lock:
            self.dns_whitelist.add(domain.lower())

    def add_dns_wildcard_blacklist(self, pattern: str, reason: str = ""):
        """添加DNS通配符黑名单（例如 *.malicious.com）"""
        with self._lock:
            self.dns_wildcard_blacklist.append(pattern.lower())

    def add_dns_wildcard_whitelist(self, pattern: str, reason: str = ""):
        """添加DNS通配符白名单"""
        with self._lock:
            self.dns_wildcard_whitelist.append(pattern.lower())

    def check_dns(self, domain: str) -> Tuple[str, Optional[str]]:
        """
        检查DNS域名

        返回：
        - ("whitelist", reason) 如果在白名单
        - ("blacklist", reason) 如果在黑名单
        - ("pass", None) 如果都不在
        """
        self.stats['total_checks'] += 1
        domain_lower = domain.lower()

        # 精确匹配白名单
        if domain_lower in self.dns_whitelist:
            self.stats['dns_whitelist_hits'] += 1
            return ("whitelist", "精确匹配DNS白名单")

        # 通配符白名单
        for pattern in self.dns_whitelist:
            if self._match_wildcard(domain_lower, pattern):
                self.stats['dns_whitelist_hits'] += 1
                return ("whitelist", f"通配符白名单: {pattern}")

        # 精确匹配黑名单
        if domain_lower in self.dns_blacklist:
            self.stats['dns_blacklist_hits'] += 1
            return ("blacklist", "精确匹配DNS黑名单")

        # 通配符黑名单
        for pattern in self.dns_wildcard_blacklist:
            if self._match_wildcard(domain_lower, pattern):
                self.stats['dns_blacklist_hits'] += 1
                return ("blacklist", f"通配符黑名单: {pattern}")

        return ("pass", None)

    def _match_wildcard(self, domain: str, pattern: str) -> bool:
        """通配符匹配（支持 *.example.com）"""
        if pattern.startswith('*.'):
            suffix = pattern[2:]
            return domain.endswith(suffix) or domain == suffix
        return domain == pattern

    # ========================================================================
    # 关键词过滤
    # ========================================================================

    def add_keyword_blacklist(self, keyword: str, reason: str = ""):
        """添加关键词黑名单"""
        with self._lock:
            self.keyword_blacklist_trie.insert(keyword)

    def add_keyword_whitelist(self, keyword: str, reason: str = ""):
        """添加关键词白名单"""
        with self._lock:
            self.keyword_whitelist_trie.insert(keyword)

    def check_keywords(self, text: str) -> Tuple[str, Optional[str]]:
        """
        检查文本中是否包含黑名单/白名单关键词

        返回：
        - ("whitelist", keyword) 如果包含白名单关键词
        - ("blacklist", keyword) 如果包含黑名单关键词
        - ("pass", None) 如果都不包含
        """
        self.stats['total_checks'] += 1

        # 优先检查白名单
        whitelist_match = self.keyword_whitelist_trie.search(text)
        if whitelist_match:
            self.stats['keyword_whitelist_hits'] += 1
            return ("whitelist", whitelist_match)

        # 检查黑名单
        blacklist_match = self.keyword_blacklist_trie.search(text)
        if blacklist_match:
            self.stats['keyword_blacklist_hits'] += 1
            return ("blacklist", blacklist_match)

        return ("pass", None)

    # ========================================================================
    # SSL证书指纹过滤
    # ========================================================================

    def add_ssl_blacklist(self, sha256: str, issuer: str = "", subject: str = ""):
        """添加SSL黑名单"""
        with self._lock:
            self.ssl_blacklist[sha256] = SSLFingerprint(
                sha256=sha256,
                issuer=issuer,
                subject=subject,
                is_trusted=False
            )

    def add_ssl_whitelist(self, sha256: str, issuer: str = "", subject: str = ""):
        """添加SSL白名单"""
        with self._lock:
            self.ssl_whitelist[sha256] = SSLFingerprint(
                sha256=sha256,
                issuer=issuer,
                subject=subject,
                is_trusted=True
            )

    def check_ssl(self, sha256: str) -> Tuple[str, Optional[str]]:
        """
        检查SSL证书指纹

        返回：
        - ("whitelist", reason) 如果在白名单
        - ("blacklist", reason) 如果在黑名单
        - ("pass", None) 如果都不在
        """
        self.stats['total_checks'] += 1

        if sha256 in self.ssl_whitelist:
            self.stats['ssl_whitelist_hits'] += 1
            fp = self.ssl_whitelist[sha256]
            return ("whitelist", f"可信证书: {fp.subject}")

        if sha256 in self.ssl_blacklist:
            self.stats['ssl_blacklist_hits'] += 1
            fp = self.ssl_blacklist[sha256]
            return ("blacklist", f"恶意证书: {fp.subject}")

        return ("pass", None)

    # ========================================================================
    # Tunnel检测
    # ========================================================================

    def detect_tunnel(self, dst_port: int, payload: bytes) -> Optional[str]:
        """
        检测Tunnel协议

        返回：Tunnel协议名称，如果未检测到则返回None
        """
        self.stats['total_checks'] += 1

        for protocol, sig in self.tunnel_signatures.items():
            # 端口匹配
            if dst_port not in sig.port_pattern:
                continue

            # Payload匹配
            if sig.payload_pattern and sig.payload_pattern in payload:
                self.stats['tunnel_detections'] += 1
                logger.warning(f"检测到Tunnel: {sig.protocol} (端口={dst_port})")
                return protocol

        return None

    # ========================================================================
    # VoIP检测
    # ========================================================================

    def detect_voip(self, dst_port: int, payload: bytes) -> Optional[str]:
        """
        检测VoIP协议

        返回：VoIP协议名称，如果未检测到则返回None
        """
        self.stats['total_checks'] += 1

        for protocol, sig in self.voip_signatures.items():
            # 端口匹配
            if dst_port in sig.port_pattern:
                self.stats['voip_detections'] += 1
                logger.info(f"检测到VoIP: {sig.protocol} (端口={dst_port})")
                return protocol

            # SIP特定检测（检查payload中的"SIP/"）
            if protocol == 'sip' and b'SIP/' in payload:
                self.stats['voip_detections'] += 1
                logger.info(f"检测到VoIP: SIP (payload匹配)")
                return protocol

        return None

    # ========================================================================
    # 综合检查
    # ========================================================================

    def comprehensive_check(
        self,
        src_ip: str = "",
        dst_ip: str = "",
        domain: str = "",
        payload: bytes = b"",
        dst_port: int = 0,
        ssl_sha256: str = "",
        email_from: str = "",
        email_subject: str = "",
        email_body: str = "",
        email_headers: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """
        综合检查（一次性检查所有过滤器）

        返回检查结果字典：
        {
            'action': 'allow/block/greylist',
            'reason': '...',
            'matched_filters': [...],
            'tunnel_detected': '...',
            'voip_detected': '...',
            'spamhaus_result': {...},
            'email_phishing': bool,
            'fbi_impersonation': bool
        }
        """
        result = {
            'action': 'allow',
            'reason': 'No filters matched',
            'matched_filters': [],
            'tunnel_detected': None,
            'voip_detected': None,
            'spamhaus_result': None,
            'email_phishing': False,
            'fbi_impersonation': False,
        }

        # 1. IP检查
        if src_ip:
            ip_result, ip_reason = self.check_ip(src_ip)
            if ip_result == 'whitelist':
                result['action'] = 'allow'
                result['reason'] = f'IP白名单: {ip_reason}'
                result['matched_filters'].append('ip_whitelist')
                return result  # 白名单立即放行
            elif ip_result == 'blacklist':
                result['action'] = 'block'
                result['reason'] = f'IP黑名单: {ip_reason}'
                result['matched_filters'].append('ip_blacklist')
                return result  # 黑名单立即阻断
            elif ip_result == 'greylist':
                result['action'] = 'greylist'
                result['reason'] = f'IP灰名单: {ip_reason}'
                result['matched_filters'].append('ip_greylist')
                # 灰名单继续检查，但已标记需额外验证

            # 1.5 Spamhaus检查
            if ip_result not in ['whitelist', 'blacklist']:  # 只有非白名单/黑名单才查Spamhaus
                is_spamhaus, severity, spamhaus_desc = self.check_spamhaus(src_ip)
                if is_spamhaus:
                    result['spamhaus_result'] = {
                        'severity': severity,
                        'description': spamhaus_desc
                    }
                    result['matched_filters'].append('spamhaus')

                    # 根据严重性决定处理方式
                    if severity == 'critical':
                        result['action'] = 'block'
                        result['reason'] = f'Spamhaus严重威胁: {spamhaus_desc}'
                        return result
                    elif severity == 'high':
                        result['action'] = 'greylist'
                        result['reason'] = f'Spamhaus高风险: {spamhaus_desc}'
                        # 继续检查其他条件
                    # low/medium 只记录，不影响最终决策

        # 2. DNS检查
        if domain:
            dns_result, dns_reason = self.check_dns(domain)
            if dns_result == 'whitelist':
                result['action'] = 'allow'
                result['reason'] = f'DNS白名单: {dns_reason}'
                result['matched_filters'].append('dns_whitelist')
                return result
            elif dns_result == 'blacklist':
                result['action'] = 'block'
                result['reason'] = f'DNS黑名单: {dns_reason}'
                result['matched_filters'].append('dns_blacklist')
                return result

        # 3. 关键词检查
        if payload:
            try:
                text = payload.decode('utf-8', errors='ignore')
                keyword_result, keyword = self.check_keywords(text)
                if keyword_result == 'whitelist':
                    result['action'] = 'allow'
                    result['reason'] = f'关键词白名单: {keyword}'
                    result['matched_filters'].append('keyword_whitelist')
                    return result
                elif keyword_result == 'blacklist':
                    result['action'] = 'block'
                    result['reason'] = f'关键词黑名单: {keyword}'
                    result['matched_filters'].append('keyword_blacklist')
                    return result
            except:
                pass

        # 4. SSL检查
        if ssl_sha256:
            ssl_result, ssl_reason = self.check_ssl(ssl_sha256)
            if ssl_result == 'whitelist':
                result['action'] = 'allow'
                result['reason'] = f'SSL白名单: {ssl_reason}'
                result['matched_filters'].append('ssl_whitelist')
                return result
            elif ssl_result == 'blacklist':
                result['action'] = 'block'
                result['reason'] = f'SSL黑名单: {ssl_reason}'
                result['matched_filters'].append('ssl_blacklist')
                return result

        # 5. Tunnel检测（仅标记，不直接阻断）
        if dst_port > 0 and payload:
            tunnel = self.detect_tunnel(dst_port, payload)
            if tunnel:
                result['tunnel_detected'] = tunnel
                result['matched_filters'].append('tunnel')

        # 6. VoIP检测（仅标记）
        if dst_port > 0 and payload:
            voip = self.detect_voip(dst_port, payload)
            if voip:
                result['voip_detected'] = voip
                result['matched_filters'].append('voip')

        # 7. 邮件钓鱼检测
        if email_from or email_subject or email_body:
            is_phishing, phishing_reason = self.check_email_phishing(
                email_from=email_from,
                subject=email_subject,
                body=email_body
            )
            if is_phishing:
                result['email_phishing'] = True
                result['matched_filters'].append('email_phishing')

                # 钓鱼邮件进入灰名单（额外验证）
                if result['action'] != 'block':
                    result['action'] = 'greylist'
                    result['reason'] = phishing_reason

        # 8. FBI伪装检测
        if email_from or email_body:
            is_fbi, fbi_reason = self.detect_fbi_impersonation(
                email_from=email_from,
                body=email_body
            )
            if is_fbi:
                result['fbi_impersonation'] = True
                result['matched_filters'].append('fbi_impersonation')

                # FBI伪装直接阻断
                result['action'] = 'block'
                result['reason'] = fbi_reason
                return result

        # 9. 邮件头检测（假封包）
        if email_headers:
            is_fake, header_reason = self.check_email_headers(email_headers)
            if is_fake:
                result['matched_filters'].append('fake_email_packet')

                # 假封包进入灰名单
                if result['action'] != 'block':
                    result['action'] = 'greylist'
                    result['reason'] = f'疑似假封包: {header_reason}'

        return result

    # ========================================================================
    # 统计和管理
    # ========================================================================

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            'ip_blacklist_count': len(self.ip_blacklist) + len(self.ip_blacklist_networks),
            'ip_whitelist_count': len(self.ip_whitelist) + len(self.ip_whitelist_networks),
            'ipv6_blacklist_count': len(self.ipv6_blacklist) + len(self.ipv6_blacklist_networks),
            'ipv6_whitelist_count': len(self.ipv6_whitelist) + len(self.ipv6_whitelist_networks),
            'dns_blacklist_count': len(self.dns_blacklist) + len(self.dns_wildcard_blacklist),
            'dns_whitelist_count': len(self.dns_whitelist) + len(self.dns_wildcard_whitelist),
            'keyword_blacklist_count': self.keyword_blacklist_trie.keyword_count,
            'keyword_whitelist_count': self.keyword_whitelist_trie.keyword_count,
            'ssl_blacklist_count': len(self.ssl_blacklist),
            'ssl_whitelist_count': len(self.ssl_whitelist),
            'tunnel_signatures_count': len(self.tunnel_signatures),
            'voip_signatures_count': len(self.voip_signatures)
        }

    def clear_all(self):
        """清空所有过滤清单"""
        with self._lock:
            self.ip_blacklist.clear()
            self.ip_whitelist.clear()
            self.ip_blacklist_networks.clear()
            self.ip_whitelist_networks.clear()
            self.ipv6_blacklist.clear()
            self.ipv6_whitelist.clear()
            self.ipv6_blacklist_networks.clear()
            self.ipv6_whitelist_networks.clear()
            self.dns_blacklist.clear()
            self.dns_whitelist.clear()
            self.dns_wildcard_blacklist.clear()
            self.dns_wildcard_whitelist.clear()
            self.keyword_blacklist_trie = KeywordTrie()
            self.keyword_whitelist_trie = KeywordTrie()
            self.ssl_blacklist.clear()
            self.ssl_whitelist.clear()
            self.tunnel_signatures.clear()
            self.voip_signatures.clear()

    # ========================================================================
    # 白名单管理器
    # ========================================================================

    def export_whitelist_config(self) -> Dict[str, List[str]]:
        """
        导出白名单配置

        返回字典格式的白名单配置，可用于保存到文件
        """
        return {
            'ip_whitelist': list(self.ip_whitelist),
            'ip_whitelist_networks': [str(net) for net in self.ip_whitelist_networks],
            'ipv6_whitelist': list(self.ipv6_whitelist),
            'ipv6_whitelist_networks': [str(net) for net in self.ipv6_whitelist_networks],
            'dns_whitelist': list(self.dns_whitelist),
            'dns_wildcard_whitelist': list(self.dns_wildcard_whitelist),
            'ssl_whitelist': [fp.sha256 for fp in self.ssl_whitelist.values()]
        }

    def import_whitelist_config(self, config: Dict[str, List[str]]):
        """
        从配置导入白名单

        config格式：
        {
            'ip_whitelist': ['10.0.0.0/8', '192.168.0.0/16'],
            'dns_whitelist': ['trusted.example.com'],
            'dns_wildcard_whitelist': ['*.safe.com'],
            ...
        }
        """
        with self._lock:
            # 导入IP白名单
            for ip in config.get('ip_whitelist', []):
                self.add_ip_whitelist(ip)

            for cidr in config.get('ip_whitelist_networks', []):
                self.add_ip_whitelist(cidr)

            # 导入IPv6白名单
            for ip in config.get('ipv6_whitelist', []):
                self.add_ip_whitelist(ip)  # add_ip_whitelist自动识别IPv6

            for cidr in config.get('ipv6_whitelist_networks', []):
                self.add_ip_whitelist(cidr)

            # 导入DNS白名单
            for domain in config.get('dns_whitelist', []):
                self.add_dns_whitelist(domain)

            for pattern in config.get('dns_wildcard_whitelist', []):
                self.add_dns_wildcard_whitelist(pattern)

            # 导入SSL白名单
            for sha256 in config.get('ssl_whitelist', []):
                self.add_ssl_whitelist(sha256)

        logger.info(f"✅ 白名单配置导入完成")

    def load_whitelist_from_file(self, filename: str):
        """从JSON文件加载白名单"""
        import json
        try:
            with open(filename, 'r') as f:
                config = json.load(f)
            self.import_whitelist_config(config)
            logger.info(f"✅ 白名单从文件加载: {filename}")
        except Exception as e:
            logger.error(f"❌ 白名单加载失败: {e}")

    def save_whitelist_to_file(self, filename: str):
        """保存白名单到JSON文件"""
        import json
        try:
            config = self.export_whitelist_config()
            with open(filename, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info(f"✅ 白名单已保存: {filename}")
        except Exception as e:
            logger.error(f"❌ 白名单保存失败: {e}")

    def get_whitelist_stats(self) -> Dict[str, int]:
        """获取白名单统计"""
        return {
            'ip_whitelist_count': len(self.ip_whitelist) + len(self.ip_whitelist_networks),
            'ipv6_whitelist_count': len(self.ipv6_whitelist) + len(self.ipv6_whitelist_networks),
            'dns_whitelist_count': len(self.dns_whitelist) + len(self.dns_wildcard_whitelist),
            'keyword_whitelist_count': self.keyword_whitelist_trie.keyword_count,
            'ssl_whitelist_count': len(self.ssl_whitelist),
            'total_whitelist_hits': (
                self.stats['ip_whitelist_hits'] +
                self.stats['dns_whitelist_hits'] +
                self.stats['keyword_whitelist_hits'] +
                self.stats['ssl_whitelist_hits']
            )
        }

    def is_whitelisted(self, ip: str = "", domain: str = "", ssl_sha256: str = "") -> bool:
        """
        快速检查是否在任何白名单中

        返回：True 如果在白名单，False 如果不在
        """
        if ip:
            result, _ = self.check_ip(ip)
            if result == 'whitelist':
                return True

        if domain:
            result, _ = self.check_dns(domain)
            if result == 'whitelist':
                return True

        if ssl_sha256:
            result, _ = self.check_ssl(ssl_sha256)
            if result == 'whitelist':
                return True

        return False


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=== HIDRS快速过滤清单测试 ===\n")

    # 创建过滤器
    filters = FastFilterLists()

    # 测试1：IP过滤
    print("测试1：IP过滤")
    result, reason = filters.check_ip("127.0.0.1")
    print(f"  127.0.0.1: {result} ({reason})")

    filters.add_ip_blacklist("1.2.3.4", reason="测试恶意IP")
    result, reason = filters.check_ip("1.2.3.4")
    print(f"  1.2.3.4: {result} ({reason})")

    filters.add_ip_whitelist("10.0.0.0/8", reason="内网白名单")
    result, reason = filters.check_ip("10.1.2.3")
    print(f"  10.1.2.3: {result} ({reason})")

    # 测试2：DNS过滤
    print("\n测试2：DNS过滤")
    result, reason = filters.check_dns("malware.example.com")
    print(f"  malware.example.com: {result} ({reason})")

    result, reason = filters.check_dns("evil.malicious.com")
    print(f"  evil.malicious.com: {result} ({reason})")

    # 测试3：关键词过滤
    print("\n测试3：关键词过滤")
    result, keyword = filters.check_keywords("SELECT * FROM users WHERE id=1 UNION SELECT password FROM admin")
    print(f"  SQL注入: {result} (关键词={keyword})")

    result, keyword = filters.check_keywords("<?php eval($_POST['cmd']); ?>")
    print(f"  Webshell: {result} (关键词={keyword})")

    # 测试4：Tunnel检测
    print("\n测试4：Tunnel检测")
    tunnel = filters.detect_tunnel(8388, b'\x05\x01\x00')
    print(f"  端口8388 + SOCKS5握手: {tunnel}")

    tunnel = filters.detect_tunnel(9001, b'\x16\x03\x01')
    print(f"  端口9001 + TLS握手: {tunnel}")

    # 测试5：VoIP检测
    print("\n测试5：VoIP检测")
    voip = filters.detect_voip(5060, b'INVITE sip:user@example.com SIP/2.0')
    print(f"  端口5060 + SIP消息: {voip}")

    # 测试6：综合检查
    print("\n测试6：综合检查")
    result = filters.comprehensive_check(
        src_ip="1.2.3.4",
        domain="malware.example.com",
        payload=b"union select * from users",
        dst_port=8388,
        ssl_sha256=""
    )
    print(f"  综合检查结果:")
    print(f"    - Action: {result['action']}")
    print(f"    - Reason: {result['reason']}")
    print(f"    - Matched filters: {result['matched_filters']}")
    print(f"    - Tunnel: {result['tunnel_detected']}")
    print(f"    - VoIP: {result['voip_detected']}")

    # 统计
    print("\n=== 统计信息 ===")
    stats = filters.get_statistics()
    print(f"IP黑名单命中: {stats['ip_blacklist_hits']} 次")
    print(f"DNS黑名单命中: {stats['dns_blacklist_hits']} 次")
    print(f"关键词黑名单命中: {stats['keyword_blacklist_hits']} 次")
    print(f"Tunnel检测: {stats['tunnel_detections']} 次")
    print(f"VoIP检测: {stats['voip_detections']} 次")
    print(f"总检查次数: {stats['total_checks']} 次")

    def check_dns(self, domain: str) -> Tuple[str, Optional[str]]:
        """
        检查DNS域名（支持灰名单）

        返回：
        - ("whitelist", reason) 如果在白名单
        - ("greylist", reason) 如果在灰名单（需额外验证）
        - ("blacklist", reason) 如果在黑名单
        - ("pass", None) 如果都不在
        """
        self.stats['total_checks'] += 1
        domain_lower = domain.lower()

        # 优先级1：钓鱼检测
        is_phishing, reason = self.check_phishing(domain)
        if is_phishing:
            return ("greylist", f"疑似钓鱼: {reason}")

        # 优先级2：白名单
        if domain_lower in self.dns_whitelist:
            self.stats['dns_whitelist_hits'] += 1
            return ("whitelist", "精确匹配DNS白名单")

        for pattern in self.dns_wildcard_whitelist:
            if self._match_wildcard(domain_lower, pattern):
                self.stats['dns_whitelist_hits'] += 1
                return ("whitelist", f"通配符白名单: {pattern}")

        # 优先级3：灰名单
        if domain_lower in self.dns_greylist:
            self.stats['dns_greylist_hits'] += 1
            return ("greylist", "精确匹配DNS灰名单")

        for pattern in self.dns_wildcard_greylist:
            if self._match_wildcard(domain_lower, pattern):
                self.stats['dns_greylist_hits'] += 1
                return ("greylist", f"通配符灰名单: {pattern}")

        # 优先级4：黑名单
        if domain_lower in self.dns_blacklist:
            self.stats['dns_blacklist_hits'] += 1
            return ("blacklist", "精确匹配DNS黑名单")

        for pattern in self.dns_wildcard_blacklist:
            if self._match_wildcard(domain_lower, pattern):
                self.stats['dns_blacklist_hits'] += 1
                return ("blacklist", f"通配符黑名单: {pattern}")

        return ("pass", None)
