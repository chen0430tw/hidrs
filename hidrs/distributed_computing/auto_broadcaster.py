"""
自动广播器 - 检测到网络就自动广播节点信息

核心功能：
1. 监听网络连接事件
2. 自动广播节点存在
3. 通知其他HIDRS节点更新拓扑
4. 处理节点退出

广播策略：
- 立即广播：网络连接后3秒内
- 心跳广播：每30秒一次
- 退出广播：断开前通知其他节点

广播内容：
- 节点ID和地址
- 算力信息（CPU/GPU/内存）
- 网络信息（带宽/延迟）
- 服务端口

这是HIDRS自举系统的核心：
新节点 → 检测网络 → 自动广播 → 加入拓扑 → 贡献算力 → 帮助其他节点
"""
import logging
import socket
import json
import threading
import time
from typing import Optional, Dict, List, Callable
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class BroadcastMessage:
    """广播消息"""

    def __init__(
        self,
        message_type: str,
        node_id: str,
        node_info: Dict,
        timestamp: Optional[datetime] = None
    ):
        """
        初始化广播消息

        参数:
        - message_type: 消息类型（join/heartbeat/leave）
        - node_id: 节点ID
        - node_info: 节点信息
        - timestamp: 时间戳
        """
        self.message_type = message_type
        self.node_id = node_id
        self.node_info = node_info
        self.timestamp = timestamp or datetime.now()
        self.message_id = f"msg_{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'message_id': self.message_id,
            'message_type': self.message_type,
            'node_id': self.node_id,
            'node_info': self.node_info,
            'timestamp': self.timestamp.isoformat()
        }

    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> 'BroadcastMessage':
        """从JSON字符串创建"""
        data = json.loads(json_str)
        return cls(
            message_type=data['message_type'],
            node_id=data['node_id'],
            node_info=data['node_info'],
            timestamp=datetime.fromisoformat(data['timestamp'])
        )


