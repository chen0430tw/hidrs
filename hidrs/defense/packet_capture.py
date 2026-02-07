"""
封包捕获层 - NFQueue拦截 + Scapy解析

实现AEGIS架构文档中的第一层：流量监控层
- NFQueue包拦截（Linux netfilter内核集成）
- 原始封包解析（IP/TCP/UDP头部提取）
- 封包裁决（放行/丢弃/修改）

运行要求：
- Linux系统
- root权限
- iptables规则将流量导入NFQUEUE
- 依赖: netfilterqueue, scapy

iptables配置示例：
    # 将所有入站TCP流量导入队列0
    iptables -I INPUT -p tcp -j NFQUEUE --queue-num 0
    # 将所有入站UDP流量导入队列1
    iptables -I INPUT -p udp -j NFQUEUE --queue-num 1
"""

import logging
import threading
import struct
from typing import Callable, Dict, Any, Optional

logger = logging.getLogger(__name__)

# NFQueue绑定（Linux内核netfilter）
try:
    from netfilterqueue import NetfilterQueue
    HAS_NFQUEUE = True
except ImportError:
    HAS_NFQUEUE = False

# Scapy封包解析/构造
try:
    from scapy.all import IP, TCP, UDP, ICMP, Raw, send, conf
    # 禁用scapy的冗余输出
    conf.verb = 0
    HAS_SCAPY = True
except ImportError:
    HAS_SCAPY = False


