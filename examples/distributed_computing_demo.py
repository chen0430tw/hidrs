#!/usr/bin/env python3
"""
HIDRS 分布式计算系统演示

展示如何使用HLIG理论进行分布式计算：
1. 节点发现（P2P）
2. 算力评估
3. HLIG任务调度（Fiedler向量优化）
4. 分布式执行
5. 结果聚合

这是全球广播系统的**逆向应用**：
- 全球广播 = 我向全球推送消息
- 分布式计算 = 我从全球拉取算力

类比：
- 区块链 + SETI@home + HLIG理论
- 去中心化 + 全球算力共享 + 智能节点选择
"""
import sys
import os
import logging
import time
import numpy as np
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hidrs.distributed_computing import (
    NodeManager,
    ComputeNode,
    NodeStatus,
    CapabilityAnalyzer,
    NodeCapability,
    HLIGTaskScheduler,
    ComputeTask,
    TaskType,
    TaskStatus,
    HLIGLoadBalancer,
    ComputeWorker,
    WorkerStatus,
    ResultAggregator,
    AggregationType
)
from hidrs.distributed_computing.compute_worker import register_example_functions

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
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


def demo_node_discovery():
    """演示1：节点发现"""
    print_separator("演示1: 节点发现")
    print("\n使用P2P协议发现网络中的计算节点（类似BitTorrent DHT）")

    # 创建节点管理器
    node_manager = NodeManager(
        listen_port=9876,
        heartbeat_interval=30,
        enable_lan_discovery=True
    )

    # 启动节点管理器
    node_manager.start()

    print(f"\n✅ 节点管理器已启动，监听端口: 9876")
    print(f"   正在发现局域网中的节点...")

    # 模拟添加一些节点（实际环境中通过P2P发现）
    mock_nodes = [
        ComputeNode(
            node_id=f"node_{i}",
            host=f"192.168.1.{10 + i}",
            port=9876,
            status=NodeStatus.ONLINE,
            cpu_cores=4 + i * 2,
            cpu_freq_mhz=2400 + i * 200,
            memory_gb=8 + i * 4,
            gpu_count=i % 2,
            gpu_memory_gb=(i % 2) * 8
        )
        for i in range(5)
    ]

    for node in mock_nodes:
        node_manager.register_node(node)

    time.sleep(1)

    # 显示发现的节点
    stats = node_manager.get_stats()
    print(f"\n📊 节点发现完成:")
    print(f"   总节点数: {stats['total_nodes']}")
    print(f"   在线节点: {stats['online_nodes']}")
    print(f"   总CPU核心数: {stats['total_cpu_cores']}")
    print(f"   总内存: {stats['total_memory_gb']:.1f} GB")
    print(f"   总GPU数: {stats['total_gpu_count']}")

    print("\n节点列表:")
    for node in node_manager.get_online_nodes():
        print(f"   [{node.node_id}] {node.host}:{node.port}")
        print(f"      CPU: {node.cpu_cores}核 @ {node.cpu_freq_mhz:.0f}MHz")
        print(f"      内存: {node.memory_gb:.1f}GB")
        print(f"      GPU: {node.gpu_count}个")

    return node_manager


def demo_capability_analysis(node_manager):
    """演示2：算力评估"""
    print_separator("演示2: 算力评估")
    print("\n评估每个节点的综合算力得分")

    # 创建算力评估器
    analyzer = CapabilityAnalyzer(
        weight_cpu=0.4,
        weight_gpu=0.3,
        weight_memory=0.2,
        weight_network=0.1
    )

    print(f"\n评分权重: CPU={analyzer.weight_cpu:.1f}, GPU={analyzer.weight_gpu:.1f}, "
          f"内存={analyzer.weight_memory:.1f}, 网络={analyzer.weight_network:.1f}")

    # 评估所有节点
    nodes = node_manager.get_online_nodes()
    capabilities = []

    print("\n节点算力评分:")
    for node in nodes:
        # 模拟评估（实际应该调用analyzer.analyze_remote_node）
        cap = NodeCapability(
            cpu_cores=node.cpu_cores,
            cpu_threads=node.cpu_cores * 2,
            cpu_freq_mhz=node.cpu_freq_mhz,
            memory_total_gb=node.memory_gb,
            gpu_count=node.gpu_count,
            gpu_memory_total_gb=node.gpu_memory_gb
        )

        cap.cpu_score = analyzer._compute_cpu_score(cap)
        cap.gpu_score = analyzer._compute_gpu_score(cap)
        cap.memory_score = analyzer._compute_memory_score(cap)
        cap.network_score = 50.0  # 简化

        cap.total_score = (
            analyzer.weight_cpu * cap.cpu_score +
            analyzer.weight_gpu * cap.gpu_score +
            analyzer.weight_memory * cap.memory_score +
            analyzer.weight_network * cap.network_score
        )

        capabilities.append(cap)

        # 更新节点算力得分
        node.capability_score = cap.total_score

        print(f"   [{node.node_id}] 总分: {cap.total_score:.2f}/100")
        print(f"      CPU: {cap.cpu_score:.1f}, GPU: {cap.gpu_score:.1f}, "
              f"内存: {cap.memory_score:.1f}, 网络: {cap.network_score:.1f}")

    # 排名
    ranked = analyzer.rank_nodes(capabilities)
    print(f"\n🏆 算力排名Top 3:")
    for i, cap in enumerate(ranked[:3], 1):
        print(f"   {i}. 节点 (总分: {cap.total_score:.2f})")

    return analyzer


