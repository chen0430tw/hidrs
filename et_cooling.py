# et_cooling.py
# ET-WCN 降温算法（ET-Weighted Chain Cooling Algorithm）
# 基于等式理论（对称落差Δ、信息量子ι=1、β₁拓扑监控）
# + 语言超结构系统的权重链网络（WCN）
# + 火种源自组织算法（SOSA）的稀疏 Markov 框架
#
# By: 430 + Claude

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import math
import time
import random


# ============================================================
# 0. ET 核心工具：对称落差、信息量子、β₁ 拓扑
# ============================================================

def delta(a: float, b: float) -> float:
    """
    对称落差函数 Δ(a, b) = ab - (a + b) = (a-1)(b-1) - 1
    
    ET 核心量：度量一对值在乘法与加法之间的偏离程度。
    - Δ = 0  → 镜像点（加法=乘法，完美对称，最高温）
    - Δ > 0  → 对称破缺（信息产生，开始降温）
    - Δ = 1  → 最小非零落差（信息量子 ι = 1）
    """
    return (a - 1.0) * (b - 1.0) - 1.0


# 信息量子：等式空间中对称破缺的最小量子
IOTA = 1.0


def count_factor_pairs(k: int) -> int:
    """
    d(k+1)：落差为 k 的整数格点对数。
    由 ET 命题 2.5：|{(a,b) ∈ ℕ⁺×ℕ⁺ : Δ(a,b) = k}| = d(k+1)
    其中 d(n) = Σ_{d|n} 1 是因子计数函数。
    """
    n = k + 1
    if n <= 0:
        return 0
    count = 0
    for i in range(1, int(math.isqrt(n)) + 1):
        if n % i == 0:
            count += 2 if i * i != n else 1
    return count


def compute_beta1(adj: Dict[int, Set[int]], N: int) -> int:
    """
    计算无向图的 β₁（第一 Betti 数）= E - V + C
    其中 E = 边数，V = 顶点数，C = 连通分量数。
    
    ET 语义：β₁ 计数等式依赖图中不可约循环推导数。
    β₁ 高 → 系统中存在大量循环依赖，需要更多探索。
    β₁ 低 → 推导结构接近树形，可以收敛。
    """
    # 计算边数（无向图，每条边只算一次）
    edges = set()
    active_nodes = set()
    for u, neighbors in adj.items():
        active_nodes.add(u)
        for v in neighbors:
            active_nodes.add(v)
            edge = (min(u, v), max(u, v))
            edges.add(edge)
    
    E = len(edges)
    V = len(active_nodes) if active_nodes else N
    
    # BFS 计算连通分量数
    visited = set()
    C = 0
    nodes_to_check = active_nodes if active_nodes else set(range(N))
    for start in nodes_to_check:
        if start in visited:
            continue
        C += 1
        queue = [start]
        visited.add(start)
        while queue:
            node = queue.pop(0)
            for nb in adj.get(node, set()):
                if nb not in visited:
                    visited.add(nb)
                    queue.append(nb)
    
    # β₁ = E - V + C（图的圈秩 / 第一 Betti 数）
    return max(0, E - V + C)


# ============================================================
# 1. 权重链网络（Weight Chain Network, WCN）
#    来自 LHS 的非线性关系网络
# ============================================================

def sigmoid(x: float) -> float:
    """Sigmoid 激活函数。"""
    if x > 500:
        return 1.0
    if x < -500:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


@dataclass
class WCNNode:
    """权重链网络中的节点（超形式元素的向量化表示）。"""
    node_id: int
    embedding: List[float]          # φ(e) ∈ ℝᵈ
    metadata: Dict[str, Any] = field(default_factory=dict)


