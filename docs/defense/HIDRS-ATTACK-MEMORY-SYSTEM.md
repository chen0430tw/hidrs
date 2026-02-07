# HIDRS攻击记忆系统

## 概述

HIDRS攻击记忆系统是一个智能防御系统，类似人类免疫系统，能够记住攻击模式并不断学习。当系统第一次遇到攻击时，会记录其特征；再次遇到时，能够立即识别并免疫；攻击变异时，会更新记忆。

## 核心特性

### 1. 攻击模式记忆
- **模式识别**：自动识别和学习攻击特征
- **频率追踪**：记录每种攻击模式出现的次数
- **时间分析**：分析攻击的时间偏好（24小时分布）
- **源追踪**：追踪使用相同模式的所有攻击源

### 2. 攻击者画像
- **行为分析**：建立攻击者的行为模型
- **威胁评分**：0-100分的威胁等级评估
- **复杂度评估**：1-5级的攻击复杂度
- **持续性监控**：追踪攻击者的活跃时间跨度

### 3. 智能预测
- **下一步攻击预测**：基于历史数据预测攻击者的下一步行动
- **目标端口预测**：预测可能被攻击的端口
- **时间预测**：预测攻击可能发生的时段

### 4. 三种运行模式

#### 正式模式 (Live Mode)
- 完整的防御功能
- 实际阻断/Tarpit恶意流量
- 实时学习攻击模式
- 适用于生产环境

#### 模拟模式 (Simulation Mode)
- **只记录日志，不实际执行防御动作**
- 学习攻击模式但不阻断
- 用于测试防火墙配置
- 查看防火墙在实际环境中会做什么
- 适用于：
  - 新环境测试
  - 规则验证
  - 培训演示

#### 测试模式 (Test Mode)
- **小范围实际测试**
- 仅对白名单IP执行防御
- 限制最大客户端数
- 用于渐进式部署
- 适用于：
  - 分阶段上线
  - A/B测试
  - 风险控制

## 技术架构

### 数据结构

#### AttackPattern（攻击模式）
```python
@dataclass
class AttackPattern:
    pattern_id: str              # 模式ID（攻击类型_哈希）
    attack_type: str             # 攻击类型
    signatures: List[str]        # 特征签名列表
    first_seen: datetime         # 首次出现时间
    last_seen: datetime          # 最后出现时间
    occurrence_count: int        # 出现次数
    source_ips: List[str]        # 来源IP列表
    target_ports: List[int]      # 目标端口列表
    success_rate: float          # 攻击成功率
    severity: int                # 严重性（1-10）
    avg_packet_size: float       # 平均包大小
    avg_request_rate: float      # 平均请求率
    time_pattern: List[int]      # 24小时时间分布
```

#### AttackerProfile（攻击者画像）
```python
@dataclass
class AttackerProfile:
    ip: str                          # 攻击者IP
    first_attack: datetime           # 首次攻击时间
    last_attack: datetime            # 最后攻击时间
    total_attacks: int               # 总攻击次数
    attack_types: List[str]          # 使用的攻击类型
    patterns_used: List[str]         # 使用的模式ID
    success_rate: float              # 成功率
    threat_score: float              # 威胁分（0-100）
    preferred_ports: List[int]       # 偏好端口
    attack_time_preference: List[int] # 攻击时间偏好
    sophistication_level: int        # 复杂度（1-5）
```

### 核心算法

#### 1. 模式识别算法
```python
def recognize_attack(signatures: List[str]) -> Optional[AttackPattern]:
    """
    基于Jaccard相似度的模式识别

    相似度 = |A ∩ B| / max(|A|, |B|)

    当相似度 > 0.5 时认为匹配成功
    """
```

#### 2. 威胁评分算法
```python
def calculate_threat_score(profile: AttackerProfile) -> float:
    """
    威胁分 = 攻击频率分(30) + 成功率分(20) + 多样性分(10n)
           + 复杂度分(5n) + 持续性分(15)

    最高100分
    """
```

#### 3. 模式ID生成
```python
pattern_id = f"{attack_type}_{MD5(signatures)[:16]}"
```

## 使用指南

### 1. 基础使用

#### 初始化（正式模式）
```python
from hidrs.defense.attack_memory import AttackMemorySystem

# 正式模式
memory = AttackMemorySystem()
```

#### 学习攻击模式
```python
memory.learn_attack(
    src_ip='1.2.3.4',
    attack_type='sql_injection',
    signatures=['UNION SELECT', 'OR 1=1'],
    packet_size=512,
    success=False,
    port=80
)
```