class AutoBroadcaster:
    """自动广播器 - 网络连接时自动广播节点"""

    def __init__(
        self,
        node_manager,
        network_detector,
        capability_analyzer,
        broadcast_port: int = 9877,
        heartbeat_interval: int = 30,
        enable_auto_broadcast: bool = True
    ):
        """
        初始化自动广播器

        参数:
        - node_manager: 节点管理器
        - network_detector: 网络检测器
        - capability_analyzer: 算力评估器
        - broadcast_port: 广播端口
        - heartbeat_interval: 心跳间隔（秒）
        - enable_auto_broadcast: 是否启用自动广播
        """
        self.node_manager = node_manager
        self.network_detector = network_detector
        self.capability_analyzer = capability_analyzer
        self.broadcast_port = broadcast_port
        self.heartbeat_interval = heartbeat_interval
        self.enable_auto_broadcast = enable_auto_broadcast

        # 本节点信息
        self.local_node_id = f"node_{uuid.uuid4().hex[:8]}"
        self.local_node_info: Optional[Dict] = None

        # 广播统计
        self.broadcast_count = 0
        self.last_broadcast_time: Optional[datetime] = None

        # 接收到的广播
        self.received_broadcasts: List[BroadcastMessage] = []

        # UDP套接字
        self._udp_socket: Optional[socket.socket] = None
        self._running = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._receiver_thread: Optional[threading.Thread] = None

        # 事件回调
        self.on_node_joined: Optional[Callable] = None
        self.on_node_left: Optional[Callable] = None

        logger.info("[AutoBroadcaster] 初始化完成")
        logger.info(f"  节点ID: {self.local_node_id}")
        logger.info(f"  广播端口: {broadcast_port}")
        logger.info(f"  心跳间隔: {heartbeat_interval}秒")

    def start(self):
        """启动自动广播器"""
        if self._running:
            logger.warning("[AutoBroadcaster] 已在运行")
            return

        if not self.enable_auto_broadcast:
            logger.info("[AutoBroadcaster] 自动广播被禁用")
            return

        # 1. 收集本节点信息
        self._collect_local_node_info()

        # 2. 绑定网络检测事件
        self.network_detector.on_connected = self._on_network_connected
        self.network_detector.on_disconnected = self._on_network_disconnected
        self.network_detector.on_ip_changed = self._on_ip_changed

        # 3. 启动UDP接收
        self._start_udp_receiver()

        # 4. 启动心跳线程
        self._running = True
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        # 5. 如果当前已连接网络，立即广播
        if self.network_detector.is_connected():
            self._broadcast_join()

        logger.info("[AutoBroadcaster] 已启动")

    def stop(self):
        """停止自动广播器"""
        if not self._running:
            return

        # 1. 广播退出消息
        if self.network_detector.is_connected():
            self._broadcast_leave()

        # 2. 停止线程
        self._running = False

        # 3. 关闭套接字
        if self._udp_socket:
            self._udp_socket.close()

        logger.info("[AutoBroadcaster] 已停止")

    def _collect_local_node_info(self):
        """收集本节点信息"""
        try:
            # 分析本地算力
            capability = self.capability_analyzer.analyze_local_node()

            # 获取网络信息
            local_ip = self.network_detector.current_ip or "unknown"
            public_ip = self.network_detector.get_public_ip()

            self.local_node_info = {
                'node_id': self.local_node_id,
                'host': local_ip,
                'public_ip': public_ip,
                'port': self.node_manager.listen_port,
                'broadcast_port': self.broadcast_port,

                # 算力信息
                'cpu_cores': capability.cpu_cores,
                'cpu_freq_mhz': capability.cpu_freq_mhz,
                'memory_gb': capability.memory_total_gb,
                'gpu_count': capability.gpu_count,
                'gpu_memory_gb': capability.gpu_memory_total_gb,

                # 网络信息
                'bandwidth_mbps': capability.bandwidth_mbps,
                'latency_ms': capability.latency_ms,

                # 综合得分
                'capability_score': capability.total_score,

                # 系统信息
                'platform': capability.platform,
                'python_version': capability.python_version,

                # 时间戳
                'joined_at': datetime.now().isoformat()
            }

            logger.info("[AutoBroadcaster] 本节点信息已收集")
            logger.info(f"  IP: {local_ip} (公网: {public_ip})")
            logger.info(f"  算力得分: {capability.total_score:.2f}")

        except Exception as e:
            logger.error(f"[AutoBroadcaster] 收集节点信息失败: {e}")
            self.local_node_info = {
                'node_id': self.local_node_id,
                'host': 'unknown',
                'port': self.node_manager.listen_port
            }

    def _start_udp_receiver(self):
        """启动UDP接收器"""
        try:
            self._udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._udp_socket.bind(('0.0.0.0', self.broadcast_port))
            self._udp_socket.settimeout(5.0)

            # 启动接收线程
            self._receiver_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self._receiver_thread.start()

            logger.info(f"[AutoBroadcaster] UDP接收器已启动: 0.0.0.0:{self.broadcast_port}")

        except Exception as e:
            logger.error(f"[AutoBroadcaster] UDP接收器启动失败: {e}")

    def _receive_loop(self):
        """接收循环"""
        while self._running:
            try:
                data, addr = self._udp_socket.recvfrom(8192)
                self._handle_broadcast_message(data, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.error(f"[AutoBroadcaster] 接收错误: {e}")

    def _handle_broadcast_message(self, data: bytes, addr: tuple):
        """处理接收到的广播消息"""
        try:
            message = BroadcastMessage.from_json(data.decode('utf-8'))

            # 忽略自己的广播
            if message.node_id == self.local_node_id:
                return

            logger.info(f"[AutoBroadcaster] 收到广播: {message.message_type} from {message.node_id} ({addr[0]})")

            # 记录广播
            self.received_broadcasts.append(message)
            if len(self.received_broadcasts) > 1000:
                self.received_broadcasts = self.received_broadcasts[-1000:]

            # 处理不同类型的消息
            if message.message_type == 'join':
                self._handle_node_join(message)
            elif message.message_type == 'heartbeat':
                self._handle_node_heartbeat(message)
            elif message.message_type == 'leave':
                self._handle_node_leave(message)

        except Exception as e:
            logger.error(f"[AutoBroadcaster] 处理广播消息失败: {e}")

    def _handle_node_join(self, message: BroadcastMessage):
        """处理节点加入"""
        logger.info(f"[AutoBroadcaster] 节点加入: {message.node_id}")

        # 创建ComputeNode对象
        from .node_manager import ComputeNode, NodeStatus

        node = ComputeNode(
            node_id=message.node_info.get('node_id'),
            host=message.node_info.get('host', 'unknown'),
            port=message.node_info.get('port', 9876),
            status=NodeStatus.ONLINE,
            cpu_cores=message.node_info.get('cpu_cores', 0),
            cpu_freq_mhz=message.node_info.get('cpu_freq_mhz', 0.0),
            memory_gb=message.node_info.get('memory_gb', 0.0),
            gpu_count=message.node_info.get('gpu_count', 0),
            gpu_memory_gb=message.node_info.get('gpu_memory_gb', 0.0),
            bandwidth_mbps=message.node_info.get('bandwidth_mbps', 0.0),
            latency_ms=message.node_info.get('latency_ms', 0.0),
            capability_score=message.node_info.get('capability_score', 0.0)
        )

        # 注册到节点管理器
        self.node_manager.register_node(node)

        # 触发回调
        if self.on_node_joined:
            threading.Thread(target=lambda: self.on_node_joined(node), daemon=True).start()

    def _handle_node_heartbeat(self, message: BroadcastMessage):
        """处理节点心跳"""
        node_id = message.node_id
        node = self.node_manager.get_node(node_id)

        if node:
            # 更新心跳时间
            from .node_manager import NodeStatus
            node.last_seen = datetime.now()
            node.status = NodeStatus.ONLINE
        else:
            # 新节点（可能是漏掉了join消息）
            self._handle_node_join(message)

    def _handle_node_leave(self, message: BroadcastMessage):
        """处理节点离开"""
        logger.info(f"[AutoBroadcaster] 节点离开: {message.node_id}")

        node = self.node_manager.get_node(message.node_id)

        if node:
            # 标记为离线
            from .node_manager import NodeStatus
            node.status = NodeStatus.OFFLINE

            # 触发回调
            if self.on_node_left:
                threading.Thread(target=lambda: self.on_node_left(node), daemon=True).start()

    def _broadcast_join(self):
        """广播加入消息"""
        message = BroadcastMessage(
            message_type='join',
            node_id=self.local_node_id,
            node_info=self.local_node_info
        )

        self._send_broadcast(message)
        logger.info(f"[AutoBroadcaster] 广播加入: {self.local_node_id}")

    def _broadcast_heartbeat(self):
        """广播心跳消息"""
        message = BroadcastMessage(
            message_type='heartbeat',
            node_id=self.local_node_id,
            node_info=self.local_node_info
        )

        self._send_broadcast(message)
        logger.debug(f"[AutoBroadcaster] 广播心跳: {self.local_node_id}")

    def _broadcast_leave(self):
        """广播离开消息"""
        message = BroadcastMessage(
            message_type='leave',
            node_id=self.local_node_id,
            node_info={'node_id': self.local_node_id}
        )

        self._send_broadcast(message)
        logger.info(f"[AutoBroadcaster] 广播离开: {self.local_node_id}")

    def _send_broadcast(self, message: BroadcastMessage):
        """发送广播消息"""
        try:
            data = message.to_json().encode('utf-8')

            # 创建广播套接字
            broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            # 广播到所有网络
            broadcast_socket.sendto(data, ('<broadcast>', self.broadcast_port))
            broadcast_socket.close()

            self.broadcast_count += 1
            self.last_broadcast_time = datetime.now()

        except Exception as e:
            logger.error(f"[AutoBroadcaster] 广播失败: {e}")

    def _heartbeat_loop(self):
        """心跳循环"""
        while self._running:
            try:
                # 检查网络是否连接
                if self.network_detector.is_connected():
                    self._broadcast_heartbeat()

                time.sleep(self.heartbeat_interval)

            except Exception as e:
                logger.error(f"[AutoBroadcaster] 心跳循环错误: {e}")

    def _on_network_connected(self):
        """网络连接事件"""
        logger.info("[AutoBroadcaster] 网络已连接，开始广播")

        # 等待3秒（让网络稳定）
        time.sleep(3)

        # 重新收集节点信息（IP可能变了）
        self._collect_local_node_info()

        # 广播加入
        self._broadcast_join()

    def _on_network_disconnected(self):
        """网络断开事件"""
        logger.info("[AutoBroadcaster] 网络已断开")

        # 不需要广播离开（因为网络已断开）
        # 其他节点会通过心跳超时检测到

    def _on_ip_changed(self, old_ip: str, new_ip: str):
        """IP变化事件"""
        logger.info(f"[AutoBroadcaster] IP变化: {old_ip} → {new_ip}")

        # 重新收集节点信息
        self._collect_local_node_info()

        # 重新广播加入（更新IP）
        self._broadcast_join()

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'local_node_id': self.local_node_id,
            'broadcast_count': self.broadcast_count,
            'received_broadcasts': len(self.received_broadcasts),
            'last_broadcast_time': self.last_broadcast_time.isoformat() if self.last_broadcast_time else None,
            'is_running': self._running,
            'network_connected': self.network_detector.is_connected()
        }
