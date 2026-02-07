"""
AEGIS根协调服务器
AEGIS Root Coordination Server

架构设计基于DNS根服务器和现代分布式防火墙：
- 控制平面：策略管理、威胁情报聚合、节点协调
- Anycast路由：自动选择最近节点，减少延迟
- 混合架构：中央管理 + 分布式执行

参考架构：
1. DNS根服务器（13个逻辑地址，1500+物理服务器，Anycast路由）
   https://www.iana.org/domains/root/servers
   https://www.cloudflare.com/learning/dns/glossary/dns-root-server/

2. 分布式防火墙（中央策略管理 + 分布式代理执行）
   https://www.fortinet.com/resources/cyberglossary/distributed-firewall
   https://www.paloaltonetworks.com/cyberpedia/what-is-a-distributed-firewall

3. Tailscale混合架构（控制平面hub-spoke，数据平面mesh）
   https://tailscale.com/blog/how-tailscale-works

By: Claude + 430
"""

import asyncio
import time
import logging
import hashlib
import json
from typing import Dict, List, Set, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from collections import defaultdict
import threading

logger = logging.getLogger(__name__)


@dataclass
class NodeInfo:
    """节点信息"""
    node_id: str
    region: str  # us-west, eu-central, as-east等
    ip_address: str
    anycast_address: Optional[str] = None  # Anycast地址（如果支持）

    # 状态
    status: str = "active"  # active, degraded, offline
    last_heartbeat: float = 0.0
    registered_at: float = 0.0

    # 性能指标
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    packet_rate: int = 0
    blocked_packets: int = 0

    # 能力
    capabilities: List[str] = field(default_factory=list)  # ["fast_filters", "hlig", "sosa"]
    version: str = "1.0.0"

    # 负载均衡权重
    weight: float = 1.0  # Anycast路由权重


@dataclass
class GlobalThreatIntel:
    """全局威胁情报"""
    intel_id: str
    threat_type: str  # ip_blacklist, domain_blacklist, attack_pattern, cc_server

    # 威胁数据
    target: str  # IP/域名/特征ID
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    confidence: float  # 0.0-1.0

    # 来源信息
    reported_by: List[str] = field(default_factory=list)  # 报告节点列表
    first_seen: float = 0.0
    last_seen: float = 0.0
    occurrence_count: int = 0

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    action: str = "BLOCK"  # ALLOW, BLOCK, ALERT, TARPIT
    ttl: int = 3600  # 生存时间（秒）


@dataclass
class GlobalPolicy:
    """全局安全策略"""
    policy_id: str
    policy_name: str
    policy_type: str  # firewall_rule, rate_limit, geo_block

    # 策略配置
    config: Dict[str, Any]
    enabled: bool = True

    # 应用范围
    target_regions: List[str] = field(default_factory=list)  # 空列表=全局
    target_nodes: List[str] = field(default_factory=list)    # 空列表=全部节点

    # 版本控制
    version: int = 1
    created_at: float = 0.0
    updated_at: float = 0.0


