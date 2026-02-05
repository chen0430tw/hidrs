"""
全球广播系统插件 - Global Broadcast System
支持流媒体实时推送、强制播放、模拟模式和小范围测试

⚠️ 合规声明 ⚠️
本插件仅用于合法授权场景：
- 企业内部紧急通知
- 公共安全警报系统
- 教育机构通知系统
- 经过授权的测试环境

未经授权使用本系统可能违反法律！
"""
import logging
import time
import json
import ipaddress
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
from collections import defaultdict
from plugin_manager import PluginBase

logger = logging.getLogger(__name__)


class BroadcastSession:
    """广播会话"""

    def __init__(self, broadcast_id: str, title: str, level: int, mode: str = 'live'):
        self.broadcast_id = broadcast_id
        self.title = title
        self.level = level  # 0=普通, 1=重要, 2=紧急, 3=最高级
        self.mode = mode  # 'live', 'simulation', 'test'
        self.start_time = time.time()
        self.end_time = None
        self.status = 'active'  # active, paused, ended
        self.connected_clients: Set[str] = set()
        self.messages: List[Dict] = []
        self.metadata = {}

    def to_dict(self) -> Dict:
        return {
            'broadcast_id': self.broadcast_id,
            'title': self.title,
            'level': self.level,
            'mode': self.mode,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'status': self.status,
            'duration': time.time() - self.start_time if not self.end_time else self.end_time - self.start_time,
            'connected_clients': len(self.connected_clients),
            'messages_count': len(self.messages)
        }


class ClientSession:
    """客户端会话"""

    def __init__(self, client_id: str, ip_address: str, device_info: Dict):
        self.client_id = client_id
        self.ip_address = ip_address
        self.device_info = device_info
        self.connected_at = time.time()
        self.last_heartbeat = time.time()
        self.status = 'connected'  # connected, playing, paused, disconnected
        self.current_broadcast = None
        self.permissions = {
            'can_close': True,
            'can_mute': True,
            'can_minimize': True
        }

    def update_permissions(self, broadcast_level: int):
        """根据广播等级更新权限"""
        if broadcast_level >= 3:
            self.permissions = {
                'can_close': False,
                'can_mute': False,
                'can_minimize': False
            }
        elif broadcast_level >= 2:
            self.permissions = {
                'can_close': False,
                'can_mute': False,
                'can_minimize': True
            }
        else:
            self.permissions = {
                'can_close': True,
                'can_mute': True,
                'can_minimize': True
            }


