"""
节点管理器 - 发现和管理分布式计算节点

功能：
1. P2P节点发现（类似BitTorrent DHT）
2. 节点注册和心跳检测
3. 节点状态监控
4. 动态节点池维护

节点发现策略：
- 本地局域网广播（UDP）
- DHT分布式哈希表（Kademlia协议）
- 已知节点列表（Bootstrap节点）
- 社交发现（可选，如果用户授权）
"""
import logging
import socket
import threading
import time
import json
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class NodeStatus(Enum):
    """节点状态"""
    UNKNOWN = "unknown"          # 未知
    DISCOVERING = "discovering"  # 发现中
    ONLINE = "online"            # 在线
    BUSY = "busy"                # 忙碌
    OFFLINE = "offline"          # 离线
    TIMEOUT = "timeout"          # 超时


@dataclass
class ComputeNode:
    """计算节点"""
    node_id: str                          # 节点ID（唯一标识）
    host: str                             # IP地址
    port: int                             # 端口
    status: NodeStatus = NodeStatus.UNKNOWN

    # 算力信息
    cpu_cores: int = 0
    cpu_freq_mhz: float = 0.0
    memory_gb: float = 0.0
    gpu_count: int = 0
    gpu_memory_gb: float = 0.0

    # 网络信息
    bandwidth_mbps: float = 0.0
    latency_ms: float = 0.0

    # 状态信息
    last_seen: Optional[datetime] = None
    uptime_seconds: float = 0.0
    tasks_completed: int = 0
    tasks_failed: int = 0

    # HLIG相关（稍后由算力分析器填充）
    capability_score: float = 0.0         # 综合算力得分
    fiedler_score: float = 0.0            # Fiedler向量分量
    is_key_node: bool = False             # 是否为关键节点

    # 元数据
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """转换为字典"""
        data = asdict(self)
        data['status'] = self.status.value
        data['last_seen'] = self.last_seen.isoformat() if self.last_seen else None
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> 'ComputeNode':
        """从字典创建"""
        data = data.copy()
        data['status'] = NodeStatus(data.get('status', 'unknown'))
        if data.get('last_seen'):
            data['last_seen'] = datetime.fromisoformat(data['last_seen'])
        return cls(**data)

    def __hash__(self):
        return hash(self.node_id)

    def __eq__(self, other):
        return isinstance(other, ComputeNode) and self.node_id == other.node_id


