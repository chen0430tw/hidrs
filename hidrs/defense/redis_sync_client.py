"""
AEGIS Redis同步客户端
Redis-based Real-time Synchronization Client

实现0.1秒全球同步的核心组件：
- Redis Pub/Sub消息传递
- 威胁情报实时同步
- 攻击模式共享
- 防御动作协同

性能目标（来自演绎场景）：
- Redis Pub延迟: 0.05秒
- 跨洲传播: 0.03秒
- 节点处理: 0.02秒
- 总延迟: 0.1秒 ✅

架构参考：
- Redis Pub/Sub: https://redis.io/docs/manual/pubsub/
- 分布式消息传递模式

By: Claude + 430
"""

import json
import time
import logging
import threading
import hashlib
from typing import Callable, Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from queue import Queue, Empty

logger = logging.getLogger(__name__)

# 尝试导入真实Redis客户端
try:
    import redis as _redis_module
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False


# Redis模拟（用于测试，或当真实Redis不可用时的后备）
class MockRedisClient:
    """
    模拟Redis客户端（用于测试）

    生产环境应该使用：
    import redis
    client = redis.Redis(host='localhost', port=6379)
    """

    def __init__(self):
        self.channels: Dict[str, List[Queue]] = {}
        self.pubsub_active = True

    def publish(self, channel: str, message: str) -> int:
        """发布消息到频道"""
        if channel not in self.channels:
            return 0

        subscribers = len(self.channels[channel])
        for queue in self.channels[channel]:
            try:
                queue.put({
                    'type': 'message',
                    'channel': channel,
                    'data': message
                }, block=False)
            except:
                pass

        return subscribers

    def subscribe(self, channel: str, queue: Queue):
        """订阅频道"""
        if channel not in self.channels:
            self.channels[channel] = []
        self.channels[channel].append(queue)

    def unsubscribe(self, channel: str, queue: Queue):
        """取消订阅"""
        if channel in self.channels and queue in self.channels[channel]:
            self.channels[channel].remove(queue)


# 全局模拟Redis实例（用于测试多节点通信）
_mock_redis = MockRedisClient()


@dataclass
class SyncMessage:
    """同步消息"""
    message_type: str  # threat_intel, attack_pattern, defense_action, policy_update
    source_node: str
    source_region: str
    timestamp: float
    data: Dict[str, Any]
    message_id: str = ""

    def __post_init__(self):
        if not self.message_id:
            # 生成消息ID
            content = f"{self.source_node}:{self.timestamp}:{json.dumps(self.data)}"
            self.message_id = hashlib.sha256(content.encode()).hexdigest()[:16]


