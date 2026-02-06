"""
HIDRS 分布式计算系统 - 基于HLIG理论的全球算力借用

核心理念：
全球广播的逆向应用 - 不是"我向全球推送"，而是"我从全球拉取算力"

HLIG理论应用：
1. Fiedler向量识别高算力节点（关键节点）
2. 拉普拉斯谱聚类划分计算任务
3. 全息映射实现本地→全局状态同步
4. 代数连通度评估网络计算能力

架构：
    任务提交
        ↓
    节点发现（P2P）  ← 发现可用计算节点
        ↓
    算力评估        ← CPU/GPU/内存/带宽
        ↓
    HLIG分析        ← Fiedler向量 + 谱聚类
        ↓
    任务分配        ← 优化分配到关键节点
        ↓
    并行计算        ← 分布式执行
        ↓
    结果聚合        ← 全息映射汇总
        ↓
    返回结果

与传统分布式计算的区别：
- BOINC/Folding@home: 中心化调度，随机分配
- HIDRS: 去中心化，HLIG理论优化分配，识别关键节点

类比：
- 全球广播 = 我有消息，找最优路径推送给全球
- 分布式计算 = 我有任务，找最优节点借用全球算力
"""

from .node_manager import NodeManager, ComputeNode, NodeStatus
from .capability_analyzer import CapabilityAnalyzer, NodeCapability
from .hlig_task_scheduler import HLIGTaskScheduler, ComputeTask, TaskType, TaskStatus
from .hlig_load_balancer import HLIGLoadBalancer
from .compute_worker import ComputeWorker, WorkerStatus
from .result_aggregator import ResultAggregator, AggregationType
from .network_detector import NetworkDetector, NetworkStatus, NetworkType
from .auto_broadcaster import AutoBroadcaster, BroadcastMessage
from .topology_updater import TopologyUpdater, TopologySnapshot

__all__ = [
    'NodeManager',
    'ComputeNode',
    'NodeStatus',
    'CapabilityAnalyzer',
    'NodeCapability',
    'HLIGTaskScheduler',
    'ComputeTask',
    'TaskType',
    'TaskStatus',
    'HLIGLoadBalancer',
    'ComputeWorker',
    'WorkerStatus',
    'ResultAggregator',
    'AggregationType',
    'NetworkDetector',
    'NetworkStatus',
    'NetworkType',
    'AutoBroadcaster',
    'BroadcastMessage',
    'TopologyUpdater',
    'TopologySnapshot'
]