class PacketCapture:
    """
    封包捕获器

    通过NFQueue从Linux netfilter获取真实网络封包，
    解析后传递给HIDRSFirewall.process_packet()处理，
    并根据裁决结果放行或丢弃。
    """

    def __init__(
        self,
        queue_num: int = 0,
        max_packet_len: int = 65535,
        packet_handler: Callable = None,
    ):
        """
        初始化封包捕获器

        参数:
        - queue_num: NFQueue队列编号（需与iptables规则对应）
        - max_packet_len: 最大封包长度
        - packet_handler: 封包处理回调函数，签名:
              handler(packet_data, src_ip, src_port, dst_ip, dst_port, protocol) -> dict
              返回 {'action': 'allow/block/tarpit', ...}
        """
        if not HAS_NFQUEUE:
            raise ImportError(
                "netfilterqueue 未安装。安装方法:\n"
                "  apt-get install libnetfilter-queue-dev\n"
                "  pip install netfilterqueue"
            )
        if not HAS_SCAPY:
            raise ImportError(
                "scapy 未安装。安装方法:\n"
                "  pip install scapy"
            )

        self.queue_num = queue_num
        self.max_packet_len = max_packet_len
        self.packet_handler = packet_handler

        self._nfqueue = NetfilterQueue()
        self._capture_thread = None
        self._running = False

        # 统计
        self.stats = {
            'captured': 0,
            'accepted': 0,
            'dropped': 0,
            'modified': 0,
            'parse_errors': 0,
        }

    def _nfqueue_callback(self, nf_packet):
        """
        NFQueue回调：每个进入队列的封包都会触发此函数

        参数:
        - nf_packet: netfilterqueue.Packet 对象
          - nf_packet.get_payload(): 获取原始IP封包字节
          - nf_packet.accept(): 放行
          - nf_packet.drop(): 丢弃
          - nf_packet.set_payload(data): 修改后放行
        """
        self.stats['captured'] += 1

        try:
            raw_data = nf_packet.get_payload()
            parsed = self._parse_packet(raw_data)

            if parsed is None:
                # 解析失败，默认放行（避免误杀）
                nf_packet.accept()
                self.stats['accepted'] += 1
                return

            # 调用上层处理器（HIDRSFirewall.process_packet）
            if self.packet_handler:
                result = self.packet_handler(
                    packet_data=parsed['payload'],
                    src_ip=parsed['src_ip'],
                    src_port=parsed['src_port'],
                    dst_ip=parsed['dst_ip'],
                    dst_port=parsed['dst_port'],
                    protocol=parsed['protocol'],
                )

                action = result.get('action', 'allow')

                if action == 'block':
                    nf_packet.drop()
                    self.stats['dropped'] += 1
                elif action == 'tarpit':
                    # tarpit: 接受封包但由Tarpit模块处理后续响应
                    # 先accept让内核知道，tarpit逻辑在defense层处理
                    nf_packet.accept()
                    self.stats['accepted'] += 1
                elif action == 'modify' and 'modified_payload' in result:
                    # 修改封包内容后放行（用于SYN Cookie注入等）
                    nf_packet.set_payload(result['modified_payload'])
                    nf_packet.accept()
                    self.stats['modified'] += 1
                else:
                    nf_packet.accept()
                    self.stats['accepted'] += 1
            else:
                # 没有处理器，默认放行
                nf_packet.accept()
                self.stats['accepted'] += 1

        except Exception as e:
            logger.error(f"[PacketCapture] 封包处理异常: {e}")
            # 异常时默认放行，避免网络中断
            try:
                nf_packet.accept()
            except Exception:
                pass
            self.stats['accepted'] += 1

    def _parse_packet(self, raw_data: bytes) -> Optional[Dict[str, Any]]:
        """
        解析原始IP封包

        使用scapy解析IP/TCP/UDP头部，提取:
        - 源/目标IP
        - 源/目标端口
        - 协议类型
        - 有效载荷

        参数:
        - raw_data: 原始IP封包字节

        返回:
        - 解析结果字典，解析失败返回None
        """
        try:
            pkt = IP(raw_data)

            src_ip = pkt.src
            dst_ip = pkt.dst
            src_port = 0
            dst_port = 0
            protocol = 'other'
            payload = b''

            if pkt.haslayer(TCP):
                tcp = pkt[TCP]
                src_port = tcp.sport
                dst_port = tcp.dport
                protocol = 'tcp'
                # TCP标志位
                flags = tcp.flags
                if pkt.haslayer(Raw):
                    payload = bytes(pkt[Raw].load)
                # 将TCP标志信息附加到结果中
                return {
                    'src_ip': src_ip,
                    'dst_ip': dst_ip,
                    'src_port': src_port,
                    'dst_port': dst_port,
                    'protocol': protocol,
                    'payload': payload,
                    'tcp_flags': str(flags),
                    'tcp_seq': tcp.seq,
                    'tcp_ack': tcp.ack,
                    'tcp_window': tcp.window,
                    'raw_packet': pkt,
                }

            elif pkt.haslayer(UDP):
                udp = pkt[UDP]
                src_port = udp.sport
                dst_port = udp.dport
                protocol = 'udp'
                if pkt.haslayer(Raw):
                    payload = bytes(pkt[Raw].load)

            elif pkt.haslayer(ICMP):
                protocol = 'icmp'

            return {
                'src_ip': src_ip,
                'dst_ip': dst_ip,
                'src_port': src_port,
                'dst_port': dst_port,
                'protocol': protocol,
                'payload': payload,
                'raw_packet': pkt,
            }

        except Exception as e:
            self.stats['parse_errors'] += 1
            logger.debug(f"[PacketCapture] 封包解析失败: {e}")
            return None

    def start(self):
        """
        启动封包捕获

        绑定NFQueue并在后台线程中运行事件循环。
        需要事先配置iptables规则将流量导入对应队列。
        """
        if self._running:
            logger.warning("[PacketCapture] 已在运行中")
            return

        self._running = True

        # 绑定NFQueue
        self._nfqueue.bind(self.queue_num, self._nfqueue_callback,
                           max_len=self.max_packet_len)

        # 在后台线程中运行NFQueue事件循环
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name=f"PacketCapture-Q{self.queue_num}"
        )
        self._capture_thread.start()

        logger.info(f"[PacketCapture] 启动封包捕获 (队列={self.queue_num})")

    def _capture_loop(self):
        """NFQueue事件循环"""
        try:
            self._nfqueue.run()
        except Exception as e:
            if self._running:
                logger.error(f"[PacketCapture] NFQueue事件循环异常: {e}")

    def stop(self):
        """停止封包捕获"""
        self._running = False
        try:
            self._nfqueue.unbind()
        except Exception:
            pass

        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=5)

        logger.info(f"[PacketCapture] 封包捕获已停止 (stats={self.stats})")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return dict(self.stats)


