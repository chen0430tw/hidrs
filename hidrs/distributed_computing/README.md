# HIDRS 分布式计算系统

## 概述

基于HLIG（Holographic Laplacian Internet Graph）理论的分布式计算系统，实现智能节点选择和全局优化任务分配。

### 核心理念

**全球广播系统的逆向应用：**
- **全球广播**: 我向全球推送消息
- **分布式计算**: 我从全球拉取算力

**融合三大技术：**
- **区块链**: P2P去中心化网络，无单点故障
- **SETI@home**: 全球算力共享，志愿者贡献闲置资源
- **HLIG理论**: 使用Fiedler向量识别关键节点，优化任务分配

### 核心优势

| 特性 | HIDRS (HLIG) | 传统方法 |
|------|--------------|----------|
| 节点发现 | P2P去中心化 | 中心化注册 |
| 任务调度 | Fiedler向量优化 | 轮询/随机 |
| 节点选择 | 识别关键节点优先 | 机械平均分配 |
| 负载均衡 | 拉普拉斯流 | 贪心算法 |
| 结果聚合 | 全息映射加权 | 简单平均 |
| 网络拓扑感知 | 是（拉普拉斯矩阵） | 否 |

## 架构

```
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
```

## 组件说明

### 1. 节点管理器 (`node_manager.py`)

负责发现和管理分布式计算节点。

**功能：**
- P2P节点发现（类似BitTorrent DHT）
- 节点注册和心跳检测
- 节点状态监控
- 动态节点池维护

**节点发现策略：**
- 本地局域网广播（UDP）
- DHT分布式哈希表（Kademlia协议）
- Bootstrap节点列表
- 社交发现（可选）

```python
from hidrs.distributed_computing import NodeManager, ComputeNode, NodeStatus

# 创建节点管理器
node_manager = NodeManager(
    listen_port=9876,
    heartbeat_interval=30,
    enable_lan_discovery=True
)

# 启动
node_manager.start()

# 获取在线节点
online_nodes = node_manager.get_online_nodes()
```

**ComputeNode数据结构：**
```python
@dataclass
class ComputeNode:
    node_id: str              # 节点ID
    host: str                 # IP地址
    port: int                 # 端口
    status: NodeStatus        # 状态

    # 算力信息
    cpu_cores: int
    memory_gb: float
    gpu_count: int

    # HLIG相关
    capability_score: float   # 综合算力得分
    fiedler_score: float      # Fiedler向量分量
    is_key_node: bool         # 是否为关键节点
```

### 2. 算力评估器 (`capability_analyzer.py`)

评估节点计算能力并打分。

**评分算法：**
```
capability_score = α·CPU得分 + β·GPU得分 + γ·内存得分 + δ·网络得分
```

默认权重：`α=0.4, β=0.3, γ=0.2, δ=0.1`

```python
from hidrs.distributed_computing import CapabilityAnalyzer

analyzer = CapabilityAnalyzer(
    weight_cpu=0.4,
    weight_gpu=0.3,
    weight_memory=0.2,
    weight_network=0.1
)

# 分析本地节点
capability = analyzer.analyze_local_node()
print(f"总得分: {capability.total_score}")
```

**评分细节：**
- **CPU得分**: 核心数 + 频率 + 空闲率
- **GPU得分**: GPU数量 + 显存大小
- **内存得分**: 总内存 + 可用比例
- **网络得分**: 带宽 + 延迟 + 丢包率

### 3. HLIG任务调度器 (`hlig_task_scheduler.py`)

使用拉普拉斯谱分析优化任务分配。

**核心算法：**
1. 构建节点网络拓扑（邻接矩阵 W）
2. 计算拉普拉斯矩阵 L = D - W
3. 计算Fiedler向量（λ₂对应的特征向量）
4. 根据Fiedler向量分配任务到关键节点

**Fiedler向量的含义：**
- 分量绝对值大 → 节点在网络中更重要/更中心
- 分量符号 → 节点所属的社区/集群

```python
from hidrs.distributed_computing import HLIGTaskScheduler, ComputeTask, TaskType

scheduler = HLIGTaskScheduler(
    node_manager=node_manager,
    capability_analyzer=analyzer,
    use_fiedler=True  # 启用HLIG优化
)

# 提交任务
task = ComputeTask(
    task_id="task_001",
    task_type=TaskType.COMPUTE_INTENSIVE,
    function_name="monte_carlo_pi",
    args=(1000000,),
    required_cpu_cores=4,
    required_memory_gb=8.0
)
scheduler.submit_task(task)

# 执行调度
assignments = scheduler.schedule_tasks()
```

**任务分配策略：**
1. **计算密集型任务** → 分配给高算力节点（基于capability_score）
2. **通信密集型任务** → 分配给网络中心节点（基于Fiedler向量）
3. **混合型任务** → 综合考虑

### 4. HLIG负载均衡器 (`hlig_load_balancer.py`)

基于拉普拉斯流的动态负载均衡。

