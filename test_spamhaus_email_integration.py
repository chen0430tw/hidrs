#!/usr/bin/env python3
"""
测试Spamhaus和邮件安全集成

测试项：
1. Spamhaus DNSBL查询
2. 邮件钓鱼检测
3. FBI伪装检测
4. 快速过滤清单综合检查
5. 防火墙集成测试
"""

import sys
import logging
sys.path.insert(0, 'hidrs/defense')

from fast_filter_lists import FastFilterLists, SpamhausChecker
from inverse_gfw import HIDRSFirewall

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_spamhaus():
    """测试Spamhaus DNSBL"""
    print("\n" + "=" * 60)
    print("测试1: Spamhaus DNSBL检查")
    print("=" * 60)

    checker = SpamhausChecker()

    # 测试已知的垃圾邮件IP（示例）
    test_ips = [
        "127.0.0.2",  # 测试返回码（应该被列入SBL）
        "8.8.8.8",    # Google DNS（应该不在黑名单）
        "1.1.1.1",    # Cloudflare DNS（应该不在黑名单）
    ]

    for ip in test_ips:
        result = checker.check_ip(ip)
        print(f"\n  IP: {ip}")
        print(f"  列入黑名单: {result.is_listed}")
        if result.is_listed:
            print(f"  清单: {', '.join(result.lists)}")
            print(f"  严重性: {result.severity}")
            print(f"  描述: {result.description}")
        else:
            print(f"  状态: {result.description}")


def test_email_phishing():
    """测试邮件钓鱼检测"""
    print("\n" + "=" * 60)
    print("测试2: 邮件钓鱼检测")
    print("=" * 60)

    filters = FastFilterLists()

    # 测试用例
    test_cases = [
        {
            'name': '伪装PayPal邮件',
            'from': 'noreply@paypal.com.fake.cn',
            'subject': 'Urgent action required - verify your account',
            'body': 'Your account has been suspended. Click here to verify.'
        },
        {
            'name': '正常邮件',
            'from': 'support@example.com',
            'subject': 'Welcome to our service',
            'body': 'Thank you for signing up.'
        },
        {
            'name': 'FBI伪装邮件',
            'from': 'agent@fbi.gov.fake.com',
            'subject': 'Legal action pending',
            'body': 'This is Special Agent John. There is a warrant for your arrest.'
        }
    ]

    for test in test_cases:
        print(f"\n  测试: {test['name']}")
        print(f"  发件人: {test['from']}")
        print(f"  主题: {test['subject']}")

        # 钓鱼检测
        is_phishing, reason = filters.check_email_phishing(
            email_from=test['from'],
            subject=test['subject'],
            body=test['body']
        )

        if is_phishing:
            print(f"  ⚠️ 钓鱼检测: {reason}")
        else:
            print(f"  ✅ 正常邮件")

        # FBI伪装检测
        is_fbi, fbi_reason = filters.detect_fbi_impersonation(
            email_from=test['from'],
            body=test['body']
        )

        if is_fbi:
            print(f"  🚨 FBI伪装: {fbi_reason}")


def test_comprehensive_check():
    """测试综合检查"""
    print("\n" + "=" * 60)
    print("测试3: 快速过滤综合检查")
    print("=" * 60)

    filters = FastFilterLists()

    # 测试用例
    test_cases = [
        {
            'name': '恶意IP',
            'src_ip': '127.0.0.1',
            'domain': 'malware.example.com',
            'payload': b'union select * from users',
        },
        {
            'name': 'Tunnel流量',
            'src_ip': '10.0.0.1',
            'dst_port': 8388,
            'payload': b'\x05\x01\x00',
        },
        {
            'name': '邮件钓鱼',
            'src_ip': '1.2.3.4',
            'email_from': 'noreply@paypal.fake.com',
            'email_subject': 'Verify your account immediately',
        }
    ]

    for test in test_cases:
        print(f"\n  测试: {test['name']}")

        result = filters.comprehensive_check(
            src_ip=test.get('src_ip', ''),
            dst_port=test.get('dst_port', 0),
            domain=test.get('domain', ''),
            payload=test.get('payload', b''),
            email_from=test.get('email_from', ''),
            email_subject=test.get('email_subject', ''),
        )

        print(f"  动作: {result['action']}")
        print(f"  原因: {result['reason']}")
        if result['matched_filters']:
            print(f"  匹配过滤器: {', '.join(result['matched_filters'])}")
        if result.get('tunnel_detected'):
            print(f"  检测到Tunnel: {result['tunnel_detected']}")
        if result.get('email_phishing'):
            print(f"  邮件钓鱼: True")


