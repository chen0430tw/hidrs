"""
OpenWrt 远程控制模块
OpenWrt Remote Controller via ubus JSON-RPC

通过 ubus JSON-RPC 接口远程管理 OpenWrt 路由器，
用于 AEGIS 防御系统向边缘路由器下发封锁规则。

核心功能：
1. ubus JSON-RPC 认证和会话管理
2. UCI 防火墙规则增删改查
3. 批量下发 AEGIS 威胁封锁策略
4. 路由器状态监控（接口、DHCP、WiFi）
5. 多路由器统一管理

依赖：
- requests（HTTP客户端）
- 目标路由器需运行 OpenWrt + uhttpd + rpcd

架构参考：
- OpenWrt ubus: https://openwrt.org/docs/techref/ubus
- JSON-RPC over HTTP: uhttpd /ubus endpoint
- UCI防火墙: https://openwrt.org/docs/guide-user/firewall/firewall_configuration

By: Claude + 430
"""

import json
import time
import logging
import hashlib
import threading
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logger.warning("requests 未安装，OpenWrt控制器不可用。安装: pip install requests")


@dataclass
class FirewallRule:
    """OpenWrt 防火墙规则"""
    name: str
    src: str = "wan"            # 源Zone
    dest: str = ""              # 目标Zone（空=input链）
    proto: str = "tcp udp"      # 协议
    src_ip: str = ""            # 源IP/CIDR
    dest_ip: str = ""           # 目标IP/CIDR
    dest_port: str = ""         # 目标端口
    target: str = "DROP"        # DROP/REJECT/ACCEPT
    enabled: bool = True
    family: str = "ipv4"        # ipv4/ipv6


@dataclass
class RouterInfo:
    """OpenWrt 路由器信息"""
    host: str
    port: int = 80
    username: str = "root"
    password: str = ""
    use_https: bool = False
    alias: str = ""  # 友好名称
    region: str = ""  # 地理区域（对应AEGIS节点区域）