**拉普拉斯流理论：**
```
L·x = b
```
- L 是拉普拉斯矩阵
- x 是节点电位（负载）
- b 是电流源（任务）

电流会自动流向低电位区域，类比：任务会自动分配到低负载节点。

```python
from hidrs.distributed_computing import HLIGLoadBalancer

load_balancer = HLIGLoadBalancer(
    node_manager=node_manager,
    rebalance_threshold=0.3,
    enable_migration=True  # 启用任务迁移
)

# 更新节点负载
load_balancer.update_node_load("node_1", 0.8)

# 检查均衡状态
balance_status = load_balancer.check_balance()
if balance_status['needs_rebalance']:
    # 执行重平衡
    result = load_balancer.rebalance()
```

### 5. 计算工作节点 (`compute_worker.py`)

执行分布式计算任务的工作节点。

**功能：**
- 接收任务
- 沙箱执行（限制资源访问）
- 超时控制
- 进度报告
- 返回结果

```python
from hidrs.distributed_computing import ComputeWorker
from hidrs.distributed_computing.compute_worker import register_example_functions

# 创建工作节点
worker = ComputeWorker(
    worker_id="worker_001",
    max_concurrent_tasks=4,
    timeout_seconds=3600
)

# 注册可执行函数
register_example_functions(worker)

# 执行任务
result = worker.execute_task(task)
```

**内置示例函数：**
- `matrix_multiply`: 矩阵乘法
- `prime_check`: 质数检查
- `monte_carlo_pi`: 蒙特卡洛法计算π
- `fibonacci`: 斐波那契数列

**自定义函数：**
```python
def my_custom_function(data):
    # 你的计算逻辑
    return result

worker.register_function('my_func', my_custom_function)
```

### 6. 结果聚合器 (`result_aggregator.py`)

使用全息映射聚合分布式计算结果。

**聚合策略：**
- `SUM`: 求和
- `AVERAGE`: 平均
- `MAX`: 最大值
- `MIN`: 最小值
- `CONCAT`: 连接
- `CUSTOM`: 自定义函数

```python
from hidrs.distributed_computing import ResultAggregator, AggregationType

aggregator = ResultAggregator(use_hlig_weighting=True)

# 聚合结果
results = [
    {'node_id': 'node_1', 'result': 3.14},
    {'node_id': 'node_2', 'result': 3.15},
    {'node_id': 'node_3', 'result': 3.14}
]

pi_average = aggregator.aggregate(
    results,
    aggregation_type=AggregationType.AVERAGE
)
```

**HLIG加权聚合：**
```python
# 使用Fiedler得分作为权重
node_weights = {
    'node_1': 0.8,  # 高Fiedler得分
    'node_2': 0.5,
    'node_3': 0.3
}

pi_weighted = aggregator.aggregate(
    results,
    aggregation_type=AggregationType.AVERAGE,
    node_weights=node_weights
)
```

**MapReduce模式：**
```python
def map_func(data):
    return compute(data)

def reduce_func(results, weights):
    return weighted_average(results, weights)

final_result = aggregator.map_reduce(
    tasks=data_chunks,
    map_func=map_func,
    reduce_func=reduce_func,
    node_weights=fiedler_scores
)
```

## 完整使用示例

### 示例1：计算π值（蒙特卡洛方法）

```python
from hidrs.distributed_computing import *

# 1. 创建组件
node_manager = NodeManager()
node_manager.start()

analyzer = CapabilityAnalyzer()
scheduler = HLIGTaskScheduler(node_manager, analyzer)
aggregator = ResultAggregator()

# 2. 创建任务
tasks = [
    ComputeTask(
        task_id=f"pi_task_{i}",
        task_type=TaskType.COMPUTE_INTENSIVE,
        function_name="monte_carlo_pi",
        args=(1000000,)  # 100万次迭代
    )
    for i in range(10)
]

# 3. 提交和调度
for task in tasks:
    scheduler.submit_task(task)

assignments = scheduler.schedule_tasks()

# 4. 分布式执行
workers = [
    ComputeWorker(worker_id=f"worker_{i}")
    for i in range(3)
]

for worker in workers:
    register_example_functions(worker)

for task_id, node_id in assignments:
    task = scheduler.get_task(task_id)
    worker = workers[int(node_id.split('_')[1]) % len(workers)]
    worker.execute_task(task)

# 5. 收集和聚合结果
results = []
for worker in workers:
    for task_id, task_info in worker.current_tasks.items():
        if task_info['status'] == 'completed':
            results.append({
                'node_id': worker.worker_id,
                'result': task_info['result']
            })

pi_estimate = aggregator.aggregate(results, AggregationType.AVERAGE)
print(f"π ≈ {pi_estimate}")
```

### 示例2：矩阵运算

