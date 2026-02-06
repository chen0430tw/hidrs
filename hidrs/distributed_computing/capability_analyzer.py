"""
算力评估器 - 评估节点计算能力

功能：
1. 硬件性能评估（CPU/GPU/内存/存储）
2. 网络性能评估（带宽/延迟/稳定性）
3. 综合算力打分
4. 实时性能监控

评分算法：
capability_score = α·CPU得分 + β·GPU得分 + γ·内存得分 + δ·网络得分

类比：
- 区块链挖矿: 只看算力（hash rate）
- HIDRS: 综合评估（计算+网络+可靠性）
"""
import logging
import time
import psutil
import platform
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class NodeCapability:
    """节点算力信息"""
    # 硬件信息
    cpu_cores: int = 0              # CPU核心数
    cpu_threads: int = 0            # 逻辑线程数
    cpu_freq_mhz: float = 0.0       # CPU频率（MHz）
    cpu_usage_percent: float = 0.0  # CPU使用率

    memory_total_gb: float = 0.0    # 总内存（GB）
    memory_available_gb: float = 0.0 # 可用内存（GB）
    memory_usage_percent: float = 0.0

    disk_total_gb: float = 0.0      # 总磁盘（GB）
    disk_free_gb: float = 0.0       # 可用磁盘（GB）

    # GPU信息（如果有）
    gpu_count: int = 0
    gpu_names: List[str] = None
    gpu_memory_total_gb: float = 0.0
    gpu_memory_free_gb: float = 0.0

    # 网络信息
    bandwidth_mbps: float = 0.0     # 带宽（Mbps）
    latency_ms: float = 0.0         # 延迟（ms）
    packet_loss_rate: float = 0.0   # 丢包率

    # 系统信息
    platform: str = ""              # 操作系统
    python_version: str = ""        # Python版本
    uptime_hours: float = 0.0       # 运行时间（小时）

    # 综合得分
    cpu_score: float = 0.0          # CPU得分
    gpu_score: float = 0.0          # GPU得分
    memory_score: float = 0.0       # 内存得分
    network_score: float = 0.0      # 网络得分
    total_score: float = 0.0        # 总得分

    # 元数据
    timestamp: Optional[datetime] = None
    metadata: Dict = None

    def __post_init__(self):
        if self.gpu_names is None:
            self.gpu_names = []
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict:
        """转换为字典"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat() if self.timestamp else None
        return data


class CapabilityAnalyzer:
    """算力评估器"""

    def __init__(
        self,
        weight_cpu: float = 0.4,
        weight_gpu: float = 0.3,
        weight_memory: float = 0.2,
        weight_network: float = 0.1,
        enable_gpu: bool = True
    ):
        """
        初始化算力评估器

        参数:
        - weight_cpu: CPU权重（默认0.4）
        - weight_gpu: GPU权重（默认0.3）
        - weight_memory: 内存权重（默认0.2）
        - weight_network: 网络权重（默认0.1）
        - enable_gpu: 是否启用GPU检测
        """
        self.weight_cpu = weight_cpu
        self.weight_gpu = weight_gpu
        self.weight_memory = weight_memory
        self.weight_network = weight_network
        self.enable_gpu = enable_gpu

        # 归一化权重
        total_weight = weight_cpu + weight_gpu + weight_memory + weight_network
        self.weight_cpu /= total_weight
        self.weight_gpu /= total_weight
        self.weight_memory /= total_weight
        self.weight_network /= total_weight

        logger.info("[CapabilityAnalyzer] 初始化完成")
        logger.info(f"  权重: CPU={self.weight_cpu:.2f}, GPU={self.weight_gpu:.2f}, "
                   f"内存={self.weight_memory:.2f}, 网络={self.weight_network:.2f}")

    def analyze_local_node(self) -> NodeCapability:
        """
        分析本地节点算力

        返回:
        - NodeCapability对象
        """
        capability = NodeCapability()

        # 1. CPU信息
        capability.cpu_cores = psutil.cpu_count(logical=False) or 0
        capability.cpu_threads = psutil.cpu_count(logical=True) or 0

        cpu_freq = psutil.cpu_freq()
        capability.cpu_freq_mhz = cpu_freq.current if cpu_freq else 0.0

        capability.cpu_usage_percent = psutil.cpu_percent(interval=1)

        # 2. 内存信息
        mem = psutil.virtual_memory()
        capability.memory_total_gb = mem.total / (1024**3)
        capability.memory_available_gb = mem.available / (1024**3)
        capability.memory_usage_percent = mem.percent

        # 3. 磁盘信息
        disk = psutil.disk_usage('/')
        capability.disk_total_gb = disk.total / (1024**3)
        capability.disk_free_gb = disk.free / (1024**3)

        # 4. GPU信息（如果启用）
        if self.enable_gpu:
            self._detect_gpu(capability)

        # 5. 网络信息
        self._measure_network(capability)

        # 6. 系统信息
        capability.platform = platform.platform()
        capability.python_version = platform.python_version()
        capability.uptime_hours = (time.time() - psutil.boot_time()) / 3600

        # 7. 计算得分
        capability.cpu_score = self._compute_cpu_score(capability)
        capability.gpu_score = self._compute_gpu_score(capability)
        capability.memory_score = self._compute_memory_score(capability)
        capability.network_score = self._compute_network_score(capability)

        capability.total_score = (
            self.weight_cpu * capability.cpu_score +
            self.weight_gpu * capability.gpu_score +
            self.weight_memory * capability.memory_score +
            self.weight_network * capability.network_score
        )

        capability.timestamp = datetime.now()

        logger.info(f"[CapabilityAnalyzer] 本地节点算力分析完成")
        logger.info(f"  CPU: {capability.cpu_cores}核/{capability.cpu_threads}线程 @ {capability.cpu_freq_mhz:.0f}MHz")
        logger.info(f"  内存: {capability.memory_available_gb:.1f}GB / {capability.memory_total_gb:.1f}GB")
        logger.info(f"  GPU: {capability.gpu_count}个")
        logger.info(f"  总得分: {capability.total_score:.2f}")

        return capability

    def _detect_gpu(self, capability: NodeCapability):
        """检测GPU"""
        try:
            # 尝试使用GPUtil
            import GPUtil
            gpus = GPUtil.getGPUs()

            capability.gpu_count = len(gpus)
            capability.gpu_names = [gpu.name for gpu in gpus]

            if gpus:
                capability.gpu_memory_total_gb = sum(gpu.memoryTotal for gpu in gpus) / 1024
                capability.gpu_memory_free_gb = sum(gpu.memoryFree for gpu in gpus) / 1024

                logger.debug(f"[CapabilityAnalyzer] 检测到 {len(gpus)} 个GPU")

        except ImportError:
            logger.debug("[CapabilityAnalyzer] GPUtil未安装，跳过GPU检测")
        except Exception as e:
            logger.debug(f"[CapabilityAnalyzer] GPU检测失败: {e}")

    def _measure_network(self, capability: NodeCapability):
        """测量网络性能"""
        try:
            # 简化版：使用ping测试延迟
            import subprocess

            # Ping Google DNS
            result = subprocess.run(
                ['ping', '-c', '3', '8.8.8.8'],
                capture_output=True,
                text=True,
                timeout=10
            )

            # 解析延迟
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'avg' in line or 'time=' in line:
                        # 提取平均延迟
                        parts = line.split('=')
                        if len(parts) > 1:
                            time_str = parts[-1].split('/')[0] if '/' in parts[-1] else parts[-1]
                            capability.latency_ms = float(time_str.strip().split()[0])
                            break

            # 简化：假设带宽（实际应该用iperf3等工具测试）
            capability.bandwidth_mbps = 100.0  # 默认100Mbps

        except Exception as e:
            logger.debug(f"[CapabilityAnalyzer] 网络测量失败: {e}")
            capability.latency_ms = 100.0  # 默认延迟
            capability.bandwidth_mbps = 10.0

    def _compute_cpu_score(self, cap: NodeCapability) -> float:
        """
        计算CPU得分（0-100）

        考虑因素：
        - 核心数
        - 频率
        - 当前使用率（空闲越多越好）
        """
        # 核心得分：假设32核为满分
        core_score = min(cap.cpu_cores / 32.0, 1.0) * 40

        # 频率得分：假设4000MHz为满分
        freq_score = min(cap.cpu_freq_mhz / 4000.0, 1.0) * 30

        # 空闲得分：CPU使用率越低越好
        idle_score = (100 - cap.cpu_usage_percent) / 100.0 * 30

        return core_score + freq_score + idle_score

    def _compute_gpu_score(self, cap: NodeCapability) -> float:
        """
        计算GPU得分（0-100）

        考虑因素：
        - GPU数量
        - GPU显存
        """
        if cap.gpu_count == 0:
            return 0.0

        # GPU数量得分：假设8个GPU为满分
        count_score = min(cap.gpu_count / 8.0, 1.0) * 50

        # 显存得分：假设80GB为满分
        memory_score = min(cap.gpu_memory_total_gb / 80.0, 1.0) * 50

        return count_score + memory_score

    def _compute_memory_score(self, cap: NodeCapability) -> float:
        """
        计算内存得分（0-100）

        考虑因素：
        - 总内存大小
        - 可用内存比例
        """
        # 总量得分：假设256GB为满分
        total_score = min(cap.memory_total_gb / 256.0, 1.0) * 50

        # 可用得分
        available_ratio = cap.memory_available_gb / cap.memory_total_gb if cap.memory_total_gb > 0 else 0
        available_score = available_ratio * 50

        return total_score + available_score

    def _compute_network_score(self, cap: NodeCapability) -> float:
        """
        计算网络得分（0-100）

        考虑因素：
        - 带宽
        - 延迟
        - 丢包率
        """
        # 带宽得分：假设1000Mbps为满分
        bandwidth_score = min(cap.bandwidth_mbps / 1000.0, 1.0) * 40

        # 延迟得分：延迟越低越好，假设100ms为阈值
        latency_score = max(0, (100 - cap.latency_ms) / 100.0) * 40

        # 丢包率得分
        loss_score = (1.0 - cap.packet_loss_rate) * 20

        return bandwidth_score + latency_score + loss_score

    def analyze_remote_node(self, node_data: Dict) -> NodeCapability:
        """
        分析远程节点算力（基于节点上报的数据）

        参数:
        - node_data: 节点数据字典

        返回:
        - NodeCapability对象
        """
        capability = NodeCapability()

        # 从字典中提取数据
        capability.cpu_cores = node_data.get('cpu_cores', 0)
        capability.cpu_threads = node_data.get('cpu_threads', 0)
        capability.cpu_freq_mhz = node_data.get('cpu_freq_mhz', 0.0)
        capability.cpu_usage_percent = node_data.get('cpu_usage_percent', 50.0)

        capability.memory_total_gb = node_data.get('memory_total_gb', 0.0)
        capability.memory_available_gb = node_data.get('memory_available_gb', 0.0)
        capability.memory_usage_percent = node_data.get('memory_usage_percent', 50.0)

        capability.gpu_count = node_data.get('gpu_count', 0)
        capability.gpu_names = node_data.get('gpu_names', [])
        capability.gpu_memory_total_gb = node_data.get('gpu_memory_total_gb', 0.0)

        capability.bandwidth_mbps = node_data.get('bandwidth_mbps', 10.0)
        capability.latency_ms = node_data.get('latency_ms', 100.0)

        # 计算得分
        capability.cpu_score = self._compute_cpu_score(capability)
        capability.gpu_score = self._compute_gpu_score(capability)
        capability.memory_score = self._compute_memory_score(capability)
        capability.network_score = self._compute_network_score(capability)

        capability.total_score = (
            self.weight_cpu * capability.cpu_score +
            self.weight_gpu * capability.gpu_score +
            self.weight_memory * capability.memory_score +
            self.weight_network * capability.network_score
        )

        capability.timestamp = datetime.now()

        return capability

    def compare_nodes(self, cap1: NodeCapability, cap2: NodeCapability) -> Dict:
        """
        比较两个节点的算力

        返回:
        - 比较结果字典
        """
        return {
            'total_score_diff': cap1.total_score - cap2.total_score,
            'cpu_score_diff': cap1.cpu_score - cap2.cpu_score,
            'gpu_score_diff': cap1.gpu_score - cap2.gpu_score,
            'memory_score_diff': cap1.memory_score - cap2.memory_score,
            'network_score_diff': cap1.network_score - cap2.network_score,
            'better_node': 'node1' if cap1.total_score > cap2.total_score else 'node2',
            'score_ratio': cap1.total_score / cap2.total_score if cap2.total_score > 0 else float('inf')
        }

    def rank_nodes(self, capabilities: List[NodeCapability]) -> List[NodeCapability]:
        """
        对节点按算力排序

        参数:
        - capabilities: 节点算力列表

        返回:
        - 排序后的列表（从高到低）
        """
        return sorted(capabilities, key=lambda c: c.total_score, reverse=True)

    def get_stats(self) -> Dict:
        """获取评估器统计信息"""
        return {
            'weights': {
                'cpu': self.weight_cpu,
                'gpu': self.weight_gpu,
                'memory': self.weight_memory,
                'network': self.weight_network
            },
            'enable_gpu': self.enable_gpu
        }