class PacketCrafter:
    """
    封包构造器

    使用scapy构造网络封包，用于:
    - SYN Cookie的SYN-ACK响应
    - Tarpit的小窗口TCP响应
    - RST包发送（连接重置）
    """

    def __init__(self):
        if not HAS_SCAPY:
            raise ImportError("scapy 未安装")

    def craft_syn_ack(
        self,
        src_ip: str,
        dst_ip: str,
        src_port: int,
        dst_port: int,
        seq_num: int,
        ack_num: int,
        window: int = 65535,
    ) -> bytes:
        """
        构造SYN-ACK封包（用于SYN Cookie响应）

        参数:
        - src_ip: 源IP（服务端）
        - dst_ip: 目标IP（客户端）
        - src_port: 源端口
        - dst_port: 目标端口
        - seq_num: 序列号（编码了SYN Cookie）
        - ack_num: 确认号（客户端SYN的seq+1）
        - window: TCP窗口大小

        返回:
        - 原始封包字节
        """
        pkt = IP(src=src_ip, dst=dst_ip) / TCP(
            sport=src_port,
            dport=dst_port,
            flags='SA',  # SYN-ACK
            seq=seq_num,
            ack=ack_num,
            window=window,
        )
        return bytes(pkt)

    def craft_tarpit_ack(
        self,
        src_ip: str,
        dst_ip: str,
        src_port: int,
        dst_port: int,
        seq_num: int,
        ack_num: int,
        window: int = 1,
    ) -> bytes:
        """
        构造Tarpit ACK封包（极小窗口）

        TCP窗口设为1字节，迫使对方每次只能发送1字节数据，
        极大降低攻击者的发送速率，同时消耗其连接资源。

        参数:
        - window: TCP窗口大小，默认1字节（最小有效值）
        """
        pkt = IP(src=src_ip, dst=dst_ip) / TCP(
            sport=src_port,
            dport=dst_port,
            flags='A',  # ACK
            seq=seq_num,
            ack=ack_num,
            window=window,  # 极小窗口
        )
        return bytes(pkt)

    def craft_rst(
        self,
        src_ip: str,
        dst_ip: str,
        src_port: int,
        dst_port: int,
        seq_num: int,
    ) -> bytes:
        """构造RST封包（强制断开连接）"""
        pkt = IP(src=src_ip, dst=dst_ip) / TCP(
            sport=src_port,
            dport=dst_port,
            flags='R',  # RST
            seq=seq_num,
        )
        return bytes(pkt)

    def send_packet(self, raw_packet: bytes):
        """
        发送原始封包

        参数:
        - raw_packet: 原始IP封包字节
        """
        pkt = IP(raw_packet)
        send(pkt)

    def send_scapy_packet(self, pkt):
        """发送scapy封包对象"""
        send(pkt)


class MultiQueueCapture:
    """
    多队列封包捕获

    同时监听多个NFQueue队列，分别处理TCP/UDP/ICMP等不同协议的流量。

    iptables配置示例：
        iptables -I INPUT -p tcp -j NFQUEUE --queue-num 0
        iptables -I INPUT -p udp -j NFQUEUE --queue-num 1
        iptables -I INPUT -p icmp -j NFQUEUE --queue-num 2
    """

    def __init__(self, packet_handler: Callable = None):
        """
        参数:
        - packet_handler: 封包处理回调（同PacketCapture）
        """
        self.packet_handler = packet_handler
        self.captures = {}
        self._running = False

    def add_queue(self, queue_num: int, protocol_label: str = ''):
        """
        添加监听队列

        参数:
        - queue_num: NFQueue队列编号
        - protocol_label: 协议标签（仅用于日志）
        """
        capture = PacketCapture(
            queue_num=queue_num,
            packet_handler=self.packet_handler,
        )
        self.captures[queue_num] = {
            'capture': capture,
            'label': protocol_label or f'queue-{queue_num}',
        }

    def start(self):
        """启动所有队列的捕获"""
        self._running = True
        for qnum, info in self.captures.items():
            info['capture'].start()
            logger.info(f"[MultiQueueCapture] 队列 {qnum} ({info['label']}) 已启动")

    def stop(self):
        """停止所有队列的捕获"""
        self._running = False
        for qnum, info in self.captures.items():
            info['capture'].stop()

    def get_stats(self) -> Dict[str, Any]:
        """获取所有队列的统计"""
        return {
            info['label']: info['capture'].get_stats()
            for qnum, info in self.captures.items()
        }