```python
import numpy as np

# 创建大矩阵
n = 1000
matrix_A = np.random.rand(n, n)
matrix_B = np.random.rand(n, n)

# 分块矩阵乘法
block_size = 100
tasks = []

for i in range(0, n, block_size):
    for j in range(0, n, block_size):
        task = ComputeTask(
            task_id=f"mm_{i}_{j}",
            task_type=TaskType.COMPUTE_INTENSIVE,
            function_name="matrix_multiply",
            args=(
                matrix_A[i:i+block_size, :],
                matrix_B[:, j:j+block_size]
            ),
            required_memory_gb=1.0
        )
        tasks.append(task)

# 调度和执行...
# 聚合结果...
```

## 运行演示

```bash
# 完整演示
python examples/distributed_computing_demo.py

# 输出示例：
# ====== HIDRS 分布式计算系统演示 ======
#
# 全球广播系统的逆向应用：跟全球借算力
#
# 演示1: 节点发现
# ✅ 节点管理器已启动，监听端口: 9876
# 📊 节点发现完成:
#    总节点数: 5
#    在线节点: 5
#    总CPU核心数: 30
#    总内存: 40.0 GB
#    总GPU数: 2
#
# 演示3: HLIG任务调度
# 开始HLIG分析和任务调度...
# ✅ 调度完成: 10 个任务已分配
# Fiedler值: 0.123456
# 关键节点数: 1
```

## 性能优化

### 1. 节点选择策略

根据任务类型选择不同策略：

```python
# 计算密集型：优先选择高算力节点
if task.task_type == TaskType.COMPUTE_INTENSIVE:
    nodes = sorted(nodes, key=lambda n: n.capability_score, reverse=True)

# 网络密集型：优先选择网络中心节点
elif task.task_type == TaskType.NETWORK_INTENSIVE:
    nodes = sorted(nodes, key=lambda n: n.fiedler_score, reverse=True)
```

### 2. 负载均衡

启用任务迁移实现动态负载均衡：

```python
load_balancer = HLIGLoadBalancer(
    node_manager=node_manager,
    rebalance_threshold=0.3,  # 负载差异>30%时触发
    enable_migration=True      # 启用任务迁移
)
```

### 3. 结果缓存

对重复计算启用结果缓存：

```python
result_cache = {}

def compute_with_cache(task_id, compute_func):
    if task_id in result_cache:
        return result_cache[task_id]

    result = compute_func()
    result_cache[task_id] = result
    return result
```

## 安全考虑

### 1. 沙箱执行

使用multiprocessing限制资源访问：

```python
with multiprocessing.Pool(processes=1) as pool:
    result = pool.apply_async(func, args, kwargs).get(timeout=timeout)
```

### 2. 超时控制

所有任务必须设置超时：

```python
task = ComputeTask(
    task_id="task_001",
    timeout_seconds=3600,  # 1小时超时
    ...
)
```

### 3. 输入验证

验证所有用户输入：

```python
def validate_task(task):
    assert task.required_cpu_cores > 0
    assert task.required_memory_gb > 0
    assert task.timeout_seconds > 0
```

## 常见问题

### Q1: HLIG与传统分布式计算的区别？

**A:** 传统方法使用轮询或随机分配任务，HIDRS使用Fiedler向量识别网络中的"超级节点"，实现全局最优分配。就像GPS导航（全局视角）vs问路（局部视角）。

### Q2: Fiedler向量如何帮助任务调度？

**A:** Fiedler向量是拉普拉斯矩阵第二小特征值对应的特征向量，其分量反映了节点在网络中的重要性和中心度。高Fiedler得分的节点更适合处理关键任务。

### Q3: 如何处理节点故障？

**A:** 系统通过心跳检测监控节点状态，超时节点会被标记为离线。任务可以通过负载均衡器迁移到健康节点。

### Q4: 支持GPU加速吗？

**A:** 支持。算力评估器会自动检测GPU，任务可以指定`required_gpu_count`要求GPU节点。

### Q5: 如何扩展到大规模集群？

**A:** 使用分层架构：
- **叶节点**: 计算工作节点
- **中间节点**: 区域调度器
- **根节点**: 全局协调器

## 依赖

```bash
pip install numpy
pip install scipy
pip install psutil  # 系统信息
pip install GPUtil  # GPU检测（可选）
```

## 未来工作

1. **DHT实现** - 完整的Kademlia分布式哈希表
2. **容错机制** - 自动任务重试和检查点
3. **数据并行** - 支持TensorFlow/PyTorch分布式训练
4. **区块链集成** - 算力贡献激励机制
5. **WebRTC支持** - 浏览器端P2P计算

## 参考文献

1. HLIG理论文档 - `/home/user/hidrs/docs/HLIG_theory.md`
2. Fiedler, M. (1973). Algebraic connectivity of graphs
3. Kademlia DHT - P2P分布式哈希表
4. MapReduce - Google分布式计算框架

## 许可

MIT License

---

**核心理念:**
> "全球广播 = 我向全球推送；分布式计算 = 我从全球拉取"

HIDRS分布式计算系统是全球广播系统的完美逆向应用，使用相同的HLIG理论，但目标相反：不是推送消息，而是借用算力。