def test_firewall_integration():
    """测试防火墙集成"""
    print("\n" + "=" * 60)
    print("测试4: HIDRS防火墙集成")
    print("=" * 60)

    # 创建防火墙（测试模式）
    firewall = HIDRSFirewall(
        enable_fast_filters=True,
        simulation_mode=True,  # 模拟模式，不实际执行防御
        enable_attack_memory=False,  # 简化测试
        enable_hlig_detection=False,
        enable_active_probing=False,
        enable_syn_cookies=False,
        enable_tarpit=False
    )

    print(f"\n  快速过滤状态: {'✅ 已启用' if firewall._filter_lists_enabled else '❌ 未启用'}")
    if firewall._filter_lists_enabled and firewall.filter_lists:
        print(f"  Spamhaus状态: {'✅ 已启用' if firewall.filter_lists.spamhaus_enabled else '❌ 未启用'}")

    # 测试包处理
    test_packets = [
        {
            'name': '正常包',
            'src_ip': '10.0.0.1',
            'src_port': 54321,
            'dst_ip': '192.168.1.1',
            'dst_port': 80,
            'payload': b'GET / HTTP/1.1\r\nHost: example.com\r\n\r\n'
        },
        {
            'name': '黑名单IP',
            'src_ip': '127.0.0.1',
            'src_port': 12345,
            'dst_ip': '192.168.1.1',
            'dst_port': 80,
            'payload': b'test'
        },
    ]

    for test in test_packets:
        print(f"\n  测试包: {test['name']}")
        result = firewall.process_packet(
            packet_data=test['payload'],
            src_ip=test['src_ip'],
            src_port=test['src_port'],
            dst_ip=test['dst_ip'],
            dst_port=test['dst_port'],
            protocol='tcp'
        )
        print(f"  处理结果: {result['action']}")
        print(f"  原因: {result['reason']}")
        print(f"  威胁级别: {result['threat_level']}")

    # 打印统计
    print(f"\n  统计信息:")
    print(f"  - 总包数: {firewall.stats['total_packets']}")
    print(f"  - 阻断包数: {firewall.stats['blocked_packets']}")
    print(f"  - 快速过滤阻断: {firewall.stats['filter_list_blocks']}")


def test_performance():
    """性能测试"""
    print("\n" + "=" * 60)
    print("测试5: 性能测试")
    print("=" * 60)

    import time

    filters = FastFilterLists()

    # IP检查性能
    start = time.time()
    for _ in range(10000):
        filters.check_ip("8.8.8.8")
    elapsed = time.time() - start
    print(f"\n  IP检查: 10,000次耗时 {elapsed:.3f}秒")
    print(f"  平均: {elapsed/10000*1000:.3f} ms/次")

    # 邮件钓鱼检测性能
    start = time.time()
    for _ in range(1000):
        filters.check_email_phishing(
            email_from="test@example.com",
            subject="Test subject",
            body="Test body"
        )
    elapsed = time.time() - start
    print(f"\n  邮件钓鱼检测: 1,000次耗时 {elapsed:.3f}秒")
    print(f"  平均: {elapsed/1000*1000:.3f} ms/次")


def main():
    """主测试函数"""
    print("=" * 60)
    print("HIDRS Spamhaus与邮件安全集成测试")
    print("=" * 60)

    try:
        test_spamhaus()
        test_email_phishing()
        test_comprehensive_check()
        test_firewall_integration()
        test_performance()

        print("\n" + "=" * 60)
        print("✅ 所有测试完成!")
        print("=" * 60)

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
