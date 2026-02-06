"""
HIDRS防火墙记忆系统
Attack Pattern Memory & Learning System

核心功能：
1. 攻击模式记忆 - 记住历史攻击特征
2. 行为学习 - 学习攻击者的行为模式
3. 智能预测 - 预测潜在攻击
4. 模式进化 - 攻击模式自动更新

类似人类免疫系统：
- 第一次遇到病毒 → 记住特征
- 再次遇到 → 立即识别并免疫
- 病毒变异 → 更新记忆
"""

import os
import json
import pickle
import hashlib
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from dataclasses import dataclass, asdict

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class AttackPattern:
    """攻击模式"""
    pattern_id: str
    attack_type: str  # 'sql_injection', 'xss', 'port_scan', 'ddos', etc.
    signatures: List[str]  # 攻击特征列表
    first_seen: datetime
    last_seen: datetime
    occurrence_count: int
    source_ips: List[str]
    target_ports: List[int]
    success_rate: float  # 攻击成功率
    severity: int  # 1-10

    # 行为特征
    avg_packet_size: float
    avg_request_rate: float
    time_pattern: List[int]  # 24小时分布

    def to_dict(self) -> Dict:
        """转换为字典（用于序列化）"""
        data = asdict(self)
        data['first_seen'] = self.first_seen.isoformat()
        data['last_seen'] = self.last_seen.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> 'AttackPattern':
        """从字典创建"""
        data['first_seen'] = datetime.fromisoformat(data['first_seen'])
        data['last_seen'] = datetime.fromisoformat(data['last_seen'])
        return cls(**data)


@dataclass
class AttackerProfile:
    """攻击者画像"""
    ip: str
    first_attack: datetime
    last_attack: datetime
    total_attacks: int
    attack_types: List[str]
    patterns_used: List[str]  # pattern_id列表
    success_rate: float
    threat_score: float  # 0-100

    # 行为特征
    preferred_ports: List[int]
    attack_time_preference: List[int]  # 偏好的攻击时段
    sophistication_level: int  # 1-5（攻击复杂度）

    def to_dict(self) -> Dict:
        """转换为字典"""
        data = asdict(self)
        data['first_attack'] = self.first_attack.isoformat()
        data['last_attack'] = self.last_attack.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> 'AttackerProfile':
        """从字典创建"""
        data['first_attack'] = datetime.fromisoformat(data['first_attack'])
        data['last_attack'] = datetime.fromisoformat(data['last_attack'])
        return cls(**data)


