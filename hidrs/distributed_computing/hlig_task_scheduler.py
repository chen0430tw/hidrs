"""
HLIG任务调度器 - 使用拉普拉斯谱分析优化任务分配

核心算法：
1. 构建节点网络拓扑（邻接矩阵 W）
2. 计算拉普拉斯矩阵 L = D - W
3. 计算Fiedler向量（λ₂对应的特征向量）
4. 根据Fiedler向量分配任务到关键节点

Fiedler向量的含义：
- 分量绝对值大 → 节点在网络中更重要/更中心
- 分量符号 → 节点所属的社区/集群

任务分配策略：
1. 计算密集型任务 → 分配给高算力节点（基于capability_score）
2. 通信密集型任务 → 分配给网络中心节点（基于Fiedler向量）
3. 混合型任务 → 综合考虑

类比：
- 传统调度: 轮询/随机分配（公平但低效）
- HLIG调度: 识别"超级节点"优先分配（效率优先）
"""
import logging
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """任务类型"""
    COMPUTE_INTENSIVE = "compute"  # 计算密集型
    NETWORK_INTENSIVE = "network"  # 网络密集型
    MEMORY_INTENSIVE = "memory"    # 内存密集型
    MIXED = "mixed"                # 混合型


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"           # 待分配
    SCHEDULED = "scheduled"       # 已调度
    RUNNING = "running"           # 运行中
    COMPLETED = "completed"       # 已完成
    FAILED = "failed"             # 失败
    CANCELLED = "cancelled"       # 已取消


@dataclass
class ComputeTask:
    """计算任务"""
    task_id: str                              # 任务ID
    task_type: TaskType                       # 任务类型
    status: TaskStatus = TaskStatus.PENDING   # 状态

    # 任务描述
    function_name: str = ""                   # 函数名
    args: tuple = field(default_factory=tuple)  # 参数
    kwargs: dict = field(default_factory=dict)  # 关键字参数

    # 资源需求
    required_cpu_cores: int = 1               # 需要的CPU核心数
    required_memory_gb: float = 1.0           # 需要的内存（GB）
    required_gpu_count: int = 0               # 需要的GPU数量
    estimated_runtime_seconds: float = 60.0   # 预计运行时间（秒）

    # 调度信息
    assigned_node_id: Optional[str] = None    # 分配的节点ID
    scheduled_at: Optional[datetime] = None   # 调度时间
    started_at: Optional[datetime] = None     # 开始时间
    completed_at: Optional[datetime] = None   # 完成时间

    # 结果
    result: Optional[any] = None              # 结果数据
    error: Optional[str] = None               # 错误信息

    # 优先级和权重
    priority: int = 0                         # 优先级（数字越大越高）
    weight: float = 1.0                       # 权重（用于负载均衡）

    # 元数据
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'task_id': self.task_id,
            'task_type': self.task_type.value,
            'status': self.status.value,
            'function_name': self.function_name,
            'required_cpu_cores': self.required_cpu_cores,
            'required_memory_gb': self.required_memory_gb,
            'required_gpu_count': self.required_gpu_count,
            'estimated_runtime_seconds': self.estimated_runtime_seconds,
            'assigned_node_id': self.assigned_node_id,
            'priority': self.priority,
            'scheduled_at': self.scheduled_at.isoformat() if self.scheduled_at else None,
            'metadata': self.metadata
        }


