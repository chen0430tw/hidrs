"""
HIDRS智能资源调度器
基于ET-WCN降温算法和SOSA火种源自组织算法

核心功能：
1. 动态调整防御强度以节省运算资源
2. 基于攻击模式的自适应资源分配
3. 智能降温/加热机制
4. SOSA流式事件处理

By: Claude + 430
"""

import logging
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import math

# 导入降温算法和SOSA
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from et_cooling import (
    ETCoolingScheduler,
    WeightChainNetwork,
    delta,
    IOTA,
    compute_beta1
)
from spark_seed_sosa import SparkSeedSOSA, Event

logger = logging.getLogger(__name__)


@dataclass
class ResourceProfile:
    """资源使用配置文件"""
    # 检测频率（每秒处理的包数上限）
    packet_rate_limit: int

    # DPI深度包检测开关
    enable_dpi: bool

    # HLIG异常检测开关
    enable_hlig: bool

    # 主动探测开关
    enable_active_probing: bool

    # DNS防御开关
    enable_dns_defense: bool

    # 攻击记忆开关
    enable_attack_memory: bool

    # CPU使用率估计（0-1）
    estimated_cpu_usage: float

    # 配置描述
    profile_name: str


class DefenseLevel:
    """防御等级常量"""
    MAXIMUM = "maximum"      # 最高防御（高温：攻击频繁）
    HIGH = "high"           # 高防御（中高温）
    NORMAL = "normal"       # 正常防御（中温）
    LOW = "low"            # 低防御（低温：攻击少）
    MINIMAL = "minimal"     # 最小防御（极低温：长时间无攻击）


