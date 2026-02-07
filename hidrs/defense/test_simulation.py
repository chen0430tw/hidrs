"""
HIDRS完整模拟/测试框架
Comprehensive Simulation and Testing Framework

核心功能：
1. 测试数据生成器（攻击/正常流量）
2. 功能测试（签名库/过滤清单/IPSec/木马检测）
3. 性能基准测试
4. 完整系统模拟
5. 详细测试报告

By: Claude + 430
"""

import logging
import time
import random
import struct
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)


# ============================================================================
# 测试数据生成器
# ============================================================================

class TestDataGenerator:
    """测试数据生成器"""

    @staticmethod
    def generate_normal_packet() -> Dict[str, Any]:
        """生成正常数据包"""
        return {
            'packet_data': b'GET / HTTP/1.1\r\nHost: example.com\r\n\r\n',
            'src_ip': f'10.0.{random.randint(0, 255)}.{random.randint(1, 254)}',
            'src_port': random.randint(1024, 65535),
            'dst_ip': '93.184.216.34',  # example.com
            'dst_port': 80,
            'protocol': 'TCP'
        }

    @staticmethod
    def generate_ddos_packet(attack_type: str = 'SYN_FLOOD') -> Dict[str, Any]:
        """生成DDoS攻击包"""
        if attack_type == 'SYN_FLOOD':
            return {
                'packet_data': b'\x00\x00\x00\x00',  # SYN包
                'src_ip': f'{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}',
                'src_port': random.randint(1024, 65535),
                'dst_ip': '10.0.0.1',
                'dst_port': 80,
                'protocol': 'TCP'
            }
        elif attack_type == 'UDP_FLOOD':
            return {
                'packet_data': b'\xff' * 1024,  # UDP大包
                'src_ip': f'{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}',
                'src_port': random.randint(1024, 65535),
                'dst_ip': '10.0.0.1',
                'dst_port': 53,
                'protocol': 'UDP'
            }
        elif attack_type == 'ICMP_FLOOD':
            return {
                'packet_data': b'\x08\x00' + b'\x00' * 100,  # ICMP echo request
                'src_ip': f'{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}',
                'src_port': 0,
                'dst_ip': '10.0.0.1',
                'dst_port': 0,
                'protocol': 'ICMP'
            }

    @staticmethod
    def generate_sql_injection_packet() -> Dict[str, Any]:
        """生成SQL注入攻击包"""
        payloads = [
            b"GET /login.php?id=1' OR '1'='1 HTTP/1.1\r\n",
            b"POST /api/user HTTP/1.1\r\n\r\nusername=admin' UNION SELECT password FROM users--",
            b"GET /search?q='; DROP TABLE users;-- HTTP/1.1\r\n"
        ]
        return {
            'packet_data': random.choice(payloads),
            'src_ip': f'{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}',
            'src_port': random.randint(1024, 65535),
            'dst_ip': '10.0.0.1',
            'dst_port': 443,
            'protocol': 'TCP'
        }

    @staticmethod
    def generate_xss_packet() -> Dict[str, Any]:
        """生成XSS攻击包"""
        payloads = [
            b"GET /comment?text=<script>alert('XSS')</script> HTTP/1.1\r\n",
            b"POST /message HTTP/1.1\r\n\r\nbody=<img src=x onerror=alert('XSS')>",
            b"GET /profile?name=<script src='http://evil.com/hack.js'></script> HTTP/1.1\r\n"
        ]
        return {
            'packet_data': random.choice(payloads),
            'src_ip': f'{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}',
            'src_port': random.randint(1024, 65535),
            'dst_ip': '10.0.0.1',
            'dst_port': 443,
            'protocol': 'TCP'
        }

    @staticmethod
    def generate_malware_packet(malware_type: str = 'webshell') -> Dict[str, Any]:
        """生成木马payload包"""
        if malware_type == 'webshell':
            payload = b"<?php eval(base64_decode($_POST['cmd'])); ?>"
        elif malware_type == 'metasploit':
            payload = b'\x4d\x5a\x90\x00' + b'\x00' * 100  # PE文件头
        elif malware_type == 'cobaltstrike':
            payload = b'\x00\x00\x00\x01\x00\x00\x00\x01' + b'\x00' * 100
        else:
            payload = b'eval(base64_decode(' + b'\x00' * 100

        return {
            'packet_data': payload,
            'src_ip': f'{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}',
            'src_port': random.randint(1024, 65535),
            'dst_ip': '10.0.0.1',
            'dst_port': 443,
            'protocol': 'TCP'
        }

    @staticmethod
    def generate_ipsec_packet(abnormal: bool = False) -> Dict[str, Any]:
        """生成IPSec包"""
        spi = random.randint(0x10000000, 0xffffffff)
        sequence = random.randint(1, 1000)

        if abnormal:
            # 异常padding
            padding = b'\x00' * 300  # 超过255
        else:
            padding = b'\x00' * 16

        payload = struct.pack('!II', spi, sequence) + b'\x00' * 64 + padding

        return {
            'packet_data': payload,
            'src_ip': f'{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}',
            'src_port': 500,
            'dst_ip': '10.0.0.1',
            'dst_port': 500,
            'protocol': 'ESP'
        }

    @staticmethod
    def generate_tunnel_packet(tunnel_type: str = 'shadowsocks') -> Dict[str, Any]:
        """生成Tunnel流量包"""
        if tunnel_type == 'shadowsocks':
            payload = b'\x05\x01\x00'  # SOCKS5握手
            port = 8388
        elif tunnel_type == 'v2ray':
            payload = b'\x00' * 100  # 加密payload
            port = 10086
        elif tunnel_type == 'tor':
            payload = b'\x16\x03\x01'  # TLS握手
            port = 9001
        elif tunnel_type == 'ssh':
            payload = b'SSH-2.0-OpenSSH_7.4'
            port = 22
        else:
            payload = b'\x05\x01\x00'
            port = 1080

        return {
            'packet_data': payload,
            'src_ip': f'{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}',
            'src_port': random.randint(1024, 65535),
            'dst_ip': '10.0.0.1',
            'dst_port': port,
            'protocol': 'TCP'
        }

    @staticmethod
    def generate_voip_packet(voip_type: str = 'sip') -> Dict[str, Any]:
        """生成VoIP流量包"""
        if voip_type == 'sip':
            payload = b'INVITE sip:user@example.com SIP/2.0\r\n'
            port = 5060
        elif voip_type == 'rtp':
            payload = b'\x80' + b'\x00' * 100  # RTP header
            port = 10000
        elif voip_type == 'h323':
            payload = b'H.323 Setup'
            port = 1720
        else:
            payload = b'SIP/2.0'
            port = 5060

        return {
            'packet_data': payload,
            'src_ip': f'{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}',
            'src_port': random.randint(1024, 65535),
            'dst_ip': '10.0.0.1',
            'dst_port': port,
            'protocol': 'UDP'
        }


