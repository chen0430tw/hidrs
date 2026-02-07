"""
AEGIS-HIDRS C&C服务器检测系统
Command & Control Server Detection System

功能：
1. 僵尸网络拓扑分析
2. 周期性通信检测
3. 关联节点识别
4. C&C行为特征匹配
5. 僵尸主机指纹追踪

检测原理：
- C&C服务器特征：
  1. 多个客户端连接到同一服务器（集中式）
  2. 周期性心跳通信（300秒、600秒等固定间隔）
  3. 小数据包通信（命令传递）
  4. 异常端口使用（非标准端口）
  5. 相似的行为模式（僵尸节点）

- 拓扑分析：
  1. 构建连接图谱
  2. 计算节点中心性（Degree Centrality）
  3. 识别异常高中心性节点
  4. 验证节点是否为C&C

By: Claude + 430
"""

import logging
import time
import math
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ConnectionEvent:
    """连接事件"""
    timestamp: float
    src_ip: str
    dst_ip: str
    dst_port: int
    packet_size: int
    protocol: str = 'tcp'


@dataclass
class BotProfile:
    """僵尸主机画像"""
    ip: str
    first_seen: datetime
    last_seen: datetime
    connection_count: int
    heartbeat_intervals: List[float] = field(default_factory=list)
    contacted_servers: Set[str] = field(default_factory=set)
    behavior_fingerprint: Optional[str] = None

    # 行为特征
    avg_packet_size: float = 0.0
    avg_interval: float = 0.0
    preferred_ports: List[int] = field(default_factory=list)

    # 可疑度评分 (0-100)
    suspicion_score: float = 0.0


@dataclass
class CCServerCandidate:
    """C&C服务器候选"""
    ip: str
    port: int
    first_seen: datetime
    last_seen: datetime

    # 连接特征
    connected_clients: Set[str] = field(default_factory=set)  # 连接的客户端IP
    connection_count: int = 0
    total_traffic_bytes: int = 0

    # 行为特征
    avg_client_packet_size: float = 0.0
    heartbeat_pattern_detected: bool = False
    heartbeat_interval: Optional[float] = None  # 心跳间隔（秒）

    # 拓扑特征
    degree_centrality: float = 0.0  # 节点中心性
    clustering_coefficient: float = 0.0  # 聚类系数

    # C&C评分 (0-100)
    cc_score: float = 0.0
    confidence: float = 0.0  # 置信度

    # 检测依据
    detection_reasons: List[str] = field(default_factory=list)


