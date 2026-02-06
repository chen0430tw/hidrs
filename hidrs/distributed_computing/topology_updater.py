"""
拓扑更新器 - 实时更新全局网络拓扑

核心功能：
1. 监听节点加入/离开事件
2. 实时更新拉普拉斯矩阵
3. 重新计算Fiedler向量
4. 更新节点重要性得分
5. 通知其他组件拓扑变化

更新策略：
- 增量更新：单个节点变化时局部更新
- 全量更新：节点数量变化>10%时全量重算
- 延迟更新：批量变化时延迟3秒再更新

这是HIDRS自我维持的核心：
用分布式算力计算分布式拓扑
"""
import logging
import numpy as np
import threading
import time
from typing import Dict, List, Optional, Callable
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


class TopologySnapshot:
    """拓扑快照"""

    def __init__(
        self,
        timestamp: datetime,
        node_count: int,
        laplacian_matrix: np.ndarray,
        fiedler_vector: np.ndarray,
        fiedler_value: float,
        key_nodes: List[str]
    ):
        """
        初始化拓扑快照

        参数:
        - timestamp: 快照时间
        - node_count: 节点数量
        - laplacian_matrix: 拉普拉斯矩阵
        - fiedler_vector: Fiedler向量
        - fiedler_value: Fiedler值
        - key_nodes: 关键节点列表
        """
        self.timestamp = timestamp
        self.node_count = node_count
        self.laplacian_matrix = laplacian_matrix
        self.fiedler_vector = fiedler_vector
        self.fiedler_value = fiedler_value
        self.key_nodes = key_nodes