#### 识别攻击
```python
pattern = memory.recognize_attack(['UNION SELECT', 'OR 1=1'])
if pattern:
    print(f"识别到已知攻击: {pattern.attack_type}")
    print(f"出现过 {pattern.occurrence_count} 次")
```

#### 检查已知攻击者
```python
is_known, profile = memory.is_known_attacker('1.2.3.4')
if is_known:
    print(f"威胁分: {profile.threat_score:.1f}/100")
    print(f"复杂度: {profile.sophistication_level}/5")
```

#### 预测下一步攻击
```python
prediction = memory.predict_next_attack('1.2.3.4')
if prediction:
    print(f"预测类型: {prediction['predicted_type']}")
    print(f"置信度: {prediction['confidence']}%")
    print(f"可能端口: {prediction['predicted_ports']}")
```

### 2. 模拟模式使用

```python
# 启用模拟模式
memory = AttackMemorySystem(simulation_mode=True)

# 学习攻击（会记录但不实际防御）
memory.learn_attack(
    src_ip='5.6.7.8',
    attack_type='xss',
    signatures=['<script>', 'javascript:'],
    packet_size=256,
    success=False,
    port=443
)

# 检查是否应该防御
should_defend, reason = memory.should_defend_against('5.6.7.8', 'xss')
print(f"是否防御: {should_defend}, 原因: {reason}")
# 输出: 是否防御: False, 原因: simulation_mode

# 查看模拟日志
sim_log = memory.get_simulation_log(limit=10)
print(f"模拟日志条目数: {sim_log['total']}")
for log in sim_log['logs']:
    print(f"  {log['action']}: {log['timestamp']}")
```

### 3. 测试模式使用

```python
# 启用测试模式
memory = AttackMemorySystem(
    test_mode=True,
    test_whitelist_ips=['192.168.1.0/24', '10.0.0.1'],
    max_test_clients=5
)

# 白名单IP - 会防御
should_defend, reason = memory.should_defend_against('192.168.1.100', 'port_scan')
print(f"白名单IP: {should_defend}, 原因: {reason}")
# 输出: True, test_mode_allowed

# 非白名单IP - 不会防御
should_defend, reason = memory.should_defend_against('8.8.8.8', 'port_scan')
print(f"非白名单IP: {should_defend}, 原因: {reason}")
# 输出: False, not_whitelisted
```

### 4. 与HIDRSFirewall集成

#### 正式模式
```python
from hidrs.defense.inverse_gfw import HIDRSFirewall

firewall = HIDRSFirewall(
    enable_attack_memory=True,
    simulation_mode=False,  # 正式模式
    test_mode=False
)

firewall.start()

# 处理数据包（会自动学习和识别攻击）
result = firewall.process_packet(
    packet_data=b"GET /?id=1' OR 1=1-- HTTP/1.1\r\n",
    src_ip='5.6.7.8',
    src_port=54321,
    dst_ip='10.0.0.1',
    dst_port=80
)

print(f"动作: {result['action']}")
print(f"防御模式: {result['defense_mode']}")
```

#### 模拟模式
```python
firewall = HIDRSFirewall(
    enable_attack_memory=True,
    simulation_mode=True  # 只记录，不实际防御
)

firewall.start()

result = firewall.process_packet(...)
# 会学习攻击模式，但不会实际阻断
print(f"动作: {result['action']}")  # 可能仍显示'block'
print(f"防御模式: {result['defense_mode']}")  # 'simulation_mode'

# 查看模拟日志
sim_log = firewall.get_simulation_log(limit=10)
```

#### 测试模式
```python
firewall = HIDRSFirewall(
    enable_attack_memory=True,
    test_mode=True,
    test_whitelist_ips=['192.168.1.0/24', '10.0.0.1'],
    max_test_clients=5
)

firewall.start()

# 白名单IP会被实际防御
result = firewall.process_packet(
    packet_data=b"malicious data",
    src_ip='192.168.1.100',  # 白名单IP
    ...
)
# 会实际阻断

# 非白名单IP不会被防御
result = firewall.process_packet(
    packet_data=b"malicious data",
    src_ip='1.2.3.4',  # 非白名单IP
    ...
)
# 不会阻断，只记录
```

## API参考

### AttackMemorySystem

#### 构造函数
```python
def __init__(
    memory_file: str = '/tmp/hidrs_attack_memory.pkl',
    simulation_mode: bool = False,
    test_mode: bool = False,
    test_whitelist_ips: List[str] = None,
    max_test_clients: int = 10
)
```

