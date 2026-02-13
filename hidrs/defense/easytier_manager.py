"""
EasyTier Mesh VPN 管理模块
EasyTier Mesh VPN Manager for AEGIS Defense Network

通过 easytier-cli 控制 easytier-core 守护进程，
管理 Mesh VPN overlay 网络，用于 AEGIS 防御节点间加密通信。

核心功能：
1. 管理 easytier-core 实例（启动/停止/配置）
2. 查询 Mesh 网络拓扑（peer/route/node 信息）
3. 威胁情报广播（通过 Mesh overlay 加密传输）
4. 拓扑数据喂给 HLIG 分析
5. 动态 Peer 管理（添加/移除节点）

依赖：
- easytier-core + easytier-cli（从 https://github.com/EasyTier/EasyTier 安装）
- 通过 CLI subprocess 交互，无需额外 Python 依赖

架构参考：
- EasyTier 使用 OSPF 路由算法进行 Peer 发现
- 支持 TCP/UDP/QUIC/KCP/WS/WSS/WireGuard 多协议
- NAT 穿透 + 公共中继节点自动回退

By: Claude + 430
"""

import json
import time
import logging
import subprocess
import shutil
import threading
import os
import signal
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class EasyTierPeer:
    """EasyTier 对等节点信息"""
    peer_id: str
    ipv4: str
    hostname: str = ""
    version: str = ""
    cost: int = 1
    latency_ms: float = 0.0
    loss_rate: float = 0.0
    tunnel_proto: str = ""  # tcp/udp/quic/kcp/ws/wss/wireguard
    nat_type: str = ""
    conn_status: str = ""  # connected/connecting/disconnected


@dataclass
class EasyTierRoute:
    """EasyTier 路由信息"""
    peer_id: str
    ipv4: str
    next_hop: str = ""
    cost: int = 1
    proxy_cidrs: List[str] = field(default_factory=list)


@dataclass
class EasyTierNodeInfo:
    """本地节点信息"""
    node_id: str = ""
    ipv4: str = ""
    hostname: str = ""
    version: str = ""
    listeners: List[str] = field(default_factory=list)
    vpn_portal: str = ""