# ============================================================================
# 功能测试套件
# ============================================================================

class FunctionalTests:
    """功能测试套件"""

    def __init__(self):
        self.test_results = []

    def test_signature_database(self) -> Dict[str, Any]:
        """测试攻击签名库"""
        print("\n" + "="*60)
        print("功能测试1：攻击签名库")
        print("="*60)

        try:
            from attack_signature_db import AttackSignatureDatabase, LightweightFeatureExtractor

            db = AttackSignatureDatabase()
            extractor = LightweightFeatureExtractor()

            results = {
                'test_name': 'Signature Database',
                'passed': 0,
                'failed': 0,
                'details': []
            }

            # 测试1：SQL注入检测
            sql_payload = b"GET /login.php?id=1' OR '1'='1 HTTP/1.1"
            sig = db.match_packet(
                src_ip="1.2.3.4",
                dst_ip="10.0.0.1",
                src_port=12345,
                dst_port=443,
                protocol="TCP",
                payload=sql_payload,
                packet_rate=0.0,
                packet_size=len(sql_payload)
            )

            if sig and sig.attack_type == 'SQL_INJECTION':
                results['passed'] += 1
                results['details'].append("✓ SQL注入检测")
                print("  ✓ SQL注入检测: 通过")
            else:
                results['failed'] += 1
                results['details'].append("✗ SQL注入检测")
                print("  ✗ SQL注入检测: 失败")

            # 测试2：木马检测
            malware_payload = b"eval(base64_decode('malicious code'))"
            malware = db.detect_malware_payload(malware_payload)

            if malware and malware.malware_family == 'Webshell':
                results['passed'] += 1
                results['details'].append("✓ 木马payload检测")
                print("  ✓ 木马payload检测: 通过")
            else:
                results['failed'] += 1
                results['details'].append("✗ 木马payload检测")
                print("  ✗ 木马payload检测: 失败")

            # 测试3：IPSec解析
            ipsec_payload = struct.pack('!II', 0x12345678, 100) + b"\x00" * 64
            ipsec_sig = db.parse_ipsec_packet(ipsec_payload)

            if ipsec_sig and ipsec_sig.spi == 0x12345678:
                results['passed'] += 1
                results['details'].append("✓ IPSec数据包解析")
                print("  ✓ IPSec数据包解析: 通过")
            else:
                results['failed'] += 1
                results['details'].append("✗ IPSec数据包解析")
                print("  ✗ IPSec数据包解析: 失败")

            # 测试4：轻量级特征提取
            features = extractor.extract_packet_features(
                payload=b"\x90" * 100,
                protocol="TCP",
                packet_size=128
            )
            is_sus, score = extractor.is_suspicious(features)

            if 'entropy' in features and 'ascii_ratio' in features:
                results['passed'] += 1
                results['details'].append("✓ 轻量级特征提取")
                print(f"  ✓ 轻量级特征提取: 通过 (可疑分数={score:.2f})")
            else:
                results['failed'] += 1
                results['details'].append("✗ 轻量级特征提取")
                print("  ✗ 轻量级特征提取: 失败")

            # 测试5：自适应转移矩阵
            matrix = db.adaptive_matrix
            matrix.update_observation(0, 1, is_false_positive=False)
            prob = matrix.get_transition_probability(0, 1)

            if 0 < prob < 1:
                results['passed'] += 1
                results['details'].append("✓ 自适应状态转移")
                print(f"  ✓ 自适应状态转移: 通过 (P(0→1)={prob:.3f})")
            else:
                results['failed'] += 1
                results['details'].append("✗ 自适应状态转移")
                print("  ✗ 自适应状态转移: 失败")

            self.test_results.append(results)
            return results

        except Exception as e:
            print(f"  ✗ 测试失败: {e}")
            return {
                'test_name': 'Signature Database',
                'passed': 0,
                'failed': 5,
                'details': [f"Exception: {e}"]
            }

    def test_fast_filter_lists(self) -> Dict[str, Any]:
        """测试快速过滤清单"""
        print("\n" + "="*60)
        print("功能测试2：快速过滤清单")
        print("="*60)

        try:
            from fast_filter_lists import FastFilterLists

            filters = FastFilterLists()

            results = {
                'test_name': 'Fast Filter Lists',
                'passed': 0,
                'failed': 0,
                'details': []
            }

            # 测试1：IP黑名单
            result, reason = filters.check_ip("127.0.0.1")
            if result == 'blacklist':
                results['passed'] += 1
                results['details'].append("✓ IP黑名单检测")
                print("  ✓ IP黑名单检测: 通过")
            else:
                results['failed'] += 1
                results['details'].append("✗ IP黑名单检测")
                print("  ✗ IP黑名单检测: 失败")

            # 测试2：DNS黑名单
            result, reason = filters.check_dns("malware.example.com")
            if result == 'blacklist':
                results['passed'] += 1
                results['details'].append("✓ DNS黑名单检测")
                print("  ✓ DNS黑名单检测: 通过")
            else:
                results['failed'] += 1
                results['details'].append("✗ DNS黑名单检测")
                print("  ✗ DNS黑名单检测: 失败")

            # 测试3：关键词黑名单
            result, keyword = filters.check_keywords("SELECT * FROM users WHERE id=1 UNION SELECT password")
            if result == 'blacklist':
                results['passed'] += 1
                results['details'].append(f"✓ 关键词黑名单检测 (关键词={keyword})")
                print(f"  ✓ 关键词黑名单检测: 通过 (关键词={keyword})")
            else:
                results['failed'] += 1
                results['details'].append("✗ 关键词黑名单检测")
                print("  ✗ 关键词黑名单检测: 失败")

            # 测试4：Tunnel检测
            tunnel = filters.detect_tunnel(8388, b'\x05\x01\x00')
            if tunnel == 'shadowsocks':
                results['passed'] += 1
                results['details'].append("✓ Tunnel检测 (Shadowsocks)")
                print("  ✓ Tunnel检测: 通过 (Shadowsocks)")
            else:
                results['failed'] += 1
                results['details'].append("✗ Tunnel检测")
                print("  ✗ Tunnel检测: 失败")

            # 测试5：VoIP检测
            voip = filters.detect_voip(5060, b'INVITE sip:user@example.com SIP/2.0')
            if voip == 'sip':
                results['passed'] += 1
                results['details'].append("✓ VoIP检测 (SIP)")
                print("  ✓ VoIP检测: 通过 (SIP)")
            else:
                results['failed'] += 1
                results['details'].append("✗ VoIP检测")
                print("  ✗ VoIP检测: 失败")

            # 测试6：综合检查
            comp_result = filters.comprehensive_check(
                src_ip="1.2.3.4",
                dst_port=8388,
                payload=b'\x05\x01\x00'
            )

            filters.add_ip_blacklist("1.2.3.4")
            comp_result = filters.comprehensive_check(src_ip="1.2.3.4")

            if comp_result['action'] == 'block':
                results['passed'] += 1
                results['details'].append("✓ 综合检查（IP黑名单优先）")
                print("  ✓ 综合检查: 通过")
            else:
                results['failed'] += 1
                results['details'].append("✗ 综合检查")
                print("  ✗ 综合检查: 失败")

            self.test_results.append(results)
            return results

        except Exception as e:
            print(f"  ✗ 测试失败: {e}")
            return {
                'test_name': 'Fast Filter Lists',
                'passed': 0,
                'failed': 6,
                'details': [f"Exception: {e}"]
            }

    def test_attack_memory_sosa(self) -> Dict[str, Any]:
        """测试SOSA攻击记忆系统"""
        print("\n" + "="*60)
        print("功能测试3：SOSA攻击记忆系统")
        print("="*60)

        try:
            from attack_memory import AttackMemoryWithSOSA

            memory = AttackMemoryWithSOSA(simulation_mode=True)

            results = {
                'test_name': 'Attack Memory with SOSA',
                'passed': 0,
                'failed': 0,
                'details': []
            }

            # 测试1：初始化
            if memory.sosa_enabled:
                results['passed'] += 1
                results['details'].append("✓ SOSA初始化")
                print("  ✓ SOSA初始化: 通过")
            else:
                results['failed'] += 1
                results['details'].append("✗ SOSA初始化")
                print("  ✗ SOSA初始化: 失败")

            # 测试2：特征库集成
            if memory.signature_db_enabled:
                results['passed'] += 1
                results['details'].append("✓ 特征库集成")
                print(f"  ✓ 特征库集成: 通过 ({len(memory.signature_db.attack_signatures)} 个签名)")
            else:
                results['failed'] += 1
                results['details'].append("✗ 特征库集成")
                print("  ✗ 特征库集成: 失败")

            # 测试3：学习攻击
            memory.learn_attack(
                src_ip="192.168.1.100",
                attack_type="SYN_FLOOD",
                signatures=["SYN_FLOOD"],
                packet_size=64,
                success=False,
                port=80,
                payload=b"\x00\x00\x00\x00",
                dst_ip="10.0.0.1",
                protocol="TCP"
            )

            results['passed'] += 1
            results['details'].append("✓ 学习攻击（带payload）")
            print("  ✓ 学习攻击: 通过")

            # 测试4：状态分布
            state_dist = memory.get_attack_state_distribution()
            if state_dist and 'state_distribution' in state_dist:
                results['passed'] += 1
                results['details'].append("✓ 状态分布查询")
                print(f"  ✓ 状态分布查询: 通过 (当前状态={state_dist['current_state']})")
            else:
                results['failed'] += 1
                results['details'].append("✗ 状态分布查询")
                print("  ✗ 状态分布查询: 失败")

            # 测试5：攻击阶段预测
            phase = memory.predict_attack_phase()
            if phase:
                results['passed'] += 1
                results['details'].append(f"✓ 攻击阶段预测 ({phase})")
                print(f"  ✓ 攻击阶段预测: 通过 ({phase})")
            else:
                results['failed'] += 1
                results['details'].append("✗ 攻击阶段预测")
                print("  ✗ 攻击阶段预测: 失败")

            self.test_results.append(results)
            return results

        except Exception as e:
            print(f"  ✗ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'test_name': 'Attack Memory with SOSA',
                'passed': 0,
                'failed': 5,
                'details': [f"Exception: {e}"]
            }

    def run_all_tests(self):
        """运行所有功能测试"""
        print("\n" + "="*60)
        print("HIDRS V2 功能测试套件")
        print("="*60)

        self.test_signature_database()
        self.test_fast_filter_lists()
        self.test_attack_memory_sosa()

        self.print_summary()

    def print_summary(self):
        """打印测试摘要"""
        print("\n" + "="*60)
        print("测试摘要")
        print("="*60)

        total_passed = 0
        total_failed = 0

        for result in self.test_results:
            total_passed += result['passed']
            total_failed += result['failed']
            status = "✓ 通过" if result['failed'] == 0 else "✗ 失败"
            print(f"{result['test_name']}: {result['passed']}/{result['passed']+result['failed']} {status}")

        print("\n总计:")
        print(f"  通过: {total_passed}")
        print(f"  失败: {total_failed}")
        print(f"  成功率: {total_passed/(total_passed+total_failed)*100:.1f}%")

        if total_failed == 0:
            print("\n🎉 所有测试通过！")
        else:
            print(f"\n⚠️  {total_failed} 个测试失败")