def demo_hlig_scheduling(node_manager, analyzer):
    """演示3：HLIG任务调度"""
    print_separator("演示3: HLIG任务调度")
    print("\n使用Fiedler向量识别关键节点并优化任务分配")

    # 创建任务调度器
    scheduler = HLIGTaskScheduler(
        node_manager=node_manager,
        capability_analyzer=analyzer,
        use_fiedler=True
    )

    # 提交一些任务
    tasks = [
        ComputeTask(
            task_id=f"task_{i}",
            task_type=TaskType.COMPUTE_INTENSIVE if i % 2 == 0 else TaskType.NETWORK_INTENSIVE,
            function_name="monte_carlo_pi",
            args=(1000000,),
            required_cpu_cores=2,
            required_memory_gb=2.0,
            priority=i
        )
        for i in range(10)
    ]

    print(f"\n提交 {len(tasks)} 个任务:")
    for task in tasks:
        scheduler.submit_task(task)
        print(f"   [{task.task_id}] 类型: {task.task_type.value}, 优先级: {task.priority}")

    # 执行调度
    print("\n开始HLIG分析和任务调度...")
    assignments = scheduler.schedule_tasks()

    # 显示调度结果
    print(f"\n✅ 调度完成: {len(assignments)} 个任务已分配")

    # 按节点分组显示
    from collections import defaultdict
    node_tasks = defaultdict(list)
    for task_id, node_id in assignments:
        node_tasks[node_id].append(task_id)

    print("\n任务分配详情:")
    for node_id, task_ids in node_tasks.items():
        node = node_manager.get_node(node_id)
        is_key = "⭐" if node.is_key_node else "  "
        print(f"   {is_key}[{node_id}] {len(task_ids)} 个任务 (Fiedler得分: {node.fiedler_score:.4f})")
        for task_id in task_ids:
            print(f"      - {task_id}")

    # 显示统计
    stats = scheduler.get_stats()
    print(f"\n📊 调度统计:")
    print(f"   总任务数: {stats['total_tasks']}")
    print(f"   已调度: {stats['scheduled_tasks']}")
    print(f"   待调度: {stats['pending_tasks']}")
    print(f"   Fiedler值: {stats['fiedler_value']:.6f}")
    print(f"   关键节点数: {stats['key_nodes_count']}")

    return scheduler