class AEGISRootServer:
    """
    AEGIS根协调服务器

    职责：
    1. 节点注册和健康监控
    2. 全局威胁情报聚合和分发
    3. 安全策略统一管理
    4. Anycast路由优化
    5. 与HIDRS主系统集成

    架构特点：
    - 控制平面：轻量级，只传输策略和情报（KB级别）
    - 数据平面：由各节点独立执行（分布式）
    - Anycast：自动路由到最近节点
    """

    # Anycast地址池（模拟13个DNS根服务器风格）
    ANYCAST_ADDRESSES = [
        "198.41.0.4",     # AEGIS-A (主根)
        "199.9.14.201",   # AEGIS-B
        "192.33.4.12",    # AEGIS-C
        "199.7.91.13",    # AEGIS-D
        "192.203.230.10", # AEGIS-E
        "192.5.5.241",    # AEGIS-F
        "192.112.36.4",   # AEGIS-G
        "198.97.190.53",  # AEGIS-H
        "192.36.148.17",  # AEGIS-I
        "192.58.128.30",  # AEGIS-J
        "193.0.14.129",   # AEGIS-K
        "199.7.83.42",    # AEGIS-L
        "202.12.27.33",   # AEGIS-M
    ]

    def __init__(
        self,
        server_id: str = "AEGIS-ROOT-01",
        anycast_enabled: bool = True,
        heartbeat_timeout: float = 30.0
    ):
        """
        初始化根服务器

        参数:
            server_id: 服务器ID
            anycast_enabled: 是否启用Anycast路由
            heartbeat_timeout: 节点心跳超时（秒）
        """
        self.server_id = server_id
        self.anycast_enabled = anycast_enabled
        self.heartbeat_timeout = heartbeat_timeout

        # 节点管理
        self.nodes: Dict[str, NodeInfo] = {}  # node_id -> NodeInfo
        self.node_by_region: Dict[str, List[str]] = defaultdict(list)  # region -> [node_ids]

        # Anycast路由表
        self.anycast_routing: Dict[str, List[str]] = defaultdict(list)  # anycast_ip -> [node_ids]

        # 威胁情报库
        self.threat_intel: Dict[str, GlobalThreatIntel] = {}  # intel_id -> GlobalThreatIntel

        # 策略库
        self.policies: Dict[str, GlobalPolicy] = {}  # policy_id -> GlobalPolicy

        # 统计
        self.stats = {
            'total_nodes': 0,
            'active_nodes': 0,
            'threat_intel_count': 0,
            'policy_count': 0,
            'total_heartbeats': 0,
            'anycast_routes': 0,
        }

        # 监控线程
        self.running = False
        self.monitor_thread = None

        logger.info(f"[{self.server_id}] AEGIS根协调服务器初始化")
        logger.info(f"  Anycast: {'启用' if anycast_enabled else '禁用'}")
        logger.info(f"  心跳超时: {heartbeat_timeout}秒")

    def start(self):
        """启动根服务器"""
        self.running = True

        # 启动健康监控
        self.monitor_thread = threading.Thread(
            target=self._health_monitor_loop,
            daemon=True
        )
        self.monitor_thread.start()

        logger.info(f"[{self.server_id}] 根服务器已启动")

    def stop(self):
        """停止根服务器"""
        self.running = False
        logger.info(f"[{self.server_id}] 根服务器已停止")

    def register_node(
        self,
        node_id: str,
        region: str,
        ip_address: str,
        capabilities: List[str],
        version: str = "1.0.0"
    ) -> Dict[str, Any]:
        """
        注册新节点

        返回:
            包含Anycast地址和初始配置的字典
        """
        # 分配Anycast地址
        anycast_address = None
        if self.anycast_enabled:
            anycast_address = self._assign_anycast_address(region)

        # 创建节点信息
        node_info = NodeInfo(
            node_id=node_id,
            region=region,
            ip_address=ip_address,
            anycast_address=anycast_address,
            capabilities=capabilities,
            version=version,
            registered_at=time.time(),
            last_heartbeat=time.time(),
        )

        # 存储节点
        self.nodes[node_id] = node_info
        self.node_by_region[region].append(node_id)

        if anycast_address:
            self.anycast_routing[anycast_address].append(node_id)
            self.stats['anycast_routes'] += 1

        self.stats['total_nodes'] += 1
        self.stats['active_nodes'] += 1

        logger.info(
            f"[{self.server_id}] 节点注册: {node_id} "
            f"(区域: {region}, Anycast: {anycast_address or 'N/A'})"
        )

        # 返回配置
        return {
            'success': True,
            'node_id': node_id,
            'anycast_address': anycast_address,
            'assigned_policies': self._get_applicable_policies(region, node_id),
            'initial_threat_intel': self._get_recent_threat_intel(limit=1000),
        }

    def _assign_anycast_address(self, region: str) -> str:
        """
        为节点分配Anycast地址

        策略：
        1. 优先分配该区域已使用的地址（增加该地址的节点数）
        2. 如果该区域无节点，分配使用最少的地址
        """
        # 检查该区域是否已有节点
        region_nodes = self.node_by_region.get(region, [])
        if region_nodes:
            # 复用该区域已分配的Anycast地址
            existing_node = self.nodes[region_nodes[0]]
            if existing_node.anycast_address:
                return existing_node.anycast_address

        # 分配使用最少的Anycast地址
        address_usage = {addr: 0 for addr in self.ANYCAST_ADDRESSES}
        for nodes in self.anycast_routing.values():
            addr = self.nodes[nodes[0]].anycast_address
            if addr in address_usage:
                address_usage[addr] += len(nodes)

        # 选择使用最少的地址
        return min(address_usage.items(), key=lambda x: x[1])[0]

    def update_heartbeat(
        self,
        node_id: str,
        metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        更新节点心跳

        参数:
            node_id: 节点ID
            metrics: 性能指标
        """
        if node_id not in self.nodes:
            return {'success': False, 'error': 'Node not registered'}

        node = self.nodes[node_id]
        node.last_heartbeat = time.time()
        node.status = "active"

        # 更新性能指标
        node.cpu_usage = metrics.get('cpu_usage', 0.0)
        node.memory_usage = metrics.get('memory_usage', 0.0)
        node.packet_rate = metrics.get('packet_rate', 0)
        node.blocked_packets = metrics.get('blocked_packets', 0)

        # 调整Anycast权重（基于负载）
        self._adjust_anycast_weight(node)

        self.stats['total_heartbeats'] += 1

        # 返回更新（如果有）
        return {
            'success': True,
            'new_policies': self._get_policy_updates(node_id),
            'new_threat_intel': self._get_threat_intel_updates(node_id),
        }

    def _adjust_anycast_weight(self, node: NodeInfo):
        """
        根据节点负载调整Anycast路由权重

        负载高 -> 权重低 -> 减少流量分配
        """
        # 简单的线性权重计算
        load_factor = (node.cpu_usage + node.memory_usage) / 2.0
        node.weight = max(0.1, 1.0 - load_factor)

    def report_threat_intel(
        self,
        node_id: str,
        threat_type: str,
        target: str,
        severity: str,
        confidence: float,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        节点报告威胁情报

        返回:
            情报ID
        """
        # 生成情报ID
        intel_id = hashlib.sha256(
            f"{threat_type}:{target}".encode()
        ).hexdigest()[:16]

        current_time = time.time()

        # 检查是否已存在
        if intel_id in self.threat_intel:
            intel = self.threat_intel[intel_id]

            # 更新现有情报
            if node_id not in intel.reported_by:
                intel.reported_by.append(node_id)

            intel.last_seen = current_time
            intel.occurrence_count += 1

            # 提升置信度（多节点确认）
            intel.confidence = min(
                1.0,
                intel.confidence + 0.1 * len(intel.reported_by)
            )

            logger.info(
                f"[{self.server_id}] 威胁情报更新: {intel_id} "
                f"(来源节点: {len(intel.reported_by)}个, 置信度: {intel.confidence:.2f})"
            )
        else:
            # 创建新情报
            intel = GlobalThreatIntel(
                intel_id=intel_id,
                threat_type=threat_type,
                target=target,
                severity=severity,
                confidence=confidence,
                reported_by=[node_id],
                first_seen=current_time,
                last_seen=current_time,
                occurrence_count=1,
                metadata=metadata or {},
            )

            self.threat_intel[intel_id] = intel
            self.stats['threat_intel_count'] += 1

            logger.warning(
                f"[{self.server_id}] 新威胁情报: {intel_id} "
                f"(类型: {threat_type}, 目标: {target}, 严重性: {severity})"
            )

        # 如果情报严重且置信度高，触发全局广播
        if severity == "CRITICAL" and intel.confidence >= 0.8:
            self._broadcast_critical_threat(intel)

        return intel_id

    def _broadcast_critical_threat(self, intel: GlobalThreatIntel):
        """广播关键威胁到所有节点"""
        logger.critical(
            f"[{self.server_id}] 🚨 全球威胁警报: {intel.intel_id} "
            f"(目标: {intel.target}, 严重性: {intel.severity})"
        )

        # 在实际实现中，这里会通过Redis Pub/Sub广播
        # 现在只是记录日志
        logger.critical(
            f"[{self.server_id}] 广播到 {len(self.nodes)} 个节点"
        )

    def deploy_policy(
        self,
        policy_name: str,
        policy_type: str,
        config: Dict[str, Any],
        target_regions: List[str] = None,
        target_nodes: List[str] = None
    ) -> str:
        """
        部署全局策略

        返回:
            策略ID
        """
        policy_id = hashlib.sha256(
            f"{policy_name}:{time.time()}".encode()
        ).hexdigest()[:16]

        policy = GlobalPolicy(
            policy_id=policy_id,
            policy_name=policy_name,
            policy_type=policy_type,
            config=config,
            target_regions=target_regions or [],
            target_nodes=target_nodes or [],
            created_at=time.time(),
            updated_at=time.time(),
        )

        self.policies[policy_id] = policy
        self.stats['policy_count'] += 1

        logger.info(
            f"[{self.server_id}] 策略部署: {policy_id} "
            f"(名称: {policy_name}, 类型: {policy_type})"
        )

        return policy_id

    def _get_applicable_policies(
        self,
        region: str,
        node_id: str
    ) -> List[Dict[str, Any]]:
        """获取适用于指定节点的策略"""
        applicable = []

        for policy in self.policies.values():
            if not policy.enabled:
                continue

            # 检查区域过滤
            if policy.target_regions and region not in policy.target_regions:
                continue

            # 检查节点过滤
            if policy.target_nodes and node_id not in policy.target_nodes:
                continue

            applicable.append({
                'policy_id': policy.policy_id,
                'policy_name': policy.policy_name,
                'policy_type': policy.policy_type,
                'config': policy.config,
                'version': policy.version,
            })

        return applicable

    def _get_recent_threat_intel(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """获取最近的威胁情报"""
        intel_list = sorted(
            self.threat_intel.values(),
            key=lambda x: x.last_seen,
            reverse=True
        )[:limit]

        return [
            {
                'intel_id': intel.intel_id,
                'threat_type': intel.threat_type,
                'target': intel.target,
                'severity': intel.severity,
                'confidence': intel.confidence,
                'action': intel.action,
                'ttl': intel.ttl,
            }
            for intel in intel_list
        ]

    def _get_policy_updates(self, node_id: str) -> List[Dict[str, Any]]:
        """获取策略更新（简化版，实际应该追踪节点已知的策略版本）"""
        # 这里简化处理，实际应该维护每个节点的策略版本状态
        return []

    def _get_threat_intel_updates(self, node_id: str) -> List[Dict[str, Any]]:
        """获取威胁情报更新"""
        # 简化版：返回最近1分钟的情报
        cutoff = time.time() - 60
        recent = [
            intel for intel in self.threat_intel.values()
            if intel.last_seen >= cutoff
        ]

        return [
            {
                'intel_id': intel.intel_id,
                'threat_type': intel.threat_type,
                'target': intel.target,
                'action': intel.action,
            }
            for intel in recent
        ]

    def _health_monitor_loop(self):
        """健康监控循环"""
        while self.running:
            self._check_node_health()
            time.sleep(10)  # 每10秒检查一次

    def _check_node_health(self):
        """检查所有节点健康状态"""
        current_time = time.time()
        active_count = 0

        for node_id, node in self.nodes.items():
            time_since_heartbeat = current_time - node.last_heartbeat

            # 更新节点状态
            if time_since_heartbeat > self.heartbeat_timeout * 2:
                if node.status != "offline":
                    logger.warning(
                        f"[{self.server_id}] 节点离线: {node_id} "
                        f"(最后心跳: {time_since_heartbeat:.0f}秒前)"
                    )
                    node.status = "offline"
            elif time_since_heartbeat > self.heartbeat_timeout:
                if node.status != "degraded":
                    logger.warning(
                        f"[{self.server_id}] 节点降级: {node_id} "
                        f"(心跳延迟: {time_since_heartbeat:.0f}秒)"
                    )
                    node.status = "degraded"
            else:
                node.status = "active"
                active_count += 1

        self.stats['active_nodes'] = active_count

    def get_global_statistics(self) -> Dict[str, Any]:
        """获取全局统计信息"""
        # 按区域统计
        region_stats = {}
        for region, node_ids in self.node_by_region.items():
            active = sum(
                1 for nid in node_ids
                if self.nodes[nid].status == "active"
            )
            region_stats[region] = {
                'total': len(node_ids),
                'active': active,
                'offline': len(node_ids) - active,
            }

        # Anycast统计
        anycast_stats = {}
        for anycast_ip, node_ids in self.anycast_routing.items():
            anycast_stats[anycast_ip] = {
                'node_count': len(node_ids),
                'regions': list(set(
                    self.nodes[nid].region for nid in node_ids
                )),
            }

        # 威胁情报统计
        threat_by_severity = defaultdict(int)
        for intel in self.threat_intel.values():
            threat_by_severity[intel.severity] += 1

        return {
            'server_id': self.server_id,
            'timestamp': time.time(),
            'nodes': {
                'total': self.stats['total_nodes'],
                'active': self.stats['active_nodes'],
                'offline': self.stats['total_nodes'] - self.stats['active_nodes'],
            },
            'regions': region_stats,
            'anycast': anycast_stats,
            'threat_intel': {
                'total': self.stats['threat_intel_count'],
                'by_severity': dict(threat_by_severity),
            },
            'policies': {
                'total': self.stats['policy_count'],
                'enabled': sum(1 for p in self.policies.values() if p.enabled),
            },
            'heartbeats': self.stats['total_heartbeats'],
        }

    def get_anycast_routing_table(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取Anycast路由表

        返回:
            {anycast_ip: [node_info, ...]}
        """
        routing_table = {}

        for anycast_ip, node_ids in self.anycast_routing.items():
            routing_table[anycast_ip] = [
                {
                    'node_id': nid,
                    'region': self.nodes[nid].region,
                    'ip_address': self.nodes[nid].ip_address,
                    'weight': self.nodes[nid].weight,
                    'status': self.nodes[nid].status,
                }
                for nid in node_ids
            ]

        return routing_table


# 与HIDRS集成接口
class HIDRSIntegration:
    """
    HIDRS系统集成接口

    功能：
    1. 保护HIDRS爬虫节点
    2. 过滤恶意流量
    3. 威胁情报共享
    """

    def __init__(self, root_server: AEGISRootServer):
        """
        初始化HIDRS集成

        参数:
            root_server: AEGIS根服务器实例
        """
        self.root_server = root_server
        logger.info("[HIDRS Integration] 初始化HIDRS集成接口")

    def register_hidrs_crawler(
        self,
        crawler_id: str,
        crawler_type: str,
        target_domains: List[str]
    ) -> Dict[str, Any]:
        """
        注册HIDRS爬虫节点

        参数:
            crawler_id: 爬虫ID
            crawler_type: 爬虫类型（wikipedia, bilibili等）
            target_domains: 目标域名列表

        返回:
            保护配置
        """
        logger.info(
            f"[HIDRS Integration] 注册爬虫: {crawler_id} "
            f"(类型: {crawler_type}, 域名: {len(target_domains)}个)"
        )

        # 为爬虫创建专用保护策略
        policy_id = self.root_server.deploy_policy(
            policy_name=f"HIDRS Crawler Protection: {crawler_id}",
            policy_type="crawler_protection",
            config={
                'crawler_id': crawler_id,
                'crawler_type': crawler_type,
                'allowed_domains': target_domains,
                'rate_limit': {
                    'requests_per_second': 100,
                    'burst': 200,
                },
                'user_agent_validation': True,
                'geo_restrictions': [],  # 空=无限制
            },
            target_nodes=[],  # 全局应用
        )

        return {
            'success': True,
            'crawler_id': crawler_id,
            'policy_id': policy_id,
            'protection_level': 'HIGH',
        }

    def report_crawler_attack(
        self,
        crawler_id: str,
        attacker_ip: str,
        attack_type: str,
        severity: str = "HIGH"
    ):
        """
        报告针对爬虫的攻击

        参数:
            crawler_id: 爬虫ID
            attacker_ip: 攻击者IP
            attack_type: 攻击类型
            severity: 严重性
        """
        logger.warning(
            f"[HIDRS Integration] 爬虫攻击: {crawler_id} "
            f"<- {attacker_ip} (类型: {attack_type})"
        )

        # 报告到根服务器
        self.root_server.report_threat_intel(
            node_id=f"hidrs-{crawler_id}",
            threat_type="crawler_attack",
            target=attacker_ip,
            severity=severity,
            confidence=0.9,
            metadata={
                'crawler_id': crawler_id,
                'attack_type': attack_type,
                'timestamp': time.time(),
            }
        )

    def get_crawler_protection_status(
        self,
        crawler_id: str
    ) -> Dict[str, Any]:
        """
        获取爬虫保护状态

        返回:
            保护状态信息
        """
        return {
            'crawler_id': crawler_id,
            'protected': True,
            'active_threats': 0,  # 简化版
            'blocked_ips': 0,
            'last_attack': None,
        }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("AEGIS根协调服务器演示")
    print("=" * 60)
    print()

    # 创建根服务器
    root_server = AEGISRootServer(
        server_id="AEGIS-ROOT-01",
        anycast_enabled=True,
        heartbeat_timeout=30.0
    )

    root_server.start()

    # 模拟节点注册
    print("\n1. 节点注册")
    print("-" * 60)

    regions = ["us-west", "us-east", "eu-central", "as-east"]
    for i, region in enumerate(regions):
        for j in range(3):  # 每个区域3个节点
            node_id = f"Node-{region.upper()}-{j+1:02d}"
            result = root_server.register_node(
                node_id=node_id,
                region=region,
                ip_address=f"10.{i}.{j}.1",
                capabilities=["fast_filters", "hlig", "sosa"],
                version="1.0.0"
            )
            print(f"  注册成功: {node_id} (Anycast: {result['anycast_address']})")

    # 显示Anycast路由表
    print("\n2. Anycast路由表")
    print("-" * 60)

    routing_table = root_server.get_anycast_routing_table()
    for anycast_ip, nodes in routing_table.items():
        print(f"\n  {anycast_ip}:")
        for node in nodes:
            print(f"    - {node['node_id']} ({node['region']}) - 权重: {node['weight']:.2f}")

    # 模拟威胁情报报告
    print("\n3. 威胁情报上报")
    print("-" * 60)

    intel_id = root_server.report_threat_intel(
        node_id="Node-US-WEST-01",
        threat_type="ip_blacklist",
        target="45.123.67.89",
        severity="CRITICAL",
        confidence=0.95,
        metadata={'attack_type': 'DDoS'}
    )
    print(f"  情报ID: {intel_id}")

    # 多个节点确认同一威胁
    for node_id in ["Node-US-EAST-01", "Node-EU-CENTRAL-01"]:
        root_server.report_threat_intel(
            node_id=node_id,
            threat_type="ip_blacklist",
            target="45.123.67.89",
            severity="CRITICAL",
            confidence=0.90,
        )

    # 部署全局策略
    print("\n4. 全局策略部署")
    print("-" * 60)

    policy_id = root_server.deploy_policy(
        policy_name="Global DDoS Protection",
        policy_type="rate_limit",
        config={
            'max_requests_per_second': 1000,
            'burst_size': 2000,
            'block_duration': 3600,
        }
    )
    print(f"  策略ID: {policy_id}")

    # HIDRS集成
    print("\n5. HIDRS集成")
    print("-" * 60)

    hidrs = HIDRSIntegration(root_server)

    # 注册爬虫
    result = hidrs.register_hidrs_crawler(
        crawler_id="wiki-crawler-01",
        crawler_type="wikipedia",
        target_domains=["*.wikipedia.org"]
    )
    print(f"  爬虫注册: {result['crawler_id']}")
    print(f"  保护策略: {result['policy_id']}")

    # 报告攻击
    hidrs.report_crawler_attack(
        crawler_id="wiki-crawler-01",
        attacker_ip="192.168.1.100",
        attack_type="rate_limit_exceeded"
    )

    # 全局统计
    print("\n6. 全局统计")
    print("-" * 60)

    stats = root_server.get_global_statistics()
    print(f"  总节点数: {stats['nodes']['total']}")
    print(f"  活跃节点: {stats['nodes']['active']}")
    print(f"  威胁情报: {stats['threat_intel']['total']}")
    print(f"  全局策略: {stats['policies']['total']}")
    print(f"\n  区域分布:")
    for region, region_stats in stats['regions'].items():
        print(f"    {region}: {region_stats['active']}/{region_stats['total']} 活跃")

    print("\n" + "=" * 60)
    print("演示完成！")
    print("=" * 60)

    root_server.stop()
