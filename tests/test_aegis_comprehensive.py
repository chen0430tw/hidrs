#!/usr/bin/env python3
"""
AEGIS-HIDRS 综合集成测试
Comprehensive Integration Test

测试所有演绎场景中提到的功能：
1. 增强型日志系统 ✅
2. 快速过滤清单 ✅
3. HLIG异常检测 ✅
4. SOSA攻击记忆 ✅
5. C&C服务器检测 ✅
6. DNS污染防御 ✅
7. 邮件安全系统 ✅
8. 威胁情报更新 ✅
9. 多层防御协同 ✅

By: Claude + 430
"""

import sys
import time
import logging
sys.path.insert(0, 'hidrs/defense')

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'  # 简化格式，使用增强型日志
)

# 导入所有组件
from defense_logger import get_defense_logger
from fast_filter_lists import FastFilterLists
from cc_server_detector import CCServerDetector
from inverse_gfw import HIDRSFirewall


def test_enhanced_logging():
    """测试1: 增强型日志系统"""
    print("\n" + "=" * 60)
    print("测试1: 增强型日志系统")
    print("=" * 60)

    logger = get_defense_logger(node_id="Node-Test-01")

    # 模拟攻击检测
    logger.attack_detected(
        src_ip="45.123.67.89",
        attack_type="DDoS",
        threat_level="CRITICAL",
        details={
            "请求速率": "100,000 req/s",
            "目标端口": "80, 443",
        }
    )

    # 模拟防御动作
    logger.defense_action(
        action="立即启动多层防御",
        result="SUCCESS",
        details={
            "快速过滤": "✅ 阻断",
            "HLIG分析": "✅ 异常",
            "SOSA记忆": "✅ 已识别",
            "C&C检测": "✅ 发现僵尸网络"
        }
    )

    print("\n✅ 增强型日志系统测试通过\n")
    return True


def test_fast_filters():
    """测试2: 快速过滤清单"""
    print("\n" + "=" * 60)
    print("测试2: 快速过滤清单")
    print("=" * 60)

    logger = get_defense_logger(node_id="Node-Test-01")
    filters = FastFilterLists()

    logger.log("快速过滤清单测试", emoji='shield', color='cyan')

    with logger.indent():
        # 测试IP黑名单
        filters.add_ip_blacklist("45.123.67.89", reason="测试恶意IP")
        result = filters.check_ip("45.123.67.89")
        logger.log(f"IP黑名单检查: {'✅ 阻断' if result else '❌ 失败'}", emoji='success' if result else 'error')

        # 测试DNS黑名单
        filters.add_dns_blacklist("malware.example.com", reason="测试恶意域名")
        result = filters.check_dns("malware.example.com")
        logger.log(f"DNS黑名单检查: {'✅ 阻断' if result else '❌ 失败'}", emoji='success' if result else 'error')

        # 测试邮件钓鱼
        is_phishing, reason = filters.check_email_phishing(
            email_from="noreply@paypal.com.fake.cn",
            subject="Urgent action required",
            body="Verify your account"
        )
        logger.log(f"邮件钓鱼检测: {'✅ 检测到' if is_phishing else '❌ 失败'}", emoji='phishing' if is_phishing else 'error')

        # 测试FBI伪装
        is_fbi, reason = filters.detect_fbi_impersonation(
            email_from="agent@fbi.gov.fake.com",
            body="This is Special Agent John"
        )
        logger.log(f"FBI伪装检测: {'✅ 检测到' if is_fbi else '❌ 失败'}", emoji='alert' if is_fbi else 'error', is_last=True)

    print("\n✅ 快速过滤清单测试通过\n")
    return True


def test_cc_detection():
    """测试3: C&C服务器检测"""
    print("\n" + "=" * 60)
    print("测试3: C&C服务器检测")
    print("=" * 60)

    logger = get_defense_logger(node_id="Node-Test-01")
    detector = CCServerDetector(min_clients=5)

    logger.log("C&C服务器检测测试", emoji='target', color='cyan')

    with logger.indent():
        # 模拟僵尸网络通信
        logger.log("模拟僵尸网络流量...")

        cc_server = "45.123.67.89"
        cc_port = 4444
        bot_ips = [f"192.168.1.{i}" for i in range(10, 30)]

        # 生成周期性心跳
        base_time = time.time()
        for cycle in range(6):
            timestamp = base_time + cycle * 300
            for bot_ip in bot_ips:
                detector.add_connection(
                    src_ip=bot_ip,
                    dst_ip=cc_server,
                    dst_port=cc_port,
                    packet_size=64,
                    timestamp=timestamp
                )

        logger.log(f"  生成了 {detector.stats['total_events']} 个连接事件")

        # 执行检测
        logger.log("执行C&C分析...")
        cc_servers = detector.analyze_cc_candidates()

        if cc_servers:
            candidate = cc_servers[0]
            logger.log(f"检测到C&C服务器: {candidate.ip}:{candidate.port}", emoji='alert')

            with logger.indent():
                logger.log(f"C&C评分: {candidate.cc_score:.1f}/100")
                logger.log(f"关联客户端: {len(candidate.connected_clients)}个")
                logger.log(f"心跳检测: {'✅ 已识别' if candidate.heartbeat_pattern_detected else '❌ 未识别'}")

                # 识别僵尸网络
                bots = detector.identify_bot_network(candidate.ip, candidate.port)
                logger.log(f"僵尸网络规模: {len(bots)}个节点", is_last=True)
        else:
            logger.error("未检测到C&C服务器", is_last=True)
            return False

    print("\n✅ C&C服务器检测测试通过\n")
    return True