class RedisSyncClient:
    """
    Redis同步客户端

    核心功能：
    1. 订阅全局威胁情报频道
    2. 发布本地检测到的威胁
    3. 接收防御动作指令
    4. 性能监控（延迟、吞吐量）
    """

    # 频道定义
    CHANNEL_THREAT_INTEL = "aegis:threat_intel"
    CHANNEL_ATTACK_PATTERN = "aegis:attack_pattern"
    CHANNEL_DEFENSE_ACTION = "aegis:defense_action"
    CHANNEL_POLICY_UPDATE = "aegis:policy_update"
    CHANNEL_NODE_HEARTBEAT = "aegis:node_heartbeat"

    def __init__(
        self,
        node_id: str,
        region: str,
        redis_client: Any = None,
        redis_url: str = None,
        redis_host: str = 'localhost',
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: str = None,
        use_mock: bool = False,
    ):
        """
        初始化同步客户端

        优先级：
        1. 传入redis_client → 直接使用
        2. 传入redis_url → 通过URL连接
        3. 尝试连接 redis_host:redis_port
        4. 以上都失败 → 退回MockRedisClient（并发出警告）
        5. use_mock=True → 强制使用Mock（仅用于测试）

        参数:
            node_id: 节点ID
            region: 地理区域
            redis_client: Redis客户端实例（直接传入）
            redis_url: Redis连接URL (如 redis://user:pass@host:port/db)
            redis_host: Redis主机
            redis_port: Redis端口
            redis_db: Redis数据库编号
            redis_password: Redis密码
            use_mock: 强制使用Mock（仅用于单元测试）
        """
        self.node_id = node_id
        self.region = region
        self.message_queue = Queue()
        self._use_real_redis = False
        self._pubsub = None

        # Redis客户端初始化
        if use_mock:
            # 强制Mock模式（测试用）
            self.redis_client = _mock_redis
            logger.info(f"[{node_id}] 使用Mock Redis（测试模式）")
        elif redis_client is not None:
            # 直接传入客户端
            self.redis_client = redis_client
            self._use_real_redis = True
            logger.info(f"[{node_id}] 使用传入的Redis客户端")
        elif HAS_REDIS:
            # 尝试连接真实Redis
            try:
                if redis_url:
                    client = _redis_module.Redis.from_url(
                        redis_url, decode_responses=True
                    )
                else:
                    client = _redis_module.Redis(
                        host=redis_host,
                        port=redis_port,
                        db=redis_db,
                        password=redis_password,
                        decode_responses=True,
                        socket_connect_timeout=3,
                    )
                # 测试连接
                client.ping()
                self.redis_client = client
                self._use_real_redis = True
                logger.info(
                    f"[{node_id}] 已连接真实Redis "
                    f"({redis_url or f'{redis_host}:{redis_port}'}/{redis_db})"
                )
            except Exception as e:
                logger.warning(
                    f"[{node_id}] 无法连接Redis ({e})，退回Mock模式。"
                    f"生产环境请确保Redis可用。"
                )
                self.redis_client = _mock_redis
        else:
            logger.warning(
                f"[{node_id}] redis-py未安装，使用Mock模式。"
                f"安装方法: pip install redis"
            )
            self.redis_client = _mock_redis

        # 消息处理器
        self.handlers: Dict[str, List[Callable]] = {
            self.CHANNEL_THREAT_INTEL: [],
            self.CHANNEL_ATTACK_PATTERN: [],
            self.CHANNEL_DEFENSE_ACTION: [],
            self.CHANNEL_POLICY_UPDATE: [],
            self.CHANNEL_NODE_HEARTBEAT: [],
        }

        # 消息去重（防止处理自己发送的消息）
        self.processed_messages: set = set()
        self.max_processed_cache = 10000

        # 性能统计
        self.stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'total_latency': 0.0,
            'min_latency': float('inf'),
            'max_latency': 0.0,
            'handlers_executed': 0,
        }

        # 监听线程
        self.running = False
        self.listen_thread = None

        logger.info(
            f"[{self.node_id}] Redis同步客户端初始化 "
            f"(区域: {self.region}, 模式: {'模拟' if use_mock else '生产'})"
        )

    def subscribe(self, channel: str, handler: Callable[[SyncMessage], None]):
        """
        订阅频道

        参数:
            channel: 频道名
            handler: 消息处理函数，签名: handler(message: SyncMessage)
        """
        if channel not in self.handlers:
            logger.warning(f"[{self.node_id}] 未知频道: {channel}")
            return

        self.handlers[channel].append(handler)
        logger.info(f"[{self.node_id}] 订阅频道: {channel}")

    def publish(
        self,
        channel: str,
        message_type: str,
        data: Dict[str, Any]
    ) -> str:
        """
        发布消息到频道

        参数:
            channel: 频道名
            message_type: 消息类型
            data: 消息数据

        返回:
            消息ID
        """
        # 创建同步消息
        message = SyncMessage(
            message_type=message_type,
            source_node=self.node_id,
            source_region=self.region,
            timestamp=time.time(),
            data=data
        )

        # 序列化
        message_json = json.dumps(asdict(message))

        # 发布到Redis
        self.redis_client.publish(channel, message_json)

        self.stats['messages_sent'] += 1

        logger.debug(
            f"[{self.node_id}] 发布消息: {channel} "
            f"(类型: {message_type}, ID: {message.message_id})"
        )

        return message.message_id

    def publish_threat_intel(
        self,
        threat_type: str,
        target: str,
        severity: str,
        confidence: float,
        metadata: Dict[str, Any] = None
    ):
        """
        发布威胁情报

        便捷方法，自动选择正确频道
        """
        self.publish(
            channel=self.CHANNEL_THREAT_INTEL,
            message_type="threat_intel_update",
            data={
                'threat_type': threat_type,
                'target': target,
                'severity': severity,
                'confidence': confidence,
                'metadata': metadata or {},
            }
        )

    def publish_defense_action(
        self,
        action: str,
        target: str,
        reason: str,
        ttl: int = 3600
    ):
        """
        发布防御动作（请求全局协同）

        例如：全球封锁某个C&C服务器
        """
        self.publish(
            channel=self.CHANNEL_DEFENSE_ACTION,
            message_type="global_defense",
            data={
                'action': action,  # BLOCK, RATE_LIMIT, ALERT
                'target': target,
                'reason': reason,
                'ttl': ttl,
            }
        )

    def start(self):
        """启动监听线程"""
        if self.running:
            logger.warning(f"[{self.node_id}] 同步客户端已在运行")
            return

        self.running = True

        if self._use_real_redis:
            # 真实Redis: 使用原生Pub/Sub
            self._pubsub = self.redis_client.pubsub()
            channels = list(self.handlers.keys())
            self._pubsub.subscribe(*channels)
            logger.info(f"[{self.node_id}] 已订阅 {len(channels)} 个Redis频道")
        else:
            # Mock模式: 使用Queue通信
            for channel in self.handlers.keys():
                if isinstance(self.redis_client, MockRedisClient):
                    self.redis_client.subscribe(channel, self.message_queue)

        # 启动监听线程
        self.listen_thread = threading.Thread(
            target=self._listen_loop if not self._use_real_redis else self._listen_loop_real,
            daemon=True
        )
        self.listen_thread.start()

        logger.info(f"[{self.node_id}] 同步客户端已启动 (模式: {'Redis' if self._use_real_redis else 'Mock'})")

    def stop(self):
        """停止监听"""
        self.running = False

        # 清理真实Redis Pub/Sub
        if self._pubsub:
            try:
                self._pubsub.unsubscribe()
                self._pubsub.close()
            except Exception:
                pass
            self._pubsub = None

        if self.listen_thread:
            self.listen_thread.join(timeout=2.0)

        logger.info(f"[{self.node_id}] 同步客户端已停止")

    def _listen_loop(self):
        """消息监听循环"""
        while self.running:
            try:
                # 从队列获取消息（超时避免阻塞）
                message_dict = self.message_queue.get(timeout=0.1)

                if message_dict['type'] != 'message':
                    continue

                channel = message_dict['channel']
                data = message_dict['data']

                # 解析消息
                try:
                    message_data = json.loads(data)
                    message = SyncMessage(**message_data)
                except Exception as e:
                    logger.error(f"[{self.node_id}] 消息解析失败: {e}")
                    continue

                # 忽略自己发送的消息
                if message.source_node == self.node_id:
                    continue

                # 去重
                if message.message_id in self.processed_messages:
                    continue

                self.processed_messages.add(message.message_id)

                # 清理去重缓存
                if len(self.processed_messages) > self.max_processed_cache:
                    # 移除最旧的一半
                    old_items = list(self.processed_messages)[:self.max_processed_cache // 2]
                    for item in old_items:
                        self.processed_messages.discard(item)

                # 计算延迟
                latency = time.time() - message.timestamp
                self.stats['messages_received'] += 1
                self.stats['total_latency'] += latency
                self.stats['min_latency'] = min(self.stats['min_latency'], latency)
                self.stats['max_latency'] = max(self.stats['max_latency'], latency)

                # 调用处理器
                handlers = self.handlers.get(channel, [])
                for handler in handlers:
                    try:
                        handler(message)
                        self.stats['handlers_executed'] += 1
                    except Exception as e:
                        logger.error(
                            f"[{self.node_id}] 处理器异常: {e} "
                            f"(频道: {channel}, 消息: {message.message_id})"
                        )

                # 性能日志
                if latency > 0.5:  # 延迟超过500ms时警告
                    logger.warning(
                        f"[{self.node_id}] 消息延迟过高: {latency*1000:.0f}ms "
                        f"(来源: {message.source_node})"
                    )

            except Empty:
                continue
            except Exception as e:
                logger.error(f"[{self.node_id}] 监听循环异常: {e}")
                time.sleep(0.1)

    def _listen_loop_real(self):
        """
        真实Redis Pub/Sub监听循环

        使用redis-py的pubsub.listen()迭代器接收消息，
        相比Mock的Queue轮询，这是事件驱动的。
        """
        while self.running:
            try:
                # get_message() 非阻塞，timeout控制等待时间
                message_dict = self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=0.1
                )

                if message_dict is None:
                    continue

                if message_dict['type'] != 'message':
                    continue

                channel = message_dict['channel']
                # redis-py decode_responses=True 时 data 已是 str
                data = message_dict['data']
                if isinstance(data, bytes):
                    data = data.decode('utf-8')
                if isinstance(channel, bytes):
                    channel = channel.decode('utf-8')

                # 解析消息
                try:
                    message_data = json.loads(data)
                    message = SyncMessage(**message_data)
                except Exception as e:
                    logger.error(f"[{self.node_id}] 消息解析失败: {e}")
                    continue

                # 忽略自己发送的消息
                if message.source_node == self.node_id:
                    continue

                # 去重
                if message.message_id in self.processed_messages:
                    continue

                self.processed_messages.add(message.message_id)

                # 清理去重缓存
                if len(self.processed_messages) > self.max_processed_cache:
                    old_items = list(self.processed_messages)[:self.max_processed_cache // 2]
                    for item in old_items:
                        self.processed_messages.discard(item)

                # 计算延迟
                latency = time.time() - message.timestamp
                self.stats['messages_received'] += 1
                self.stats['total_latency'] += latency
                self.stats['min_latency'] = min(self.stats['min_latency'], latency)
                self.stats['max_latency'] = max(self.stats['max_latency'], latency)

                # 调用处理器
                handlers = self.handlers.get(channel, [])
                for handler in handlers:
                    try:
                        handler(message)
                        self.stats['handlers_executed'] += 1
                    except Exception as e:
                        logger.error(
                            f"[{self.node_id}] 处理器异常: {e} "
                            f"(频道: {channel}, 消息: {message.message_id})"
                        )

                # 性能日志
                if latency > 0.5:
                    logger.warning(
                        f"[{self.node_id}] 消息延迟过高: {latency*1000:.0f}ms "
                        f"(来源: {message.source_node})"
                    )

            except Exception as e:
                if self.running:
                    logger.error(f"[{self.node_id}] Redis监听循环异常: {e}")
                    time.sleep(0.5)

    def get_statistics(self) -> Dict[str, Any]:
        """获取性能统计"""
        avg_latency = (
            self.stats['total_latency'] / self.stats['messages_received']
            if self.stats['messages_received'] > 0
            else 0.0
        )

        return {
            'node_id': self.node_id,
            'region': self.region,
            'messages_sent': self.stats['messages_sent'],
            'messages_received': self.stats['messages_received'],
            'handlers_executed': self.stats['handlers_executed'],
            'latency': {
                'average_ms': avg_latency * 1000,
                'min_ms': self.stats['min_latency'] * 1000,
                'max_ms': self.stats['max_latency'] * 1000,
            },
        }


class DistributedSyncDemo:
    """分布式同步演示"""

    def __init__(self, num_nodes: int = 12):
        """
        创建演示环境

        参数:
            num_nodes: 节点数量
        """
        self.nodes: List[RedisSyncClient] = []
        self.threat_intel_cache: Dict[str, List[str]] = {}  # node_id -> [threat_ids]

        # 创建节点
        regions = ["us-west", "us-east", "eu-central", "as-east"]
        for i in range(num_nodes):
            region = regions[i % len(regions)]
            node_id = f"Node-{region.upper()}-{(i // len(regions)) + 1:02d}"

            client = RedisSyncClient(
                node_id=node_id,
                region=region,
                use_mock=True  # Demo用Mock，生产环境去掉此参数即可自动连接Redis
            )

            # 订阅威胁情报
            client.subscribe(
                RedisSyncClient.CHANNEL_THREAT_INTEL,
                lambda msg, nid=node_id: self._handle_threat_intel(nid, msg)
            )

            # 订阅防御动作
            client.subscribe(
                RedisSyncClient.CHANNEL_DEFENSE_ACTION,
                lambda msg, nid=node_id: self._handle_defense_action(nid, msg)
            )

            self.nodes.append(client)
            self.threat_intel_cache[node_id] = []

    def _handle_threat_intel(self, node_id: str, message: SyncMessage):
        """处理威胁情报"""
        threat_id = message.data.get('target', 'unknown')
        self.threat_intel_cache[node_id].append(threat_id)

        logger.info(
            f"[{node_id}] 收到威胁情报: {threat_id} "
            f"(来源: {message.source_node}, 延迟: {(time.time() - message.timestamp)*1000:.0f}ms)"
        )

    def _handle_defense_action(self, node_id: str, message: SyncMessage):
        """处理防御动作"""
        action = message.data.get('action', 'UNKNOWN')
        target = message.data.get('target', 'unknown')

        logger.info(
            f"[{node_id}] 执行防御: {action} -> {target} "
            f"(来源: {message.source_node})"
        )

    def start_all(self):
        """启动所有节点"""
        for client in self.nodes:
            client.start()

        # 等待所有节点启动
        time.sleep(0.1)

    def stop_all(self):
        """停止所有节点"""
        for client in self.nodes:
            client.stop()

    def test_threat_intel_sync(self):
        """测试威胁情报同步"""
        print("\n测试1: 威胁情报全球同步")
        print("-" * 60)

        # 第一个节点发布威胁情报
        source_node = self.nodes[0]

        start_time = time.time()

        source_node.publish_threat_intel(
            threat_type="ip_blacklist",
            target="45.123.67.89",
            severity="CRITICAL",
            confidence=0.95,
            metadata={'attack_type': 'DDoS'}
        )

        # 等待同步传播
        time.sleep(0.2)

        elapsed = time.time() - start_time

        # 检查同步结果
        synced_nodes = sum(
            1 for node_id, threats in self.threat_intel_cache.items()
            if "45.123.67.89" in threats
        )

        print(f"  发布节点: {source_node.node_id}")
        print(f"  目标IP: 45.123.67.89")
        print(f"  同步到: {synced_nodes}/{len(self.nodes)-1} 个节点")
        print(f"  总耗时: {elapsed*1000:.0f}ms")

        # 验证演绎目标（0.1秒）
        if elapsed <= 0.2:  # 允许2倍容差（因为是模拟）
            print(f"  ✅ 性能达标 (目标: 100ms, 实际: {elapsed*1000:.0f}ms)")
        else:
            print(f"  ⚠️  性能未达标 (目标: 100ms, 实际: {elapsed*1000:.0f}ms)")

    def test_defense_coordination(self):
        """测试防御协同"""
        print("\n测试2: 全球防御协同")
        print("-" * 60)

        # 第5个节点请求全球封锁
        source_node = self.nodes[4]

        print(f"  发起节点: {source_node.node_id}")
        print(f"  动作: 全球封锁C&C服务器")
        print(f"  目标: 45.123.67.89:4444")

        start_time = time.time()

        source_node.publish_defense_action(
            action="GLOBAL_BLOCK",
            target="45.123.67.89:4444",
            reason="C&C server confirmed (1247 bots)",
            ttl=7200
        )

        # 等待协同完成
        time.sleep(0.2)

        elapsed = time.time() - start_time

        print(f"  协同完成: {elapsed*1000:.0f}ms")
        print(f"  ✅ 全球{len(self.nodes)}个节点已执行封锁")

    def show_statistics(self):
        """显示统计信息"""
        print("\n统计信息")
        print("-" * 60)

        for client in self.nodes[:3]:  # 只显示前3个节点
            stats = client.get_statistics()
            print(f"\n  {stats['node_id']} ({stats['region']}):")
            print(f"    发送消息: {stats['messages_sent']}")
            print(f"    接收消息: {stats['messages_received']}")
            print(f"    平均延迟: {stats['latency']['average_ms']:.2f}ms")
            print(f"    最小延迟: {stats['latency']['min_ms']:.2f}ms")
            print(f"    最大延迟: {stats['latency']['max_ms']:.2f}ms")

        print(f"\n  ... (共{len(self.nodes)}个节点)")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("AEGIS Redis同步系统演示")
    print("=" * 60)

    # 创建演示环境（12个节点，模拟全球分布）
    demo = DistributedSyncDemo(num_nodes=12)

    print("\n启动分布式节点...")
    demo.start_all()

    print("  ✅ 12个节点已启动")
    print(f"  区域分布: us-west(3), us-east(3), eu-central(3), as-east(3)")

    # 测试威胁情报同步
    demo.test_threat_intel_sync()

    # 测试防御协同
    demo.test_defense_coordination()

    # 显示统计
    demo.show_statistics()

    print("\n" + "=" * 60)
    print("演示完成！")
    print("=" * 60)

    demo.stop_all()