class AttackMemorySystem:
    """
    攻击记忆系统
    类似人类免疫系统，记住攻击模式并学习

    支持三种运行模式：
    1. 正式模式 (live): 完整防御功能
    2. 模拟模式 (simulation): 只记录日志，不实际执行防御动作
    3. 测试模式 (test): 小范围测试，仅对白名单IP执行防御
    """

    def __init__(
        self,
        memory_file: str = '/tmp/hidrs_attack_memory.pkl',
        simulation_mode: bool = False,
        test_mode: bool = False,
        test_whitelist_ips: List[str] = None,
        max_test_clients: int = 10
    ):
        """
        初始化记忆系统

        参数:
        - memory_file: 记忆文件路径
        - simulation_mode: 模拟模式（不实际执行防御）
        - test_mode: 测试模式（小范围测试）
        - test_whitelist_ips: IP白名单（测试模式用）
        - max_test_clients: 最大测试客户端数
        """
        self.memory_file = memory_file

        # 攻击模式库
        self.attack_patterns: Dict[str, AttackPattern] = {}

        # 攻击者画像库
        self.attacker_profiles: Dict[str, AttackerProfile] = {}

        # 特征向量索引（用于快速匹配）
        self.feature_vectors: Dict[str, np.ndarray] = {}

        # 模式配置
        self.simulation_mode = simulation_mode
        self.test_mode = test_mode
        self.test_whitelist_ips = test_whitelist_ips or []
        self.max_test_clients = max_test_clients

        # 模拟日志（用于模拟模式）
        self.simulation_log: List[Dict] = []

        # 测试客户端计数
        self.test_client_count = 0

        # 加载历史记忆
        self._load_memory()

        # 根据模式输出不同提示
        if simulation_mode:
            logger.warning(f"[AttackMemory] ⚠️ 模拟模式已启用 - 不会实际执行防御动作")
        elif test_mode:
            logger.warning(
                f"[AttackMemory] ⚠️ 测试模式已启用 - "
                f"仅限白名单IP ({len(self.test_whitelist_ips)}个) 和最多 {max_test_clients} 个客户端"
            )
        else:
            logger.info(f"[AttackMemory] 正式模式已启用 - 完整防御功能")

        logger.info(f"[AttackMemory] 记忆系统初始化完成")
        logger.info(f"  已知攻击模式: {len(self.attack_patterns)}")
        logger.info(f"  已知攻击者: {len(self.attacker_profiles)}")

    def _load_memory(self):
        """加载历史记忆"""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'rb') as f:
                    data = pickle.load(f)

                # 恢复攻击模式
                for pattern_dict in data.get('patterns', []):
                    pattern = AttackPattern.from_dict(pattern_dict)
                    self.attack_patterns[pattern.pattern_id] = pattern

                # 恢复攻击者画像
                for profile_dict in data.get('profiles', []):
                    profile = AttackerProfile.from_dict(profile_dict)
                    self.attacker_profiles[profile.ip] = profile

                logger.info(f"[AttackMemory] 加载历史记忆: {len(self.attack_patterns)} 个模式")

            except Exception as e:
                logger.error(f"[AttackMemory] 加载记忆失败: {e}")

    def save_memory(self):
        """保存记忆到文件"""
        try:
            data = {
                'patterns': [p.to_dict() for p in self.attack_patterns.values()],
                'profiles': [p.to_dict() for p in self.attacker_profiles.values()],
                'version': '1.0',
                'saved_at': datetime.utcnow().isoformat()
            }

            with open(self.memory_file, 'wb') as f:
                pickle.dump(data, f)

            logger.debug(f"[AttackMemory] 记忆已保存")

        except Exception as e:
            logger.error(f"[AttackMemory] 保存记忆失败: {e}")

    def learn_attack(
        self,
        src_ip: str,
        attack_type: str,
        signatures: List[str],
        packet_size: int,
        success: bool,
        port: int
    ):
        """
        学习攻击模式

        参数:
        - src_ip: 来源IP
        - attack_type: 攻击类型
        - signatures: 攻击特征
        - packet_size: 包大小
        - success: 是否成功
        - port: 目标端口
        """
        # 1. 生成模式ID
        pattern_hash = hashlib.md5(
            f"{attack_type}:{':'.join(sorted(signatures))}".encode()
        ).hexdigest()[:16]

        pattern_id = f"{attack_type}_{pattern_hash}"

        # 模拟模式：记录日志但仍然学习（记忆系统需要学习）
        if self.simulation_mode:
            self._log_simulation('learn_attack', {
                'src_ip': src_ip,
                'attack_type': attack_type,
                'pattern_id': pattern_id,
                'signatures': signatures,
                'packet_size': packet_size,
                'success': success,
                'port': port
            })

        # 2. 更新或创建攻击模式（即使在模拟模式也要学习）
        if pattern_id in self.attack_patterns:
            pattern = self.attack_patterns[pattern_id]
            pattern.last_seen = datetime.utcnow()
            pattern.occurrence_count += 1

            if src_ip not in pattern.source_ips:
                pattern.source_ips.append(src_ip)

            if port not in pattern.target_ports:
                pattern.target_ports.append(port)

            # 更新成功率
            old_success = pattern.success_rate * (pattern.occurrence_count - 1)
            pattern.success_rate = (old_success + (1.0 if success else 0.0)) / pattern.occurrence_count

            # 更新包大小
            old_avg = pattern.avg_packet_size * (pattern.occurrence_count - 1)
            pattern.avg_packet_size = (old_avg + packet_size) / pattern.occurrence_count

        else:
            # 创建新模式
            pattern = AttackPattern(
                pattern_id=pattern_id,
                attack_type=attack_type,
                signatures=signatures,
                first_seen=datetime.utcnow(),
                last_seen=datetime.utcnow(),
                occurrence_count=1,
                source_ips=[src_ip],
                target_ports=[port],
                success_rate=1.0 if success else 0.0,
                severity=self._estimate_severity(attack_type),
                avg_packet_size=float(packet_size),
                avg_request_rate=0.0,
                time_pattern=[0] * 24
            )

            self.attack_patterns[pattern_id] = pattern

            if self.simulation_mode:
                logger.info(f"[AttackMemory] 🎬 模拟模式：学习新攻击模式 {pattern_id}")
            else:
                logger.info(f"[AttackMemory] 🧠 学习新攻击模式: {pattern_id}")

        # 3. 更新时间模式
        hour = datetime.utcnow().hour
        pattern.time_pattern[hour] += 1

        # 4. 更新攻击者画像
        self._update_attacker_profile(src_ip, pattern_id, attack_type, success, port)

    def _update_attacker_profile(
        self,
        ip: str,
        pattern_id: str,
        attack_type: str,
        success: bool,
        port: int
    ):
        """更新攻击者画像"""
        if ip in self.attacker_profiles:
            profile = self.attacker_profiles[ip]
            profile.last_attack = datetime.utcnow()
            profile.total_attacks += 1

            if attack_type not in profile.attack_types:
                profile.attack_types.append(attack_type)

            if pattern_id not in profile.patterns_used:
                profile.patterns_used.append(pattern_id)

            if port not in profile.preferred_ports:
                profile.preferred_ports.append(port)

            # 更新成功率
            old_success = profile.success_rate * (profile.total_attacks - 1)
            profile.success_rate = (old_success + (1.0 if success else 0.0)) / profile.total_attacks

            # 更新威胁分数
            profile.threat_score = self._calculate_threat_score(profile)

        else:
            # 创建新画像
            profile = AttackerProfile(
                ip=ip,
                first_attack=datetime.utcnow(),
                last_attack=datetime.utcnow(),
                total_attacks=1,
                attack_types=[attack_type],
                patterns_used=[pattern_id],
                success_rate=1.0 if success else 0.0,
                threat_score=50.0,
                preferred_ports=[port],
                attack_time_preference=[0] * 24,
                sophistication_level=1
            )

            self.attacker_profiles[ip] = profile
            logger.info(f"[AttackMemory] 🎯 创建攻击者画像: {ip}")

        # 更新时间偏好
        hour = datetime.utcnow().hour
        profile.attack_time_preference[hour] += 1

        # 更新复杂度
        profile.sophistication_level = min(5, len(profile.attack_types))

    def _estimate_severity(self, attack_type: str) -> int:
        """估计攻击严重性（1-10）"""
        severity_map = {
            'sql_injection': 9,
            'xss': 7,
            'ddos': 10,
            'port_scan': 3,
            'brute_force': 6,
            'malware': 10,
            'phishing': 8,
            'unknown': 5
        }
        return severity_map.get(attack_type, 5)

    def _calculate_threat_score(self, profile: AttackerProfile) -> float:
        """计算威胁分数（0-100）"""
        score = 0.0

        # 攻击频率
        score += min(30, profile.total_attacks / 10)

        # 成功率
        score += profile.success_rate * 20

        # 攻击类型多样性
        score += len(profile.attack_types) * 10

        # 复杂度
        score += profile.sophistication_level * 5

        # 持续性
        duration = (profile.last_attack - profile.first_attack).total_seconds()
        if duration > 3600:  # 1小时以上
            score += 15

        return min(100, score)

    def recognize_attack(self, signatures: List[str]) -> Optional[AttackPattern]:
        """
        识别攻击模式

        参数:
        - signatures: 攻击特征列表

        返回:
        - 匹配的攻击模式（如果识别成功）
        """
        best_match = None
        best_score = 0.0

        for pattern in self.attack_patterns.values():
            # 计算特征相似度
            common = set(signatures) & set(pattern.signatures)
            if not common:
                continue

            similarity = len(common) / max(len(signatures), len(pattern.signatures))

            if similarity > best_score:
                best_score = similarity
                best_match = pattern

        if best_match and best_score > 0.5:
            logger.info(f"[AttackMemory] 🧠 识别到已知攻击模式: {best_match.pattern_id} (相似度: {best_score:.2f})")
            return best_match

        return None

    def is_known_attacker(self, ip: str) -> Tuple[bool, Optional[AttackerProfile]]:
        """
        检查是否为已知攻击者

        返回:
        - (True, profile) 如果是已知攻击者
        - (False, None) 如果是新IP
        """
        if ip in self.attacker_profiles:
            profile = self.attacker_profiles[ip]

            # 检查是否为高威胁攻击者
            if profile.threat_score > 70:
                logger.warning(f"[AttackMemory] ⚠️  检测到高威胁攻击者: {ip} (威胁分: {profile.threat_score:.1f})")

            return True, profile

        return False, None

    def predict_next_attack(self, ip: str) -> Optional[Dict[str, Any]]:
        """
        预测攻击者的下一步行动

        返回:
        - 预测信息（攻击类型、时间、目标端口等）
        """
        if ip not in self.attacker_profiles:
            return None

        profile = self.attacker_profiles[ip]

        # 预测攻击类型（基于历史）
        type_counter = Counter(profile.attack_types)
        most_common_type = type_counter.most_common(1)[0][0]

        # 预测时间（基于偏好）
        hour_counter = Counter(
            i for i, count in enumerate(profile.attack_time_preference) if count > 0
        )
        preferred_hours = [h for h, _ in hour_counter.most_common(3)]

        # 预测端口
        port_counter = Counter(profile.preferred_ports)
        likely_ports = [p for p, _ in port_counter.most_common(3)]

        prediction = {
            'ip': ip,
            'predicted_type': most_common_type,
            'predicted_hours': preferred_hours,
            'predicted_ports': likely_ports,
            'confidence': min(100, profile.total_attacks * 10),
            'threat_score': profile.threat_score
        }

        logger.info(f"[AttackMemory] 🔮 预测 {ip} 的下一步攻击: {most_common_type}")

        return prediction

    def get_top_threats(self, limit: int = 10) -> List[AttackerProfile]:
        """获取威胁最高的攻击者"""
        sorted_profiles = sorted(
            self.attacker_profiles.values(),
            key=lambda p: p.threat_score,
            reverse=True
        )
        return sorted_profiles[:limit]

    def get_pattern_evolution(self, attack_type: str) -> List[AttackPattern]:
        """
        获取攻击模式演化历史

        返回:
        - 该类型攻击的所有已知模式（按时间排序）
        """
        patterns = [
            p for p in self.attack_patterns.values()
            if p.attack_type == attack_type
        ]

        return sorted(patterns, key=lambda p: p.first_seen)

    def cleanup_old_memories(self, days: int = 30):
        """清理旧记忆"""
        cutoff = datetime.utcnow() - timedelta(days=days)

        # 清理旧模式
        old_patterns = [
            pid for pid, pattern in self.attack_patterns.items()
            if pattern.last_seen < cutoff
        ]

        for pid in old_patterns:
            del self.attack_patterns[pid]

        # 清理旧攻击者
        old_attackers = [
            ip for ip, profile in self.attacker_profiles.items()
            if profile.last_attack < cutoff and profile.threat_score < 50
        ]

        for ip in old_attackers:
            del self.attacker_profiles[ip]

        if old_patterns or old_attackers:
            logger.info(f"[AttackMemory] 清理旧记忆: {len(old_patterns)} 个模式, {len(old_attackers)} 个攻击者")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_attacks = sum(p.occurrence_count for p in self.attack_patterns.values())

        attack_type_dist = Counter()
        for pattern in self.attack_patterns.values():
            attack_type_dist[pattern.attack_type] += pattern.occurrence_count

        mode = 'simulation' if self.simulation_mode else ('test' if self.test_mode else 'live')

        return {
            'mode': mode,
            'simulation_mode': self.simulation_mode,
            'test_mode': self.test_mode,
            'test_whitelist_count': len(self.test_whitelist_ips),
            'max_test_clients': self.max_test_clients,
            'total_patterns': len(self.attack_patterns),
            'total_attackers': len(self.attacker_profiles),
            'total_attacks_remembered': total_attacks,
            'attack_type_distribution': dict(attack_type_dist),
            'average_threat_score': np.mean([p.threat_score for p in self.attacker_profiles.values()]) if self.attacker_profiles else 0.0,
            'simulation_log_count': len(self.simulation_log)
        }

    def _is_ip_whitelisted(self, ip_address: str) -> bool:
        """检查IP是否在白名单中（用于测试模式）"""
        if not self.test_whitelist_ips:
            return False

        try:
            import ipaddress
            ip = ipaddress.ip_address(ip_address)
            for whitelist_entry in self.test_whitelist_ips:
                # 支持单个IP或CIDR范围
                if '/' in whitelist_entry:
                    network = ipaddress.ip_network(whitelist_entry, strict=False)
                    if ip in network:
                        return True
                else:
                    if ip == ipaddress.ip_address(whitelist_entry):
                        return True
            return False
        except Exception as e:
            logger.error(f"IP白名单检查失败: {e}")
            return False

    def _should_process_ip(self, ip: str) -> bool:
        """判断是否应该处理该IP（根据运行模式）"""
        if self.simulation_mode:
            # 模拟模式：记录所有IP但不实际处理
            return False

        if self.test_mode:
            # 测试模式：只处理白名单IP
            if not self._is_ip_whitelisted(ip):
                return False

            # 检查是否超过最大测试客户端数
            if self.test_client_count >= self.max_test_clients:
                return False

        # 正式模式或测试模式且符合条件
        return True

    def _log_simulation(self, action: str, data: Dict):
        """记录模拟日志"""
        if self.simulation_mode:
            log_entry = {
                'action': action,
                'data': data,
                'timestamp': datetime.now().isoformat()
            }
            self.simulation_log.append(log_entry)

    def get_simulation_log(self, limit: int = 100) -> Dict:
        """获取模拟日志"""
        if not self.simulation_mode:
            return {'error': '非模拟模式'}

        return {
            'success': True,
            'logs': self.simulation_log[-limit:],
            'total': len(self.simulation_log)
        }

    def should_defend_against(self, ip: str, attack_type: str) -> Tuple[bool, str]:
        """
        判断是否应该对该IP进行防御

        返回:
        - (True, reason) 如果应该防御
        - (False, reason) 如果不应该防御
        """
        # 模拟模式：记录但不防御
        if self.simulation_mode:
            self._log_simulation('defense_check', {
                'ip': ip,
                'attack_type': attack_type,
                'action': 'would_defend',
                'reason': 'simulation_mode'
            })
            logger.info(f"[AttackMemory] 🎬 模拟模式：将防御 {ip} 的 {attack_type} 攻击")
            return False, 'simulation_mode'

        # 测试模式：检查白名单和数量限制
        if self.test_mode:
            if not self._is_ip_whitelisted(ip):
                logger.debug(f"[AttackMemory] 测试模式：{ip} 不在白名单，跳过防御")
                return False, 'not_whitelisted'

            if self.test_client_count >= self.max_test_clients:
                logger.debug(f"[AttackMemory] 测试模式：已达到最大客户端数，跳过防御")
                return False, 'max_clients_reached'

            logger.info(f"[AttackMemory] 🧪 测试模式：防御白名单IP {ip} 的 {attack_type} 攻击")
            self.test_client_count += 1
            return True, 'test_mode_allowed'

        # 正式模式：执行完整防御
        logger.info(f"[AttackMemory] 🛡️ 正式模式：防御 {ip} 的 {attack_type} 攻击")
        return True, 'live_mode'