class CCServerDetector:
    """
    C&C服务器检测器

    检测算法：
    1. 连接图谱分析 - 识别集中式连接节点
    2. 周期性通信检测 - 识别心跳模式
    3. 行为特征匹配 - 识别僵尸主机行为
    4. 拓扑异常检测 - 识别异常高中心性节点
    """

    # C&C检测阈值
    MIN_CLIENTS_THRESHOLD = 10  # 最少客户端数（集中式特征）
    HEARTBEAT_TOLERANCE = 0.15  # 心跳间隔容差（15%）
    CENTRALITY_THRESHOLD = 0.7  # 中心性阈值
    CC_SCORE_THRESHOLD = 60.0  # C&C评分阈值

    # 常见C&C端口
    COMMON_CC_PORTS = {
        6667, 6668, 6669,  # IRC
        1337, 31337,       # 常见后门
        8080, 8443,        # HTTP代理
        4444, 5555,        # 常见远控
        1234, 12345,       # Netbus等
    }

    def __init__(
        self,
        detection_window: float = 3600.0,  # 检测时间窗口（秒）
        min_clients: int = 10,  # 最少客户端数
        heartbeat_ranges: List[Tuple[float, float]] = None  # 心跳间隔范围
    ):
        """
        初始化C&C检测器

        参数:
            detection_window: 检测时间窗口（秒）
            min_clients: 判定C&C的最小客户端数
            heartbeat_ranges: 心跳间隔范围列表 [(min, max), ...]
        """
        self.detection_window = detection_window
        self.min_clients = min_clients

        # 默认心跳间隔范围（秒）
        self.heartbeat_ranges = heartbeat_ranges or [
            (290, 310),    # ~300秒（5分钟）
            (590, 610),    # ~600秒（10分钟）
            (890, 910),    # ~900秒（15分钟）
            (1790, 1810),  # ~1800秒（30分钟）
        ]

        # 连接事件存储
        self.connection_events: List[ConnectionEvent] = []

        # 连接图谱（邻接表）
        self.connection_graph: Dict[str, Set[str]] = defaultdict(set)  # src -> {dst, ...}

        # 服务器候选列表
        self.server_candidates: Dict[Tuple[str, int], CCServerCandidate] = {}

        # 僵尸主机列表
        self.bot_profiles: Dict[str, BotProfile] = {}

        # 已确认的C&C服务器
        self.confirmed_cc_servers: Dict[Tuple[str, int], CCServerCandidate] = {}

        # 统计
        self.stats = {
            'total_events': 0,
            'cc_servers_detected': 0,
            'bots_detected': 0,
            'total_checks': 0,
        }

    def add_connection(
        self,
        src_ip: str,
        dst_ip: str,
        dst_port: int,
        packet_size: int,
        timestamp: Optional[float] = None,
        protocol: str = 'tcp'
    ):
        """
        添加连接事件

        参数:
            src_ip: 源IP
            dst_ip: 目标IP
            dst_port: 目标端口
            packet_size: 数据包大小
            timestamp: 时间戳（可选）
            protocol: 协议
        """
        if timestamp is None:
            timestamp = time.time()

        event = ConnectionEvent(
            timestamp=timestamp,
            src_ip=src_ip,
            dst_ip=dst_ip,
            dst_port=dst_port,
            packet_size=packet_size,
            protocol=protocol
        )

        self.connection_events.append(event)
        self.stats['total_events'] += 1

        # 更新连接图谱
        self.connection_graph[src_ip].add(dst_ip)

        # 更新服务器候选
        self._update_server_candidate(event)

        # 更新僵尸主机画像
        self._update_bot_profile(event)

        # 清理过期事件
        self._cleanup_old_events()

    def _update_server_candidate(self, event: ConnectionEvent):
        """更新服务器候选信息"""
        server_key = (event.dst_ip, event.dst_port)

        if server_key not in self.server_candidates:
            self.server_candidates[server_key] = CCServerCandidate(
                ip=event.dst_ip,
                port=event.dst_port,
                first_seen=datetime.fromtimestamp(event.timestamp),
                last_seen=datetime.fromtimestamp(event.timestamp),
            )

        candidate = self.server_candidates[server_key]
        candidate.connected_clients.add(event.src_ip)
        candidate.connection_count += 1
        candidate.total_traffic_bytes += event.packet_size
        candidate.last_seen = datetime.fromtimestamp(event.timestamp)

        # 更新平均包大小
        candidate.avg_client_packet_size = (
            candidate.total_traffic_bytes / candidate.connection_count
        )

    def _update_bot_profile(self, event: ConnectionEvent):
        """更新僵尸主机画像"""
        if event.src_ip not in self.bot_profiles:
            self.bot_profiles[event.src_ip] = BotProfile(
                ip=event.src_ip,
                first_seen=datetime.fromtimestamp(event.timestamp),
                last_seen=datetime.fromtimestamp(event.timestamp),
                connection_count=0,
            )

        bot = self.bot_profiles[event.src_ip]
        bot.connection_count += 1
        bot.contacted_servers.add(f"{event.dst_ip}:{event.dst_port}")
        bot.last_seen = datetime.fromtimestamp(event.timestamp)

        # 记录端口偏好
        bot.preferred_ports.append(event.dst_port)

    def _cleanup_old_events(self):
        """清理过期的连接事件"""
        current_time = time.time()
        cutoff_time = current_time - self.detection_window

        # 移除过期事件
        self.connection_events = [
            event for event in self.connection_events
            if event.timestamp >= cutoff_time
        ]

    def detect_heartbeat_pattern(
        self,
        src_ip: str,
        dst_ip: str,
        dst_port: int
    ) -> Tuple[bool, Optional[float]]:
        """
        检测心跳模式

        返回:
            (is_heartbeat, interval) - 是否检测到心跳，心跳间隔
        """
        # 提取特定连接的事件
        events = [
            e for e in self.connection_events
            if e.src_ip == src_ip and e.dst_ip == dst_ip and e.dst_port == dst_port
        ]

        if len(events) < 5:  # 至少5次连接才能判断
            return False, None

        # 计算间隔
        timestamps = sorted([e.timestamp for e in events])
        intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]

        if not intervals:
            return False, None

        # 计算平均间隔和标准差
        avg_interval = np.mean(intervals)
        std_interval = np.std(intervals)

        # 检查是否在心跳范围内
        for min_interval, max_interval in self.heartbeat_ranges:
            if min_interval <= avg_interval <= max_interval:
                # 检查标准差（周期性）
                tolerance = avg_interval * self.HEARTBEAT_TOLERANCE
                if std_interval <= tolerance:
                    return True, avg_interval

        return False, None

    def calculate_degree_centrality(self, node: str) -> float:
        """
        计算节点中心性

        Degree Centrality = 节点度数 / (总节点数 - 1)
        """
        if not self.connection_graph:
            return 0.0

        # 统计所有节点
        all_nodes = set()
        for src, dsts in self.connection_graph.items():
            all_nodes.add(src)
            all_nodes.update(dsts)

        total_nodes = len(all_nodes)
        if total_nodes <= 1:
            return 0.0

        # 入度（多少个节点连接到该节点）
        in_degree = sum(1 for src, dsts in self.connection_graph.items() if node in dsts)

        # 出度（该节点连接到多少个节点）
        out_degree = len(self.connection_graph.get(node, set()))

        # 总度数
        degree = in_degree + out_degree

        # 归一化
        centrality = degree / (total_nodes - 1)

        return centrality

    def analyze_cc_candidates(self) -> List[CCServerCandidate]:
        """
        分析C&C服务器候选

        返回:
            检测到的C&C服务器列表
        """
        self.stats['total_checks'] += 1
        detected_cc_servers = []

        for server_key, candidate in self.server_candidates.items():
            # 重置评分
            candidate.cc_score = 0.0
            candidate.detection_reasons = []

            # 1. 客户端数量检查（集中式特征）
            client_count = len(candidate.connected_clients)
            if client_count >= self.min_clients:
                score = min(30.0, (client_count / self.min_clients) * 15.0)
                candidate.cc_score += score
                candidate.detection_reasons.append(
                    f"集中式连接: {client_count}个客户端"
                )

            # 2. 端口检查
            if candidate.port in self.COMMON_CC_PORTS:
                candidate.cc_score += 15.0
                candidate.detection_reasons.append(
                    f"可疑端口: {candidate.port}"
                )

            # 3. 心跳模式检查
            heartbeat_count = 0
            for client_ip in list(candidate.connected_clients)[:20]:  # 采样前20个
                is_heartbeat, interval = self.detect_heartbeat_pattern(
                    src_ip=client_ip,
                    dst_ip=candidate.ip,
                    dst_port=candidate.port
                )
                if is_heartbeat:
                    heartbeat_count += 1
                    candidate.heartbeat_interval = interval

            if heartbeat_count >= 3:  # 至少3个客户端有心跳
                candidate.heartbeat_pattern_detected = True
                candidate.cc_score += 25.0
                candidate.detection_reasons.append(
                    f"周期性心跳: {heartbeat_count}个客户端 (间隔: {candidate.heartbeat_interval:.0f}秒)"
                )

            # 4. 小包通信检查（命令传递）
            if 0 < candidate.avg_client_packet_size < 200:
                candidate.cc_score += 10.0
                candidate.detection_reasons.append(
                    f"小包通信: 平均{candidate.avg_client_packet_size:.0f}字节"
                )

            # 5. 节点中心性检查
            centrality = self.calculate_degree_centrality(candidate.ip)
            candidate.degree_centrality = centrality
            if centrality >= self.CENTRALITY_THRESHOLD:
                candidate.cc_score += 20.0
                candidate.detection_reasons.append(
                    f"高中心性节点: {centrality:.2f}"
                )

            # 6. 计算置信度
            candidate.confidence = min(1.0, candidate.cc_score / 100.0)

            # 判定为C&C服务器
            if candidate.cc_score >= self.CC_SCORE_THRESHOLD:
                detected_cc_servers.append(candidate)
                self.confirmed_cc_servers[server_key] = candidate
                self.stats['cc_servers_detected'] += 1

                logger.warning(
                    f"[C&C检测] 识别出C&C服务器: {candidate.ip}:{candidate.port} "
                    f"(评分: {candidate.cc_score:.1f}, 客户端: {len(candidate.connected_clients)})"
                )

        return detected_cc_servers

    def identify_bot_network(
        self,
        cc_server_ip: str,
        cc_server_port: int
    ) -> List[BotProfile]:
        """
        识别与特定C&C服务器关联的僵尸网络

        返回:
            僵尸主机列表
        """
        server_key = (cc_server_ip, cc_server_port)
        if server_key not in self.confirmed_cc_servers:
            return []

        candidate = self.confirmed_cc_servers[server_key]
        bot_network = []

        for client_ip in candidate.connected_clients:
            if client_ip in self.bot_profiles:
                bot = self.bot_profiles[client_ip]

                # 计算可疑度
                bot.suspicion_score = 0.0

                # 1. 只连接少数服务器（僵尸特征）
                if len(bot.contacted_servers) <= 3:
                    bot.suspicion_score += 30.0

                # 2. 有心跳通信
                is_heartbeat, _ = self.detect_heartbeat_pattern(
                    src_ip=client_ip,
                    dst_ip=cc_server_ip,
                    dst_port=cc_server_port
                )
                if is_heartbeat:
                    bot.suspicion_score += 40.0

                # 3. 行为单一（端口偏好集中）
                if bot.preferred_ports:
                    port_counter = Counter(bot.preferred_ports)
                    most_common_ratio = port_counter.most_common(1)[0][1] / len(bot.preferred_ports)
                    if most_common_ratio > 0.8:
                        bot.suspicion_score += 30.0

                bot_network.append(bot)
                self.stats['bots_detected'] += 1

        return bot_network

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'total_events': self.stats['total_events'],
            'total_checks': self.stats['total_checks'],
            'cc_servers_detected': self.stats['cc_servers_detected'],
            'bots_detected': self.stats['bots_detected'],
            'server_candidates': len(self.server_candidates),
            'bot_profiles': len(self.bot_profiles),
            'confirmed_cc_servers': len(self.confirmed_cc_servers),
        }

    def get_cc_report(self) -> Dict[str, Any]:
        """
        生成C&C检测报告

        返回:
            包含所有C&C服务器和僵尸网络信息的报告
        """
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'statistics': self.get_statistics(),
            'cc_servers': [],
        }

        for server_key, candidate in self.confirmed_cc_servers.items():
            # 识别僵尸网络
            bot_network = self.identify_bot_network(
                cc_server_ip=candidate.ip,
                cc_server_port=candidate.port
            )

            server_report = {
                'ip': candidate.ip,
                'port': candidate.port,
                'cc_score': candidate.cc_score,
                'confidence': candidate.confidence,
                'connected_clients': len(candidate.connected_clients),
                'bot_network_size': len(bot_network),
                'heartbeat_detected': candidate.heartbeat_pattern_detected,
                'heartbeat_interval': candidate.heartbeat_interval,
                'degree_centrality': candidate.degree_centrality,
                'detection_reasons': candidate.detection_reasons,
                'first_seen': candidate.first_seen.isoformat(),
                'last_seen': candidate.last_seen.isoformat(),
            }

            report['cc_servers'].append(server_report)

        return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("AEGIS-HIDRS C&C服务器检测系统测试")
    print("=" * 60)
    print()

    # 创建检测器
    detector = CCServerDetector(
        detection_window=3600.0,
        min_clients=5  # 降低阈值以便测试
    )

    # 模拟僵尸网络通信
    print("模拟僵尸网络流量...")

    cc_server = "45.123.67.89"
    cc_port = 4444
    bot_ips = [f"192.168.1.{i}" for i in range(10, 30)]  # 20个僵尸主机

    # 模拟周期性心跳（每300秒）
    base_time = time.time()
    for cycle in range(6):  # 6个周期
        timestamp = base_time + cycle * 300  # 300秒间隔
        for bot_ip in bot_ips:
            detector.add_connection(
                src_ip=bot_ip,
                dst_ip=cc_server,
                dst_port=cc_port,
                packet_size=64,  # 小包通信
                timestamp=timestamp
            )

    print(f"  生成了 {detector.stats['total_events']} 个连接事件")
    print()

    # 执行C&C检测
    print("执行C&C服务器分析...")
    cc_servers = detector.analyze_cc_candidates()

    print(f"  检测到 {len(cc_servers)} 个C&C服务器")
    print()

    # 显示检测结果
    if cc_servers:
        for candidate in cc_servers:
            print(f"🚨 C&C服务器: {candidate.ip}:{candidate.port}")
            print(f"  ├─ C&C评分: {candidate.cc_score:.1f}/100")
            print(f"  ├─ 置信度: {candidate.confidence:.2%}")
            print(f"  ├─ 关联客户端: {len(candidate.connected_clients)}个")
            print(f"  ├─ 节点中心性: {candidate.degree_centrality:.2f}")
            print(f"  ├─ 心跳检测: {'✅ ' if candidate.heartbeat_pattern_detected else '❌ '}")
            if candidate.heartbeat_interval:
                print(f"  ├─ 心跳间隔: {candidate.heartbeat_interval:.0f}秒")
            print(f"  └─ 检测依据:")
            for reason in candidate.detection_reasons:
                print(f"      - {reason}")
            print()

            # 识别僵尸网络
            print(f"  僵尸网络分析:")
            bots = detector.identify_bot_network(candidate.ip, candidate.port)
            print(f"  ├─ 僵尸主机数: {len(bots)}个")
            if bots:
                print(f"  └─ 示例僵尸主机:")
                for bot in bots[:5]:
                    print(f"      - {bot.ip} (可疑度: {bot.suspicion_score:.1f})")
            print()

    # 生成报告
    print("生成检测报告...")
    report = detector.get_cc_report()

    print(f"  总事件数: {report['statistics']['total_events']}")
    print(f"  检测到C&C服务器: {report['statistics']['cc_servers_detected']}个")
    print(f"  识别出僵尸主机: {report['statistics']['bots_detected']}个")
    print()

    print("=" * 60)
    print("测试完成！")
    print("=" * 60)
