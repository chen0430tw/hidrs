"""
实时Tracker追踪系统 WebSocket服务器
支持多目标GPS实时追踪，位置广播，轨迹记录
"""
import logging
import time
from threading import Thread
from typing import Dict
from flask import Flask
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TrackerServer:
    """实时追踪服务器"""

    def __init__(self, host='0.0.0.0', port=5002):
        self.host = host
        self.port = port

        # Flask应用
        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = 'hidrs-tracker-secret-2026'
        CORS(self.app)

        # SocketIO实例
        self.socketio = SocketIO(
            self.app,
            cors_allowed_origins="*",
            async_mode='eventlet',
            logger=True,
            engineio_logger=True
        )

        # 活跃目标字典
        self.active_targets: Dict[str, dict] = {}

        # 连接的客户端
        self.connected_clients = set()

        # 注册事件处理器
        self._register_handlers()

        # 启动清理线程
        self.cleanup_thread = Thread(target=self._cleanup_old_targets, daemon=True)
        self.cleanup_thread.start()

        logger.info("🛰️ 追踪服务器初始化完成")

    def _register_handlers(self):
        """注册WebSocket事件处理器"""

        @self.socketio.on('connect')
        def handle_connect():
            """客户端连接"""
            client_id = id(self.socketio)
            self.connected_clients.add(client_id)
            logger.info(f"✅ 客户端已连接 (总数: {len(self.connected_clients)})")

            # 发送当前所有活跃目标
            emit('connected', {
                'status': 'success',
                'active_targets': list(self.active_targets.keys()),
                'count': len(self.active_targets)
            })

            # 发送所有目标的当前状态
            for target_id, target_data in self.active_targets.items():
                emit('target_update', target_data)

        @self.socketio.on('disconnect')
        def handle_disconnect():
            """客户端断开"""
            client_id = id(self.socketio)
            self.connected_clients.discard(client_id)
            logger.info(f"❌ 客户端已断开 (剩余: {len(self.connected_clients)})")

        @self.socketio.on('report_position')
        def handle_position_report(data):
            """接收GPS设备上报的位置"""
            try:
                target_id = data.get('target_id')
                if not target_id:
                    emit('error', {'message': 'target_id is required'})
                    return

                # 更新目标数据
                target_data = {
                    'target_id': target_id,
                    'name': data.get('name', f'Target {target_id}'),
                    'lat': float(data.get('lat', 0)),
                    'lon': float(data.get('lon', 0)),
                    'speed': float(data.get('speed', 0)),
                    'heading': float(data.get('heading', 0)),
                    'altitude': float(data.get('altitude', 0)),
                    'timestamp': time.time()
                }

                self.active_targets[target_id] = target_data

                # 广播给所有客户端
                emit('target_update', target_data, broadcast=True)

                logger.debug(
                    f"📡 {target_id}: ({target_data['lat']:.5f}, {target_data['lon']:.5f}) "
                    f"速度: {target_data['speed']:.1f} km/h"
                )

            except Exception as e:
                logger.error(f"位置上报处理失败: {e}")
                emit('error', {'message': str(e)})

        @self.socketio.on('request_target_list')
        def handle_request_target_list():
            """请求目标列表"""
            emit('target_list', {
                'targets': list(self.active_targets.values()),
                'count': len(self.active_targets)
            })

        @self.socketio.on('remove_target')
        def handle_remove_target(data):
            """移除目标"""
            target_id = data.get('target_id')
            if target_id in self.active_targets:
                del self.active_targets[target_id]
                emit('target_lost', {
                    'target_id': target_id,
                    'reason': 'manual_removal'
                }, broadcast=True)
                logger.info(f"🔴 目标 {target_id} 已手动移除")

        @self.socketio.on('ping')
        def handle_ping():
            """心跳检测"""
            emit('pong', {'timestamp': time.time()})

    def _cleanup_old_targets(self):
        """清理超时目标（后台线程）"""
        while True:
            try:
                current_time = time.time()
                to_remove = []

                # 查找超过5分钟未更新的目标
                for target_id, data in self.active_targets.items():
                    if current_time - data.get('timestamp', 0) > 300:  # 5分钟
                        to_remove.append(target_id)

                # 移除超时目标
                for target_id in to_remove:
                    del self.active_targets[target_id]
                    self.socketio.emit('target_lost', {
                        'target_id': target_id,
                        'reason': 'timeout'
                    })
                    logger.warning(f"⏰ 目标 {target_id} 超时已移除")

                time.sleep(60)  # 每分钟检查一次

            except Exception as e:
                logger.error(f"清理线程错误: {e}")
                time.sleep(60)

    def run(self):
        """启动服务器"""
        logger.info(f"🛰️ 追踪服务器启动在 http://{self.host}:{self.port}")
        logger.info(f"📡 WebSocket端点: ws://{self.host}:{self.port}/socket.io/")
        self.socketio.run(self.app, host=self.host, port=self.port, debug=False)


def main():
    """主函数"""
    server = TrackerServer(host='0.0.0.0', port=5002)
    server.run()


if __name__ == '__main__':
    main()