class SmartResourceScheduler:
    """
    HIDRS智能资源调度器

    使用ET降温算法动态调整防御资源分配：

    温度阶段 → 防御等级 → 资源配置
    ========================================
    T ≈ T_max (对称阶段)
      ↓
    MAXIMUM: 全面防御，所有功能开启
    - DPI + HLIG + 主动探测 + DNS防御 + 攻击记忆
    - CPU使用率: 80-100%

    0.6*T_max < T < T_max (破缺阶段)
      ↓
    HIGH: 高防御，核心功能开启
    - DPI + HLIG + 攻击记忆
    - CPU使用率: 50-80%

    0.3*T_max < T < 0.6*T_max
      ↓
    NORMAL: 正常防御
    - DPI + 攻击记忆
    - CPU使用率: 30-50%

    T_min < T < 0.3*T_max
      ↓
    LOW: 低防御（结晶阶段）
    - 仅攻击记忆快速识别
    - CPU使用率: 10-30%

    T ≈ T_min
      ↓
    MINIMAL: 最小防御（长时间稳定）
    - 仅基础包检查
    - CPU使用率: <10%
    """

    # 预定义资源配置文件
    PROFILES = {
        DefenseLevel.MAXIMUM: ResourceProfile(
            packet_rate_limit=10000,
            enable_dpi=True,
            enable_hlig=True,
            enable_active_probing=True,
            enable_dns_defense=True,
            enable_attack_memory=True,
            estimated_cpu_usage=0.9,
            profile_name="最高防御"
        ),
        DefenseLevel.HIGH: ResourceProfile(
            packet_rate_limit=5000,
            enable_dpi=True,
            enable_hlig=True,
            enable_active_probing=False,
            enable_dns_defense=True,
            enable_attack_memory=True,
            estimated_cpu_usage=0.65,
            profile_name="高防御"
        ),
        DefenseLevel.NORMAL: ResourceProfile(
            packet_rate_limit=2000,
            enable_dpi=True,
            enable_hlig=False,
            enable_active_probing=False,
            enable_dns_defense=False,
            enable_attack_memory=True,
            estimated_cpu_usage=0.4,
            profile_name="正常防御"
        ),
        DefenseLevel.LOW: ResourceProfile(
            packet_rate_limit=1000,
            enable_dpi=False,
            enable_hlig=False,
            enable_active_probing=False,
            enable_dns_defense=False,
            enable_attack_memory=True,
            estimated_cpu_usage=0.2,
            profile_name="低防御"
        ),
        DefenseLevel.MINIMAL: ResourceProfile(
            packet_rate_limit=500,
            enable_dpi=False,
            enable_hlig=False,
            enable_active_probing=False,
            enable_dns_defense=False,
            enable_attack_memory=False,
            estimated_cpu_usage=0.05,
            profile_name="最小防御"
        )
    }

    def __init__(
        self,
        T_max: float = 1.0,
        T_min: float = 0.01,
        delta_crit: float = 5.0,
        beta1_target: int = 0,
        wcn_dim: int = 8,
        wcn_nodes: int = 10,
        sosa_states: int = 5,
        sosa_groups: int = 8,
        window_size: float = 60.0,  # 60秒窗口
        signature_db = None  # 可选：攻击特征库
    ):
        """
        初始化智能资源调度器

        参数:
        - T_max: 最高温度（对应最高防御）
        - T_min: 最低温度（对应最低防御）
        - delta_crit: 结晶临界落差
        - beta1_target: 目标β₁
        - wcn_dim: WCN嵌入维度
        - wcn_nodes: WCN节点数
        - sosa_states: SOSA状态数
        - sosa_groups: SOSA行为组数
        - window_size: 时间窗口大小（秒）
        """
        logger.info("=" * 60)
        logger.info("🧠 HIDRS智能资源调度器初始化")
        logger.info("=" * 60)

        # ET降温调度器
        self.scheduler = ETCoolingScheduler(
            T_max=T_max,
            T_min=T_min,
            delta_crit=delta_crit,
            beta1_target=beta1_target
        )

        # WCN权重链网络（用于建模攻击模式关系）
        self.wcn = WeightChainNetwork(dim=wcn_dim, bias=-1.0)
        for i in range(wcn_nodes):
            self.wcn.add_node(i)

        # SOSA火种源自组织算法（流式事件处理）
        self.sosa = SparkSeedSOSA(
            N_states=sosa_states,
            M_groups=sosa_groups,
            dt_window=window_size
        )

        # 攻击特征库（可选）
        self.signature_db = signature_db
        self.signature_db_enabled = signature_db is not None
        if self.signature_db_enabled:
            logger.info(f"  ✅ 特征库已集成: {len(signature_db.attack_signatures)} 个签名")

        # 当前资源配置
        self.current_profile = self.PROFILES[DefenseLevel.MAXIMUM]
        self.current_level = DefenseLevel.MAXIMUM

        # 统计信息
        self.stats = {
            'total_events': 0,
            'attack_events': 0,
            'normal_events': 0,
            'profile_switches': 0,
            'resource_saved_ratio': 0.0,
            'last_profile_switch': datetime.utcnow(),
            'signature_matches': 0,  # 特征库匹配次数
            'malware_detections': 0   # 木马检测次数
        }

        # 事件历史（用于计算对称落差）
        self.attack_rate_history: List[float] = []
        self.energy_history: List[float] = []

        logger.info(f"  ET降温调度器: T_max={T_max}, T_min={T_min}")
        logger.info(f"  WCN网络: dim={wcn_dim}, nodes={wcn_nodes}")
        logger.info(f"  SOSA算法: states={sosa_states}, groups={sosa_groups}")
        logger.info(f"  初始防御等级: {self.current_level}")
        logger.info("=" * 60)

    def process_traffic_event(
        self,
        is_attack: bool,
        attack_type: Optional[str] = None,
        threat_level: int = 0,
        packet_count: int = 1
    ) -> Tuple[ResourceProfile, Dict[str, Any]]:
        """
        处理流量事件，返回动态调整后的资源配置

        参数:
        - is_attack: 是否为攻击
        - attack_type: 攻击类型
        - threat_level: 威胁等级（0-3）
        - packet_count: 包数量

        返回:
        - (ResourceProfile, 调度信息字典)
        """
        self.stats['total_events'] += 1
        if is_attack:
            self.stats['attack_events'] += 1
        else:
            self.stats['normal_events'] += 1

        # 1. 将事件送入SOSA处理
        obs = {
            'is_attack': is_attack,
            'attack_type': attack_type,
            'threat_level': threat_level,
            'packet_count': packet_count
        }
        action = 'defend' if is_attack else 'allow'
        self.sosa.process_event(obs=obs, action=action, timestamp=time.time())

        # 2. 计算当前攻击率
        window_size = 100
        recent_attacks = self.stats['attack_events']
        recent_total = min(window_size, self.stats['total_events'])
        attack_rate = recent_attacks / max(1, recent_total)
        self.attack_rate_history.append(attack_rate)

        # 3. 计算"能量"（系统压力）
        # 能量 = 攻击率 * 威胁等级平均值
        energy = attack_rate * (threat_level / 3.0)
        self.energy_history.append(energy)

        # 4. 计算对称落差Δ
        current_delta, current_beta1 = self._compute_delta_and_beta1()

        # 5. ET降温调度器更新温度
        temperature = self.scheduler.step(
            current_delta=current_delta,
            current_beta1=current_beta1,
            current_energy=energy
        )

        # 6. 根据温度和阶段确定防御等级
        new_level = self._temperature_to_defense_level(
            temperature,
            self.scheduler.state.phase
        )

        # 7. 如果等级变化，切换资源配置
        profile_changed = False
        if new_level != self.current_level:
            self._switch_profile(new_level)
            profile_changed = True

        # 8. 检查是否需要再加热
        if self.scheduler.should_reheat(stagnation_threshold=50):
            logger.warning(
                f"[ResourceScheduler] 检测到停滞，触发再加热 "
                f"(T: {temperature:.4f} → {self.scheduler.T_max * 0.6:.4f})"
            )
            self.scheduler.reheat()
            # 再加热后提升防御等级
            self._switch_profile(DefenseLevel.HIGH)
            profile_changed = True

        # 9. 计算资源节省比例
        baseline_cpu = self.PROFILES[DefenseLevel.MAXIMUM].estimated_cpu_usage
        current_cpu = self.current_profile.estimated_cpu_usage
        self.stats['resource_saved_ratio'] = 1.0 - (current_cpu / baseline_cpu)

        # 10. 返回当前资源配置和调度信息
        schedule_info = {
            'temperature': temperature,
            'phase': self.scheduler.state.phase,
            'delta': current_delta,
            'beta1': current_beta1,
            'energy': energy,
            'attack_rate': attack_rate,
            'defense_level': self.current_level,
            'profile_changed': profile_changed,
            'estimated_cpu': current_cpu,
            'resource_saved': self.stats['resource_saved_ratio']
        }

        return self.current_profile, schedule_info

    def _compute_delta_and_beta1(self) -> Tuple[float, int]:
        """
        计算对称落差Δ和拓扑复杂度β₁

        对称落差的ET意义：
        - a = 攻击率的"加法特征"（变化波动）
        - b = 攻击率的"乘法特征"（趋势强度）
        - Δ(a,b) 度量攻击模式的对称破缺程度

        返回: (delta, beta1)
        """
        # 需要足够的历史数据
        if len(self.attack_rate_history) < 5:
            return 0.0, 0

        # 取最近窗口
        window = min(50, len(self.attack_rate_history))
        recent_rates = self.attack_rate_history[-window:]

        # a = 2 + 攻击率变化的标准差（加法波动）
        mean_rate = sum(recent_rates) / len(recent_rates)
        var_rate = sum((r - mean_rate) ** 2 for r in recent_rates) / len(recent_rates)
        sigma_rate = math.sqrt(var_rate)
        a = 2.0 + sigma_rate * 10.0  # 放大系数

        # b = 2 + 攻击率趋势强度（单调性）
        # 计算上升趋势的强度
        increases = 0
        for i in range(1, len(recent_rates)):
            if recent_rates[i] > recent_rates[i-1]:
                increases += 1
        trend_strength = increases / max(1, len(recent_rates) - 1)
        b = 2.0 + trend_strength * mean_rate * 20.0  # 结合趋势和平均攻击率

        # 计算对称落差
        current_delta = max(0.0, delta(a, b))

        # 从WCN计算β₁
        adj = self.wcn.get_adjacency(threshold=0.5)
        current_beta1 = compute_beta1(adj, len(self.wcn.nodes))

        return current_delta, current_beta1

    def _temperature_to_defense_level(self, temperature: float, phase: str) -> str:
        """
        将温度映射到防御等级

        温度 → 防御等级映射：
        T ≥ 0.8 * T_max  → MAXIMUM
        0.6 ≤ T < 0.8    → HIGH
        0.3 ≤ T < 0.6    → NORMAL
        0.1 ≤ T < 0.3    → LOW
        T < 0.1          → MINIMAL
        """
        T_max = self.scheduler.T_max
        ratio = temperature / T_max

        if ratio >= 0.8:
            return DefenseLevel.MAXIMUM
        elif ratio >= 0.6:
            return DefenseLevel.HIGH
        elif ratio >= 0.3:
            return DefenseLevel.NORMAL
        elif ratio >= 0.1:
            return DefenseLevel.LOW
        else:
            return DefenseLevel.MINIMAL

    def _switch_profile(self, new_level: str) -> None:
        """切换资源配置文件"""
        old_level = self.current_level
        old_profile = self.current_profile

        self.current_level = new_level
        self.current_profile = self.PROFILES[new_level]

        self.stats['profile_switches'] += 1
        self.stats['last_profile_switch'] = datetime.utcnow()

        logger.info(
            f"[ResourceScheduler] 🔄 防御等级切换: {old_profile.profile_name} → "
            f"{self.current_profile.profile_name} "
            f"(CPU: {old_profile.estimated_cpu_usage:.1%} → "
            f"{self.current_profile.estimated_cpu_usage:.1%})"
        )

    def get_current_profile(self) -> ResourceProfile:
        """获取当前资源配置"""
        return self.current_profile

    def get_stats(self) -> Dict[str, Any]:
        """获取调度器统计信息"""
        return {
            **self.stats,
            'current_level': self.current_level,
            'current_profile': self.current_profile.profile_name,
            'temperature': self.scheduler.state.temperature,
            'phase': self.scheduler.state.phase,
            'epochs': self.scheduler.state.epoch,
            'sosa_state_distribution': self.sosa.get_state_distribution()
        }

    def get_scheduling_history(self) -> Dict[str, List]:
        """获取调度历史"""
        return {
            'delta_history': self.scheduler.state.delta_history,
            'beta1_history': self.scheduler.state.beta1_history,
            'energy_history': self.scheduler.state.energy_history,
            'attack_rate_history': self.attack_rate_history[-100:]  # 最近100条
        }

    def force_level(self, level: str) -> None:
        """
        强制设置防御等级（用于紧急情况）

        参数:
        - level: DefenseLevel常量
        """
        if level not in self.PROFILES:
            raise ValueError(f"Invalid defense level: {level}")

        logger.warning(f"[ResourceScheduler] ⚠️ 强制设置防御等级: {level}")
        self._switch_profile(level)

        # 重置降温调度器到对应温度
        if level == DefenseLevel.MAXIMUM:
            self.scheduler.state.temperature = self.scheduler.T_max
        elif level == DefenseLevel.HIGH:
            self.scheduler.state.temperature = self.scheduler.T_max * 0.7
        elif level == DefenseLevel.NORMAL:
            self.scheduler.state.temperature = self.scheduler.T_max * 0.45
        elif level == DefenseLevel.LOW:
            self.scheduler.state.temperature = self.scheduler.T_max * 0.2
        else:  # MINIMAL
            self.scheduler.state.temperature = self.scheduler.T_min