class NodeManager:
    """节点管理器 - 发现和管理计算节点"""

    def __init__(
        self,
        listen_port: int = 9876,
        heartbeat_interval: int = 30,
        node_timeout: int = 120,
        enable_lan_discovery: bool = True,
        enable_dht: bool = False,  # DHT暂未实现
        bootstrap_nodes: Optional[List[str]] = None
    ):
        """
        初始化节点管理器

        参数:
        - listen_port: 监听端口
        - heartbeat_interval: 心跳间隔（秒）
        - node_timeout: 节点超时时间（秒）
        - enable_lan_discovery: 启用局域网发现
        - enable_dht: 启用DHT（分布式哈希表）
        - bootstrap_nodes: Bootstrap节点列表 ["host:port", ...]
        """
        self.listen_port = listen_port
        self.heartbeat_interval = heartbeat_interval
        self.node_timeout = node_timeout
        self.enable_lan_discovery = enable_lan_discovery
        self.enable_dht = enable_dht
        self.bootstrap_nodes = bootstrap_nodes or []

        # 节点池
        self.nodes: Dict[str, ComputeNode] = {}
        self.nodes_lock = threading.RLock()

        # 服务线程
        self._udp_socket: Optional[socket.socket] = None
        self._discovery_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._running = False

        logger.info("[NodeManager] 初始化完成")
        logger.info(f"  监听端口: {listen_port}")
        logger.info(f"  心跳间隔: {heartbeat_interval}秒")
        logger.info(f"  节点超时: {node_timeout}秒")
        logger.info(f"  局域网发现: {'启用' if enable_lan_discovery else '禁用'}")
        logger.info(f"  DHT: {'启用' if enable_dht else '禁用（未实现）'}")

    def start(self):
        """启动节点管理器"""
        if self._running:
            logger.warning("[NodeManager] 已经在运行")
            return

        self._running = True

        # 启动UDP监听（用于局域网发现）
        if self.enable_lan_discovery:
            self._start_udp_listener()

        # 启动心跳线程
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        # 启动发现线程
        if self.enable_lan_discovery:
            self._discovery_thread = threading.Thread(target=self._discovery_loop, daemon=True)
            self._discovery_thread.start()

        # 连接Bootstrap节点
        self._connect_bootstrap_nodes()

        logger.info("[NodeManager] 启动成功")

    def stop(self):
        """停止节点管理器"""
        self._running = False

        # 关闭UDP socket
        if self._udp_socket:
            self._udp_socket.close()

        logger.info("[NodeManager] 已停止")

    def _start_udp_listener(self):
        """启动UDP监听"""
        try:
            self._udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._udp_socket.bind(('0.0.0.0', self.listen_port))
            self._udp_socket.settimeout(5.0)

            # 启动接收线程
            listener_thread = threading.Thread(target=self._udp_receive_loop, daemon=True)
            listener_thread.start()

            logger.info(f"[NodeManager] UDP监听启动: 0.0.0.0:{self.listen_port}")
        except Exception as e:
            logger.error(f"[NodeManager] UDP监听启动失败: {e}")

    def _udp_receive_loop(self):
        """UDP接收循环"""
        while self._running:
            try:
                data, addr = self._udp_socket.recvfrom(4096)
                self._handle_udp_message(data, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.error(f"[NodeManager] UDP接收错误: {e}")

    def _handle_udp_message(self, data: bytes, addr: tuple):
        """处理UDP消息"""
        try:
            message = json.loads(data.decode('utf-8'))
            msg_type = message.get('type')

            if msg_type == 'discover':
                # 发现请求 - 回复自己的信息
                self._send_node_info(addr[0], addr[1])
                logger.debug(f"[NodeManager] 收到发现请求: {addr[0]}:{addr[1]}")

            elif msg_type == 'node_info':
                # 节点信息 - 注册节点
                node_data = message.get('node')
                if node_data:
                    node = ComputeNode.from_dict(node_data)
                    self.register_node(node)
                    logger.debug(f"[NodeManager] 发现节点: {node.node_id}")

            elif msg_type == 'heartbeat':
                # 心跳 - 更新节点状态
                node_id = message.get('node_id')
                if node_id and node_id in self.nodes:
                    with self.nodes_lock:
                        self.nodes[node_id].last_seen = datetime.now()
                        self.nodes[node_id].status = NodeStatus.ONLINE

        except Exception as e:
            logger.error(f"[NodeManager] 处理UDP消息失败: {e}")

    def _send_node_info(self, host: str, port: int):
        """发送本节点信息"""
        try:
            # 获取本机信息（简化版）
            local_node = self._get_local_node_info()

            message = {
                'type': 'node_info',
                'node': local_node.to_dict()
            }

            data = json.dumps(message).encode('utf-8')
            self._udp_socket.sendto(data, (host, port))

        except Exception as e:
            logger.error(f"[NodeManager] 发送节点信息失败: {e}")

    def _get_local_node_info(self) -> ComputeNode:
        """获取本地节点信息"""
        import uuid
        import psutil

        # 生成节点ID
        node_id = f"node_{uuid.uuid4().hex[:8]}"

        # 获取主机名和IP
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)

        # 获取系统信息
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()
        mem = psutil.virtual_memory()

        node = ComputeNode(
            node_id=node_id,
            host=local_ip,
            port=self.listen_port,
            status=NodeStatus.ONLINE,
            cpu_cores=cpu_count,
            cpu_freq_mhz=cpu_freq.current if cpu_freq else 0,
            memory_gb=mem.total / (1024**3),
            last_seen=datetime.now()
        )

        return node

    def _discovery_loop(self):
        """节点发现循环"""
        while self._running:
            try:
                # 局域网广播发现
                self._broadcast_discover()

                # 等待一段时间
                time.sleep(60)  # 每分钟发现一次

            except Exception as e:
                logger.error(f"[NodeManager] 发现循环错误: {e}")

    def _broadcast_discover(self):
        """广播发现消息"""
        try:
            message = {'type': 'discover'}
            data = json.dumps(message).encode('utf-8')

            # 广播到255.255.255.255
            broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            broadcast_socket.sendto(data, ('<broadcast>', self.listen_port))
            broadcast_socket.close()

            logger.debug("[NodeManager] 广播发现消息")

        except Exception as e:
            logger.error(f"[NodeManager] 广播失败: {e}")

    def _heartbeat_loop(self):
        """心跳循环"""
        while self._running:
            try:
                # 发送心跳到所有节点
                self._send_heartbeats()

                # 检查超时节点
                self._check_timeouts()

                # 等待心跳间隔
                time.sleep(self.heartbeat_interval)

            except Exception as e:
                logger.error(f"[NodeManager] 心跳循环错误: {e}")

    def _send_heartbeats(self):
        """发送心跳"""
        with self.nodes_lock:
            local_node = self._get_local_node_info()
            message = {
                'type': 'heartbeat',
                'node_id': local_node.node_id
            }
            data = json.dumps(message).encode('utf-8')

            for node in self.nodes.values():
                if node.status == NodeStatus.ONLINE:
                    try:
                        self._udp_socket.sendto(data, (node.host, node.port))
                    except Exception as e:
                        logger.debug(f"[NodeManager] 发送心跳失败到 {node.node_id}: {e}")

    def _check_timeouts(self):
        """检查超时节点"""
        now = datetime.now()
        with self.nodes_lock:
            for node in self.nodes.values():
                if node.last_seen:
                    elapsed = (now - node.last_seen).total_seconds()
                    if elapsed > self.node_timeout:
                        node.status = NodeStatus.TIMEOUT
                        logger.warning(f"[NodeManager] 节点超时: {node.node_id}")

    def _connect_bootstrap_nodes(self):
        """连接Bootstrap节点"""
        for bootstrap in self.bootstrap_nodes:
            try:
                host, port = bootstrap.split(':')
                port = int(port)

                # 发送发现消息
                message = {'type': 'discover'}
                data = json.dumps(message).encode('utf-8')
                self._udp_socket.sendto(data, (host, port))

                logger.info(f"[NodeManager] 连接Bootstrap节点: {host}:{port}")

            except Exception as e:
                logger.error(f"[NodeManager] 连接Bootstrap节点失败 {bootstrap}: {e}")

    def register_node(self, node: ComputeNode):
        """注册节点"""
        with self.nodes_lock:
            node.last_seen = datetime.now()
            self.nodes[node.node_id] = node
            logger.info(f"[NodeManager] 注册节点: {node.node_id} ({node.host}:{node.port})")

    def unregister_node(self, node_id: str):
        """注销节点"""
        with self.nodes_lock:
            if node_id in self.nodes:
                del self.nodes[node_id]
                logger.info(f"[NodeManager] 注销节点: {node_id}")

    def get_node(self, node_id: str) -> Optional[ComputeNode]:
        """获取节点"""
        with self.nodes_lock:
            return self.nodes.get(node_id)

    def get_all_nodes(self) -> List[ComputeNode]:
        """获取所有节点"""
        with self.nodes_lock:
            return list(self.nodes.values())

    def get_online_nodes(self) -> List[ComputeNode]:
        """获取在线节点"""
        with self.nodes_lock:
            return [node for node in self.nodes.values()
                   if node.status == NodeStatus.ONLINE]

    def get_available_nodes(self) -> List[ComputeNode]:
        """获取可用节点（在线且不忙碌）"""
        with self.nodes_lock:
            return [node for node in self.nodes.values()
                   if node.status in [NodeStatus.ONLINE]]

    def update_node_status(self, node_id: str, status: NodeStatus):
        """更新节点状态"""
        with self.nodes_lock:
            if node_id in self.nodes:
                self.nodes[node_id].status = status
                logger.debug(f"[NodeManager] 更新节点状态: {node_id} -> {status.value}")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self.nodes_lock:
            total = len(self.nodes)
            online = sum(1 for n in self.nodes.values() if n.status == NodeStatus.ONLINE)
            busy = sum(1 for n in self.nodes.values() if n.status == NodeStatus.BUSY)
            offline = sum(1 for n in self.nodes.values() if n.status in [NodeStatus.OFFLINE, NodeStatus.TIMEOUT])

            # 总算力
            total_cpu_cores = sum(n.cpu_cores for n in self.nodes.values())
            total_memory_gb = sum(n.memory_gb for n in self.nodes.values())
            total_gpu_count = sum(n.gpu_count for n in self.nodes.values())

            return {
                'total_nodes': total,
                'online_nodes': online,
                'busy_nodes': busy,
                'offline_nodes': offline,
                'available_nodes': online - busy,
                'total_cpu_cores': total_cpu_cores,
                'total_memory_gb': total_memory_gb,
                'total_gpu_count': total_gpu_count,
                'key_nodes': sum(1 for n in self.nodes.values() if n.is_key_node)
            }