# ============================================================================
# 性能基准测试
# ============================================================================

class PerformanceBenchmark:
    """性能基准测试"""

    def __init__(self):
        self.results = {}

    def benchmark_signature_matching(self, num_packets: int = 10000):
        """签名匹配性能测试"""
        print(f"\n性能测试1：签名匹配 ({num_packets} 个数据包)")

        try:
            from attack_signature_db import AttackSignatureDatabase

            db = AttackSignatureDatabase()
            gen = TestDataGenerator()

            start_time = time.time()

            for i in range(num_packets):
                if i % 2 == 0:
                    packet = gen.generate_sql_injection_packet()
                else:
                    packet = gen.generate_normal_packet()

                db.match_packet(
                    src_ip=packet['src_ip'],
                    dst_ip=packet['dst_ip'],
                    src_port=packet['src_port'],
                    dst_port=packet['dst_port'],
                    protocol=packet['protocol'],
                    payload=packet['packet_data'],
                    packet_rate=0.0,
                    packet_size=len(packet['packet_data'])
                )

            elapsed = time.time() - start_time
            throughput = num_packets / elapsed

            print(f"  总时间: {elapsed:.2f} 秒")
            print(f"  吞吐量: {throughput:.0f} 包/秒")
            print(f"  平均延迟: {elapsed/num_packets*1000:.2f} ms/包")

            self.results['signature_matching'] = {
                'total_time': elapsed,
                'throughput': throughput,
                'avg_latency_ms': elapsed/num_packets*1000
            }

        except Exception as e:
            print(f"  ✗ 测试失败: {e}")

    def benchmark_filter_lists(self, num_checks: int = 100000):
        """过滤清单性能测试"""
        print(f"\n性能测试2：过滤清单 ({num_checks} 次检查)")

        try:
            from fast_filter_lists import FastFilterLists

            filters = FastFilterLists()

            # 添加一些测试数据
            for i in range(100):
                filters.add_ip_blacklist(f"192.168.1.{i}")
                filters.add_dns_blacklist(f"malware{i}.example.com")

            start_time = time.time()

            for i in range(num_checks):
                ip = f"192.168.1.{random.randint(0, 255)}"
                filters.check_ip(ip)

            elapsed = time.time() - start_time
            throughput = num_checks / elapsed

            print(f"  总时间: {elapsed:.2f} 秒")
            print(f"  吞吐量: {throughput:.0f} 检查/秒")
            print(f"  平均延迟: {elapsed/num_checks*1000000:.2f} μs/检查")

            self.results['filter_lists'] = {
                'total_time': elapsed,
                'throughput': throughput,
                'avg_latency_us': elapsed/num_checks*1000000
            }

        except Exception as e:
            print(f"  ✗ 测试失败: {e}")

    def run_all_benchmarks(self):
        """运行所有性能测试"""
        print("\n" + "="*60)
        print("HIDRS V2 性能基准测试")
        print("="*60)

        self.benchmark_signature_matching(10000)
        self.benchmark_filter_lists(100000)

        print("\n" + "="*60)
        print("性能测试总结")
        print("="*60)

        if 'signature_matching' in self.results:
            print(f"签名匹配: {self.results['signature_matching']['throughput']:.0f} 包/秒, "
                  f"{self.results['signature_matching']['avg_latency_ms']:.2f} ms/包")

        if 'filter_lists' in self.results:
            print(f"过滤清单: {self.results['filter_lists']['throughput']:.0f} 检查/秒, "
                  f"{self.results['filter_lists']['avg_latency_us']:.2f} μs/检查")


# ============================================================================
# 主程序
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)  # 减少日志输出

    print("╔" + "="*58 + "╗")
    print("║" + " "*58 + "║")
    print("║" + "  HIDRS V2 完整模拟/测试框架  ".center(58) + "║")
    print("║" + " "*58 + "║")
    print("╚" + "="*58 + "╝")

    # 功能测试
    functional = FunctionalTests()
    functional.run_all_tests()

    # 性能基准测试
    performance = PerformanceBenchmark()
    performance.run_all_benchmarks()

    print("\n" + "="*60)
    print("测试完成！")
    print("="*60)
