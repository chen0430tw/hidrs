"""
HLIG负载均衡器 - 基于拉普拉斯流的动态负载均衡

核心思想：
1. 将负载视为网络中的"流"
2. 使用拉普拉斯矩阵计算流的分布
3. Fiedler向量指示最优流向

拉普拉斯流理论：
- L·x = b （L是拉普拉斯矩阵，x是节点电位，b是电流源）
- 电流会自动流向低电位区域
- 类比：任务会自动分配到低负载节点

与传统负载均衡的区别：
- 轮询（Round Robin）: 机械平均分配
- 最少连接（Least Connections）: 贪心选择
- HLIG: 全局最优，考虑网络拓扑
"""
import logging
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class HLIGLoadBalancer:
    """HLIG负载均衡器"""

    def __init__(
        self,
        node_manager,
        rebalance_threshold: float = 0.3,
        enable_migration: bool = False
    ):
        """
        初始化HLIG负载均衡器

        参数:
        - node_manager: 节点管理器
        - rebalance_threshold: 重平衡阈值（负载差异超过此值时触发）
        - enable_migration: 是否启用任务迁移（默认禁用）
        """
        self.node_manager = node_manager
        self.rebalance_threshold = rebalance_threshold
        self.enable_migration = enable_migration

        # 负载统计
        self.node_loads: Dict[str, float] = {}  # 节点负载 {node_id: load}
        self.last_rebalance_time: Optional[datetime] = None

        logger.info("[HLIGLoadBalancer] 初始化完成")
        logger.info(f"  重平衡阈值: {rebalance_threshold}")
        logger.info(f"  任务迁移: {'启用' if enable_migration else '禁用'}")

    def update_node_load(self, node_id: str, load: float):
        """
        更新节点负载

        参数:
        - node_id: 节点ID
        - load: 负载值（0-1）
        """
        self.node_loads[node_id] = load
        logger.debug(f"[HLIGLoadBalancer] 更新节点负载: {node_id} -> {load:.2f}")

    def check_balance(self) -> Dict:
        """
        检查负载均衡状态

        返回:
        - 均衡状态信息
        """
        if not self.node_loads:
            return {
                'balanced': True,
                'max_load': 0,
                'min_load': 0,
                'avg_load': 0,
                'load_variance': 0,
                'needs_rebalance': False
            }

        loads = list(self.node_loads.values())
        max_load = max(loads)
        min_load = min(loads)
        avg_load = sum(loads) / len(loads)
        load_variance = np.var(loads)

        # 负载不平衡度 = (最大负载 - 最小负载) / 平均负载
        imbalance = (max_load - min_load) / avg_load if avg_load > 0 else 0

        needs_rebalance = imbalance > self.rebalance_threshold

        return {
            'balanced': not needs_rebalance,
            'max_load': max_load,
            'min_load': min_load,
            'avg_load': avg_load,
            'load_variance': load_variance,
            'imbalance': imbalance,
            'needs_rebalance': needs_rebalance
        }

    def rebalance(self) -> Dict:
        """
        执行负载重平衡

        使用HLIG理论计算最优负载分布：
        1. 构建网络拉普拉斯矩阵 L
        2. 当前负载作为"电流源" b
        3. 求解 L·x = b 得到目标负载分布
        4. 生成重平衡建议

        返回:
        - 重平衡建议 {'migrations': [(task_id, from_node, to_node), ...]}
        """
        balance_status = self.check_balance()

        if not balance_status['needs_rebalance']:
            logger.info("[HLIGLoadBalancer] 负载已均衡，无需重平衡")
            return {'migrations': [], 'status': 'already_balanced'}

        logger.info(f"[HLIGLoadBalancer] 开始重平衡 (不平衡度: {balance_status['imbalance']:.2f})")

        try:
            # 1. 获取节点列表
            nodes = self.node_manager.get_online_nodes()
            if len(nodes) < 2:
                logger.warning("[HLIGLoadBalancer] 节点数不足，无法重平衡")
                return {'migrations': [], 'status': 'insufficient_nodes'}

            # 2. 构建拉普拉斯矩阵
            L = self._build_laplacian_matrix(nodes)

            # 3. 当前负载向量
            current_loads = np.array([self.node_loads.get(n.node_id, 0) for n in nodes])

            # 4. 计算目标负载分布
            target_loads = self._compute_target_loads(L, current_loads)

            # 5. 生成迁移建议
            migrations = self._generate_migration_plan(nodes, current_loads, target_loads)

            logger.info(f"[HLIGLoadBalancer] 重平衡完成，建议 {len(migrations)} 次迁移")

            self.last_rebalance_time = datetime.now()

            return {
                'migrations': migrations,
                'status': 'success',
                'current_loads': current_loads.tolist(),
                'target_loads': target_loads.tolist()
            }

        except Exception as e:
            logger.error(f"[HLIGLoadBalancer] 重平衡失败: {e}", exc_info=True)
            return {'migrations': [], 'status': 'failed', 'error': str(e)}

    def _build_laplacian_matrix(self, nodes: List) -> np.ndarray:
        """
        构建拉普拉斯矩阵

        基于节点间的"连接强度"：
        - 网络延迟低 → 连接强
        - 算力相似 → 连接强
        """
        from hidrs.network_topology.laplacian_matrix_calculator import LaplacianMatrixCalculator

        n = len(nodes)
        W = np.zeros((n, n))

        # 构建邻接矩阵（基于网络距离和算力相似度）
        for i in range(n):
            for j in range(i + 1, n):
                # 简化：所有节点间都有连接，权重=1
                # 实际应该基于网络延迟和算力相似度
                weight = 1.0
                W[i, j] = weight
                W[j, i] = weight

        # 计算拉普拉斯矩阵
        laplacian_calc = LaplacianMatrixCalculator(normalized=False)
        L = laplacian_calc.compute_laplacian(W)

        return L

    def _compute_target_loads(self, L: np.ndarray, current_loads: np.ndarray) -> np.ndarray:
        """
        计算目标负载分布

        通过拉普拉斯扩散使负载沿图的拓扑结构从高负载节点流向低负载节点。

        数学原理：
        拉普拉斯矩阵L的行和为0（奇异），不能直接求逆。
        使用热扩散迭代：x_{t+1} = x_t - α · L · x_t
        其中 L·x 表示每个节点的净流出梯度，α是步长。
        按最大特征值缩放α保证数值稳定性。
        """
        n = len(current_loads)

        if n < 2:
            return current_loads.copy()

        # 转为稠密矩阵
        if hasattr(L, 'toarray'):
            L_dense = L.toarray().astype(float)
        else:
            L_dense = np.array(L, dtype=float)

        # 归一化步长（按最大特征值缩放，保证扩散收敛）
        eigenvalues = np.linalg.eigvalsh(L_dense)
        lambda_max = max(abs(eigenvalues.max()), 1e-10)
        alpha = 0.5 / lambda_max

        # 迭代扩散
        x = current_loads.copy().astype(float)
        total_load = np.sum(x)

        for _ in range(20):
            gradient = L_dense @ x
            x_new = x - alpha * gradient

            # 总负载守恒
            x_new = x_new * (total_load / (np.sum(x_new) + 1e-10))

            # 非负约束
            x_new = np.maximum(x_new, 0.0)

            # 收敛检查
            if np.linalg.norm(x_new - x) < 1e-6 * np.linalg.norm(x):
                break

            x = x_new

        return x

    def _generate_migration_plan(
        self,
        nodes: List,
        current_loads: np.ndarray,
        target_loads: np.ndarray
    ) -> List[Dict]:
        """
        生成任务迁移计划

        参数:
        - nodes: 节点列表
        - current_loads: 当前负载
        - target_loads: 目标负载

        返回:
        - 迁移计划列表 [{'from_node', 'to_node', 'load_amount'}, ...]
        """
        migrations = []

        if not self.enable_migration:
            logger.info("[HLIGLoadBalancer] 任务迁移被禁用")
            return migrations

        # 计算负载差异
        load_diffs = target_loads - current_loads

        # 找出需要减负载的节点（负载过高）
        overloaded_indices = np.where(load_diffs < -0.05)[0]  # 阈值5%
        # 找出可以增负载的节点（负载过低）
        underloaded_indices = np.where(load_diffs > 0.05)[0]

        # 生成迁移对
        for i in overloaded_indices:
            for j in underloaded_indices:
                from_node = nodes[i]
                to_node = nodes[j]
                load_to_migrate = min(-load_diffs[i], load_diffs[j])

                if load_to_migrate > 0.01:  # 至少迁移1%负载
                    migrations.append({
                        'from_node': from_node.node_id,
                        'to_node': to_node.node_id,
                        'load_amount': float(load_to_migrate),
                        'from_current_load': float(current_loads[i]),
                        'to_current_load': float(current_loads[j])
                    })

                    # 更新差异
                    load_diffs[i] += load_to_migrate
                    load_diffs[j] -= load_to_migrate

        return migrations

    def get_least_loaded_node(self, nodes: Optional[List] = None) -> Optional:
        """
        获取负载最低的节点

        参数:
        - nodes: 节点列表（可选，默认使用所有在线节点）

        返回:
        - 负载最低的节点
        """
        if nodes is None:
            nodes = self.node_manager.get_online_nodes()

        if not nodes:
            return None

        # 找出负载最低的节点
        min_load = float('inf')
        best_node = None

        for node in nodes:
            load = self.node_loads.get(node.node_id, 0)
            if load < min_load:
                min_load = load
                best_node = node

        return best_node

    def predict_node_load(self, node_id: str, additional_tasks: int = 0) -> float:
        """
        预测节点负载

        参数:
        - node_id: 节点ID
        - additional_tasks: 额外任务数

        返回:
        - 预测负载
        """
        current_load = self.node_loads.get(node_id, 0)

        # 简化：假设每个任务增加5%负载
        predicted_load = current_load + (additional_tasks * 0.05)

        return min(predicted_load, 1.0)  # 负载不超过100%

    def get_stats(self) -> Dict:
        """获取统计信息"""
        balance_status = self.check_balance()

        return {
            **balance_status,
            'total_nodes': len(self.node_loads),
            'enable_migration': self.enable_migration,
            'rebalance_threshold': self.rebalance_threshold,
            'last_rebalance_time': self.last_rebalance_time.isoformat() if self.last_rebalance_time else None
        }