class WeightChainNetwork:
    """
    权重链网络（Weighted Chain Network, WCN）
    
    来自 LHS：以超形式元素为节点，通过非线性关系函数
        f(eᵢ, eⱼ) = σ(⟨φ(eᵢ), φ(eⱼ)⟩ + b)
    为每条边赋予权重。
    
    在 ET 降温算法中的角色：
    - 节点 = 搜索空间中的状态/解
    - 边权 = 状态间的"等式关联强度"
    - 邻接图的 β₁ = 当前解空间的拓扑复杂度
    """

    def __init__(self, dim: int, bias: float = 0.0):
        """
        dim: 嵌入维度 d
        bias: 关系函数的偏置 b
        """
        self.dim = dim
        self.bias = bias
        self.nodes: Dict[int, WCNNode] = {}
        self._weight_cache: Dict[Tuple[int, int], float] = {}

    def add_node(self, node_id: int, embedding: Optional[List[float]] = None) -> WCNNode:
        """添加节点。若不提供 embedding，随机初始化。"""
        if embedding is None:
            embedding = [random.gauss(0, 1.0 / math.sqrt(self.dim)) for _ in range(self.dim)]
        node = WCNNode(node_id=node_id, embedding=embedding)
        self.nodes[node_id] = node
        self._weight_cache.clear()
        return node

    def compute_weight(self, i: int, j: int) -> float:
        """
        计算节点 i, j 之间的权重：
        f(eᵢ, eⱼ) = σ(⟨φ(eᵢ), φ(eⱼ)⟩ + b)
        """
        key = (min(i, j), max(i, j))
        if key in self._weight_cache:
            return self._weight_cache[key]
        
        if i not in self.nodes or j not in self.nodes:
            return 0.0
        
        ei = self.nodes[i].embedding
        ej = self.nodes[j].embedding
        
        # 内积
        dot = sum(a * b for a, b in zip(ei, ej))
        w = sigmoid(dot + self.bias)
        
        self._weight_cache[key] = w
        return w

    def get_adjacency(self, threshold: float = 0.5) -> Dict[int, Set[int]]:
        """
        获取阈值化的邻接表（用于 β₁ 计算）。
        权重 > threshold 的边视为"连接"。
        """
        adj: Dict[int, Set[int]] = {nid: set() for nid in self.nodes}
        node_ids = sorted(self.nodes.keys())
        for idx_a in range(len(node_ids)):
            for idx_b in range(idx_a + 1, len(node_ids)):
                i, j = node_ids[idx_a], node_ids[idx_b]
                w = self.compute_weight(i, j)
                if w > threshold:
                    adj[i].add(j)
                    adj[j].add(i)
        return adj

    def get_transition_matrix(self) -> Dict[int, List[Tuple[int, float]]]:
        """
        从 WCN 权重构造转移概率矩阵。
        P(i→j) ∝ f(eᵢ, eⱼ)，归一化。
        """
        trans: Dict[int, List[Tuple[int, float]]] = {}
        for i in self.nodes:
            neighbors = []
            total = 0.0
            for j in self.nodes:
                if i == j:
                    continue
                w = self.compute_weight(i, j)
                if w > 1e-8:
                    neighbors.append((j, w))
                    total += w
            if total > 0:
                trans[i] = [(j, w / total) for j, w in neighbors]
            else:
                trans[i] = []
        return trans

    def update_embedding(self, node_id: int, new_embedding: List[float]) -> None:
        """更新节点嵌入（学习过程中调用）。"""
        if node_id in self.nodes:
            self.nodes[node_id].embedding = new_embedding
            self._weight_cache.clear()


# ============================================================
# 2. ET 降温调度器（ET Cooling Scheduler）
# ============================================================

@dataclass
class CoolingState:
    """降温算法的内部状态。"""
    temperature: float              # 当前温度 T
    epoch: int = 0                  # 当前轮次
    delta_history: List[float] = field(default_factory=list)   # Δ 历史
    beta1_history: List[int] = field(default_factory=list)     # β₁ 历史
    energy_history: List[float] = field(default_factory=list)  # 能量历史
    best_energy: float = float('inf')
    best_solution: Any = None
    phase: str = "symmetric"        # symmetric → breaking → crystallized