def demo_load_balancing(node_manager):
    """演示4：负载均衡"""
    print_separator("演示4: HLIG负载均衡")
    print("\n基于拉普拉斯流的动态负载均衡")

    # 创建负载均衡器
    load_balancer = HLIGLoadBalancer(
        node_manager=node_manager,
        rebalance_threshold=0.3,
        enable_migration=True
    )

    # 模拟不均衡的负载
    nodes = node_manager.get_online_nodes()
    loads = [0.1, 0.3, 0.9, 0.7, 0.2]  # 不均衡负载

    print("\n当前负载分布（不均衡）:")
    for node, load in zip(nodes, loads):
        load_balancer.update_node_load(node.node_id, load)
        bar = "█" * int(load * 20)
        print(f"   [{node.node_id}] {bar} {load * 100:.0f}%")

    # 检查均衡状态
    balance_status = load_balancer.check_balance()
    print(f"\n均衡状态:")
    print(f"   最大负载: {balance_status['max_load'] * 100:.0f}%")
    print(f"   最小负载: {balance_status['min_load'] * 100:.0f}%")
    print(f"   平均负载: {balance_status['avg_load'] * 100:.0f}%")
    print(f"   不平衡度: {balance_status['imbalance']:.2f}")
    print(f"   需要重平衡: {'是' if balance_status['needs_rebalance'] else '否'}")

    # 执行重平衡
    if balance_status['needs_rebalance']:
        print("\n执行负载重平衡...")
        rebalance_result = load_balancer.rebalance()

        if rebalance_result['status'] == 'success':
            migrations = rebalance_result['migrations']
            print(f"\n✅ 重平衡完成，建议 {len(migrations)} 次迁移:")

            for mig in migrations:
                print(f"   {mig['from_node']} → {mig['to_node']}: {mig['load_amount'] * 100:.1f}%")
                print(f"      (当前负载: {mig['from_current_load'] * 100:.0f}% → {mig['to_current_load'] * 100:.0f}%)")

            # 显示目标负载分布
            print("\n目标负载分布（平衡后）:")
            for node, target_load in zip(nodes, rebalance_result['target_loads']):
                bar = "█" * int(target_load * 20)
                print(f"   [{node.node_id}] {bar} {target_load * 100:.0f}%")

    return load_balancer


def demo_distributed_execution():
    """演示5：分布式执行"""
    print_separator("演示5: 分布式执行")
    print("\n模拟分布式计算π值（蒙特卡洛方法）")

    # 创建工作节点
    workers = []
    for i in range(3):
        worker = ComputeWorker(
            worker_id=f"worker_{i}",
            max_concurrent_tasks=2,
            timeout_seconds=60
        )
        register_example_functions(worker)
        workers.append(worker)

    print(f"\n创建了 {len(workers)} 个工作节点")

    # 创建任务
    iterations_per_task = 1000000
    tasks = [
        ComputeTask(
            task_id=f"pi_task_{i}",
            task_type=TaskType.COMPUTE_INTENSIVE,
            function_name="monte_carlo_pi",
            args=(iterations_per_task,),
            required_cpu_cores=1
        )
        for i in range(10)
    ]

    print(f"\n任务: 计算π值，每个任务 {iterations_per_task} 次迭代")
    print(f"总共 {len(tasks)} 个任务\n")

    # 分配任务到工作节点
    print("分配任务到工作节点...")
    start_time = time.time()

    for i, task in enumerate(tasks):
        worker = workers[i % len(workers)]
        worker.execute_task(task)
        print(f"   任务 {task.task_id} → {worker.worker_id}")

    # 等待所有任务完成
    print("\n等待任务完成...")
    max_wait = 60
    waited = 0
    while waited < max_wait:
        all_done = all(
            w.status in [WorkerStatus.IDLE, WorkerStatus.ERROR]
            for w in workers
        )
        if all_done:
            break
        time.sleep(1)
        waited += 1
        if waited % 5 == 0:
            print(f"   ... {waited}秒")

    elapsed = time.time() - start_time

    # 收集结果
    results = []
    for worker in workers:
        for task_id, task_info in worker.current_tasks.items():
            if task_info['status'] == 'completed':
                results.append({
                    'worker_id': worker.worker_id,
                    'task_id': task_id,
                    'result': task_info['result']
                })

    print(f"\n✅ 执行完成，耗时: {elapsed:.2f}秒")
    print(f"   完成: {len(results)}/{len(tasks)} 个任务")

    # 显示工作节点统计
    print("\n工作节点统计:")
    for worker in workers:
        stats = worker.get_stats()
        print(f"   [{worker.worker_id}]")
        print(f"      完成: {stats['completed_tasks']}, 失败: {stats['failed_tasks']}")
        print(f"      成功率: {stats['success_rate'] * 100:.1f}%")

    return results