# 使用示例
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("🧠 HIDRS智能资源调度器演示")
    print("=" * 70)

    scheduler = SmartResourceScheduler(
        T_max=1.0,
        T_min=0.01,
        delta_crit=3.0,
        window_size=10.0
    )

    # 模拟场景1: 初期高攻击
    print("\n场景1: 高频攻击阶段（前50个事件）")
    for i in range(50):
        is_attack = i % 3 == 0  # 33%攻击率
        threat = 2 if is_attack else 0

        profile, info = scheduler.process_traffic_event(
            is_attack=is_attack,
            attack_type='sql_injection' if is_attack else None,
            threat_level=threat
        )

        if i % 10 == 0:
            print(f"  事件{i}: 温度={info['temperature']:.4f}, "
                  f"等级={info['defense_level']}, "
                  f"CPU={info['estimated_cpu']:.1%}, "
                  f"节省={info['resource_saved']:.1%}")

    # 模拟场景2: 攻击减少
    print("\n场景2: 攻击减少阶段（50-150个事件）")
    for i in range(50, 150):
        is_attack = i % 10 == 0  # 10%攻击率
        threat = 1 if is_attack else 0

        profile, info = scheduler.process_traffic_event(
            is_attack=is_attack,
            attack_type='xss' if is_attack else None,
            threat_level=threat
        )

        if i % 20 == 0:
            print(f"  事件{i}: 温度={info['temperature']:.4f}, "
                  f"等级={info['defense_level']}, "
                  f"CPU={info['estimated_cpu']:.1%}, "
                  f"节省={info['resource_saved']:.1%}")

    # 模拟场景3: 长时间稳定
    print("\n场景3: 稳定阶段（150-250个事件）")
    for i in range(150, 250):
        is_attack = i % 50 == 0  # 2%攻击率
        threat = 1 if is_attack else 0

        profile, info = scheduler.process_traffic_event(
            is_attack=is_attack,
            attack_type='port_scan' if is_attack else None,
            threat_level=threat
        )

        if i % 25 == 0:
            print(f"  事件{i}: 温度={info['temperature']:.4f}, "
                  f"等级={info['defense_level']}, "
                  f"CPU={info['estimated_cpu']:.1%}, "
                  f"节省={info['resource_saved']:.1%}")

    # 统计信息
    print("\n" + "=" * 70)
    print("最终统计:")
    stats = scheduler.get_stats()
    print(f"  总事件数: {stats['total_events']}")
    print(f"  攻击事件: {stats['attack_events']}")
    print(f"  正常事件: {stats['normal_events']}")
    print(f"  配置切换次数: {stats['profile_switches']}")
    print(f"  当前防御等级: {stats['current_level']}")
    print(f"  当前温度: {stats['temperature']:.4f}")
    print(f"  当前阶段: {stats['phase']}")
    print(f"  资源节省: {stats['resource_saved_ratio']:.1%}")
    print("=" * 70)