class TopologyUpdater:
    """拓扑更新器 - 实时维护全局拓扑"""

    def __init__(
        self,
        node_manager,
        auto_broadcaster,
        update_interval: int = 30,
        enable_auto_update: bool = True,
        batch_delay: float = 3.0
    ):
        """
        初始化拓扑更新器

        参数:
        - node_manager: 节点管理器
        - auto_broadcaster: 自动广播器
        - update_interval: 更新间隔（秒）
        - enable_auto_update: 是否启用自动更新
        - batch_delay: 批量更新延迟（秒）
        """
        self.node_manager = node_manager
        self.auto_broadcaster = auto_broadcaster
        self.update_interval = update_interval
        self.enable_auto_update = enable_auto_update
        self.batch_delay = batch_delay

        # 当前拓扑
        self.current_snapshot: Optional[TopologySnapshot] = None
        self.last_update_time: Optional[datetime] = None

        # 历史快照
        self.snapshots: deque = deque(maxlen=100)

        # 待处理的变化
        self.pending_changes: List[Dict] = []
        self.pending_changes_lock = threading.Lock()

        # 更新线程
        self._update_thread: Optional[threading.Thread] = None
        self._running = False

        # 事件回调
        self.on_topology_updated: Optional[Callable] = None

        # 统计
        self.update_count = 0
        self.full_updates = 0
        self.incremental_updates = 0

        logger.info("[TopologyUpdater] 初始化完成")
        logger.info(f"  更新间隔: {update_interval}秒")
        logger.info(f"  批量延迟: {batch_delay}秒")

    def start(self):
        """启动拓扑更新器"""
        if self._running:
            logger.warning("[TopologyUpdater] 已在运行")
            return

        if not self.enable_auto_update:
            logger.info("[TopologyUpdater] 自动更新被禁用")
            return

        # 1. 绑定广播器事件
        self.auto_broadcaster.on_node_joined = self._on_node_joined
        self.auto_broadcaster.on_node_left = self._on_node_left

        # 2. 启动更新线程
        self._running = True
        self._update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self._update_thread.start()

        # 3. 立即执行一次全量更新
        self.update_topology(force_full=True)

        logger.info("[TopologyUpdater] 已启动")

    def stop(self):
        """停止拓扑更新器"""
        self._running = False
        logger.info("[TopologyUpdater] 已停止")

    def _update_loop(self):
        """更新循环"""
        while self._running:
            try:
                # 检查是否有待处理的变化
                with self.pending_changes_lock:
                    if self.pending_changes:
                        # 等待批量延迟
                        time.sleep(self.batch_delay)

                        # 处理变化
                        self._process_pending_changes()

                # 定期全量更新
                time.sleep(self.update_interval)
                self.update_topology(force_full=False)

            except Exception as e:
                logger.error(f"[TopologyUpdater] 更新循环错误: {e}")

    def _on_node_joined(self, node):
        """节点加入事件"""
        logger.info(f"[TopologyUpdater] 节点加入: {node.node_id}")

        with self.pending_changes_lock:
            self.pending_changes.append({
                'type': 'join',
                'node': node,
                'timestamp': datetime.now()
            })

    def _on_node_left(self, node):
        """节点离开事件"""
        logger.info(f"[TopologyUpdater] 节点离开: {node.node_id}")

        with self.pending_changes_lock:
            self.pending_changes.append({
                'type': 'leave',
                'node': node,
                'timestamp': datetime.now()
            })

    def _process_pending_changes(self):
        """处理待处理的变化"""
        with self.pending_changes_lock:
            if not self.pending_changes:
                return

            change_count = len(self.pending_changes)
            logger.info(f"[TopologyUpdater] 处理 {change_count} 个待处理变化")

            # 清空待处理列表
            self.pending_changes = []

        # 执行更新
        current_node_count = len(self.node_manager.get_online_nodes())
        previous_node_count = self.current_snapshot.node_count if self.current_snapshot else 0

        # 判断是否需要全量更新
        if previous_node_count == 0:
            force_full = True
        else:
            change_ratio = abs(current_node_count - previous_node_count) / previous_node_count
            force_full = change_ratio > 0.1  # 变化>10%时全量更新

        self.update_topology(force_full=force_full)

    def update_topology(self, force_full: bool = False):
        """
        更新拓扑

        参数:
        - force_full: 是否强制全量更新
        """
        try:
            start_time = time.time()

            # 1. 获取在线节点
            nodes = self.node_manager.get_online_nodes()

            if len(nodes) < 2:
                logger.warning("[TopologyUpdater] 节点数不足(<2)，跳过更新")
                return

            logger.info(f"[TopologyUpdater] 开始更新拓扑（{'全量' if force_full else '增量'}），节点数: {len(nodes)}")

            # 2. 构建拉普拉斯矩阵
            L, W = self._build_laplacian_matrix(nodes)

            # 3. 计算Fiedler向量
            fiedler_vector, fiedler_value = self._compute_fiedler(L)

            # 4. 更新节点重要性得分
            key_nodes = self._update_node_importance(nodes, fiedler_vector)

            # 5. 创建快照
            snapshot = TopologySnapshot(
                timestamp=datetime.now(),
                node_count=len(nodes),
                laplacian_matrix=L,
                fiedler_vector=fiedler_vector,
                fiedler_value=fiedler_value,
                key_nodes=key_nodes
            )

            self.current_snapshot = snapshot
            self.snapshots.append(snapshot)
            self.last_update_time = datetime.now()

            # 6. 更新统计
            self.update_count += 1
            if force_full:
                self.full_updates += 1
            else:
                self.incremental_updates += 1

            elapsed = time.time() - start_time

            logger.info(f"[TopologyUpdater] 拓扑更新完成")
            logger.info(f"  节点数: {len(nodes)}")
            logger.info(f"  Fiedler值: {fiedler_value:.6f}")
            logger.info(f"  关键节点数: {len(key_nodes)}")
            logger.info(f"  耗时: {elapsed:.2f}秒")

            # 7. 触发回调
            if self.on_topology_updated:
                threading.Thread(target=lambda: self.on_topology_updated(snapshot), daemon=True).start()

        except Exception as e:
            logger.error(f"[TopologyUpdater] 拓扑更新失败: {e}", exc_info=True)

    def _build_laplacian_matrix(self, nodes: List) -> tuple:
        """
        构建拉普拉斯矩阵

        返回:
        - (L, W): 拉普拉斯矩阵和邻接矩阵
        """
        from hidrs.network_topology.laplacian_matrix_calculator import LaplacianMatrixCalculator

        n = len(nodes)
        W = np.zeros((n, n))

        # 构建邻接矩阵（基于节点相似度）
        for i in range(n):
            for j in range(i + 1, n):
                # 计算相似度
                sim = self._compute_node_similarity(nodes[i], nodes[j])

                if sim > 0.1:  # 相似度阈值
                    W[i, j] = sim
                    W[j, i] = sim

        # 计算拉普拉斯矩阵
        laplacian_calc = LaplacianMatrixCalculator(normalized=True)
        L = laplacian_calc.compute_laplacian(W)

        return L, W

    def _compute_node_similarity(self, node1, node2) -> float:
        """
        计算节点相似度

        考虑因素：
        - 算力相似度
        - 网络距离相似度
        - 系统类型相似度
        """
        # 1. 算力相似度
        cap1 = node1.capability_score if hasattr(node1, 'capability_score') else 50.0
        cap2 = node2.capability_score if hasattr(node2, 'capability_score') else 50.0

        cap_diff = abs(cap1 - cap2)
        cap_similarity = 1.0 - min(cap_diff / 100.0, 1.0)

        # 2. 网络距离相似度（简化：假设同一子网相似度高）
        ip1 = node1.host.split('.')
        ip2 = node2.host.split('.')

        if len(ip1) >= 3 and len(ip2) >= 3:
            # 检查前3个字节是否相同（同一C类网络）
            if ip1[0] == ip2[0] and ip1[1] == ip2[1] and ip1[2] == ip2[2]:
                net_similarity = 0.9
            elif ip1[0] == ip2[0] and ip1[1] == ip2[1]:
                net_similarity = 0.6
            else:
                net_similarity = 0.3
        else:
            net_similarity = 0.5

        # 综合相似度
        similarity = 0.5 * cap_similarity + 0.5 * net_similarity

        return similarity

    def _compute_fiedler(self, L: np.ndarray) -> tuple:
        """
        计算Fiedler向量

        返回:
        - (fiedler_vector, fiedler_value): Fiedler向量和值
        """
        from hidrs.network_topology.spectral_analyzer import SpectralAnalyzer

        spectral = SpectralAnalyzer(use_sparse=True, k=10)
        fiedler_vector = spectral.compute_fiedler_vector(L)
        fiedler_value = spectral.compute_fiedler_value(L)

        return fiedler_vector, fiedler_value

    def _update_node_importance(self, nodes: List, fiedler_vector: np.ndarray) -> List[str]:
        """
        更新节点重要性得分

        返回:
        - key_nodes: 关键节点ID列表
        """
        key_nodes = []

        # 更新每个节点的Fiedler得分
        for i, node in enumerate(nodes):
            importance = abs(fiedler_vector[i])
            node.fiedler_score = float(importance)

        # 识别关键节点（Fiedler得分在前20%）
        sorted_nodes = sorted(nodes, key=lambda n: n.fiedler_score, reverse=True)
        top_20_percent = max(1, int(len(sorted_nodes) * 0.2))

        for node in sorted_nodes[:top_20_percent]:
            node.is_key_node = True
            key_nodes.append(node.node_id)

        # 其他节点标记为非关键
        for node in sorted_nodes[top_20_percent:]:
            node.is_key_node = False

        return key_nodes

    def get_current_topology(self) -> Optional[TopologySnapshot]:
        """获取当前拓扑快照"""
        return self.current_snapshot

    def get_topology_history(self, limit: int = 10) -> List[TopologySnapshot]:
        """
        获取拓扑历史

        参数:
        - limit: 返回数量限制

        返回:
        - 拓扑快照列表（从新到旧）
        """
        return list(self.snapshots)[-limit:]

    def get_stats(self) -> Dict:
        """获取统计信息"""
        current = self.current_snapshot

        return {
            'update_count': self.update_count,
            'full_updates': self.full_updates,
            'incremental_updates': self.incremental_updates,
            'last_update_time': self.last_update_time.isoformat() if self.last_update_time else None,
            'current_node_count': current.node_count if current else 0,
            'current_fiedler_value': float(current.fiedler_value) if current else None,
            'current_key_nodes_count': len(current.key_nodes) if current else 0,
            'snapshot_history_count': len(self.snapshots),
            'pending_changes': len(self.pending_changes),
            'is_running': self._running
        }

    def analyze_topology_change(self) -> Optional[Dict]:
        """
        分析拓扑变化趋势

        返回:
        - 分析结果
        """
        if len(self.snapshots) < 2:
            return None

        # 取最近两个快照
        current = self.snapshots[-1]
        previous = self.snapshots[-2]

        # 计算变化
        node_count_change = current.node_count - previous.node_count
        fiedler_change = current.fiedler_value - previous.fiedler_value

        # 关键节点变化
        current_key_set = set(current.key_nodes)
        previous_key_set = set(previous.key_nodes)

        new_key_nodes = current_key_set - previous_key_set
        lost_key_nodes = previous_key_set - current_key_set

        return {
            'timestamp': current.timestamp.isoformat(),
            'node_count_change': node_count_change,
            'fiedler_value_change': float(fiedler_change),
            'new_key_nodes': list(new_key_nodes),
            'lost_key_nodes': list(lost_key_nodes),
            'topology_stability': abs(fiedler_change) < 0.1  # Fiedler值变化<0.1认为稳定
        }
