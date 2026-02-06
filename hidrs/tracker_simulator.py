"""
GPS追踪器模拟器
模拟真实GPS设备的移动和位置上报
用于测试实时追踪系统
"""
import time
import random
import math
import socketio
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GPSTrackerSimulator:
    """GPS追踪器模拟器"""

    def __init__(self, target_id, name, start_lat, start_lon, server_url='http://localhost:5002'):
        self.target_id = target_id
        self.name = name
        self.lat = start_lat
        self.lon = start_lon
        self.heading = random.uniform(0, 360)
        self.speed = random.uniform(20, 80)  # km/h
        self.altitude = random.randint(50, 200)  # 米
        self.server_url = server_url

        # 创建Socket.IO客户端
        self.sio = socketio.Client()
        self._register_handlers()

    def _register_handlers(self):
        """注册Socket.IO事件处理器"""

        @self.sio.on('connect')
        def on_connect():
            logger.info(f"✅ [{self.target_id}] 已连接到追踪服务器")

        @self.sio.on('disconnect')
        def on_disconnect():
            logger.warning(f"❌ [{self.target_id}] 与服务器断开连接")

        @self.sio.on('error')
        def on_error(data):
            logger.error(f"⚠️ [{self.target_id}] 错误: {data}")

    def connect(self):
        """连接到追踪服务器"""
        try:
            self.sio.connect(self.server_url)
            logger.info(f"🔗 [{self.target_id}] 正在连接 {self.server_url}...")
            return True
        except Exception as e:
            logger.error(f"❌ [{self.target_id}] 连接失败: {e}")
            return False

    def simulate_movement(self):
        """模拟真实的移动模式"""
        # 速度变化（加速或减速）
        self.speed += random.uniform(-5, 5)
        self.speed = max(0, min(120, self.speed))  # 限制在0-120 km/h

        # 方向变化（转向）
        self.heading += random.uniform(-15, 15)
        self.heading = self.heading % 360

        # 海拔变化
        self.altitude += random.randint(-10, 10)
        self.altitude = max(0, min(5000, self.altitude))

        # 计算新位置
        # 1秒移动的距离（km）
        distance_km = self.speed / 3600

        # 纬度变化（1度纬度 ≈ 111 km）
        lat_change = distance_km * math.cos(math.radians(self.heading)) / 111

        # 经度变化（1度经度 = 111 * cos(纬度) km）
        lon_change = distance_km * math.sin(math.radians(self.heading)) / \
                     (111 * math.cos(math.radians(self.lat)))

        self.lat += lat_change
        self.lon += lon_change

        # 边界检查（防止超出地球范围）
        self.lat = max(-90, min(90, self.lat))
        self.lon = max(-180, min(180, self.lon))

    def report_position(self):
        """向服务器上报当前位置"""
        try:
            data = {
                'target_id': self.target_id,
                'name': self.name,
                'lat': round(self.lat, 6),
                'lon': round(self.lon, 6),
                'speed': round(self.speed, 1),
                'heading': round(self.heading, 1),
                'altitude': int(self.altitude)
            }

            self.sio.emit('report_position', data)

            logger.info(
                f"📡 [{self.target_id}] "
                f"位置: ({data['lat']:.5f}, {data['lon']:.5f}) | "
                f"速度: {data['speed']} km/h | "
                f"方向: {data['heading']}° | "
                f"海拔: {data['altitude']}m"
            )

        except Exception as e:
            logger.error(f"❌ [{self.target_id}] 上报失败: {e}")

    def run(self, interval=2):
        """持续运行模拟器"""
        if not self.connect():
            logger.error(f"❌ [{self.target_id}] 无法启动，连接失败")
            return

        logger.info(f"🚀 [{self.target_id}] 模拟器启动，更新间隔: {interval}秒")

        try:
            while True:
                self.simulate_movement()
                self.report_position()
                time.sleep(interval)

        except KeyboardInterrupt:
            logger.info(f"🛑 [{self.target_id}] 模拟器停止")
            self.sio.disconnect()

        except Exception as e:
            logger.error(f"⚠️ [{self.target_id}] 运行错误: {e}")
            self.sio.disconnect()


def run_multiple_trackers():
    """运行多个追踪器模拟多目标场景"""
    import threading

    # 定义多个目标
    trackers = [
        GPSTrackerSimulator('ALPHA', '车辆-Alpha', 39.9042, 116.4074),  # 北京
        GPSTrackerSimulator('BRAVO', '车辆-Bravo', 31.2304, 121.4737),  # 上海
        GPSTrackerSimulator('CHARLIE', '车辆-Charlie', 22.5431, 114.0579),  # 深圳
    ]

    # 启动所有追踪器
    threads = []
    for tracker in trackers:
        thread = threading.Thread(target=tracker.run, args=(2,))
        thread.daemon = True
        thread.start()
        threads.append(thread)
        time.sleep(0.5)  # 错开启动时间

    # 等待所有线程
    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        logger.info("🛑 停止所有模拟器")


if __name__ == '__main__':
    print("""
╔═══════════════════════════════════════════════════════╗
║         GPS追踪器模拟器 - HIDRS Tracker System        ║
╚═══════════════════════════════════════════════════════╝

选择运行模式:
1. 单目标模拟（ALPHA）
2. 多目标模拟（ALPHA + BRAVO + CHARLIE）

请输入选项 [1/2]: """, end='')

    choice = input().strip()

    if choice == '1':
        # 单目标
        tracker = GPSTrackerSimulator('ALPHA', '车辆-Alpha', 39.9042, 116.4074)
        tracker.run(interval=2)

    elif choice == '2':
        # 多目标
        run_multiple_trackers()

    else:
        print("❌ 无效选项")