class GlobalBroadcastPlugin(PluginBase):
    """全球广播系统插件"""

    # 合规性警告
    COMPLIANCE_WARNING = """
    ⚠️⚠️⚠️ 全球广播系统严格合规声明 ⚠️⚠️⚠️

    本插件仅用于合法授权场景：
    1. 企业内部紧急通知系统
    2. 公共安全警报系统
    3. 教育机构通知系统
    4. 经过授权的测试环境

    未经授权使用本系统可能违反法律！
    使用者承担一切法律责任！
    """

    def __init__(self):
        super().__init__()
        self.name = "GlobalBroadcast"
        self.version = "1.0.0"
        self.author = "HIDRS Team"
        self.description = "全球广播系统：流媒体推送 + 强制播放 + 模拟模式"

        # 广播会话管理
        self.active_broadcasts: Dict[str, BroadcastSession] = {}
        self.broadcast_history: List[Dict] = []

        # 客户端会话管理
        self.connected_clients: Dict[str, ClientSession] = {}

        # 模式配置
        self.simulation_mode = False  # 模拟模式（不实际发送）
        self.test_mode = False  # 测试模式（小范围）
        self.test_whitelist_ips: List[str] = []  # IP白名单
        self.max_test_clients = 10  # 测试模式最大客户端数

        # 消息日志（用于模拟模式）
        self.simulation_log: List[Dict] = []

    def on_load(self):
        """插件加载时调用"""
        logger.info(f"[{self.name}] 正在加载...")

        # 显示合规性警告
        logger.warning(self.COMPLIANCE_WARNING)

        # 读取配置
        config = self.get_config()

        # 强制要求用户明确同意
        if not config.get('user_consent', False):
            raise ValueError(
                f"[{self.name}] 需要用户明确同意合规条款。\n"
                f"请阅读合规声明后，在配置中设置 'user_consent: true'"
            )

        # 加载模式配置
        self.simulation_mode = config.get('simulation_mode', False)
        self.test_mode = config.get('test_mode', False)
        self.test_whitelist_ips = config.get('test_whitelist_ips', [])
        self.max_test_clients = config.get('max_test_clients', 10)

        if self.simulation_mode:
            logger.warning(f"[{self.name}] ⚠️ 模拟模式已启用 - 不会实际推送广播")

        if self.test_mode:
            logger.warning(
                f"[{self.name}] ⚠️ 测试模式已启用 - "
                f"仅限白名单IP ({len(self.test_whitelist_ips)}个) 和最多 {self.max_test_clients} 个客户端"
            )

        logger.info(f"[{self.name}] 加载完成")

    def on_unload(self):
        """插件卸载时调用"""
        logger.info(f"[{self.name}] 正在卸载...")

        # 结束所有活跃广播
        for broadcast_id in list(self.active_broadcasts.keys()):
            self.stop_broadcast(broadcast_id)

        # 断开所有客户端
        for client_id in list(self.connected_clients.keys()):
            self.disconnect_client(client_id)

        logger.info(f"[{self.name}] 卸载完成")

    def start_broadcast(self, title: str, level: int = 0, content_type: str = 'message',
                       content: str = '', duration: int = 0) -> Dict:
        """
        启动广播

        Args:
            title: 广播标题
            level: 级别 (0=普通, 1=重要, 2=紧急, 3=最高级)
            content_type: 内容类型 ('message', 'video', 'image')
            content: 内容（文本消息/视频URL/图片URL）
            duration: 持续时间（秒，0=无限期）
        """
        try:
            # 生成广播ID
            broadcast_id = f"bc_{int(time.time())}"

            # 确定运行模式
            mode = 'simulation' if self.simulation_mode else ('test' if self.test_mode else 'live')

            # 创建广播会话
            session = BroadcastSession(broadcast_id, title, level, mode)
            session.metadata = {
                'content_type': content_type,
                'content': content,
                'duration': duration,
                'created_at': datetime.now().isoformat()
            }

            self.active_broadcasts[broadcast_id] = session

            # 构建广播消息
            broadcast_message = {
                'broadcast_id': broadcast_id,
                'title': title,
                'level': level,
                'content_type': content_type,
                'content': content,
                'mode': mode,
                'timestamp': time.time()
            }

            if self.simulation_mode:
                # 模拟模式：不实际发送，只记录日志
                log_entry = {
                    'action': 'start_broadcast',
                    'broadcast': broadcast_message,
                    'simulated_clients': len(self.connected_clients),
                    'timestamp': datetime.now().isoformat()
                }
                self.simulation_log.append(log_entry)

                logger.info(
                    f"[{self.name}] 🎬 模拟广播启动: {title} (级别{level}) "
                    f"- 模拟推送到 {len(self.connected_clients)} 个客户端"
                )

                return {
                    'success': True,
                    'broadcast_id': broadcast_id,
                    'mode': 'simulation',
                    'simulated_clients': len(self.connected_clients),
                    'message': '模拟模式：广播未实际发送，已记录日志'
                }

            elif self.test_mode:
                # 测试模式：仅发送到白名单客户端
                eligible_clients = self._get_eligible_test_clients()

                for client_id in eligible_clients:
                    self._send_to_client(client_id, broadcast_message)

                session.connected_clients = eligible_clients

                logger.info(
                    f"[{self.name}] 🧪 测试广播启动: {title} (级别{level}) "
                    f"- 推送到 {len(eligible_clients)} 个测试客户端"
                )

                return {
                    'success': True,
                    'broadcast_id': broadcast_id,
                    'mode': 'test',
                    'clients_notified': len(eligible_clients),
                    'whitelist_count': len(self.test_whitelist_ips)
                }

            else:
                # 正式模式：发送到所有客户端
                for client_id in self.connected_clients:
                    self._send_to_client(client_id, broadcast_message)

                session.connected_clients = set(self.connected_clients.keys())

                logger.info(
                    f"[{self.name}] 📡 广播启动: {title} (级别{level}) "
                    f"- 推送到 {len(self.connected_clients)} 个客户端"
                )

                return {
                    'success': True,
                    'broadcast_id': broadcast_id,
                    'mode': 'live',
                    'clients_notified': len(self.connected_clients)
                }

        except Exception as e:
            logger.error(f"启动广播失败: {e}")
            return {'error': str(e)}

    def stop_broadcast(self, broadcast_id: str) -> Dict:
        """停止广播"""
        try:
            if broadcast_id not in self.active_broadcasts:
                return {'error': '广播不存在或已结束'}

            session = self.active_broadcasts[broadcast_id]
            session.status = 'ended'
            session.end_time = time.time()

            # 发送停止消息
            stop_message = {
                'action': 'stop_broadcast',
                'broadcast_id': broadcast_id
            }

            if self.simulation_mode:
                # 模拟模式
                log_entry = {
                    'action': 'stop_broadcast',
                    'broadcast_id': broadcast_id,
                    'duration': session.end_time - session.start_time,
                    'timestamp': datetime.now().isoformat()
                }
                self.simulation_log.append(log_entry)

                logger.info(f"[{self.name}] 🛑 模拟广播停止: {broadcast_id}")

            else:
                # 实际发送停止消息
                for client_id in session.connected_clients:
                    if client_id in self.connected_clients:
                        self._send_to_client(client_id, stop_message)

                logger.info(f"[{self.name}] 🛑 广播停止: {broadcast_id}")

            # 归档到历史记录
            self.broadcast_history.append(session.to_dict())

            # 从活跃列表移除
            del self.active_broadcasts[broadcast_id]

            return {
                'success': True,
                'broadcast_id': broadcast_id,
                'duration': session.end_time - session.start_time,
                'clients_affected': len(session.connected_clients)
            }

        except Exception as e:
            logger.error(f"停止广播失败: {e}")
            return {'error': str(e)}

    def register_client(self, client_id: str, ip_address: str, device_info: Dict) -> Dict:
        """注册客户端"""
        try:
            # 测试模式检查
            if self.test_mode:
                if not self._is_ip_whitelisted(ip_address):
                    return {
                        'error': '测试模式：您的IP不在白名单中',
                        'mode': 'test'
                    }

                if len(self.connected_clients) >= self.max_test_clients:
                    return {
                        'error': f'测试模式：已达到最大客户端数 ({self.max_test_clients})',
                        'mode': 'test'
                    }

            # 创建客户端会话
            client = ClientSession(client_id, ip_address, device_info)
            self.connected_clients[client_id] = client

            mode = 'simulation' if self.simulation_mode else ('test' if self.test_mode else 'live')

            logger.info(
                f"[{self.name}] ✅ 客户端连接: {client_id} ({ip_address}) "
                f"[模式: {mode}] (总数: {len(self.connected_clients)})"
            )

            return {
                'success': True,
                'client_id': client_id,
                'mode': mode,
                'active_broadcasts': [bc.to_dict() for bc in self.active_broadcasts.values()]
            }

        except Exception as e:
            logger.error(f"注册客户端失败: {e}")
            return {'error': str(e)}

    def disconnect_client(self, client_id: str):
        """断开客户端"""
        if client_id in self.connected_clients:
            client = self.connected_clients[client_id]
            client.status = 'disconnected'

            # 从所有活跃广播中移除
            for session in self.active_broadcasts.values():
                session.connected_clients.discard(client_id)

            del self.connected_clients[client_id]

            logger.info(
                f"[{self.name}] ❌ 客户端断开: {client_id} "
                f"(剩余: {len(self.connected_clients)})"
            )

    def get_active_broadcasts(self) -> Dict:
        """获取活跃广播列表"""
        return {
            'success': True,
            'broadcasts': [bc.to_dict() for bc in self.active_broadcasts.values()],
            'count': len(self.active_broadcasts)
        }

    def get_broadcast_status(self, broadcast_id: str) -> Dict:
        """获取广播状态"""
        if broadcast_id not in self.active_broadcasts:
            return {'error': '广播不存在'}

        session = self.active_broadcasts[broadcast_id]
        return {
            'success': True,
            'broadcast': session.to_dict()
        }

    def get_connected_clients(self) -> Dict:
        """获取已连接客户端列表"""
        clients = []
        for client_id, client in self.connected_clients.items():
            clients.append({
                'client_id': client_id,
                'ip_address': client.ip_address,
                'device_info': client.device_info,
                'status': client.status,
                'connected_at': client.connected_at,
                'current_broadcast': client.current_broadcast
            })

        return {
            'success': True,
            'clients': clients,
            'count': len(clients),
            'mode': 'simulation' if self.simulation_mode else ('test' if self.test_mode else 'live')
        }

    def get_simulation_log(self, limit: int = 100) -> Dict:
        """获取模拟日志"""
        if not self.simulation_mode:
            return {'error': '非模拟模式'}

        return {
            'success': True,
            'logs': self.simulation_log[-limit:],
            'total': len(self.simulation_log)
        }

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'mode': 'simulation' if self.simulation_mode else ('test' if self.test_mode else 'live'),
            'simulation_mode': self.simulation_mode,
            'test_mode': self.test_mode,
            'test_whitelist_count': len(self.test_whitelist_ips),
            'max_test_clients': self.max_test_clients,
            'active_broadcasts': len(self.active_broadcasts),
            'connected_clients': len(self.connected_clients),
            'broadcast_history_count': len(self.broadcast_history),
            'simulation_log_count': len(self.simulation_log)
        }

    def _get_eligible_test_clients(self) -> Set[str]:
        """获取符合测试条件的客户端"""
        eligible = set()
        for client_id, client in self.connected_clients.items():
            if self._is_ip_whitelisted(client.ip_address):
                eligible.add(client_id)
                if len(eligible) >= self.max_test_clients:
                    break
        return eligible

    def _is_ip_whitelisted(self, ip_address: str) -> bool:
        """检查IP是否在白名单中"""
        if not self.test_whitelist_ips:
            return False

        try:
            ip = ipaddress.ip_address(ip_address)
            for whitelist_entry in self.test_whitelist_ips:
                # 支持单个IP或CIDR范围
                if '/' in whitelist_entry:
                    network = ipaddress.ip_network(whitelist_entry, strict=False)
                    if ip in network:
                        return True
                else:
                    if ip == ipaddress.ip_address(whitelist_entry):
                        return True
            return False
        except Exception as e:
            logger.error(f"IP白名单检查失败: {e}")
            return False

    def _send_to_client(self, client_id: str, message: Dict):
        """发送消息到客户端（模拟WebSocket）"""
        if client_id not in self.connected_clients:
            return

        client = self.connected_clients[client_id]

        # 这里应该通过WebSocket发送消息
        # 由于这是插件，实际的WebSocket实现在外部
        # 这里只记录发送行为
        logger.debug(f"[{self.name}] 📤 发送消息到客户端 {client_id}: {message.get('action', 'broadcast')}")

        # 更新客户端状态
        if 'broadcast_id' in message:
            client.current_broadcast = message['broadcast_id']
            client.status = 'playing'