class ETCoolingScheduler:
    """
    ET 降温调度器
    
    核心思想：温度不是简单的指数/线性衰减，而是由 ET 的对称落差驱动。
    
    三阶段降温：
    1. 对称阶段（Δ ≈ 0）：系统在镜像点附近，完全探索，T 最高
    2. 破缺阶段（0 < Δ < Δ_crit）：对称开始破缺，T 按 ι=1 量子步下降
    3. 结晶阶段（Δ ≥ Δ_crit）：拓扑简化，β₁ 下降，快速收敛
    
    温度公式：
        T(Δ) = T_max / (1 + Δ/ι)
    
    即每增加一个信息量子 ι=1 的落差，温度降低一个"温度量子"。
    """

    def __init__(
        self,
        T_max: float = 1.0,
        T_min: float = 0.01,
        delta_crit: float = 5.0,
        beta1_target: int = 0,
    ):
        """
        T_max: 初始温度（对称阶段）
        T_min: 最低温度（结晶终点）
        delta_crit: 进入结晶阶段的临界落差
        beta1_target: 目标 β₁（达到后加速收敛）
        """
        self.T_max = T_max
        self.T_min = T_min
        self.delta_crit = delta_crit
        self.beta1_target = beta1_target
        self.state = CoolingState(temperature=T_max)

    def compute_temperature(self, current_delta: float, current_beta1: int) -> float:
        """
        ET 降温公式：
        
        T(Δ, β₁) = T_max / (1 + Δ/ι) × β₁_factor
        
        其中 β₁_factor = 1 / (1 + max(0, β₁ - β₁_target))
        
        物理意义：
        - Δ 每增加 ι=1，温度降一个量子台阶
        - β₁ 超过目标时，额外降温（循环依赖已被消除，可以加速收敛）
        """
        # Δ 驱动的基础降温
        T_delta = self.T_max / (1.0 + max(0.0, current_delta) / IOTA)
        
        # β₁ 驱动的加速因子
        beta1_excess = max(0, current_beta1 - self.beta1_target)
        beta1_factor = 1.0 / (1.0 + 0.5 * beta1_excess)
        
        T = T_delta * beta1_factor
        T = max(self.T_min, min(self.T_max, T))
        
        return T

    def step(self, current_delta: float, current_beta1: int, current_energy: float,
             solution: Any = None) -> float:
        """
        执行一步降温。返回新温度。
        
        同时更新阶段判定和历史记录。
        """
        T_new = self.compute_temperature(current_delta, current_beta1)
        
        # 阶段判定
        if current_delta < IOTA:
            phase = "symmetric"
        elif current_delta < self.delta_crit:
            phase = "breaking"
        else:
            phase = "crystallized"
        
        # 更新最优解
        if current_energy < self.state.best_energy:
            self.state.best_energy = current_energy
            self.state.best_solution = solution
        
        # 记录历史
        self.state.temperature = T_new
        self.state.epoch += 1
        self.state.delta_history.append(current_delta)
        self.state.beta1_history.append(current_beta1)
        self.state.energy_history.append(current_energy)
        self.state.phase = phase
        
        return T_new

    def should_accept(self, energy_old: float, energy_new: float) -> bool:
        """
        Metropolis 判据（ET 版）：
        
        接受概率 = exp(-ΔE / T)，但 T 由 ET 落差驱动。
        
        当 T 高（Δ ≈ 0，对称阶段）→ 几乎总接受（自由探索）
        当 T 低（Δ 大，结晶阶段）→ 只接受更优解
        """
        dE = energy_new - energy_old
        if dE <= 0:
            return True
        
        T = self.state.temperature
        if T < 1e-12:
            return False
        
        prob = math.exp(-dE / T)
        return random.random() < prob

    def is_converged(self, patience: int = 10) -> bool:
        """
        收敛判定：
        - 已进入结晶阶段
        - β₁ 达到目标
        - 能量在 patience 步内未改善
        """
        if self.state.phase != "crystallized":
            return False
        
        if len(self.state.beta1_history) > 0 and self.state.beta1_history[-1] > self.beta1_target:
            return False
        
        if len(self.state.energy_history) < patience:
            return False
        
        recent = self.state.energy_history[-patience:]
        return max(recent) - min(recent) < 1e-6

    def should_reheat(self, stagnation_threshold: int = 30) -> bool:
        """
        再加热判定（ET 原理：镜像递归 = 内耗，需要重新破缺）。
        
        当能量停滞超过阈值但尚未达到满意水平时，
        回到镜像点（Δ → 0, T → T_max）重新探索。
        """
        if len(self.state.energy_history) < stagnation_threshold:
            return False
        
        recent = self.state.energy_history[-stagnation_threshold:]
        is_stagnant = max(recent) - min(recent) < 1e-4
        
        # 只在 breaking 阶段再加热（crystallized 阶段视为已收敛）
        return is_stagnant and self.state.phase == "breaking"

    def reheat(self) -> None:
        """
        再加热：重置温度到 T_max 的一半，回到 breaking 阶段。
        ET 意义：从当前 Δ 回退到 Δ ≈ ι，重新经历对称破缺。
        """
        self.state.temperature = self.T_max * 0.6
        self.state.phase = "symmetric"