class EasyTierCLI:
    """
    EasyTier CLI 封装

    通过 subprocess 调用 easytier-cli 获取 Mesh 网络状态。
    easytier-cli 通过 RPC (protobuf over tarpc) 与 easytier-core 通信。
    """

    def __init__(
        self,
        cli_path: str = None,
        rpc_portal: str = "127.0.0.1:15888",
    ):
        """
        初始化 CLI 封装

        参数:
            cli_path: easytier-cli 可执行文件路径（None 则从 PATH 搜索）
            rpc_portal: easytier-core RPC 监听地址
        """
        self.rpc_portal = rpc_portal

        # 查找 easytier-cli
        if cli_path:
            self.cli_path = cli_path
        else:
            self.cli_path = shutil.which("easytier-cli")

        if not self.cli_path:
            logger.warning(
                "easytier-cli 未找到。安装方法: "
                "https://github.com/EasyTier/EasyTier/releases"
            )

    @property
    def available(self) -> bool:
        """检查 easytier-cli 是否可用"""
        return self.cli_path is not None and os.path.isfile(self.cli_path)

    def _run_cli(self, *args, timeout: float = 10.0) -> Optional[str]:
        """
        执行 easytier-cli 命令

        参数:
            args: CLI 子命令参数
            timeout: 超时秒数

        返回:
            命令输出文本，失败返回 None
        """
        if not self.available:
            logger.error("easytier-cli 不可用")
            return None

        cmd = [self.cli_path, "-p", self.rpc_portal] + list(args)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                stderr = result.stderr.strip()
                if stderr:
                    logger.error(f"easytier-cli 错误: {stderr}")
                return None

            return result.stdout.strip()

        except subprocess.TimeoutExpired:
            logger.error(f"easytier-cli 超时 ({timeout}s): {' '.join(cmd)}")
            return None
        except FileNotFoundError:
            logger.error(f"easytier-cli 可执行文件不存在: {self.cli_path}")
            self.cli_path = None
            return None
        except Exception as e:
            logger.error(f"easytier-cli 执行失败: {e}")
            return None

    def get_peers(self) -> List[EasyTierPeer]:
        """
        获取所有对等节点

        调用: easytier-cli peer
        """
        output = self._run_cli("peer")
        if not output:
            return []

        return self._parse_peer_output(output)

    def get_routes(self) -> List[EasyTierRoute]:
        """
        获取路由表

        调用: easytier-cli route
        """
        output = self._run_cli("route")
        if not output:
            return []

        return self._parse_route_output(output)

    def get_node_info(self) -> Optional[EasyTierNodeInfo]:
        """
        获取本地节点信息

        调用: easytier-cli node
        """
        output = self._run_cli("node")
        if not output:
            return None

        return self._parse_node_output(output)

    def get_vpn_portal(self) -> Optional[str]:
        """
        获取 VPN Portal WireGuard 配置

        调用: easytier-cli vpn-portal
        """
        return self._run_cli("vpn-portal")

    def _parse_peer_output(self, output: str) -> List[EasyTierPeer]:
        """
        解析 easytier-cli peer 输出

        输出格式为表格，例如:
        ┌──────────┬────────────┬──────────┬─────────┬──────────┬───────────┐
        │ PEER_ID  │ IPV4       │ HOSTNAME │ COST    │ LATENCY  │ LOSS_RATE │
        ├──────────┼────────────┼──────────┼─────────┼──────────┼───────────┤
        │ abc123   │ 10.0.0.2   │ node-02  │ 1       │ 5.2ms    │ 0.0%      │
        └──────────┴────────────┴──────────┴─────────┴──────────┴───────────┘
        """
        peers = []
        lines = output.split('\n')

        # 跳过表头，找数据行（包含 │ 分隔符的非边框行）
        for line in lines:
            if '│' not in line or '─' in line or '┌' in line or '└' in line or '├' in line:
                continue

            cells = [c.strip() for c in line.split('│') if c.strip()]

            # 跳过表头行
            if not cells or cells[0] in ('PEER_ID', 'peer_id', 'ID'):
                continue

            try:
                peer = EasyTierPeer(
                    peer_id=cells[0] if len(cells) > 0 else "",
                    ipv4=cells[1] if len(cells) > 1 else "",
                    hostname=cells[2] if len(cells) > 2 else "",
                    cost=int(cells[3]) if len(cells) > 3 and cells[3].isdigit() else 1,
                )

                # 解析延迟 (如 "5.2ms")
                if len(cells) > 4:
                    lat_str = cells[4].replace('ms', '').strip()
                    try:
                        peer.latency_ms = float(lat_str)
                    except ValueError:
                        pass

                # 解析丢包率 (如 "0.5%")
                if len(cells) > 5:
                    loss_str = cells[5].replace('%', '').strip()
                    try:
                        peer.loss_rate = float(loss_str) / 100.0
                    except ValueError:
                        pass

                # 解析隧道协议
                if len(cells) > 6:
                    peer.tunnel_proto = cells[6].lower()

                # 解析NAT类型
                if len(cells) > 7:
                    peer.nat_type = cells[7]

                # 解析连接状态
                if len(cells) > 8:
                    peer.conn_status = cells[8].lower()
                else:
                    peer.conn_status = "connected"  # 出现在peer列表中默认已连接

                peers.append(peer)

            except (IndexError, ValueError) as e:
                logger.debug(f"解析 peer 行失败: {line!r} ({e})")
                continue

        return peers

    def _parse_route_output(self, output: str) -> List[EasyTierRoute]:
        """
        解析 easytier-cli route 输出

        格式类似 peer 输出的表格
        """
        routes = []
        lines = output.split('\n')

        for line in lines:
            if '│' not in line or '─' in line or '┌' in line or '└' in line or '├' in line:
                continue

            cells = [c.strip() for c in line.split('│') if c.strip()]

            if not cells or cells[0] in ('PEER_ID', 'peer_id', 'ID', 'ROUTE'):
                continue

            try:
                route = EasyTierRoute(
                    peer_id=cells[0] if len(cells) > 0 else "",
                    ipv4=cells[1] if len(cells) > 1 else "",
                    next_hop=cells[2] if len(cells) > 2 else "",
                    cost=int(cells[3]) if len(cells) > 3 and cells[3].isdigit() else 1,
                )

                # 解析代理CIDR
                if len(cells) > 4 and cells[4]:
                    cidrs = [c.strip() for c in cells[4].split(',') if c.strip()]
                    route.proxy_cidrs = cidrs

                routes.append(route)

            except (IndexError, ValueError) as e:
                logger.debug(f"解析 route 行失败: {line!r} ({e})")
                continue

        return routes

    def _parse_node_output(self, output: str) -> EasyTierNodeInfo:
        """
        解析 easytier-cli node 输出

        可能是 key: value 格式或表格格式
        """
        info = EasyTierNodeInfo()
        lines = output.split('\n')

        for line in lines:
            line = line.strip()

            # key: value 格式
            if ':' in line and '│' not in line:
                key, _, value = line.partition(':')
                key = key.strip().lower()
                value = value.strip()

                if 'node' in key and 'id' in key:
                    info.node_id = value
                elif key in ('ipv4', 'ip', 'virtual_ip', 'virtual_ipv4'):
                    info.ipv4 = value
                elif key in ('hostname', 'host'):
                    info.hostname = value
                elif key in ('version', 'ver'):
                    info.version = value
                elif 'listener' in key:
                    info.listeners = [v.strip() for v in value.split(',') if v.strip()]
                elif 'portal' in key:
                    info.vpn_portal = value

            # 表格格式 - 尝试解析
            elif '│' in line and '─' not in line and '┌' not in line:
                cells = [c.strip() for c in line.split('│') if c.strip()]
                if len(cells) >= 2:
                    key = cells[0].lower()
                    value = cells[1]
                    if 'node' in key and 'id' in key:
                        info.node_id = value
                    elif 'ipv4' in key or 'ip' in key:
                        info.ipv4 = value
                    elif 'hostname' in key:
                        info.hostname = value
                    elif 'version' in key:
                        info.version = value

        return info


