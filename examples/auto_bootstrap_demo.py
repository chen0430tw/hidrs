#!/usr/bin/env python3
"""
HIDRS 自举系统演示 - 接入网络自动广播

展示完整的自我维持循环：
1. 网络检测器 - 监控网络连接
2. 自动广播器 - 发现网络就广播节点
3. 拓扑更新器 - 实时更新全局拓扑
4. 分布式计算 - 用算力维护算力

这是HIDRS的终极形态：
一个用分布式计算来维护自己的分布式计算能力的自指系统

就像：
- 蛇吞尾（Ouroboros）：咬住自己尾巴的蛇
- 比特币：用算力保护算力
- 互联网：用网络管理网络
- HIDRS：用算力维护拓扑
"""
import sys
import os
import logging
import time
import signal
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hidrs.distributed_computing import (
    NodeManager,
    CapabilityAnalyzer,
    NetworkDetector,
    NetworkStatus,
    AutoBroadcaster,
    TopologyUpdater
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def print_separator(title=""):
    """打印分隔符"""
    width = 80
    if title:
        padding = (width - len(title) - 2) // 2
        print("=" * padding + f" {title} " + "=" * padding)
    else:
        print("=" * width)


class HIDRSBootstrapSystem:
    """HIDRS自举系统"""

    def __init__(self):
        """初始化自举系统"""
        print_separator("HIDRS 自举系统初始化")

        # 1. 创建节点管理器
        print("\n1. 创建节点管理器...")
        self.node_manager = NodeManager(
            listen_port=9876,
            heartbeat_interval=30,
            enable_lan_discovery=True
        )

        # 2. 创建算力评估器
        print("2. 创建算力评估器...")
        self.capability_analyzer = CapabilityAnalyzer(
            weight_cpu=0.4,
            weight_gpu=0.3,
            weight_memory=0.2,
            weight_network=0.1
        )

        # 3. 创建网络检测器
        print("3. 创建网络检测器...")
        self.network_detector = NetworkDetector(
            check_interval=10,
            enable_auto_check=True
        )

        # 4. 创建自动广播器
        print("4. 创建自动广播器...")
        self.auto_broadcaster = AutoBroadcaster(
            node_manager=self.node_manager,
            network_detector=self.network_detector,
            capability_analyzer=self.capability_analyzer,
            broadcast_port=9877,
            heartbeat_interval=30
        )

        # 5. 创建拓扑更新器
        print("5. 创建拓扑更新器...")
        self.topology_updater = TopologyUpdater(
            node_manager=self.node_manager,
            auto_broadcaster=self.auto_broadcaster,
            update_interval=30
        )

        self._running = False

        print("\n✅ 自举系统初始化完成")
        print("\n系统架构:")
        print("  网络检测器 → 监控网络连接")
        print("      ↓")
        print("  自动广播器 → 发现网络就广播节点")
        print("      ↓")
        print("  拓扑更新器 → 实时更新全局拓扑")
        print("      ↓")
        print("  节点管理器 → 维护节点池")
        print("      ↓")
        print("  【循环】用算力维护拓扑")

    def start(self):
        """启动自举系统"""
        print_separator("启动自举系统")

        print("\n启动顺序:")

        # 1. 启动节点管理器
        print("1. 启动节点管理器...")
        self.node_manager.start()
        time.sleep(0.5)

        # 2. 启动网络检测器
        print("2. 启动网络检测器...")
        self.network_detector.start()
        time.sleep(0.5)

        # 3. 启动自动广播器
        print("3. 启动自动广播器...")
        self.auto_broadcaster.start()
        time.sleep(0.5)

        # 4. 启动拓扑更新器
        print("4. 启动拓扑更新器...")
        self.topology_updater.start()
        time.sleep(0.5)

        self._running = True

        print("\n✅ 自举系统已启动")
        print("\n系统现在会自动:")
        print("  1. 检测网络连接状态（每10秒）")
        print("  2. 网络连接时自动广播节点信息")
        print("  3. 接收其他节点的广播")
        print("  4. 实时更新全局拓扑图")
        print("  5. 计算Fiedler向量识别关键节点")

        # 显示初始状态
        self._show_status()

    def stop(self):
        """停止自举系统"""
        print_separator("停止自举系统")

        if not self._running:
            return

        self._running = False

        print("\n停止顺序:")

        # 逆序停止
        print("1. 停止拓扑更新器...")
        self.topology_updater.stop()

        print("2. 停止自动广播器...")
        self.auto_broadcaster.stop()

        print("3. 停止网络检测器...")
        self.network_detector.stop()

        print("4. 停止节点管理器...")
        self.node_manager.stop()

        print("\n✅ 自举系统已停止")

    def run(self):
        """运行自举系统（阻塞）"""
        print_separator("HIDRS 自举系统运行中")
        print("\n系统正在运行...")
        print("  - 按 Ctrl+C 停止")
        print("  - 按 's' + Enter 显示状态")
        print("  - 按 't' + Enter 显示拓扑")
        print("  - 按 'n' + Enter 显示节点列表")
        print()

        try:
            while self._running:
                # 定期显示状态
                time.sleep(5)
                self._show_brief_status()

        except KeyboardInterrupt:
            print("\n\n收到停止信号，正在关闭...")
            self.stop()

    def _show_status(self):
        """显示系统状态"""
        print_separator("系统状态")

        # 1. 网络状态
        net_stats = self.network_detector.get_stats()
        print("\n📡 网络状态:")
        print(f"  状态: {net_stats['current_status']}")
        print(f"  本地IP: {net_stats['current_ip']}")
        print(f"  网关: {net_stats['current_gateway']}")
        print(f"  网络类型: {net_stats['network_type']}")
        print(f"  已连接: {'是' if net_stats['is_connected'] else '否'}")

        # 2. 广播统计
        bc_stats = self.auto_broadcaster.get_stats()
        print("\n📢 广播统计:")
        print(f"  本节点ID: {bc_stats['local_node_id']}")
        print(f"  广播次数: {bc_stats['broadcast_count']}")
        print(f"  接收广播: {bc_stats['received_broadcasts']}")
        print(f"  上次广播: {bc_stats['last_broadcast_time'] or '未广播'}")

        # 3. 节点统计
        node_stats = self.node_manager.get_stats()
        print("\n🌐 节点统计:")
        print(f"  总节点数: {node_stats['total_nodes']}")
        print(f"  在线节点: {node_stats['online_nodes']}")
        print(f"  关键节点: {node_stats['key_nodes']}")
        print(f"  总CPU核心: {node_stats['total_cpu_cores']}")
        print(f"  总内存: {node_stats['total_memory_gb']:.1f} GB")
        print(f"  总GPU: {node_stats['total_gpu_count']}")

        # 4. 拓扑统计
        topo_stats = self.topology_updater.get_stats()
        print("\n🗺️ 拓扑统计:")
        print(f"  更新次数: {topo_stats['update_count']}")
        print(f"  全量更新: {topo_stats['full_updates']}")
        print(f"  增量更新: {topo_stats['incremental_updates']}")
        print(f"  当前节点数: {topo_stats['current_node_count']}")
        if topo_stats['current_fiedler_value']:
            print(f"  Fiedler值: {topo_stats['current_fiedler_value']:.6f}")
        print(f"  关键节点数: {topo_stats['current_key_nodes_count']}")

    def _show_brief_status(self):
        """显示简要状态"""
        net_stats = self.network_detector.get_stats()
        node_stats = self.node_manager.get_stats()
        topo_stats = self.topology_updater.get_stats()

        status_line = (
            f"[{datetime.now().strftime('%H:%M:%S')}] "
            f"网络: {net_stats['current_status']} | "
            f"节点: {node_stats['online_nodes']}/{node_stats['total_nodes']} | "
            f"关键节点: {node_stats['key_nodes']} | "
            f"拓扑更新: {topo_stats['update_count']} 次"
        )

        print(status_line)

    def _show_topology(self):
        """显示拓扑详情"""
        print_separator("全局拓扑")

        snapshot = self.topology_updater.get_current_topology()

        if not snapshot:
            print("\n⚠️ 拓扑尚未初始化")
            return

        print(f"\n时间: {snapshot.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"节点数: {snapshot.node_count}")
        print(f"Fiedler值: {snapshot.fiedler_value:.6f}")

        print(f"\n关键节点 ({len(snapshot.key_nodes)}):")
        for node_id in snapshot.key_nodes:
            node = self.node_manager.get_node(node_id)
            if node:
                print(f"  ⭐ [{node_id}] {node.host}:{node.port}")
                print(f"      Fiedler得分: {node.fiedler_score:.4f}")
                print(f"      算力得分: {node.capability_score:.2f}")

        # 拓扑变化分析
        change = self.topology_updater.analyze_topology_change()
        if change:
            print(f"\n拓扑变化:")
            print(f"  节点变化: {change['node_count_change']:+d}")
            print(f"  Fiedler值变化: {change['fiedler_value_change']:+.6f}")
            print(f"  拓扑稳定性: {'稳定' if change['topology_stability'] else '不稳定'}")

            if change['new_key_nodes']:
                print(f"  新增关键节点: {', '.join(change['new_key_nodes'])}")
            if change['lost_key_nodes']:
                print(f"  失去关键节点: {', '.join(change['lost_key_nodes'])}")

    def _show_nodes(self):
        """显示节点列表"""
        print_separator("节点列表")

        nodes = self.node_manager.get_online_nodes()

        if not nodes:
            print("\n⚠️ 没有在线节点")
            return

        print(f"\n在线节点 ({len(nodes)}):")

        for node in nodes:
            key_mark = "⭐" if node.is_key_node else "  "
            print(f"\n{key_mark}[{node.node_id}]")
            print(f"  地址: {node.host}:{node.port}")
            print(f"  状态: {node.status.value}")
            print(f"  CPU: {node.cpu_cores}核 @ {node.cpu_freq_mhz:.0f}MHz")
            print(f"  内存: {node.memory_gb:.1f}GB")
            print(f"  GPU: {node.gpu_count}个")
            print(f"  算力得分: {node.capability_score:.2f}")
            print(f"  Fiedler得分: {node.fiedler_score:.4f}")
            if node.last_seen:
                print(f"  最后心跳: {node.last_seen.strftime('%H:%M:%S')}")


def demo_scenario_1():
    """场景1：笔记本从睡眠唤醒"""
    print_separator("场景1: 笔记本从睡眠唤醒")
    print("\n模拟场景:")
    print("  1. 笔记本合上盖子（断网）")
    print("  2. 移动到新地点")
    print("  3. 打开盖子（自动连接WiFi）")
    print("  4. HIDRS检测到网络 → 自动广播 → 加入拓扑")

    print("\n预期行为:")
    print("  ✅ 网络检测器检测到连接")
    print("  ✅ 自动广播器发送JOIN消息")
    print("  ✅ 其他节点收到广播并更新拓扑")
    print("  ✅ 拓扑更新器重新计算Fiedler向量")
    print("  ✅ 新节点被分配任务（如果是关键节点）")


def demo_scenario_2():
    """场景2：服务器重启"""
    print_separator("场景2: 服务器重启")
    print("\n模拟场景:")
    print("  1. 数据中心服务器例行重启")
    print("  2. 系统启动")
    print("  3. 网络服务就绪")
    print("  4. HIDRS自动启动并广播")

    print("\n预期行为:")
    print("  ✅ 开机自启动（systemd service）")
    print("  ✅ 网络检测器等待网络就绪")
    print("  ✅ 3秒后自动广播节点信息")
    print("  ✅ 重新加入全球拓扑")
    print("  ✅ 恢复承担计算任务")


def demo_scenario_3():
    """场景3：网络切换"""
    print_separator("场景3: 网络切换")
    print("\n模拟场景:")
    print("  1. 手机从家庭WiFi切换到移动数据")
    print("  2. IP地址改变")
    print("  3. HIDRS检测到IP变化")
    print("  4. 重新广播新地址")

    print("\n预期行为:")
    print("  ✅ 网络检测器检测到IP变化")
    print("  ✅ 自动广播器发送更新的节点信息")
    print("  ✅ 其他节点更新路由表")
    print("  ✅ 任务继续无缝执行")


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print(" " * 20 + "HIDRS 自举系统演示")
    print(" " * 15 + "接入网络就自动广播节点信息")
    print("=" * 80)

    print("\n核心概念:")
    print("  用HIDRS来养HIDRS - 自我维持的分布式拓扑监控系统")
    print("\n类比:")
    print("  - 蛇吞尾（Ouroboros）：咬住自己尾巴的蛇")
    print("  - 比特币：用算力保护算力")
    print("  - HIDRS：用算力维护拓扑")

    print("\n自举循环:")
    print("  新节点接入网络")
    print("      ↓")
    print("  网络检测器发现连接")
    print("      ↓")
    print("  自动广播节点信息")
    print("      ↓")
    print("  被加入全局拓扑")
    print("      ↓")
    print("  开始贡献算力")
    print("      ↓")
    print("  帮助维护拓扑")
    print("      ↓")
    print("  【循环】")

    # 演示场景
    print("\n")
    demo_scenario_1()
    input("\n按Enter键继续...")

    demo_scenario_2()
    input("\n按Enter键继续...")

    demo_scenario_3()
    input("\n按Enter键继续...")

    # 启动系统
    print_separator("启动实际系统")
    print("\n现在启动真实的HIDRS自举系统...")
    input("按Enter键开始...")

    system = HIDRSBootstrapSystem()

    # 设置信号处理
    def signal_handler(sig, frame):
        print("\n\n收到停止信号")
        system.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # 启动
    system.start()

    # 运行
    system.run()


if __name__ == "__main__":
    main()