#### 主要方法

##### learn_attack()
学习攻击模式
```python
def learn_attack(
    src_ip: str,
    attack_type: str,
    signatures: List[str],
    packet_size: int,
    success: bool,
    port: int
) -> None
```

##### recognize_attack()
识别攻击模式
```python
def recognize_attack(
    signatures: List[str]
) -> Optional[AttackPattern]
```

##### is_known_attacker()
检查是否为已知攻击者
```python
def is_known_attacker(
    ip: str
) -> Tuple[bool, Optional[AttackerProfile]]
```

##### predict_next_attack()
预测下一步攻击
```python
def predict_next_attack(
    ip: str
) -> Optional[Dict[str, Any]]
```

##### should_defend_against()
判断是否应该防御（根据模式）
```python
def should_defend_against(
    ip: str,
    attack_type: str
) -> Tuple[bool, str]
```

##### get_top_threats()
获取威胁最高的攻击者
```python
def get_top_threats(
    limit: int = 10
) -> List[AttackerProfile]
```

##### get_simulation_log()
获取模拟日志（仅模拟模式）
```python
def get_simulation_log(
    limit: int = 100
) -> Dict
```

##### save_memory()
保存记忆到文件
```python
def save_memory() -> None
```

##### cleanup_old_memories()
清理旧记忆
```python
def cleanup_old_memories(
    days: int = 30
) -> None
```

### HIDRSFirewall（更新后）

#### 新增构造参数
```python
def __init__(
    ...,
    enable_attack_memory: bool = True,
    simulation_mode: bool = False,
    test_mode: bool = False,
    test_whitelist_ips: List[str] = None,
    max_test_clients: int = 10
)
```

#### 新增方法

##### get_top_threats()
```python
def get_top_threats(limit: int = 10) -> List[Dict]
```

##### predict_next_attack()
```python
def predict_next_attack(ip: str) -> Optional[Dict]
```

##### get_simulation_log()
```python
def get_simulation_log(limit: int = 100) -> Dict
```

##### get_memory_stats()
```python
def get_memory_stats() -> Dict
```

## 统计信息

### 攻击记忆统计
```python
stats = memory.get_stats()
# 返回:
{
    'mode': 'live|simulation|test',
    'simulation_mode': bool,
    'test_mode': bool,
    'test_whitelist_count': int,
    'max_test_clients': int,
    'total_patterns': int,
    'total_attackers': int,
    'total_attacks_remembered': int,
    'attack_type_distribution': dict,
    'average_threat_score': float,
    'simulation_log_count': int
}
```

### 防火墙统计（含记忆）
```python
stats = firewall.get_stats()
# 返回:
{
    'total_packets': int,
    'blocked_packets': int,
    'suspicious_packets': int,
    'tarpitted_connections': int,
    'reflected_attacks': int,
    'active_probes': int,
    'memory_recognitions': int,  # 记忆识别次数
    'active_connections': int,
    'blacklisted_ips': int,
    'whitelisted_ips': int,
    'attack_memory': {
        # 攻击记忆统计（嵌套）
        ...
    }
}
```

## 部署建议

### 1. 渐进式部署

#### 阶段1: 观察模式（1-2周）
```python
# 使用模拟模式，只观察不防御
firewall = HIDRSFirewall(
    simulation_mode=True,
    enable_attack_memory=True
)
```
- 收集真实流量数据
- 观察防火墙会如何响应
- 调整规则以减少误报

#### 阶段2: 小范围测试（1-2周）
```python
# 对少数IP进行实际防御
firewall = HIDRSFirewall(
    test_mode=True,
    test_whitelist_ips=['内部测试IP段'],
    max_test_clients=10
)
```
- 在可控范围内测试防御效果
- 验证不会影响正常业务
- 收集性能指标

#### 阶段3: 全面部署
```python
# 启用完整防御
firewall = HIDRSFirewall(
    simulation_mode=False,
    test_mode=False,
    enable_attack_memory=True
)
```
- 监控系统性能
- 定期审查威胁报告
- 调整防御策略

### 2. 配置建议

#### 生产环境
```python
firewall = HIDRSFirewall(
    enable_active_probing=True,
    enable_hlig_detection=True,
    enable_syn_cookies=True,
    enable_tarpit=True,
    enable_traffic_reflection=False,  # 谨慎启用
    enable_attack_memory=True,
    simulation_mode=False,
    test_mode=False
)
```