# 使用示例
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    print("🧠 HIDRS攻击记忆系统演示")
    print("=" * 60)

    # ========== 示例1: 正式模式 ==========
    print("\n【示例1：正式模式 (Live Mode)】")
    print("-" * 60)
    memory_live = AttackMemorySystem()

    memory_live.learn_attack(
        src_ip='1.2.3.4',
        attack_type='sql_injection',
        signatures=['UNION SELECT', 'OR 1=1'],
        packet_size=512,
        success=False,
        port=80
    )

    should_defend, reason = memory_live.should_defend_against('1.2.3.4', 'sql_injection')
    print(f"是否防御: {should_defend}, 原因: {reason}")

    # ========== 示例2: 模拟模式 ==========
    print("\n【示例2：模拟模式 (Simulation Mode)】")
    print("-" * 60)
    memory_sim = AttackMemorySystem(simulation_mode=True)

    # 学习攻击（会记录日志）
    memory_sim.learn_attack(
        src_ip='5.6.7.8',
        attack_type='xss',
        signatures=['<script>', 'javascript:'],
        packet_size=256,
        success=False,
        port=443
    )

    # 检查是否防御（不会实际防御）
    should_defend, reason = memory_sim.should_defend_against('5.6.7.8', 'xss')
    print(f"是否防御: {should_defend}, 原因: {reason}")

    # 查看模拟日志
    sim_log = memory_sim.get_simulation_log(limit=10)
    print(f"模拟日志条目数: {sim_log.get('total', 0)}")
    if sim_log.get('logs'):
        print(f"最新日志: {sim_log['logs'][-1]['action']}")

    # ========== 示例3: 测试模式 ==========
    print("\n【示例3：测试模式 (Test Mode)】")
    print("-" * 60)
    memory_test = AttackMemorySystem(
        test_mode=True,
        test_whitelist_ips=['192.168.1.0/24', '10.0.0.1'],
        max_test_clients=5
    )

    # 白名单IP - 应该防御
    should_defend, reason = memory_test.should_defend_against('192.168.1.100', 'port_scan')
    print(f"白名单IP (192.168.1.100) - 是否防御: {should_defend}, 原因: {reason}")

    # 非白名单IP - 不应该防御
    should_defend, reason = memory_test.should_defend_against('8.8.8.8', 'port_scan')
    print(f"非白名单IP (8.8.8.8) - 是否防御: {should_defend}, 原因: {reason}")

    # ========== 通用功能测试 ==========
    print("\n【通用功能测试】")
    print("-" * 60)

    # 使用正式模式进行功能测试
    memory = AttackMemorySystem()

    # 学习多个攻击
    memory.learn_attack(
        src_ip='1.2.3.4',
        attack_type='sql_injection',
        signatures=['UNION SELECT', 'OR 1=1'],
        packet_size=512,
        success=False,
        port=80
    )

    memory.learn_attack(
        src_ip='1.2.3.4',
        attack_type='sql_injection',
        signatures=['UNION SELECT', 'OR 1=1'],
        packet_size=520,
        success=False,
        port=80
    )

    # 识别攻击
    print("\n识别攻击...")
    pattern = memory.recognize_attack(['UNION SELECT', 'OR 1=1'])
    if pattern:
        print(f"✓ 识别成功: {pattern.attack_type}")
        print(f"  出现次数: {pattern.occurrence_count}")
        print(f"  严重性: {pattern.severity}/10")

    # 检查已知攻击者
    print("\n检查攻击者...")
    is_known, profile = memory.is_known_attacker('1.2.3.4')
    if is_known:
        print(f"✓ 已知攻击者: {profile.ip}")
        print(f"  威胁分: {profile.threat_score:.1f}/100")
        print(f"  攻击次数: {profile.total_attacks}")
        print(f"  复杂度: {profile.sophistication_level}/5")

    # 预测下一步攻击
    print("\n预测攻击...")
    prediction = memory.predict_next_attack('1.2.3.4')
    if prediction:
        print(f"✓ 预测类型: {prediction['predicted_type']}")
        print(f"  置信度: {prediction['confidence']}%")
        print(f"  可能端口: {prediction['predicted_ports']}")

    # 获取统计信息
    print("\n统计信息...")
    stats = memory.get_stats()
    print(f"✓ 运行模式: {stats['mode']}")
    print(f"  已知模式: {stats['total_patterns']}")
    print(f"  已知攻击者: {stats['total_attackers']}")
    print(f"  记忆的攻击: {stats['total_attacks_remembered']}")
    print(f"  平均威胁分: {stats['average_threat_score']:.1f}")

    # 保存记忆
    memory.save_memory()
    print("\n✓ 记忆已保存")

    print("\n" + "=" * 60)
    print("演示完成！")