# ============================================================
# 3. ET-WCN 降温算法主体
# ============================================================

@dataclass
class ETCoolingResult:
    """降温算法的输出结果。"""
    best_solution: Any
    best_energy: float
    epochs: int
    final_phase: str
    final_temperature: float
    final_beta1: int
    delta_history: List[float]
    beta1_history: List[int]
    energy_history: List[float]


class ETWCNCooling:
    """
    ET-WCN 降温算法（ET-Weighted Chain Cooling）
    
    整合三个系统：
    1. ET 降温调度器：用对称落差 Δ 驱动温度，ι=1 为最小降温步长
    2. WCN 权重链网络：构建解空间的关系图，计算 β₁ 监控拓扑
    3. SOSA 式流式处理：按窗口聚合事件，Binary-Twin 编码经验
    
    算法流程（每个 epoch）：
    ┌──────────────────────────────────────────────────────────┐
    │ 1. 在当前解的邻域生成候选解（由 WCN 引导邻域结构）        │
    │ 2. 计算候选解的能量（目标函数）                           │
    │ 3. 计算当前解对与候选解对之间的对称落差 Δ                 │
    │ 4. 从 WCN 邻接图计算 β₁                                  │
    │ 5. ET 降温调度器更新温度 T(Δ, β₁)                        │
    │ 6. Metropolis 判据决定是否接受候选解                      │
    │ 7. 更新 WCN 嵌入（将新解的信息编码到网络中）              │
    └──────────────────────────────────────────────────────────┘
    
    对称落差在算法中的角色：
    - 当前解的"加法特征" a = 解的各分量之和（线性组合）
    - 当前解的"乘法特征" b = 解的各分量之积的某种归一化
    - Δ(a, b) = (a-1)(b-1) - 1 度量解的加法结构与乘法结构的偏离
    - Δ ≈ 0：解在镜像点附近，加法和乘法视角一致 → 高度对称，需要探索
    - Δ 大：解已经产生结构性分化 → 可以开始收敛
    """

    def __init__(
        self,
        dim: int,
        n_nodes: int = 20,
        T_max: float = 1.0,
        T_min: float = 0.01,
        delta_crit: float = 5.0,
        beta1_target: int = 0,
        wcn_bias: float = -1.0,
        wcn_threshold: float = 0.5,
        seed: Optional[int] = None,
    ):
        """
        dim: 解空间维度（也是 WCN 嵌入维度）
        n_nodes: WCN 初始节点数（搜索空间的锚点数）
        T_max, T_min: 温度范围
        delta_crit: 结晶阶段的临界落差
        beta1_target: 目标 β₁
        wcn_bias: WCN 关系函数偏置（负值使稀疏图更容易出现）
        wcn_threshold: WCN 邻接阈值
        """
        if seed is not None:
            random.seed(seed)
        
        self.dim = dim
        self.n_nodes = n_nodes
        self.wcn_threshold = wcn_threshold
        
        # 初始化 WCN
        self.wcn = WeightChainNetwork(dim=dim, bias=wcn_bias)
        for i in range(n_nodes):
            self.wcn.add_node(i)
        
        # 初始化 ET 降温调度器
        self.scheduler = ETCoolingScheduler(
            T_max=T_max,
            T_min=T_min,
            delta_crit=delta_crit,
            beta1_target=beta1_target,
        )

    def _solution_to_ab(self, solution: List[float]) -> Tuple[float, float]:
        """
        将优化动态映射为 (a, b) 对，用于计算对称落差。
        
        ET 核心洞察：Δ 应该反映"加法视角"与"乘法视角"的分离。
        
        映射规则：
        - a = 2 + σ_E  （能量方差：搜索的"加法波动"）
        - b = 2 + μ_‖Δx‖（解移动量均值：搜索的"结构变化率"）
        
        物理意义：
        - a ≈ b（Δ ≈ 0）：能量波动与解移动同步 → 自由探索阶段
        - a ≫ b（Δ > 0）：能量剧烈变化但解不怎么动 → 找到局部盆地
        - a ≪ b（Δ > 0）：解在大幅移动但能量稳定 → 等能面上滑行
        
        后两种都是对称破缺，应该触发降温。
        """
        hist = self.scheduler.state.energy_history
        n_hist = len(hist)
        
        # 需要至少几步历史才能计算动态
        if n_hist < 3:
            return (2.0, 2.0)  # 返回镜像点，不降温
        
        # 取最近 window 步
        window = min(20, n_hist)
        recent_E = hist[-window:]
        
        # a = 2 + 能量变化的标准差（加法波动）
        mean_E = sum(recent_E) / len(recent_E)
        var_E = sum((e - mean_E) ** 2 for e in recent_E) / len(recent_E)
        sigma_E = math.sqrt(var_E)
        a = 2.0 + sigma_E
        
        # b = 2 + 能量下降的单调性指标（结构收敛度）
        # 计算相邻步的能量差，正差（改善）占比越高 → 收敛越强
        improvements = 0
        for i in range(1, len(recent_E)):
            if recent_E[i] <= recent_E[i - 1]:
                improvements += 1
        convergence = improvements / max(1, len(recent_E) - 1)
        b = 2.0 + convergence * sigma_E * 2.0
        
        # 当能量不再变化（完全收敛）时，Δ 应该随停滞时间增长
        # 这是 ET 的核心洞察：持续的对称 = 镜像递归 = 内耗
        # 需要强制破缺才能逃逸
        if sigma_E < 0.01 and n_hist > 10:
            # 停滞轮数
            stagnation = 0
            for i in range(n_hist - 1, max(0, n_hist - 100) - 1, -1):
                if abs(hist[i] - hist[-1]) < 0.01:
                    stagnation += 1
                else:
                    break
            b += 1.0 + stagnation * 0.1  # Δ 随停滞时间线性增长
        
        return (max(1.01, a), max(1.01, b))

    def _generate_neighbor(self, solution: List[float], temperature: float) -> List[float]:
        """
        由 WCN 引导的邻域生成。
        
        策略：
        1. 找到 WCN 中与当前解最近的节点
        2. 沿着该节点高权重邻居的方向扰动
        3. 扰动幅度 ∝ temperature（高温大扰动，低温小扰动）
        """
        # 找最近的 WCN 节点
        best_node = 0
        best_sim = -float('inf')
        for nid, node in self.wcn.nodes.items():
            sim = sum(a * b for a, b in zip(solution, node.embedding))
            if sim > best_sim:
                best_sim = sim
                best_node = nid
        
        # 获取该节点的高权重邻居
        neighbors_with_weights = []
        for nid in self.wcn.nodes:
            if nid == best_node:
                continue
            w = self.wcn.compute_weight(best_node, nid)
            neighbors_with_weights.append((nid, w))
        
        # 按权重选择一个方向
        if neighbors_with_weights:
            total_w = sum(w for _, w in neighbors_with_weights)
            if total_w > 0:
                r = random.random() * total_w
                cumsum = 0.0
                target_node = neighbors_with_weights[0][0]
                for nid, w in neighbors_with_weights:
                    cumsum += w
                    if cumsum >= r:
                        target_node = nid
                        break
                
                # 方向 = target_node.embedding - solution
                target_emb = self.wcn.nodes[target_node].embedding
                direction = [t - s for t, s in zip(target_emb, solution)]
            else:
                direction = [random.gauss(0, 1) for _ in range(self.dim)]
        else:
            direction = [random.gauss(0, 1) for _ in range(self.dim)]
        
        # 归一化方向
        norm = math.sqrt(sum(d * d for d in direction))
        if norm > 1e-10:
            direction = [d / norm for d in direction]
        
        # 扰动幅度 ∝ T × ι
        step_size = temperature * IOTA
        
        # 添加高斯噪声确保遍历性
        noise = [random.gauss(0, temperature * 0.1) for _ in range(self.dim)]
        
        new_solution = [
            s + step_size * d + n
            for s, d, n in zip(solution, direction, noise)
        ]
        
        return new_solution

    def optimize(
        self,
        energy_fn: Callable[[List[float]], float],
        initial_solution: Optional[List[float]] = None,
        max_epochs: int = 1000,
        patience: int = 50,
        verbose: bool = False,
        callback: Optional[Callable[[int, CoolingState], None]] = None,
    ) -> ETCoolingResult:
        """
        执行 ET-WCN 降温优化。
        
        参数：
            energy_fn: 目标函数（最小化）
            initial_solution: 初始解（None 则随机）
            max_epochs: 最大迭代次数
            patience: 收敛耐心（能量无改善的最大轮数）
            verbose: 是否打印过程
            callback: 每轮回调函数
            
        返回：
            ETCoolingResult 包含最优解、历史轨迹等
        """
        # 初始化
        if initial_solution is None:
            current = [random.gauss(0, 1) for _ in range(self.dim)]
        else:
            current = list(initial_solution)
        
        current_energy = energy_fn(current)
        best_solution = list(current)
        best_energy = current_energy
        
        for epoch in range(max_epochs):
            # 1. 计算当前解的 ET 特征
            a, b = self._solution_to_ab(current)
            current_delta = max(0.0, delta(a, b))
            
            # 2. 计算 WCN 的 β₁
            adj = self.wcn.get_adjacency(threshold=self.wcn_threshold)
            current_beta1 = compute_beta1(adj, self.n_nodes)
            
            # 3. ET 降温调度器更新温度
            T = self.scheduler.step(
                current_delta=current_delta,
                current_beta1=current_beta1,
                current_energy=current_energy,
                solution=list(current),
            )
            
            # 4. 生成候选解（WCN 引导）
            candidate = self._generate_neighbor(current, T)
            candidate_energy = energy_fn(candidate)
            
            # 5. Metropolis 判据
            if self.scheduler.should_accept(current_energy, candidate_energy):
                current = candidate
                current_energy = candidate_energy
                
                # 更新最优
                if current_energy < best_energy:
                    best_energy = current_energy
                    best_solution = list(current)
                
                # 6. 将接受的解编码到 WCN（替换最远的节点）
                self._update_wcn_with_solution(current)
            
            # 回调
            if callback is not None:
                callback(epoch, self.scheduler.state)
            
            # 打印
            if verbose and epoch % max(1, max_epochs // 20) == 0:
                print(
                    f"[epoch {epoch:4d}] phase={self.scheduler.state.phase:12s} "
                    f"T={T:.4f}  Δ={current_delta:.3f}  β₁={current_beta1}  "
                    f"E={current_energy:.6f}  E*={best_energy:.6f}"
                )
            
            # 再加热检查（ET：逃逸镜像递归陷阱）
            if self.scheduler.should_reheat(stagnation_threshold=30):
                self.scheduler.reheat()
                # 从最优解的邻域重新开始（不丢失历史最优）
                current = [
                    x + random.gauss(0, 0.5)
                    for x in best_solution
                ]
                current_energy = energy_fn(current)
                if verbose:
                    print(f"  [REHEAT at epoch {epoch}] T → {self.scheduler.state.temperature:.4f}")
            
            # 收敛检查
            if self.scheduler.is_converged(patience=patience):
                if verbose:
                    print(f"[Converged at epoch {epoch}]")
                break
        
        return ETCoolingResult(
            best_solution=best_solution,
            best_energy=best_energy,
            epochs=self.scheduler.state.epoch,
            final_phase=self.scheduler.state.phase,
            final_temperature=self.scheduler.state.temperature,
            final_beta1=self.scheduler.state.beta1_history[-1] if self.scheduler.state.beta1_history else 0,
            delta_history=self.scheduler.state.delta_history,
            beta1_history=self.scheduler.state.beta1_history,
            energy_history=self.scheduler.state.energy_history,
        )

    def _update_wcn_with_solution(self, solution: List[float]) -> None:
        """
        将新接受的解编码到 WCN 中。
        
        策略：替换网络中与当前解最不相似的节点。
        这使得 WCN 逐渐"学习"解空间的结构。
        """
        worst_node = 0
        worst_sim = float('inf')
        for nid, node in self.wcn.nodes.items():
            sim = sum(a * b for a, b in zip(solution, node.embedding))
            if sim < worst_sim:
                worst_sim = sim
                worst_node = nid
        
        # 用解的信息更新该节点的嵌入（指数滑动平均）
        alpha = 0.3
        old_emb = self.wcn.nodes[worst_node].embedding
        new_emb = [
            alpha * s + (1 - alpha) * o
            for s, o in zip(solution, old_emb)
        ]
        self.wcn.update_embedding(worst_node, new_emb)


# ============================================================
# 4. SOSA 集成层：流式事件处理 + ET 降温
# ============================================================

class ETCoolingSOSA:
    """
    ET 降温 + SOSA 集成：将火种源自组织算法与 ET 降温融合。
    
    SOSA 的 Markov 状态转移概率 = WCN 的转移矩阵
    SOSA 的 explore_factor = ET 温度 T
    SOSA 的吸引子 = ET 结晶阶段的低 β₁ 分布
    """

    def __init__(
        self,
        N_states: int,
        embedding_dim: int = 8,
        dt_window: float = 5.0,
        T_max: float = 1.0,
        T_min: float = 0.01,
        wcn_bias: float = -0.5,
    ):
        self.N_states = N_states
        self.embedding_dim = embedding_dim
        self.dt_window = dt_window
        
        # WCN：节点 = Markov 状态
        self.wcn = WeightChainNetwork(dim=embedding_dim, bias=wcn_bias)
        for i in range(N_states):
            self.wcn.add_node(i)
        
        # ET 降温调度器
        self.scheduler = ETCoolingScheduler(T_max=T_max, T_min=T_min)
        
        # 状态分布
        self.pi = [1.0 / N_states] * N_states
        
        # 事件缓冲
        self.window_buf: List[Dict[str, Any]] = []
        self.last_flush = time.time()
        self.epoch = 0

    def process_event(self, obs: Any, action: Any, timestamp: Optional[float] = None) -> None:
        """流式接收事件。"""
        if timestamp is None:
            timestamp = time.time()
        self.window_buf.append({"obs": obs, "action": action, "ts": timestamp})
        
        if timestamp - self.last_flush >= self.dt_window:
            self._flush_window()
            self.last_flush = timestamp

    def _flush_window(self) -> None:
        """窗口刷新：ET 降温 + WCN 拓扑更新 + Markov 状态推进。"""
        if not self.window_buf:
            return
        
        # 1. 从事件窗口提取特征
        actions = [e["action"] for e in self.window_buf]
        n_events = len(self.window_buf)
        n_unique = len(set(str(a) for a in actions))
        diversity = n_unique / max(1, n_events)
        
        # 2. 计算"能量"（事件窗口的信息量）
        energy = 1.0 - diversity  # 低多样性 = 高能量（已收敛）
        
        # 3. 计算对称落差
        a_feat = 1.0 + n_events / 10.0        # 加法特征：事件量
        b_feat = 1.0 + n_unique               # 乘法特征：种类数
        current_delta = max(0.0, delta(a_feat, b_feat))
        
        # 4. 计算 β₁
        adj = self.wcn.get_adjacency(threshold=0.5)
        current_beta1 = compute_beta1(adj, self.N_states)
        
        # 5. ET 降温
        T = self.scheduler.step(current_delta, current_beta1, energy)
        
        # 6. WCN 驱动的 Markov 转移
        trans = self.wcn.get_transition_matrix()
        pi_next = [0.0] * self.N_states
        for i, p_i in enumerate(self.pi):
            if p_i < 1e-12:
                continue
            if i in trans:
                for j, p_ij in trans[i]:
                    if j < self.N_states:
                        pi_next[j] += p_i * p_ij
        
        # 7. ET 温度控制探索 vs 固化
        attractor = [1.0 / self.N_states] * self.N_states
        # 如果结晶，吸引子偏向当前最大概率状态
        if self.scheduler.state.phase == "crystallized":
            max_idx = self.pi.index(max(self.pi))
            attractor = [0.01 / self.N_states] * self.N_states
            attractor[max_idx] = 0.99
        
        explore = T / self.scheduler.T_max  # T 归一化为探索度
        self.pi = [
            explore * pn + (1.0 - explore) * at
            for pn, at in zip(pi_next, attractor)
        ]
        
        # 归一化
        Z = sum(self.pi)
        if Z > 0:
            self.pi = [p / Z for p in self.pi]
        
        # 8. 清空窗口
        self.window_buf.clear()
        self.epoch += 1

    def get_state(self) -> Dict[str, Any]:
        """返回当前算法状态。"""
        return {
            "pi": list(self.pi),
            "temperature": self.scheduler.state.temperature,
            "phase": self.scheduler.state.phase,
            "epoch": self.epoch,
            "beta1_history": self.scheduler.state.beta1_history,
            "delta_history": self.scheduler.state.delta_history,
            "energy_history": self.scheduler.state.energy_history,
        }


# ============================================================
# 5. Demo：基准测试
# ============================================================

def demo_rastrigin():
    """
    在 Rastrigin 函数上测试 ET-WCN 降温算法。
    Rastrigin 有大量局部极小值，是退火算法的经典测试函数。
    全局最小值：f(0,...,0) = 0
    """
    print("=" * 60)
    print("ET-WCN 降温算法 — Rastrigin 函数优化 (dim=5)")
    print("全局最优: f(0,...,0) = 0")
    print("=" * 60)
    
    dim = 5
    
    def rastrigin(x: List[float]) -> float:
        A = 10
        return A * len(x) + sum(xi ** 2 - A * math.cos(2 * math.pi * xi) for xi in x)
    
    optimizer = ETWCNCooling(
        dim=dim,
        n_nodes=15,
        T_max=2.0,
        T_min=0.001,
        delta_crit=2.0,
        beta1_target=0,
        wcn_bias=-1.5,
        wcn_threshold=0.5,
        seed=42,
    )
    
    result = optimizer.optimize(
        energy_fn=rastrigin,
        max_epochs=1000,
        patience=80,
        verbose=True,
    )
    
    print(f"\n最优能量: {result.best_energy:.6f}")
    print(f"最优解:   [{', '.join(f'{x:.4f}' for x in result.best_solution)}]")
    print(f"总轮次:   {result.epochs}")
    print(f"最终阶段: {result.final_phase}")
    print(f"最终温度: {result.final_temperature:.6f}")
    print(f"最终 β₁:  {result.final_beta1}")
    
    return result


def demo_rosenbrock():
    """
    Rosenbrock 函数：窄谷优化，测试 WCN 引导能力。
    全局最小值：f(1,...,1) = 0
    """
    print("\n" + "=" * 60)
    print("ET-WCN 降温算法 — Rosenbrock 函数优化 (dim=4)")
    print("全局最优: f(1,...,1) = 0")
    print("=" * 60)
    
    dim = 4
    
    def rosenbrock(x: List[float]) -> float:
        return sum(
            100 * (x[i+1] - x[i]**2)**2 + (1 - x[i])**2
            for i in range(len(x) - 1)
        )
    
    optimizer = ETWCNCooling(
        dim=dim,
        n_nodes=12,
        T_max=3.0,
        T_min=0.001,
        delta_crit=2.0,
        beta1_target=0,
        wcn_bias=-1.0,
        wcn_threshold=0.5,
        seed=123,
    )
    
    result = optimizer.optimize(
        energy_fn=rosenbrock,
        max_epochs=1500,
        patience=100,
        verbose=True,
    )
    
    print(f"\n最优能量: {result.best_energy:.6f}")
    print(f"最优解:   [{', '.join(f'{x:.4f}' for x in result.best_solution)}]")
    print(f"总轮次:   {result.epochs}")
    print(f"最终阶段: {result.final_phase}")
    
    return result


def demo_sosa_integration():
    """
    测试 ET 降温 + SOSA 流式集成。
    """
    print("\n" + "=" * 60)
    print("ET-Cooling-SOSA 流式集成 Demo")
    print("=" * 60)
    
    system = ETCoolingSOSA(
        N_states=6,
        embedding_dim=4,
        dt_window=2.0,
        T_max=1.0,
    )
    
    now = time.time()
    actions = ["observe", "patch_small", "patch_big", "rollback", "observe", "observe"]
    
    for i in range(30):
        obs = f"event-{i}: metric={random.gauss(50, 10):.1f}"
        action = actions[i % len(actions)]
        system.process_event(obs=obs, action=action, timestamp=now + i * 0.8)
    
    # 强制刷新
    system._flush_window()
    
    state = system.get_state()
    print(f"状态分布 π: [{', '.join(f'{p:.4f}' for p in state['pi'])}]")
    print(f"当前温度:    {state['temperature']:.4f}")
    print(f"当前阶段:    {state['phase']}")
    print(f"处理轮次:    {state['epoch']}")
    if state['delta_history']:
        print(f"落差历史:    [{', '.join(f'{d:.2f}' for d in state['delta_history'])}]")
    if state['beta1_history']:
        print(f"β₁ 历史:     {state['beta1_history']}")


if __name__ == "__main__":
    r1 = demo_rastrigin()
    r2 = demo_rosenbrock()
    demo_sosa_integration()