#### 测试环境
```python
firewall = HIDRSFirewall(
    enable_active_probing=True,
    enable_hlig_detection=True,
    enable_attack_memory=True,
    simulation_mode=True  # 安全的测试方式
)
```

#### 分阶段上线
```python
firewall = HIDRSFirewall(
    enable_attack_memory=True,
    test_mode=True,
    test_whitelist_ips=[
        '192.168.1.0/24',  # 内网段
        '10.0.0.0/8'       # 特定业务
    ],
    max_test_clients=50
)
```

## 性能优化

### 1. 记忆清理
- 默认每小时清理一次旧记忆
- 保留30天内的攻击记录
- 高威胁攻击者永久保留

### 2. 模式匹配优化
- 使用MD5哈希加速模式查找
- Jaccard相似度阈值: 0.5
- 最多匹配前100个模式

### 3. 持久化策略
- 使用pickle序列化
- 停机时自动保存
- 每小时自动备份

## 安全考虑

### 1. 模拟模式安全性
- **不会执行任何防御动作**
- 所有"阻断"都只是日志记录
- 适合在生产环境中测试新规则
- 无风险观察防火墙行为

### 2. 测试模式安全性
- 只对白名单IP执行防御
- 限制最大客户端数防止意外扩散
- 支持CIDR范围
- 非白名单IP完全不受影响

### 3. 隐私保护
- IP地址仅用于防御目的
- 记忆文件权限: 600 (仅所有者可读写)
- 定期清理旧数据
- 不记录业务数据内容

## 故障排查

### 问题1: 记忆未生效
```bash
# 检查记忆文件
ls -la /tmp/hidrs_attack_memory.pkl

# 检查统计
stats = memory.get_stats()
print(stats['total_patterns'])  # 应该 > 0
```

### 问题2: 模拟模式仍在阻断
```python
# 确认模式
stats = firewall.get_stats()
print(stats['attack_memory']['mode'])  # 应该是 'simulation'

# 检查defense_mode
result = firewall.process_packet(...)
print(result['defense_mode'])  # 应该是 'simulation_mode'
```

### 问题3: 测试模式未生效
```python
# 验证IP在白名单中
from hidrs.defense.attack_memory import AttackMemorySystem
memory = AttackMemorySystem(
    test_mode=True,
    test_whitelist_ips=['192.168.1.0/24']
)
print(memory._is_ip_whitelisted('192.168.1.100'))  # 应该是 True
```

## 最佳实践

### 1. 日志监控
```python
import logging
logging.basicConfig(level=logging.INFO)

# 关键日志标识:
# 🧠 - 记忆系统学习
# 🎬 - 模拟模式动作
# 🧪 - 测试模式动作
# 🛡️ - 正式模式防御
```

### 2. 定期审查
```python
# 每日审查Top威胁
top_threats = firewall.get_top_threats(limit=20)
for threat in top_threats:
    if threat['threat_score'] > 80:
        # 考虑加入永久黑名单
        pass
```

### 3. 内存管理
```python
# 定期清理旧记忆（释放内存）
memory.cleanup_old_memories(days=30)

# 手动保存
memory.save_memory()
```

### 4. 模式演化追踪
```python
# 追踪攻击模式演化
patterns = memory.get_pattern_evolution('sql_injection')
for pattern in patterns:
    print(f"{pattern.first_seen}: {pattern.signatures}")
```

## 示例场景

### 场景1: 新系统上线
1. **第1周**：模拟模式，收集数据
2. **第2周**：分析日志，调整规则
3. **第3周**：测试模式，10个内部IP
4. **第4周**：全面上线

### 场景2: 已有系统增强
1. 启用攻击记忆（正式模式）
2. 观察1周，学习正常流量
3. 审查Top威胁
4. 调整HLIG检测阈值

### 场景3: 紧急响应
1. 检测到新型攻击
2. 系统自动学习并记忆
3. 第二次攻击立即识别
4. 自动阻断，无需人工干预

## 总结

HIDRS攻击记忆系统提供了类似免疫系统的智能防御能力：

✅ **自动学习** - 无需手动配置规则
✅ **快速识别** - 已知攻击立即响应
✅ **智能预测** - 提前预警潜在威胁
✅ **安全测试** - 模拟/测试模式保证安全部署
✅ **持续进化** - 随着攻击变化而更新

通过合理使用三种运行模式，可以实现零风险的防火墙升级和部署。
