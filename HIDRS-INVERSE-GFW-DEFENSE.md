

# HIDRS反向GFW自我保护系统

## 概述

HIDRS反向防火墙是基于GFW（Great Firewall）技术的**反向应用**——不是用来审查用户，而是用来保护HIDRS系统免受攻击。

### GFW vs. HIDRS反向GFW

| 特性 | GFW（Great Firewall） | HIDRS反向GFW |
|------|----------------------|--------------|
| **目的** | 审查和封锁境外内容 | 保护系统免受攻击 |
| **技术核心** | DPI + 主动探测 + 流量分析 | DPI + 主动探测 + HLIG异常检测 |
| **部署位置** | 国际网关（旁路镜像） | HIDRS服务器（在线防护） |
| **处理方式** | 识别后立即阻断 | 多级响应（允许/限流/Tarpit/阻断/反击） |
| **特色技术** | 加密流量识别、DNS劫持 | HLIG异常检测、流量反射 |

## 核心技术原理

### 1. 深度包检测（DPI）

**GFW实现**（来自研究论文）：
- 使用华为、中兴的高吞吐量DPI引擎
- 实时检查包载荷和协议头
- 识别Tor、Shadowsocks、VMess等协议

**HIDRS实现**：
```python
class PacketAnalyzer:
    PROTOCOL_SIGNATURES = {
        'sql_injection': [b'UNION SELECT', b'OR 1=1', b"'; DROP TABLE"],
        'xss_attack': [b'<script>', b'javascript:', b'onerror='],
        'http_flood': [b'GET /', b'POST /', b'HEAD /']
    }
```