class EasyTierManager:
    """
    EasyTier Mesh 网络管理器

    管理 easytier-core 进程的生命周期，
    监控 Mesh 网络拓扑变化，
    提供数据接口给 HLIG 拓扑分析和 AEGIS 威胁广播。
    """

    def __init__(
        self,
        network_name: str = "hidrs-aegis",
        network_secret: str = "",
        ipv4: str = "",
        listeners: List[str] = None,
        peers: List[str] = None,
        proxy_networks: List[str] = None,
        enable_vpn_portal: bool = False,
        vpn_portal_listen: str = "",
        vpn_portal_client_cidr: str = "",
        core_path: str = None,
        cli_path: str = None,
        rpc_portal: str = "127.0.0.1:15888",
        config_file: str = None,
        topology_poll_interval: float = 10.0,
    ):
        """
        初始化 EasyTier 管理器

        参数:
            network_name: 网络名称（同一网络名称的节点自动组网）
            network_secret: 网络密钥（空则不加密）
            ipv4: 本节点虚拟IPv4地址（空则自动分配）
            listeners: 监听地址列表 (如 ["tcp://0.0.0.0:11010", "udp://0.0.0.0:11010"])
            peers: 初始对等节点列表 (如 ["tcp://peer1:11010"])
            proxy_networks: 子网代理列表 (如 ["10.1.1.0/24"])
            enable_vpn_portal: 启用 WireGuard VPN Portal
            vpn_portal_listen: VPN Portal 监听地址
            vpn_portal_client_cidr: VPN Portal 客户端地址段
            core_path: easytier-core 可执行文件路径
            cli_path: easytier-cli 可执行文件路径
            rpc_portal: RPC 监听地址
            config_file: TOML 配置文件路径（优先于命令行参数）
            topology_poll_interval: 拓扑轮询间隔（秒）
        """
        self.network_name = network_name
        self.network_secret = network_secret
        self.ipv4 = ipv4
        self.listeners = listeners or []
        self.peers = peers or []
        self.proxy_networks = proxy_networks or []
        self.enable_vpn_portal = enable_vpn_portal
        self.vpn_portal_listen = vpn_portal_listen
        self.vpn_portal_client_cidr = vpn_portal_client_cidr
        self.rpc_portal = rpc_portal
        self.config_file = config_file
        self.topology_poll_interval = topology_poll_interval

        # easytier-core 进程
        if core_path:
            self.core_path = core_path
        else:
            self.core_path = shutil.which("easytier-core")

        # CLI 客户端
        self.cli = EasyTierCLI(cli_path=cli_path, rpc_portal=rpc_portal)

        # 进程管理
        self._core_process: Optional[subprocess.Popen] = None
        self._running = False

        # 拓扑缓存
        self._current_peers: List[EasyTierPeer] = []
        self._current_routes: List[EasyTierRoute] = []
        self._node_info: Optional[EasyTierNodeInfo] = None
        self._topology_lock = threading.Lock()
        self._poll_thread: Optional[threading.Thread] = None

        # 拓扑变化回调
        self._topology_callbacks: List = []

        # 统计
        self.stats = {
            'core_starts': 0,
            'core_restarts': 0,
            'topology_polls': 0,
            'peers_discovered': 0,
            'peer_changes': 0,
        }

        logger.info(
            f"EasyTier管理器初始化 (网络: {network_name}, "
            f"core: {'可用' if self.core_path else '未找到'}, "
            f"cli: {'可用' if self.cli.available else '未找到'})"
        )

    def _build_core_args(self) -> List[str]:
        """构建 easytier-core 启动参数"""
        args = [self.core_path]

        # 网络名称和密钥
        if self.network_name:
            args += ["--network-name", self.network_name]
        if self.network_secret:
            args += ["--network-secret", self.network_secret]

        # IPv4 地址
        if self.ipv4:
            args += ["--ipv4", self.ipv4]

        # 监听地址
        for listener in self.listeners:
            args += ["--listeners", listener]

        # 对等节点
        for peer in self.peers:
            args += ["--peers", peer]

        # 子网代理
        for network in self.proxy_networks:
            args += ["-n", network]

        # RPC 监听
        args += ["--rpc-portal", self.rpc_portal]

        # VPN Portal
        if self.enable_vpn_portal:
            if self.vpn_portal_listen:
                args += ["--vpn-portal", f"wg://{self.vpn_portal_listen}/{self.vpn_portal_client_cidr}"]

        return args

    def start_core(self) -> bool:
        """
        启动 easytier-core 守护进程

        返回:
            是否成功启动
        """
        if self._core_process and self._core_process.poll() is None:
            logger.warning("easytier-core 已在运行")
            return True

        if not self.core_path:
            logger.error(
                "easytier-core 未找到。安装方法: "
                "https://github.com/EasyTier/EasyTier/releases"
            )
            return False

        if self.config_file and os.path.isfile(self.config_file):
            # 使用配置文件启动
            cmd = [self.core_path, "-c", self.config_file]
        else:
            # 使用命令行参数启动
            cmd = self._build_core_args()

        try:
            self._core_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # 等待 RPC 端口就绪
            time.sleep(1.0)

            if self._core_process.poll() is not None:
                stderr = self._core_process.stderr.read().decode('utf-8', errors='replace')
                logger.error(f"easytier-core 启动失败: {stderr}")
                self._core_process = None
                return False

            self.stats['core_starts'] += 1
            self._running = True

            # 启动拓扑轮询
            self._start_topology_poll()

            logger.info(f"easytier-core 已启动 (PID: {self._core_process.pid})")
            return True

        except FileNotFoundError:
            logger.error(f"easytier-core 可执行文件不存在: {self.core_path}")
            self.core_path = None
            return False
        except Exception as e:
            logger.error(f"easytier-core 启动异常: {e}")
            return False

    def stop_core(self):
        """停止 easytier-core 守护进程"""
        self._running = False

        # 停止拓扑轮询
        if self._poll_thread:
            self._poll_thread.join(timeout=5.0)
            self._poll_thread = None

        if self._core_process and self._core_process.poll() is None:
            try:
                self._core_process.terminate()
                self._core_process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self._core_process.kill()
                self._core_process.wait(timeout=2.0)
            except Exception as e:
                logger.error(f"停止 easytier-core 异常: {e}")

            logger.info("easytier-core 已停止")

        self._core_process = None

    def is_running(self) -> bool:
        """检查 easytier-core 是否在运行"""
        if self._core_process is None:
            return False
        return self._core_process.poll() is None

    def _start_topology_poll(self):
        """启动拓扑轮询线程"""
        if self._poll_thread and self._poll_thread.is_alive():
            return

        self._poll_thread = threading.Thread(
            target=self._topology_poll_loop,
            daemon=True,
        )
        self._poll_thread.start()

    def _topology_poll_loop(self):
        """拓扑轮询循环"""
        while self._running:
            try:
                self._update_topology()
                self.stats['topology_polls'] += 1
            except Exception as e:
                logger.error(f"拓扑轮询异常: {e}")

            # 等待下一次轮询
            wait_start = time.time()
            while self._running and (time.time() - wait_start) < self.topology_poll_interval:
                time.sleep(0.5)

    def _update_topology(self):
        """更新拓扑信息"""
        new_peers = self.cli.get_peers()
        new_routes = self.cli.get_routes()
        new_node = self.cli.get_node_info()

        with self._topology_lock:
            old_peer_ids = {p.peer_id for p in self._current_peers}
            new_peer_ids = {p.peer_id for p in new_peers}

            # 检测 Peer 变化
            added = new_peer_ids - old_peer_ids
            removed = old_peer_ids - new_peer_ids

            if added:
                self.stats['peers_discovered'] += len(added)
                self.stats['peer_changes'] += 1
                logger.info(f"发现新 Peer: {added}")

            if removed:
                self.stats['peer_changes'] += 1
                logger.info(f"Peer 离线: {removed}")

            self._current_peers = new_peers
            self._current_routes = new_routes
            self._node_info = new_node

        # 触发拓扑变化回调
        if added or removed:
            for callback in self._topology_callbacks:
                try:
                    callback(
                        added=list(added),
                        removed=list(removed),
                        peers=new_peers,
                        routes=new_routes,
                    )
                except Exception as e:
                    logger.error(f"拓扑变化回调异常: {e}")

    def on_topology_change(self, callback):
        """
        注册拓扑变化回调

        callback 签名:
            callback(added: List[str], removed: List[str],
                     peers: List[EasyTierPeer], routes: List[EasyTierRoute])
        """
        self._topology_callbacks.append(callback)

    def get_peers(self) -> List[EasyTierPeer]:
        """获取当前 Peer 列表（从缓存）"""
        with self._topology_lock:
            return list(self._current_peers)

    def get_routes(self) -> List[EasyTierRoute]:
        """获取当前路由表（从缓存）"""
        with self._topology_lock:
            return list(self._current_routes)

    def get_node_info(self) -> Optional[EasyTierNodeInfo]:
        """获取本地节点信息（从缓存）"""
        with self._topology_lock:
            return self._node_info

    def add_peer(self, peer_url: str) -> bool:
        """
        动态添加对等节点

        通过重启 core 或 CLI 命令添加
        注意: 当前 easytier-cli 不支持运行时添加 peer，
        需要通过配置文件修改 + SIGHUP 或重启实现。

        参数:
            peer_url: 对等节点地址 (如 "tcp://1.2.3.4:11010")
        """
        if peer_url not in self.peers:
            self.peers.append(peer_url)

        # 如果使用配置文件，更新配置
        if self.config_file:
            return self._update_config_peers()

        # 否则需要重启 core
        if self.is_running():
            logger.info(f"添加 Peer {peer_url}，重启 easytier-core")
            self.stop_core()
            time.sleep(0.5)
            return self.start_core()

        return True

    def remove_peer(self, peer_url: str) -> bool:
        """动态移除对等节点"""
        if peer_url in self.peers:
            self.peers.remove(peer_url)

        if self.config_file:
            return self._update_config_peers()

        if self.is_running():
            logger.info(f"移除 Peer {peer_url}，重启 easytier-core")
            self.stop_core()
            time.sleep(0.5)
            return self.start_core()

        return True

    def _update_config_peers(self) -> bool:
        """更新 TOML 配置文件中的 peers 列表"""
        if not self.config_file or not os.path.isfile(self.config_file):
            return False

        try:
            # 读取配置文件
            with open(self.config_file, 'r') as f:
                content = f.read()

            # 简单替换 peers 配置（TOML 格式）
            # [[peer]]
            # uri = "tcp://..."
            lines = content.split('\n')
            new_lines = []
            skip_peer_block = False

            for line in lines:
                stripped = line.strip()
                if stripped == '[[peer]]':
                    skip_peer_block = True
                    continue
                if skip_peer_block:
                    if stripped.startswith('uri') or stripped == '':
                        continue
                    else:
                        skip_peer_block = False
                new_lines.append(line)

            # 添加新的 peer 配置
            for peer_url in self.peers:
                new_lines.append('')
                new_lines.append('[[peer]]')
                new_lines.append(f'uri = "{peer_url}"')

            with open(self.config_file, 'w') as f:
                f.write('\n'.join(new_lines))

            # 发送 SIGHUP 让 core 重新加载配置
            if self._core_process and self._core_process.poll() is None:
                try:
                    self._core_process.send_signal(signal.SIGHUP)
                    logger.info("已发送 SIGHUP 重载配置")
                except Exception:
                    logger.warning("SIGHUP 发送失败，可能需要手动重启")

            return True

        except Exception as e:
            logger.error(f"更新配置文件失败: {e}")
            return False

    def get_topology_for_hlig(self) -> Dict[str, Any]:
        """
        将 Mesh 拓扑转换为 HLIG 分析格式

        返回包含节点列表和边(链路)列表的字典，
        可直接传给 TopologyBuilder 构建拓扑图。
        """
        peers = self.get_peers()
        routes = self.get_routes()
        node_info = self.get_node_info()

        # 节点列表
        nodes = []
        if node_info:
            nodes.append({
                'id': node_info.node_id,
                'ipv4': node_info.ipv4,
                'hostname': node_info.hostname,
                'type': 'local',
            })

        for peer in peers:
            nodes.append({
                'id': peer.peer_id,
                'ipv4': peer.ipv4,
                'hostname': peer.hostname,
                'type': 'peer',
                'latency_ms': peer.latency_ms,
                'loss_rate': peer.loss_rate,
                'tunnel_proto': peer.tunnel_proto,
            })

        # 边列表（从路由表推导）
        edges = []
        local_id = node_info.node_id if node_info else "local"

        for route in routes:
            # 直连路由: next_hop 为空或等于 peer_id
            if not route.next_hop or route.next_hop == route.peer_id:
                source = local_id
            else:
                source = route.next_hop

            edges.append({
                'source': source,
                'target': route.peer_id,
                'cost': route.cost,
                'proxy_cidrs': route.proxy_cidrs,
            })

        # 补充直连 peer 的边
        peer_ids_in_routes = {r.peer_id for r in routes}
        for peer in peers:
            if peer.peer_id not in peer_ids_in_routes:
                edges.append({
                    'source': local_id,
                    'target': peer.peer_id,
                    'cost': peer.cost,
                })

        return {
            'nodes': nodes,
            'edges': edges,
            'mesh_network': self.network_name,
            'timestamp': time.time(),
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取管理器统计信息"""
        return {
            **self.stats,
            'core_running': self.is_running(),
            'core_pid': self._core_process.pid if self._core_process else None,
            'network_name': self.network_name,
            'peer_count': len(self._current_peers),
            'route_count': len(self._current_routes),
            'cli_available': self.cli.available,
        }