class HLIGTaskScheduler:
    """HLIG任务调度器 - 使用拉普拉斯谱分析优化任务分配"""

    def __init__(
        self,
        node_manager,
        capability_analyzer,
        similarity_threshold: float = 0.5,
        use_fiedler: bool = True
    ):
        """
        初始化HLIG任务调度器

        参数:
        - node_manager: 节点管理器
        - capability_analyzer: 算力评估器
        - similarity_threshold: 相似度阈值（构建邻接矩阵时使用）
        - use_fiedler: 是否使用Fiedler向量优化（默认True）
        """
        self.node_manager = node_manager
        self.capability_analyzer = capability_analyzer
        self.similarity_threshold = similarity_threshold
        self.use_fiedler = use_fiedler

        # 任务队列
        self.tasks: Dict[str, ComputeTask] = {}
        self.pending_tasks: List[str] = []  # 待分配任务ID列表

        # HLIG分析结果（缓存）
        self._fiedler_vector: Optional[np.ndarray] = None
        self._fiedler_value: Optional[float] = None
        self._node_importance: Dict[str, float] = {}  # 节点重要性得分
        self._last_analysis_time: Optional[datetime] = None

        logger.info("[HLIGTaskScheduler] 初始化完成")
        logger.info(f"  使用Fiedler向量优化: {use_fiedler}")
        logger.info(f"  相似度阈值: {similarity_threshold}")

    def submit_task(self, task: ComputeTask) -> str:
        """
        提交任务

        参数:
        - task: 计算任务

        返回:
        - task_id: 任务ID
        """
        if not task.task_id:
            task.task_id = f"task_{uuid.uuid4().hex[:8]}"

        self.tasks[task.task_id] = task
        self.pending_tasks.append(task.task_id)

        logger.info(f"[HLIGTaskScheduler] 提交任务: {task.task_id} (类型: {task.task_type.value})")
        return task.task_id

    def schedule_tasks(self) -> List[Tuple[str, str]]:
        """
        调度所有待分配任务

        返回:
        - 分配结果列表 [(task_id, node_id), ...]
        """
        if not self.pending_tasks:
            logger.debug("[HLIGTaskScheduler] 没有待调度任务")
            return []

        # 1. 获取可用节点
        available_nodes = self.node_manager.get_available_nodes()
        if not available_nodes:
            logger.warning("[HLIGTaskScheduler] 没有可用节点")
            return []

        logger.info(f"[HLIGTaskScheduler] 开始调度 {len(self.pending_tasks)} 个任务到 {len(available_nodes)} 个节点")

        # 2. 执行HLIG分析（识别关键节点）
        if self.use_fiedler:
            self._analyze_network_topology(available_nodes)

        # 3. 分配任务
        assignments = []
        for task_id in self.pending_tasks[:]:  # 复制列表以避免修改迭代对象
            task = self.tasks[task_id]

            # 选择最佳节点
            best_node = self._select_best_node(task, available_nodes)

            if best_node:
                # 分配任务
                task.assigned_node_id = best_node.node_id
                task.status = TaskStatus.SCHEDULED
                task.scheduled_at = datetime.now()

                assignments.append((task_id, best_node.node_id))
                self.pending_tasks.remove(task_id)

                logger.info(f"[HLIGTaskScheduler] 任务 {task_id} 分配到节点 {best_node.node_id}")

        logger.info(f"[HLIGTaskScheduler] 调度完成: {len(assignments)}/{len(self.pending_tasks) + len(assignments)} 个任务")

        return assignments

    def _analyze_network_topology(self, nodes: List):
        """
        分析网络拓扑（HLIG核心）

        步骤：
        1. 构建邻接矩阵 W（基于节点相似度）
        2. 计算拉普拉斯矩阵 L = D - W
        3. 计算Fiedler向量
        4. 更新节点重要性得分
        """
        try:
            from hidrs.network_topology.laplacian_matrix_calculator import LaplacianMatrixCalculator
            from hidrs.network_topology.spectral_analyzer import SpectralAnalyzer

            n = len(nodes)
            if n < 2:
                logger.warning("[HLIGTaskScheduler] 节点数不足，跳过HLIG分析")
                return

            logger.debug(f"[HLIGTaskScheduler] 开始HLIG分析，节点数: {n}")

            # 1. 构建邻接矩阵 W
            # 基于节点算力和网络距离的相似度
            W = np.zeros((n, n))

            for i in range(n):
                for j in range(i + 1, n):
                    # 计算相似度（简化版）
                    sim = self._compute_node_similarity(nodes[i], nodes[j])
                    if sim >= self.similarity_threshold:
                        W[i, j] = sim
                        W[j, i] = sim

            # 2. 构建拉普拉斯矩阵
            laplacian_calc = LaplacianMatrixCalculator(normalized=True)
            L = laplacian_calc.compute_laplacian(W)

            # 3. 计算Fiedler向量
            spectral = SpectralAnalyzer(use_sparse=True, k=10)
            self._fiedler_vector = spectral.compute_fiedler_vector(L)
            self._fiedler_value = spectral.compute_fiedler_value(L)

            logger.info(f"[HLIGTaskScheduler] HLIG分析完成: Fiedler值={self._fiedler_value:.6f}")

            # 4. 更新节点重要性得分
            self._node_importance = {}
            for i, node in enumerate(nodes):
                # Fiedler向量分量的绝对值 = 节点重要性
                importance = abs(self._fiedler_vector[i])
                self._node_importance[node.node_id] = float(importance)

                # 标记关键节点（Fiedler得分在前20%）
                node.fiedler_score = float(importance)

            # 标记关键节点
            sorted_nodes = sorted(nodes, key=lambda n: n.fiedler_score, reverse=True)
            top_20_percent = max(1, int(len(sorted_nodes) * 0.2))
            for node in sorted_nodes[:top_20_percent]:
                node.is_key_node = True

            logger.info(f"[HLIGTaskScheduler] 识别到 {top_20_percent} 个关键节点")

            self._last_analysis_time = datetime.now()

        except Exception as e:
            logger.error(f"[HLIGTaskScheduler] HLIG分析失败: {e}", exc_info=True)

    def _compute_node_similarity(self, node1, node2) -> float:
        """
        计算节点相似度

        考虑因素：
        - 算力相似度（CPU/GPU/内存）
        - 网络距离相似度（延迟/带宽）

        返回:
        - 相似度（0-1）
        """
        # 1. 算力相似度
        cap1_score = node1.capability_score if hasattr(node1, 'capability_score') else 50.0
        cap2_score = node2.capability_score if hasattr(node2, 'capability_score') else 50.0

        cap_diff = abs(cap1_score - cap2_score)
        cap_similarity = 1.0 - min(cap_diff / 100.0, 1.0)

        # 2. 网络距离相似度（简化：假设同一局域网内相似度高）
        # 实际应该测量节点间的网络延迟
        net_similarity = 0.8  # 简化假设

        # 综合相似度
        similarity = 0.6 * cap_similarity + 0.4 * net_similarity

        return similarity

    def _select_best_node(self, task: ComputeTask, available_nodes: List) -> Optional:
        """
        选择最佳节点

        策略：
        1. 过滤资源不足的节点
        2. 根据任务类型选择优先策略
        3. 使用HLIG重要性得分（如果启用）

        返回:
        - 最佳节点，如果没有合适节点则返回None
        """
        # 1. 过滤资源不足的节点
        capable_nodes = []
        for node in available_nodes:
            if self._node_can_handle_task(node, task):
                capable_nodes.append(node)

        if not capable_nodes:
            logger.warning(f"[HLIGTaskScheduler] 没有节点能处理任务 {task.task_id}")
            return None

        # 2. 根据任务类型计算节点得分
        node_scores = []
        for node in capable_nodes:
            score = self._compute_node_score_for_task(node, task)
            node_scores.append((node, score))

        # 3. 选择得分最高的节点
        node_scores.sort(key=lambda x: x[1], reverse=True)
        best_node = node_scores[0][0]

        logger.debug(f"[HLIGTaskScheduler] 为任务 {task.task_id} 选择节点 {best_node.node_id} (得分: {node_scores[0][1]:.2f})")

        return best_node

    def _node_can_handle_task(self, node, task: ComputeTask) -> bool:
        """检查节点是否有足够资源处理任务"""
        # 简化检查：只检查基本资源
        if task.required_cpu_cores > node.cpu_cores:
            return False
        if task.required_memory_gb > node.memory_gb:
            return False
        if task.required_gpu_count > node.gpu_count:
            return False

        return True

    def _compute_node_score_for_task(self, node, task: ComputeTask) -> float:
        """
        计算节点对任务的适配得分

        返回:
        - 得分（0-100）
        """
        score = 0.0

        # 1. 基础算力得分
        cap_score = node.capability_score if hasattr(node, 'capability_score') else 50.0
        score += cap_score * 0.5

        # 2. Fiedler重要性得分（如果启用HLIG）
        if self.use_fiedler and node.node_id in self._node_importance:
            fiedler_importance = self._node_importance[node.node_id]
            score += fiedler_importance * 100 * 0.3

        # 3. 任务类型特定得分
        if task.task_type == TaskType.COMPUTE_INTENSIVE:
            # 计算密集型 → 优先选择高CPU/GPU节点
            cpu_score = min(node.cpu_cores / 32.0, 1.0) * 10
            gpu_score = min(node.gpu_count / 8.0, 1.0) * 10
            score += cpu_score + gpu_score

        elif task.task_type == TaskType.NETWORK_INTENSIVE:
            # 网络密集型 → 优先选择网络中心节点（高Fiedler得分）
            if self.use_fiedler and hasattr(node, 'fiedler_score'):
                score += node.fiedler_score * 100 * 0.5

        elif task.task_type == TaskType.MEMORY_INTENSIVE:
            # 内存密集型 → 优先选择大内存节点
            mem_score = min(node.memory_gb / 256.0, 1.0) * 20
            score += mem_score

        return score

    def get_task(self, task_id: str) -> Optional[ComputeTask]:
        """获取任务"""
        return self.tasks.get(task_id)

    def update_task_status(self, task_id: str, status: TaskStatus, result=None, error=None):
        """更新任务状态"""
        task = self.tasks.get(task_id)
        if not task:
            logger.warning(f"[HLIGTaskScheduler] 任务不存在: {task_id}")
            return

        task.status = status

        if status == TaskStatus.RUNNING:
            task.started_at = datetime.now()
        elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            task.completed_at = datetime.now()

        if result is not None:
            task.result = result
        if error is not None:
            task.error = error

        logger.info(f"[HLIGTaskScheduler] 任务状态更新: {task_id} -> {status.value}")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        total = len(self.tasks)
        pending = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING)
        scheduled = sum(1 for t in self.tasks.values() if t.status == TaskStatus.SCHEDULED)
        running = sum(1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING)
        completed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)

        return {
            'total_tasks': total,
            'pending_tasks': pending,
            'scheduled_tasks': scheduled,
            'running_tasks': running,
            'completed_tasks': completed,
            'failed_tasks': failed,
            'success_rate': completed / total if total > 0 else 0,
            'use_fiedler': self.use_fiedler,
            'fiedler_value': float(self._fiedler_value) if self._fiedler_value is not None else None,
            'key_nodes_count': len([n for n in self._node_importance.values() if n > 0.5]),
            'last_analysis_time': self._last_analysis_time.isoformat() if self._last_analysis_time else None
        }