class UbusSession:
    """
    ubus JSON-RPC 会话

    管理与单个 OpenWrt 路由器的 ubus 会话，
    包括认证、会话保活、RPC调用。
    """

    # ubus JSON-RPC 无认证时使用的空 session ID
    UNAUTHENTICATED_SID = "00000000000000000000000000000000"

    def __init__(self, router: RouterInfo):
        """
        初始化 ubus 会话

        参数:
            router: 路由器连接信息
        """
        if not HAS_REQUESTS:
            raise RuntimeError("requests 未安装，无法创建 ubus 会话")

        self.router = router
        self._session_id = self.UNAUTHENTICATED_SID
        self._session_expires = 0.0
        self._rpc_id = 0

        protocol = "https" if router.use_https else "http"
        self.base_url = f"{protocol}://{router.host}:{router.port}/ubus"

        # 请求超时
        self.timeout = 10.0

        # requests Session（连接复用）
        self._http = requests.Session()
        if router.use_https:
            # 允许自签证书（路由器常用自签）
            self._http.verify = False

    def _next_rpc_id(self) -> int:
        """生成递增的 RPC ID"""
        self._rpc_id += 1
        return self._rpc_id

    def login(self) -> bool:
        """
        ubus 认证登录

        调用 session.login RPC，获取 session ID。
        会话默认有效期 300秒，需要定期续约。

        返回:
            是否登录成功
        """
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_rpc_id(),
            "method": "call",
            "params": [
                self.UNAUTHENTICATED_SID,
                "session",
                "login",
                {
                    "username": self.router.username,
                    "password": self.router.password,
                }
            ]
        }

        try:
            resp = self._http.post(
                self.base_url,
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            # ubus RPC 响应格式: {"result": [0, {"ubus_rpc_session": "..."}]}
            result = data.get("result", [])
            if len(result) >= 2 and result[0] == 0:
                session_data = result[1]
                self._session_id = session_data.get("ubus_rpc_session", "")
                timeout_secs = session_data.get("timeout", 300)
                self._session_expires = time.time() + timeout_secs - 30  # 提前30秒过期

                logger.info(
                    f"OpenWrt 登录成功: {self.router.host} "
                    f"(SID: {self._session_id[:8]}..., TTL: {timeout_secs}s)"
                )
                return True
            else:
                error_code = result[0] if result else "unknown"
                logger.error(f"OpenWrt 登录失败: {self.router.host} (code: {error_code})")
                return False

        except requests.ConnectionError as e:
            logger.error(f"OpenWrt 连接失败: {self.router.host} ({e})")
            return False
        except requests.Timeout:
            logger.error(f"OpenWrt 登录超时: {self.router.host}")
            return False
        except Exception as e:
            logger.error(f"OpenWrt 登录异常: {self.router.host} ({e})")
            return False

    def _ensure_session(self) -> bool:
        """确保会话有效，过期则重新登录"""
        if time.time() >= self._session_expires:
            return self.login()
        return True

    def call(
        self,
        ubus_object: str,
        method: str,
        params: Dict[str, Any] = None,
    ) -> Tuple[int, Optional[Dict]]:
        """
        调用 ubus RPC 方法

        参数:
            ubus_object: ubus 对象名 (如 "uci", "system", "network.interface")
            method: 方法名 (如 "get", "set", "commit")
            params: 方法参数

        返回:
            (error_code, result_dict)
            error_code 0 = 成功
        """
        if not self._ensure_session():
            return (-1, None)

        payload = {
            "jsonrpc": "2.0",
            "id": self._next_rpc_id(),
            "method": "call",
            "params": [
                self._session_id,
                ubus_object,
                method,
                params or {},
            ]
        }

        try:
            resp = self._http.post(
                self.base_url,
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            result = data.get("result", [])
            if not result:
                return (-1, None)

            error_code = result[0] if len(result) > 0 else -1
            result_data = result[1] if len(result) > 1 else None

            if error_code != 0:
                logger.debug(
                    f"ubus {ubus_object}.{method} 失败: code={error_code}"
                )

            return (error_code, result_data)

        except requests.ConnectionError as e:
            logger.error(f"ubus 连接失败: {self.router.host} ({e})")
            return (-1, None)
        except requests.Timeout:
            logger.error(f"ubus 请求超时: {self.router.host}")
            return (-1, None)
        except Exception as e:
            logger.error(f"ubus 请求异常: {e}")
            return (-1, None)

    def close(self):
        """关闭会话"""
        if self._session_id != self.UNAUTHENTICATED_SID:
            try:
                self.call("session", "destroy", {"ubus_rpc_session": self._session_id})
            except Exception:
                pass
            self._session_id = self.UNAUTHENTICATED_SID

        self._http.close()


class OpenWrtFirewallController:
    """
    OpenWrt 防火墙控制器

    通过 ubus JSON-RPC + UCI 接口管理防火墙规则。
    AEGIS 威胁检测结果通过此控制器下发到 OpenWrt 路由器。
    """

    # AEGIS 管理的规则名称前缀（避免与用户规则冲突）
    AEGIS_RULE_PREFIX = "aegis_"

    def __init__(self, session: UbusSession):
        """
        初始化防火墙控制器

        参数:
            session: ubus 会话
        """
        self.session = session

    def get_all_rules(self) -> List[Dict[str, Any]]:
        """
        获取所有防火墙规则

        通过 uci get firewall 获取所有 rule 类型的条目。
        """
        code, result = self.session.call("uci", "get", {
            "config": "firewall",
            "type": "rule",
        })

        if code != 0 or not result:
            logger.error(f"获取防火墙规则失败: code={code}")
            return []

        # UCI 返回格式: {"values": {"cfg01": {...}, "cfg02": {...}}}
        values = result.get("values", {})
        rules = []
        for section_name, rule_data in values.items():
            rule_data['_section'] = section_name
            rules.append(rule_data)

        return rules

    def get_aegis_rules(self) -> List[Dict[str, Any]]:
        """获取所有 AEGIS 管理的防火墙规则"""
        all_rules = self.get_all_rules()
        return [
            r for r in all_rules
            if r.get('name', '').startswith(self.AEGIS_RULE_PREFIX)
        ]

    def add_rule(self, rule: FirewallRule) -> Optional[str]:
        """
        添加防火墙规则

        通过 UCI add + set + commit + reload 实现。

        参数:
            rule: 防火墙规则

        返回:
            UCI section 名称，失败返回 None
        """
        # Step 1: 添加新的 firewall rule section
        code, result = self.session.call("uci", "add", {
            "config": "firewall",
            "type": "rule",
            "name": rule.name,
        })

        if code != 0:
            logger.error(f"UCI add 失败: code={code}")
            return None

        section = result.get("section") if result else None
        if not section:
            logger.error("UCI add 未返回 section 名称")
            return None

        # Step 2: 设置规则属性
        values = {
            "name": rule.name,
            "src": rule.src,
            "proto": rule.proto,
            "target": rule.target,
            "enabled": "1" if rule.enabled else "0",
            "family": rule.family,
        }

        if rule.dest:
            values["dest"] = rule.dest
        if rule.src_ip:
            values["src_ip"] = rule.src_ip
        if rule.dest_ip:
            values["dest_ip"] = rule.dest_ip
        if rule.dest_port:
            values["dest_port"] = rule.dest_port

        code, _ = self.session.call("uci", "set", {
            "config": "firewall",
            "section": section,
            "values": values,
        })

        if code != 0:
            logger.error(f"UCI set 失败: code={code}, section={section}")
            return None

        # Step 3: 提交更改
        if not self._commit_and_reload():
            return None

        logger.info(
            f"防火墙规则已添加: {rule.name} "
            f"({rule.src_ip or '*'} -> {rule.dest_ip or '*'}:{rule.dest_port or '*'} "
            f"= {rule.target})"
        )

        return section

    def delete_rule(self, section_name: str) -> bool:
        """
        删除防火墙规则

        参数:
            section_name: UCI section 名称
        """
        code, _ = self.session.call("uci", "delete", {
            "config": "firewall",
            "section": section_name,
        })

        if code != 0:
            logger.error(f"UCI delete 失败: code={code}, section={section_name}")
            return False

        if not self._commit_and_reload():
            return False

        logger.info(f"防火墙规则已删除: {section_name}")
        return True

    def block_ip(self, ip: str, reason: str = "", ttl: int = 0) -> Optional[str]:
        """
        封锁指定IP

        便捷方法：创建 DROP 规则阻止来自该IP的所有流量。

        参数:
            ip: 要封锁的IP地址或CIDR
            reason: 封锁原因（存入规则名称）
            ttl: 封锁有效期（秒），0=永久

        返回:
            UCI section 名称
        """
        # 生成规则名称
        ip_hash = hashlib.md5(ip.encode()).hexdigest()[:8]
        rule_name = f"{self.AEGIS_RULE_PREFIX}block_{ip_hash}"

        rule = FirewallRule(
            name=rule_name,
            src="wan",
            src_ip=ip,
            target="DROP",
        )

        section = self.add_rule(rule)

        # 如果有 TTL，启动定时清理线程
        if section and ttl > 0:
            timer = threading.Timer(
                ttl,
                self._auto_unblock,
                args=(section, ip),
            )
            timer.daemon = True
            timer.start()

        return section

    def unblock_ip(self, ip: str) -> bool:
        """
        解封指定IP

        查找并删除对应的 AEGIS 封锁规则。
        """
        ip_hash = hashlib.md5(ip.encode()).hexdigest()[:8]
        target_name = f"{self.AEGIS_RULE_PREFIX}block_{ip_hash}"

        aegis_rules = self.get_aegis_rules()
        for rule in aegis_rules:
            if rule.get('name') == target_name:
                return self.delete_rule(rule['_section'])

        logger.warning(f"未找到IP {ip} 的封锁规则")
        return False

    def _auto_unblock(self, section: str, ip: str):
        """TTL 到期自动解封"""
        try:
            self.delete_rule(section)
            logger.info(f"TTL到期，自动解封: {ip}")
        except Exception as e:
            logger.error(f"自动解封失败: {ip} ({e})")

    def clear_aegis_rules(self) -> int:
        """
        清除所有 AEGIS 管理的防火墙规则

        返回:
            删除的规则数量
        """
        aegis_rules = self.get_aegis_rules()
        deleted = 0

        for rule in aegis_rules:
            section = rule.get('_section')
            if section:
                code, _ = self.session.call("uci", "delete", {
                    "config": "firewall",
                    "section": section,
                })
                if code == 0:
                    deleted += 1

        if deleted > 0:
            self._commit_and_reload()
            logger.info(f"已清除 {deleted} 条 AEGIS 防火墙规则")

        return deleted

    def _commit_and_reload(self) -> bool:
        """提交 UCI 更改并重新加载防火墙"""
        # commit
        code, _ = self.session.call("uci", "commit", {
            "config": "firewall",
        })

        if code != 0:
            logger.error(f"UCI commit 失败: code={code}")
            return False

        # reload (fw3/fw4 reload)
        # 通过 uci commit 时 rpcd 会自动触发 service reload
        # 但为确保生效，显式调用 luci.sys exec
        code, _ = self.session.call("file", "exec", {
            "command": "/etc/init.d/firewall",
            "params": ["reload"],
        })

        if code != 0:
            # 备用方案: 直接调用 fw3/fw4
            self.session.call("file", "exec", {
                "command": "/sbin/fw4",
                "params": ["reload"],
            })

        return True

    def batch_block_ips(self, ip_list: List[str], reason: str = "aegis_threat") -> Dict[str, Any]:
        """
        批量封锁IP列表

        优化：先添加所有规则，最后只 commit+reload 一次。

        参数:
            ip_list: IP地址列表
            reason: 封锁原因

        返回:
            {"success": N, "failed": N, "sections": [...]}
        """
        sections = []
        failed = 0

        for ip in ip_list:
            ip_hash = hashlib.md5(ip.encode()).hexdigest()[:8]
            rule_name = f"{self.AEGIS_RULE_PREFIX}block_{ip_hash}"

            # add section
            code, result = self.session.call("uci", "add", {
                "config": "firewall",
                "type": "rule",
                "name": rule_name,
            })

            if code != 0 or not result:
                failed += 1
                continue

            section = result.get("section")
            if not section:
                failed += 1
                continue

            # set values
            code, _ = self.session.call("uci", "set", {
                "config": "firewall",
                "section": section,
                "values": {
                    "name": rule_name,
                    "src": "wan",
                    "src_ip": ip,
                    "proto": "tcp udp",
                    "target": "DROP",
                    "enabled": "1",
                    "family": "ipv4",
                },
            })

            if code == 0:
                sections.append(section)
            else:
                failed += 1

        # 一次性 commit + reload
        if sections:
            self._commit_and_reload()

        logger.info(f"批量封锁: {len(sections)} 成功, {failed} 失败 (共 {len(ip_list)} 个IP)")

        return {
            "success": len(sections),
            "failed": failed,
            "sections": sections,
        }


class OpenWrtSystemMonitor:
    """
    OpenWrt 系统监控

    获取路由器系统信息、网络接口状态、DHCP租约等。
    """

    def __init__(self, session: UbusSession):
        self.session = session

    def get_system_board(self) -> Optional[Dict]:
        """获取系统板卡信息（型号、架构等）"""
        code, result = self.session.call("system", "board", {})
        return result if code == 0 else None

    def get_system_info(self) -> Optional[Dict]:
        """获取系统信息（负载、内存、运行时间等）"""
        code, result = self.session.call("system", "info", {})
        return result if code == 0 else None

    def get_network_interfaces(self) -> List[Dict]:
        """获取所有网络接口状态"""
        code, result = self.session.call("network.interface", "dump", {})
        if code != 0 or not result:
            return []
        return result.get("interface", [])

    def get_dhcp_leases(self) -> List[Dict]:
        """获取 DHCP 租约列表"""
        code, result = self.session.call("dhcp", "ipv4leases", {})
        if code != 0 or not result:
            return []

        leases = []
        for device_leases in result.get("device", {}).values():
            for lease in device_leases.get("leases", []):
                leases.append(lease)
        return leases

    def get_wireless_status(self) -> List[Dict]:
        """获取无线接口状态"""
        code, result = self.session.call("network.wireless", "status", {})
        if code != 0 or not result:
            return []

        radios = []
        for radio_name, radio_data in result.items():
            radio_data['radio'] = radio_name
            radios.append(radio_data)
        return radios

    def get_connected_clients(self) -> List[Dict]:
        """获取所有连接的客户端（WiFi + 有线）"""
        clients = []

        # WiFi客户端
        wireless = self.get_wireless_status()
        for radio in wireless:
            for iface in radio.get("interfaces", []):
                ifname = iface.get("ifname", "")
                # 获取关联列表
                code, result = self.session.call("iwinfo", "assoclist", {
                    "device": ifname,
                })
                if code == 0 and result:
                    for assoc in result.get("results", []):
                        clients.append({
                            'mac': assoc.get('mac', ''),
                            'signal': assoc.get('signal', 0),
                            'noise': assoc.get('noise', 0),
                            'type': 'wifi',
                            'interface': ifname,
                            'rx_rate': assoc.get('rx', {}).get('rate', 0),
                            'tx_rate': assoc.get('tx', {}).get('rate', 0),
                        })

        # DHCP客户端（有线+WiFi）
        dhcp_leases = self.get_dhcp_leases()
        dhcp_macs = {c['mac'] for c in clients}
        for lease in dhcp_leases:
            mac = lease.get('macaddr', '')
            if mac not in dhcp_macs:
                clients.append({
                    'mac': mac,
                    'ip': lease.get('ipaddr', ''),
                    'hostname': lease.get('hostname', ''),
                    'type': 'wired',
                    'expires': lease.get('expires', 0),
                })

        return clients


class OpenWrtFleetManager:
    """
    OpenWrt 路由器集群管理器

    管理多台 OpenWrt 路由器，统一下发 AEGIS 防御策略。
    """

    def __init__(self):
        self._routers: Dict[str, RouterInfo] = {}
        self._sessions: Dict[str, UbusSession] = {}
        self._firewalls: Dict[str, OpenWrtFirewallController] = {}
        self._monitors: Dict[str, OpenWrtSystemMonitor] = {}
        self._lock = threading.Lock()

        # 统计
        self.stats = {
            'routers_registered': 0,
            'routers_connected': 0,
            'rules_deployed': 0,
            'ips_blocked': 0,
            'deploy_failures': 0,
        }

    def add_router(self, router: RouterInfo) -> str:
        """
        注册路由器

        参数:
            router: 路由器连接信息

        返回:
            路由器ID
        """
        router_id = router.alias or f"{router.host}:{router.port}"

        with self._lock:
            self._routers[router_id] = router
            self.stats['routers_registered'] += 1

        logger.info(f"路由器已注册: {router_id} (区域: {router.region})")
        return router_id

    def connect(self, router_id: str) -> bool:
        """
        连接到路由器

        参数:
            router_id: 路由器ID
        """
        with self._lock:
            router = self._routers.get(router_id)
            if not router:
                logger.error(f"路由器未注册: {router_id}")
                return False

        session = UbusSession(router)
        if not session.login():
            return False

        with self._lock:
            self._sessions[router_id] = session
            self._firewalls[router_id] = OpenWrtFirewallController(session)
            self._monitors[router_id] = OpenWrtSystemMonitor(session)
            self.stats['routers_connected'] += 1

        return True

    def connect_all(self) -> Dict[str, bool]:
        """连接所有已注册的路由器"""
        results = {}
        for router_id in list(self._routers.keys()):
            results[router_id] = self.connect(router_id)
        return results

    def disconnect(self, router_id: str):
        """断开路由器连接"""
        with self._lock:
            session = self._sessions.pop(router_id, None)
            self._firewalls.pop(router_id, None)
            self._monitors.pop(router_id, None)

        if session:
            session.close()
            logger.info(f"路由器已断开: {router_id}")

    def disconnect_all(self):
        """断开所有路由器连接"""
        for router_id in list(self._sessions.keys()):
            self.disconnect(router_id)

    def deploy_block_rule(
        self,
        ip: str,
        reason: str = "",
        ttl: int = 0,
        target_routers: List[str] = None,
    ) -> Dict[str, bool]:
        """
        向路由器集群部署封锁规则

        参数:
            ip: 要封锁的IP
            reason: 封锁原因
            ttl: 有效期（秒）
            target_routers: 目标路由器列表（None=所有）

        返回:
            {router_id: success}
        """
        results = {}
        target_ids = target_routers or list(self._firewalls.keys())

        for router_id in target_ids:
            fw = self._firewalls.get(router_id)
            if not fw:
                results[router_id] = False
                self.stats['deploy_failures'] += 1
                continue

            try:
                section = fw.block_ip(ip, reason=reason, ttl=ttl)
                results[router_id] = section is not None
                if section:
                    self.stats['rules_deployed'] += 1
                else:
                    self.stats['deploy_failures'] += 1
            except Exception as e:
                logger.error(f"部署封锁规则到 {router_id} 失败: {e}")
                results[router_id] = False
                self.stats['deploy_failures'] += 1

        if any(results.values()):
            self.stats['ips_blocked'] += 1
            logger.info(
                f"封锁规则已部署: {ip} → "
                f"{sum(results.values())}/{len(results)} 台路由器"
            )

        return results

    def deploy_batch_block(
        self,
        ip_list: List[str],
        reason: str = "aegis_threat",
        target_routers: List[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        向路由器集群批量部署封锁规则

        参数:
            ip_list: IP列表
            reason: 封锁原因
            target_routers: 目标路由器列表

        返回:
            {router_id: {"success": N, "failed": N}}
        """
        results = {}
        target_ids = target_routers or list(self._firewalls.keys())

        for router_id in target_ids:
            fw = self._firewalls.get(router_id)
            if not fw:
                results[router_id] = {"success": 0, "failed": len(ip_list)}
                continue

            try:
                result = fw.batch_block_ips(ip_list, reason=reason)
                results[router_id] = result
                self.stats['rules_deployed'] += result['success']
                self.stats['deploy_failures'] += result['failed']
            except Exception as e:
                logger.error(f"批量部署到 {router_id} 失败: {e}")
                results[router_id] = {"success": 0, "failed": len(ip_list)}

        self.stats['ips_blocked'] += len(ip_list)
        return results

    def clear_all_aegis_rules(self, target_routers: List[str] = None) -> Dict[str, int]:
        """
        清除所有路由器上的 AEGIS 规则

        返回:
            {router_id: deleted_count}
        """
        results = {}
        target_ids = target_routers or list(self._firewalls.keys())

        for router_id in target_ids:
            fw = self._firewalls.get(router_id)
            if fw:
                try:
                    results[router_id] = fw.clear_aegis_rules()
                except Exception as e:
                    logger.error(f"清除 {router_id} 规则失败: {e}")
                    results[router_id] = 0

        return results

    def get_fleet_status(self) -> Dict[str, Any]:
        """获取路由器集群状态"""
        statuses = {}

        for router_id, monitor in self._monitors.items():
            try:
                sys_info = monitor.get_system_info()
                board = monitor.get_system_board()
                clients = monitor.get_connected_clients()
                aegis_rules = self._firewalls[router_id].get_aegis_rules()

                statuses[router_id] = {
                    'region': self._routers[router_id].region,
                    'model': board.get('model', 'unknown') if board else 'unknown',
                    'uptime': sys_info.get('uptime', 0) if sys_info else 0,
                    'load': sys_info.get('load', []) if sys_info else [],
                    'memory': sys_info.get('memory', {}) if sys_info else {},
                    'connected_clients': len(clients),
                    'aegis_rules': len(aegis_rules),
                    'status': 'online',
                }
            except Exception as e:
                statuses[router_id] = {
                    'region': self._routers.get(router_id, RouterInfo(host="")).region,
                    'status': 'error',
                    'error': str(e),
                }

        return {
            'routers': statuses,
            'stats': self.stats,
        }