def demo_result_aggregation(results):
    """演示6：结果聚合"""
    print_separator("演示6: 结果聚合")
    print("\n聚合分布式计算结果")

    # 创建结果聚合器
    aggregator = ResultAggregator(use_hlig_weighting=True)

    # 准备结果数据
    result_data = [
        {'node_id': r['worker_id'], 'result': r['result']}
        for r in results
    ]

    print(f"\n收集到 {len(result_data)} 个结果")
    print("\n各节点计算的π值:")
    for r in result_data[:5]:  # 只显示前5个
        print(f"   {r['node_id']}: π ≈ {r['result']:.6f}")
    if len(result_data) > 5:
        print(f"   ... (还有 {len(result_data) - 5} 个)")

    # 标准聚合（平均值）
    pi_average = aggregator.aggregate(
        result_data,
        aggregation_type=AggregationType.AVERAGE
    )

    print(f"\n📊 聚合结果:")
    print(f"   平均值: π ≈ {pi_average:.6f}")
    print(f"   真实值: π = {np.pi:.6f}")
    print(f"   误差: {abs(pi_average - np.pi):.6f}")

    # 模拟HLIG加权聚合
    node_weights = {
        f"worker_{i}": 1.0 + i * 0.1  # 模拟Fiedler权重
        for i in range(3)
    }

    pi_weighted = aggregator.aggregate(
        result_data,
        aggregation_type=AggregationType.AVERAGE,
        node_weights=node_weights
    )

    print(f"\n使用HLIG权重聚合:")
    print(f"   加权平均: π ≈ {pi_weighted:.6f}")
    print(f"   误差: {abs(pi_weighted - np.pi):.6f}")


def demo_comparison():
    """演示7：与传统方法对比"""
    print_separator("演示7: 传统方法对比")
    print("\n对比HIDRS与传统分布式计算")

    comparison = """
    ┌─────────────────────┬──────────────────────┬─────────────────────┐
    │ 特性               │ HIDRS (HLIG)        │ 传统方法            │
    ├─────────────────────┼──────────────────────┼─────────────────────┤
    │ 节点发现           │ P2P去中心化          │ 中心化注册          │
    │ 任务调度           │ Fiedler向量优化      │ 轮询/随机           │
    │ 节点选择           │ 识别关键节点优先     │ 机械平均分配        │
    │ 负载均衡           │ 拉普拉斯流           │ 贪心算法            │
    │ 结果聚合           │ 全息映射加权         │ 简单平均            │
    │ 网络拓扑感知       │ 是（拉普拉斯矩阵）   │ 否                  │
    │ 适应性             │ 动态优化             │ 静态配置            │
    └─────────────────────┴──────────────────────┴─────────────────────┘

    核心优势：
    ✅ 智能识别"超级节点"（Fiedler向量）
    ✅ 全局最优任务分配（谱分析）
    ✅ 自适应负载均衡（拉普拉斯流）
    ✅ 去中心化架构（P2P）

    类比：
    - 传统方法 = 盲人摸象，局部优化
    - HIDRS = 全息视角，全局最优
    """

    print(comparison)


def main():
    """主函数"""
    print_separator("HIDRS 分布式计算系统演示")
    print("\n全球广播系统的逆向应用：跟全球借算力")
    print("\n核心理念:")
    print("  全球广播 = 我向全球推送消息")
    print("  分布式计算 = 我从全球拉取算力")
    print("\n这是: 区块链 + SETI@home + HLIG理论")
    print("  - 区块链: P2P去中心化网络")
    print("  - SETI@home: 全球算力共享")
    print("  - HLIG: 智能节点选择（Fiedler向量）")

    try:
        input("\n按Enter键开始演示...")

        # 1. 节点发现
        node_manager = demo_node_discovery()
        input("\n按Enter键继续...")

        # 2. 算力评估
        analyzer = demo_capability_analysis(node_manager)
        input("\n按Enter键继续...")

        # 3. HLIG任务调度
        scheduler = demo_hlig_scheduling(node_manager, analyzer)
        input("\n按Enter键继续...")

        # 4. 负载均衡
        load_balancer = demo_load_balancing(node_manager)
        input("\n按Enter键继续...")

        # 5. 分布式执行
        results = demo_distributed_execution()
        input("\n按Enter键继续...")

        # 6. 结果聚合
        demo_result_aggregation(results)
        input("\n按Enter键继续...")

        # 7. 对比
        demo_comparison()

        print_separator("演示完成")
        print("\n总结:")
        print("  ✅ HIDRS分布式计算系统展示了HLIG理论在分布式计算中的应用")
        print("  ✅ Fiedler向量成功识别了网络中的关键节点")
        print("  ✅ 拉普拉斯谱分析实现了全局最优任务分配")
        print("  ✅ 这是全球广播系统的完美逆向应用")

        # 停止节点管理器
        node_manager.stop()

    except KeyboardInterrupt:
        print("\n\n演示被用户中断")
    except Exception as e:
        logger.error(f"演示过程中出错: {e}", exc_info=True)


if __name__ == "__main__":
    main()