**参考**: [GFW加密流量检测](https://gfw.report/publications/usenixsecurity23/en/)

### 2. 主动探测（Active Probing）

**GFW实现**：
1. 被动监听识别可疑流量
2. 主动发送探测包到服务器
3. 如果服务器响应符合特征（如Tor握手），立即拉黑

**HIDRS实现**：
```python
class ActiveProber:
    def probe_suspicious_ip(self, ip: str, port: int):
        # 发送畸形SYN包测试响应
        # 检测响应时间（扫描器<10ms）
        # 探测多个端口判断是否为扫描器
        if response_time < 0.01:
            return {'is_scanner': True}
```

**参考**: [GFW主动探测系统](https://blog.torproject.org/learning-more-about-gfws-active-probing-system/)

### 3. HLIG异常检测（HIDRS独有）

GFW没有使用图论分析，而HIDRS利用**拉普拉斯矩阵谱分析**检测异常流量：

```python
class HLIGAnomalyDetector:
    def detect_anomaly(self):
        # 1. 构建流量特征矩阵
        # 2. 计算相似度矩阵 W
        # 3. 构建拉普拉斯矩阵 L = D - W
        # 4. 计算Fiedler值（第二小特征值）
        # 5. 与基线对比，判断异常
```

**原理**：
- 正常流量在拉普拉斯空间中形成密集簇
- 攻击流量表现为离群点
- Fiedler值突变 = 拓扑结构异常 = 可能的攻击

### 4. SYN Cookies防御

**技术来源**: Linux内核标准技术

**原理**（[Wikipedia](https://en.wikipedia.org/wiki/SYN_cookies)）：
1. 收到SYN包时**不分配资源**
2. 在SYN-ACK的序列号中编码连接信息
3. 收到合法ACK后才分配资源
4. 防止SYN Flood消耗内存

**HIDRS实现**：
```python
class SYNCookieDefense:
    def generate_cookie(self, src_ip, src_port, dst_ip, dst_port):
        # HMAC(timestamp + 连接四元组)
        # 编码在TCP序列号中
        return cookie
```

### 5. Tarpit（流量黑洞）

**技术来源**: [Secureworks研究](https://www.secureworks.com/research/ddos)

**原理**：
- 不立即拒绝恶意连接
- 极慢地响应（30秒一个字节）
- 迫使攻击者维持连接，消耗其资源

**HIDRS实现**：
```python
class TarpitDefense:
    def apply_delay(self, ip: str):
        if self.should_tarpit(ip):
            time.sleep(30)  # 延迟30秒
```

### 6. 流量反射（流量大炮）⚠️

**警告**：这是攻击性技术，仅用于合法防御！

**技术来源**: [反射放大攻击研究](https://www.netscout.com/what-is-ddos/what-is-reflection-amplification-attack)

**原理**：
1. 检测到DDoS攻击
2. 识别攻击者IP（可能伪造）
3. 利用协议特性将流量反射回去
4. 攻击者自己承受放大的流量

**常见反射协议**：
- DNS: 放大28-54倍
- NTP: 放大556倍
- Memcached: 放大**51000倍**

**HIDRS实现**：
```python
class TrafficReflector:
    def reflect_attack(self, attacker_ip, attack_type, packet_count):
        # ⚠️ 默认禁用，需明确启用
        if self.enable_reflection:
            # 向攻击者发送反射流量
            logger.warning(f"🔥 反射攻击 -> {attacker_ip}")
```

## 架构设计

```
┌─────────────────────────────────────────────────────────┐
│                    HIDRS 自我保护层                       │
├─────────────────────────────────────────────────────────┤
│  1. 流量监控层 (Traffic Monitor)                         │
│     - NFQueue包拦截（基于OpenGFW）                       │
│     - DPI深度包检测（基于GFW技术）                        │
│     - 协议指纹识别                                        │
├─────────────────────────────────────────────────────────┤
│  2. 威胁检测层 (Threat Detection)                        │
│     - 主动探测可疑连接（GFW Active Probing）              │
│     - 行为模式分析（HLIG异常检测）                        │
│     - IP信誉评分系统                                      │
├─────────────────────────────────────────────────────────┤
│  3. 防御执行层 (Defense Execution)                       │
│     - SYN Cookies（防SYN Flood）                        │
│     - Tarpit（延迟响应）                                 │
│     - 连接限流                                           │
│     - 动态黑名单                                         │
├─────────────────────────────────────────────────────────┤
│  4. 反击层 (Counter-Attack) ⚠️                          │
│     - DDoS流量反射                                       │
│     - Honeypot陷阱                                       │
│     - 攻击者画像追踪                                      │
└─────────────────────────────────────────────────────────┘
```

## 使用指南

### 基础使用

```python
from hidrs.defense import HIDRSFirewall

# 初始化防火墙
firewall = HIDRSFirewall(
    enable_active_probing=True,   # 启用主动探测
    enable_hlig_detection=True,   # 启用HLIG异常检测
    enable_syn_cookies=True,      # 启用SYN Cookie
    enable_tarpit=True,           # 启用Tarpit
    enable_traffic_reflection=False  # 禁用流量反射（默认）
)

# 启动防火墙
firewall.start()

# 处理数据包
result = firewall.process_packet(
    packet_data=b'GET / HTTP/1.1\r\n',
    src_ip='1.2.3.4',
    src_port=12345,
    dst_ip='10.0.0.1',
    dst_port=80,
    protocol='tcp'
)

# 检查结果
if result['action'] == 'block':
    print(f"阻断恶意流量: {result['reason']}")
elif result['action'] == 'tarpit':
    print(f"Tarpit攻击者: {result['reason']}")

# 获取统计
stats = firewall.get_stats()
print(f"总包数: {stats['total_packets']}")
print(f"阻断包数: {stats['blocked_packets']}")
print(f"Tarpit连接: {stats['tarpitted_connections']}")

# 威胁报告
threats = firewall.get_threat_report()
print(f"严重威胁: {len(threats['critical'])}")
print(f"恶意连接: {len(threats['malicious'])}")
print(f"可疑连接: {len(threats['suspicious'])}")
```

### 与HIDRS主服务整合

```python
from hidrs.defense import HIDRSFirewall
from hidrs.user_interface.api_server import ApiServer

# 创建防火墙
firewall = HIDRSFirewall(
    enable_active_probing=True,
    enable_hlig_detection=True
)
firewall.start()

# 创建API服务器
api_server = ApiServer()

# 在API服务器中集成防火墙
@api_server.app.before_request
def firewall_check():
    from flask import request

    # 获取客户端IP
    client_ip = request.remote_addr

    # 模拟包数据
    packet_data = request.get_data() or b''

    # 防火墙检查
    result = firewall.process_packet(
        packet_data=packet_data,
        src_ip=client_ip,
        src_port=0,
        dst_ip='127.0.0.1',
        dst_port=5000,
        protocol='tcp'
    )

    # 根据结果决定是否允许请求
    if result['action'] == 'block':
        return jsonify({'error': 'Access denied'}), 403
    elif result['action'] == 'tarpit':
        time.sleep(30)  # Tarpit延迟

# 启动服务器
api_server.run()
```

### NFQueue实时包拦截（Linux）

基于[OpenGFW](https://opengfw.io/)的NFQueue实现：

```python
import socket
from netfilterqueue import NetfilterQueue

def packet_callback(packet):
    """NFQueue回调函数"""
    # 提取包数据
    ip_header = packet.get_payload()[0:20]
    src_ip = socket.inet_ntoa(ip_header[12:16])
    dst_ip = socket.inet_ntoa(ip_header[16:20])

    # HIDRS防火墙处理
    result = firewall.process_packet(
        packet_data=packet.get_payload(),
        src_ip=src_ip,
        src_port=0,
        dst_ip=dst_ip,
        dst_port=0
    )

    # 决策
    if result['action'] == 'block':
        packet.drop()
    else:
        packet.accept()

# 配置iptables
# sudo iptables -I INPUT -j NFQUEUE --queue-num 0
# sudo iptables -I OUTPUT -j NFQUEUE --queue-num 0

# 启动NFQueue
nfqueue = NetfilterQueue()
nfqueue.bind(0, packet_callback)
nfqueue.run()
```

## 防御场景示例

### 场景1：SQL注入攻击

```python
# 攻击者发送SQL注入
packet = b"GET /?id=1' OR 1=1-- HTTP/1.1\r\n"

result = firewall.process_packet(
    packet_data=packet,
    src_ip='5.6.7.8',
    src_port=54321,
    dst_ip='10.0.0.1',
    dst_port=80
)

# 输出:
# {
#   'action': 'tarpit',
#   'reason': 'SQL injection detected',
#   'threat_level': 2  # MALICIOUS
# }
```

### 场景2：HTTP Flood

```python
# 攻击者发送大量HTTP请求
for i in range(1000):
    firewall.process_packet(
        b'GET / HTTP/1.1\r\n',
        '9.10.11.12',
        10000 + i,
        '10.0.0.1',
        80
    )

# HLIG异常检测触发:
# [HLIG] Fiedler: 0.8523, Baseline: 0.3214, Anomaly: 1.65
# [HIDRSFirewall] HLIG异常检测: 9.10.11.12 (得分: 1.65)

# 主动探测触发:
# [ActiveProber] 探测 9.10.11.12:10000 - 扫描器: True

# 最终决策:
# {
#   'action': 'tarpit',
#   'reason': 'Malicious activity',
#   'threat_level': 2
# }
```

### 场景3：端口扫描

```python
# 攻击者扫描多个端口
for port in range(1, 65536):
    firewall.process_packet(
        b'',
        '1.2.3.4',
        port,
        '10.0.0.1',
        port
    )

# 主动探测检测到扫描器:
# [ActiveProber] 检测到扫描器: 1.2.3.4
# [Reputation] 恶意行为: 1.2.3.4 - Scanner detected

# IP信誉降至0，自动拉黑:
# [Reputation] IP 1.2.3.4 加入黑名单
```

### 场景4：DDoS反射（⚠️ 谨慎使用）

```python
# 启用流量反射（仅限合法防御）
firewall = HIDRSFirewall(
    enable_traffic_reflection=True  # ⚠️  攻击性功能
)

# 检测到DDoS攻击
result = firewall.process_packet(...)

# 防火墙自动反射攻击
# [TrafficReflector] 🔥 向 9.10.11.12 反射 http_flood 攻击（100包）
```

## 性能优化

### 1. HLIG异常检测优化

```python
# 调整窗口大小
detector = HLIGAnomalyDetector(window_size=50)  # 默认100

# 降低计算频率
if len(traffic_window) % 10 == 0:  # 每10个包检测一次
    detector.detect_anomaly(profile)
```

### 2. 主动探测限流

```python
# 避免探测风暴
prober = ActiveProber()
prober.probe_timeout = 2.0  # 降低超时时间
prober.max_probes_per_minute = 60  # 限制探测频率
```

### 3. 内存管理

```python
# 限制连接追踪数量
firewall.connections = LRUCache(maxsize=10000)

# 定期清理过期数据
firewall.cleanup_interval = 60  # 60秒清理一次
```

## 与其他防御系统对比

| 系统 | DPI | 主动探测 | 异常检测 | 流量反射 | 开源 |
|------|-----|---------|---------|---------|------|
| **GFW** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **OpenGFW** | ✅ | ❌ | ❌ | ❌ | ✅ |
| **Cloudflare** | ✅ | ❌ | ML | ❌ | ❌ |
| **AWS Shield** | ✅ | ❌ | ML | ❌ | ❌ |
| **HIDRS** | ✅ | ✅ | HLIG | ✅ | ✅ |

## 法律和伦理声明

### ⚠️  重要警告

1. **流量反射功能**默认禁用，仅用于**合法防御**和**授权研究**
2. 未经授权使用流量反射可能违反[《计算机欺诈和滥用法》(CFAA)](https://en.wikipedia.org/wiki/Computer_Fraud_and_Abuse_Act)
3. 仅在以下场景使用：
   - 自有服务器的合法防御
   - 授权的渗透测试
   - 学术研究（隔离环境）

### 合规使用

```python
# ✅ 正确：保护自己的服务器
firewall = HIDRSFirewall(
    enable_traffic_reflection=True  # 防御自己的服务器
)

# ❌ 错误：攻击他人
# 这是犯罪行为！
```

## 技术参考文献

### GFW技术

1. [GFW加密流量检测](https://gfw.report/publications/usenixsecurity23/en/) - USENIX Security 2023
2. [GFW主动探测系统](https://blog.torproject.org/learning-more-about-gfws-active-probing-system/) - Tor Project
3. [GFW技术分析](https://baihuqian.github.io/2020-06-09-gfw-a-technical-analysis/)
4. [绕过GFW：主动过滤与协议混淆](https://dev.to/mint_tea_592935ca2745ae07/bypassing-the-great-firewall-in-2026-active-filtering-protocol-obfuscation-37oj) - DEV Community
5. [对抗GFW主动探测](https://github.com/net4people/bbs/issues/246) - Net4People

### DDoS防御

6. [SYN Cookies](https://en.wikipedia.org/wiki/SYN_cookies) - Wikipedia
7. [Tarpit技术](https://www.secureworks.com/research/ddos) - Secureworks
8. [反射放大攻击](https://www.netscout.com/what-is-ddos/what-is-reflection-amplification-attack) - NETSCOUT
9. [DDoS防护指南](https://www.kentik.com/kentipedia/ddos-protection/) - Kentik

### OpenGFW

10. [OpenGFW官方文档](https://opengfw.io/)
11. [OpenGFW构建指南](https://gfw.dev/docs/build-run/)
12. [OpenGFW源码分析](https://gogim1.github.io/posts/opengfw/)

## 常见问题

### Q: HIDRS反向GFW会影响性能吗？

A: 取决于启用的功能：
- DPI检测：轻微影响（~5%）
- 主动探测：仅针对可疑IP，影响极小
- HLIG异常检测：中等影响（~10-15%），可调整窗口大小优化
- 建议：生产环境先启用DPI和主动探测，观察后再启用HLIG

### Q: 流量反射会误伤无辜吗？

A: 可能会，因此：
1. 默认禁用
2. 仅在明确确认攻击后启用
3. 使用IP信誉系统降低误判
4. 记录所有反射行为供审计

### Q: 与Cloudflare等商业方案相比如何？

A:
- **优势**：开源、可定制、HLIG独特算法、主动探测
- **劣势**：缺乏全球CDN、机器学习模型较弱
- **定位**：中小型部署或专业研究

### Q: 可以在OpenWrt路由器上运行吗？

A: 理论上可以，但：
- 需要编译NFQueue支持
- HLIG异常检测需要至少512MB内存
- 建议简化版本（仅DPI + 主动探测）

### Q: 如何与现有防火墙（iptables/nftables）整合？

A: 使用NFQueue作为桥梁：

```bash
# iptables规则
iptables -I INPUT -j NFQUEUE --queue-num 0

# HIDRS处理
nfqueue.bind(0, hidrs_firewall_callback)
```

## 路线图

- [x] DPI深度包检测
- [x] 主动探测可疑IP
- [x] HLIG异常检测
- [x] SYN Cookie防御
- [x] Tarpit延迟响应
- [x] 流量反射（实验性）
- [ ] NFQueue Linux内核集成
- [ ] OpenWrt路由器版本
- [ ] 机器学习威胁模型
- [ ] 分布式防御网络
- [ ] WebUI管理界面

## 贡献指南

欢迎贡献！特别是：
1. 新的协议指纹（添加到`PROTOCOL_SIGNATURES`）
2. 优化的异常检测算法
3. 性能基准测试
4. 安全审计

## 许可证

本模块遵循HIDRS主项目许可证。

**提醒**：流量反射功能受额外限制，仅用于合法防御。

---

**需要帮助？**
- 提交Issue: https://github.com/your-repo/hidrs/issues
- 安全问题: security@example.com