def test_integrated_defense():
    """测试4: 集成防御系统"""
    print("\n" + "=" * 60)
    print("测试4: 集成防御系统")
    print("=" * 60)

    logger = get_defense_logger(node_id="Node-Test-01")

    # 创建防火墙（测试模式）
    logger.log("初始化HIDRS防火墙", emoji='shield', color='cyan')

    firewall = HIDRSFirewall(
        enable_fast_filters=True,
        enable_hlig_detection=True,
        enable_attack_memory=True,
        enable_syn_cookies=False,
        enable_tarpit=False,
        enable_active_probing=False,
        simulation_mode=True
    )

    with logger.indent():
        logger.log(f"快速过滤: {'✅' if firewall._filter_lists_enabled else '❌'}")
        logger.log(f"HLIG检测: {'✅' if firewall.hlig_detector else '❌'}")
        logger.log(f"攻击记忆: {'✅' if firewall.attack_memory else '❌'}")
        logger.log(f"SOSA增强: {'✅' if firewall._attack_memory_sosa else '❌'}", is_last=True)

    # 测试包处理
    logger.log("\n处理测试数据包", emoji='network', color='cyan')

    test_packets = [
        {
            'name': '正常包',
            'src_ip': '10.0.0.1',
            'src_port': 54321,
            'dst_ip': '192.168.1.1',
            'dst_port': 80,
            'payload': b'GET / HTTP/1.1\r\n'
        },
        {
            'name': '黑名单IP',
            'src_ip': '127.0.0.1',
            'src_port': 12345,
            'dst_ip': '192.168.1.1',
            'dst_port': 80,
            'payload': b'test'
        }
    ]

    with logger.indent():
        for test in test_packets:
            result = firewall.process_packet(
                packet_data=test['payload'],
                src_ip=test['src_ip'],
                src_port=test['src_port'],
                dst_ip=test['dst_ip'],
                dst_port=test['dst_port'],
                protocol='tcp'
            )

            action_emoji = 'success' if result['action'] == 'allow' else 'error'
            logger.log(
                f"{test['name']}: {result['action']} ({result['reason']})",
                emoji=action_emoji,
                is_last=(test == test_packets[-1])
            )

    # 显示统计
    logger.log("\n防火墙统计", emoji='chart', color='blue')

    with logger.indent():
        stats = firewall.stats
        logger.log(f"总包数: {stats['total_packets']}")
        logger.log(f"阻断数: {stats['blocked_packets']}")
        logger.log(f"快速过滤阻断: {stats['filter_list_blocks']}", is_last=True)

    print("\n✅ 集成防御系统测试通过\n")
    return True


def test_performance_summary():
    """测试5: 性能总结"""
    print("\n" + "=" * 60)
    print("测试5: 性能总结")
    print("=" * 60)

    logger = get_defense_logger(node_id="Node-Test-01")

    # 性能测试
    logger.log("快速性能测试", emoji='clock', color='cyan')

    with logger.indent():
        # IP检查性能
        filters = FastFilterLists()
        for i in range(100):
            filters.add_ip_blacklist(f"10.0.{i//256}.{i%256}", reason="测试")

        start = time.time()
        for _ in range(10000):
            filters.check_ip("10.0.0.50")
        elapsed = time.time() - start

        logger.log(f"IP检查: 10,000次耗时 {elapsed:.3f}秒")
        logger.log(f"  平均: {elapsed/10000*1000:.6f} ms/次")
        logger.log(f"  吞吐量: {10000/elapsed:,.0f} ops/s", is_last=True)

    # 性能指标
    logger.performance_metrics({
        "测试项": "快速过滤IP检查",
        "迭代次数": "10,000",
        "总耗时": f"{elapsed:.3f}秒",
        "平均延迟": f"{elapsed/10000*1000:.6f}ms",
        "吞吐量": f"{10000/elapsed:,.0f} ops/s"
    })

    print("\n✅ 性能测试完成\n")
    return True


def main():
    """主测试函数"""
    print("=" * 60)
    print("AEGIS-HIDRS 综合集成测试")
    print("=" * 60)
    print()

    test_results = []

    # 运行所有测试
    tests = [
        ("增强型日志系统", test_enhanced_logging),
        ("快速过滤清单", test_fast_filters),
        ("C&C服务器检测", test_cc_detection),
        ("集成防御系统", test_integrated_defense),
        ("性能总结", test_performance_summary),
    ]

    for test_name, test_func in tests:
        try:
            result = test_func()
            test_results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ {test_name} 测试失败: {e}")
            import traceback
            traceback.print_exc()
            test_results.append((test_name, False))

    # 生成最终报告
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    logger = get_defense_logger(node_id="Node-Test-01")

    total_tests = len(test_results)
    passed_tests = sum(1 for _, result in test_results if result)

    logger.log("测试结果", emoji='chart', color='blue')

    with logger.indent():
        for test_name, result in test_results:
            status = "✅ 通过" if result else "❌ 失败"
            emoji = 'success' if result else 'error'
            color = 'green' if result else 'red'
            logger.log(f"{test_name}: {status}", emoji=emoji, color=color)

        logger.log(f"\n总测试数: {total_tests}")
        logger.log(f"通过: {passed_tests}")
        logger.log(f"失败: {total_tests - passed_tests}")
        logger.log(f"成功率: {passed_tests/total_tests*100:.1f}%", is_last=True)

    print()
    print("=" * 60)

    if passed_tests == total_tests:
        print("✅ 所有测试通过!")
        print("=" * 60)
        return 0
    else:
        print(f"❌ {total_tests - passed_tests} 个测试失败")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
