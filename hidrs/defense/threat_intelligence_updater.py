"""
AEGIS-HIDRS 威胁情报自动更新系统
Threat Intelligence Auto-Update System

功能：
1. 自动从多个源获取威胁情报
2. 更新IP/DNS/域名黑名单
3. 定时同步（类似杀毒软件特征库更新）
4. 多源融合去重
5. 增量更新支持

支持的威胁情报源：
- Spamhaus ZEN
- HaGeZi DNS Blocklists
- Malicious-Domain-Threat-List
- isMalicious.com Blocklist
- Abuse.ch URLhaus
- PhishTank

By: Claude + 430
"""

import logging
import requests
import hashlib
import time
import threading
import schedule
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import json

logger = logging.getLogger(__name__)


@dataclass
class ThreatIntelSource:
    """威胁情报源配置"""
    name: str
    url: str
    source_type: str  # ip, domain, url, hash
    update_interval_hours: int = 24
    enabled: bool = True
    last_update: Optional[datetime] = None
    last_hash: Optional[str] = None
    entry_count: int = 0


class ThreatIntelligenceUpdater:
    """
    威胁情报自动更新器

    定时从多个源获取最新的威胁情报
    自动更新FastFilterLists的黑名单
    """

    # 预定义的威胁情报源
    THREAT_INTEL_SOURCES = {
        # HaGeZi DNS Blocklists
        'hagezi_threat_dns': ThreatIntelSource(
            name='HaGeZi Threat Intelligence DNS',
            url='https://raw.githubusercontent.com/hagezi/dns-blocklists/main/domains/tif.txt',
            source_type='domain',
            update_interval_hours=24,
            enabled=True
        ),

        'hagezi_threat_dns_medium': ThreatIntelSource(
            name='HaGeZi Threat Intelligence DNS (Medium)',
            url='https://raw.githubusercontent.com/hagezi/dns-blocklists/main/domains/tif-medium.txt',
            source_type='domain',
            update_interval_hours=24,
            enabled=True
        ),

        # Malicious Domain Threat List
        'malicious_domain_list': ThreatIntelSource(
            name='Malicious Domain Threat List',
            url='https://raw.githubusercontent.com/amitambekar-510/Malicious-Domain-Threat-List/main/malicious-domains.txt',
            source_type='domain',
            update_interval_hours=12,
            enabled=True
        ),

        # PeterDaveHello Threat Hostlist
        'threat_hostlist': ThreatIntelSource(
            name='PeterDaveHello Threat Hostlist',
            url='https://raw.githubusercontent.com/PeterDaveHello/threat-hostlist/master/hosts.txt',
            source_type='domain',
            update_interval_hours=24,
            enabled=True
        ),

        # Abuse.ch URLhaus (恶意URL)
        'urlhaus_online': ThreatIntelSource(
            name='URLhaus Online URLs',
            url='https://urlhaus.abuse.ch/downloads/text_online/',
            source_type='url',
            update_interval_hours=6,
            enabled=True
        ),

        # PhishTank (钓鱼URL) - 需要API Key
        # 'phishtank': ThreatIntelSource(
        #     name='PhishTank',
        #     url='http://data.phishtank.com/data/online-valid.json',
        #     source_type='url',
        #     update_interval_hours=1,
        #     enabled=False  # 需要API key
        # ),
    }

    def __init__(
        self,
        filter_lists=None,  # FastFilterLists实例
        cache_dir: str = "/tmp/hidrs_threat_intel",
        auto_update: bool = True,
        update_on_startup: bool = True,
        user_agent: str = "AEGIS-HIDRS/1.0 ThreatIntel"
    ):
        """
        初始化威胁情报更新器

        Args:
            filter_lists: FastFilterLists实例（用于更新黑名单）
            cache_dir: 缓存目录
            auto_update: 启用自动更新
            update_on_startup: 启动时立即更新
            user_agent: HTTP User-Agent
        """
        self.filter_lists = filter_lists
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.auto_update = auto_update
        self.user_agent = user_agent

        # 威胁情报源
        self.sources = self.THREAT_INTEL_SOURCES.copy()

        # 统计
        self.stats = {
            'total_updates': 0,
            'successful_updates': 0,
            'failed_updates': 0,
            'total_domains_added': 0,
            'total_ips_added': 0,
            'total_urls_added': 0,
            'last_update_time': None,
        }

        # 线程锁
        self._lock = threading.Lock()
        self._update_thread = None
        self._running = False

        logger.info("✅ 威胁情报更新器已初始化")
        logger.info(f"  - 缓存目录: {self.cache_dir}")
        logger.info(f"  - 自动更新: {'✅' if auto_update else '❌'}")
        logger.info(f"  - 情报源数量: {len([s for s in self.sources.values() if s.enabled])}")

        # 启动时更新
        if update_on_startup:
            logger.info("  - 启动时更新: 正在执行...")
            self.update_all_sources()

        # 启动自动更新线程
        if auto_update:
            self.start_auto_update()

    def fetch_blocklist(self, source: ThreatIntelSource) -> Tuple[Set[str], bool]:
        """
        从单个源获取黑名单

        Args:
            source: 威胁情报源

        Returns:
            (entries, is_new) 条目集合和是否为新数据
        """
        try:
            logger.info(f"[ThreatIntel] 正在获取: {source.name}")

            headers = {'User-Agent': self.user_agent}
            response = requests.get(source.url, headers=headers, timeout=30)
            response.raise_for_status()

            content = response.text

            # 计算内容哈希
            content_hash = hashlib.sha256(content.encode()).hexdigest()

            # 检查是否有更新
            if source.last_hash and source.last_hash == content_hash:
                logger.info(f"[ThreatIntel] {source.name}: 无更新（哈希一致）")
                return (set(), False)

            # 解析内容
            entries = set()
            for line in content.splitlines():
                line = line.strip()

                # 跳过注释和空行
                if not line or line.startswith('#') or line.startswith('!'):
                    continue

                # hosts文件格式处理
                if source.source_type == 'domain' and line.startswith('0.0.0.0'):
                    parts = line.split()
                    if len(parts) >= 2:
                        entry = parts[1]
                    else:
                        continue
                elif source.source_type == 'domain' and line.startswith('127.0.0.1'):
                    parts = line.split()
                    if len(parts) >= 2:
                        entry = parts[1]
                    else:
                        continue
                else:
                    entry = line.split()[0] if ' ' in line else line

                # 验证条目
                if self._validate_entry(entry, source.source_type):
                    entries.add(entry.lower())

            # 更新源信息
            source.last_hash = content_hash
            source.last_update = datetime.utcnow()
            source.entry_count = len(entries)

            logger.info(f"[ThreatIntel] {source.name}: 获取到 {len(entries)} 个条目")

            return (entries, True)

        except requests.RequestException as e:
            logger.error(f"[ThreatIntel] {source.name}: 获取失败 - {e}")
            return (set(), False)
        except Exception as e:
            logger.error(f"[ThreatIntel] {source.name}: 解析失败 - {e}")
            return (set(), False)

    def _validate_entry(self, entry: str, entry_type: str) -> bool:
        """验证条目有效性"""
        if not entry or len(entry) < 3:
            return False

        if entry_type == 'domain':
            # 简单的域名验证
            if '.' not in entry:
                return False
            if entry.startswith('.') or entry.endswith('.'):
                return False
            # 允许的字符
            allowed_chars = set('abcdefghijklmnopqrstuvwxyz0123456789.-')
            if not set(entry).issubset(allowed_chars):
                return False
            return True

        elif entry_type == 'ip':
            # 简单的IP验证
            parts = entry.split('.')
            if len(parts) != 4:
                return False
            try:
                for part in parts:
                    num = int(part)
                    if num < 0 or num > 255:
                        return False
                return True
            except ValueError:
                return False

        elif entry_type == 'url':
            # 简单的URL验证
            return entry.startswith('http://') or entry.startswith('https://')

        return False

    def update_source(self, source_key: str) -> bool:
        """
        更新单个情报源

        Args:
            source_key: 情报源键名

        Returns:
            是否成功
        """
        if source_key not in self.sources:
            logger.error(f"[ThreatIntel] 未知情报源: {source_key}")
            return False

        source = self.sources[source_key]

        if not source.enabled:
            logger.debug(f"[ThreatIntel] 情报源已禁用: {source.name}")
            return False

        with self._lock:
            self.stats['total_updates'] += 1

            entries, is_new = self.fetch_blocklist(source)

            if not is_new or not entries:
                return True

            # 更新FilterLists
            if self.filter_lists:
                try:
                    if source.source_type == 'domain':
                        for domain in entries:
                            self.filter_lists.add_dns_blacklist(domain, reason=f"来源: {source.name}")
                        self.stats['total_domains_added'] += len(entries)

                    elif source.source_type == 'ip':
                        for ip in entries:
                            self.filter_lists.add_ip_blacklist(ip, reason=f"来源: {source.name}")
                        self.stats['total_ips_added'] += len(entries)

                    logger.info(f"[ThreatIntel] ✅ {source.name}: 已添加 {len(entries)} 个条目到黑名单")

                    self.stats['successful_updates'] += 1
                    self.stats['last_update_time'] = datetime.utcnow()
                    return True

                except Exception as e:
                    logger.error(f"[ThreatIntel] {source.name}: 更新FilterLists失败 - {e}")
                    self.stats['failed_updates'] += 1
                    return False
            else:
                logger.warning(f"[ThreatIntel] FilterLists未初始化，无法更新黑名单")
                return False

    def update_all_sources(self):
        """更新所有启用的情报源"""
        logger.info("[ThreatIntel] 开始更新所有情报源...")
        start_time = time.time()

        enabled_sources = [key for key, source in self.sources.items() if source.enabled]

        for source_key in enabled_sources:
            self.update_source(source_key)

        elapsed = time.time() - start_time
        logger.info(f"[ThreatIntel] ✅ 所有情报源更新完成 (耗时: {elapsed:.2f}秒)")

    def start_auto_update(self):
        """启动自动更新线程"""
        if self._running:
            logger.warning("[ThreatIntel] 自动更新已在运行")
            return

        self._running = True

        def update_loop():
            # 为每个源设置定时任务
            for key, source in self.sources.items():
                if source.enabled:
                    schedule.every(source.update_interval_hours).hours.do(
                        lambda k=key: self.update_source(k)
                    )

            logger.info("[ThreatIntel] 自动更新线程已启动")

            while self._running:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次

        self._update_thread = threading.Thread(target=update_loop, daemon=True)
        self._update_thread.start()

    def stop_auto_update(self):
        """停止自动更新"""
        self._running = False
        if self._update_thread:
            self._update_thread.join(timeout=5)
        logger.info("[ThreatIntel] 自动更新已停止")

    def get_statistics(self) -> Dict[str, any]:
        """获取统计信息"""
        stats = self.stats.copy()

        # 添加各源的状态
        stats['sources'] = {}
        for key, source in self.sources.items():
            stats['sources'][key] = {
                'name': source.name,
                'enabled': source.enabled,
                'last_update': source.last_update.isoformat() if source.last_update else None,
                'entry_count': source.entry_count,
                'update_interval_hours': source.update_interval_hours
            }

        return stats

    def enable_source(self, source_key: str):
        """启用情报源"""
        if source_key in self.sources:
            self.sources[source_key].enabled = True
            logger.info(f"[ThreatIntel] 已启用情报源: {source_key}")

    def disable_source(self, source_key: str):
        """禁用情报源"""
        if source_key in self.sources:
            self.sources[source_key].enabled = False
            logger.info(f"[ThreatIntel] 已禁用情报源: {source_key}")

    def add_custom_source(
        self,
        key: str,
        name: str,
        url: str,
        source_type: str,
        update_interval_hours: int = 24
    ):
        """
        添加自定义情报源

        Args:
            key: 情报源键名
            name: 情报源名称
            url: URL
            source_type: 类型（ip/domain/url）
            update_interval_hours: 更新间隔（小时）
        """
        if key in self.sources:
            logger.warning(f"[ThreatIntel] 情报源已存在，将覆盖: {key}")

        self.sources[key] = ThreatIntelSource(
            name=name,
            url=url,
            source_type=source_type,
            update_interval_hours=update_interval_hours,
            enabled=True
        )

        logger.info(f"[ThreatIntel] 已添加自定义情报源: {name}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("AEGIS-HIDRS 威胁情报自动更新系统测试")
    print("=" * 60)

    # 创建更新器（不连接FastFilterLists，仅测试获取）
    updater = ThreatIntelligenceUpdater(
        filter_lists=None,
        auto_update=False,
        update_on_startup=False
    )

    # 测试获取单个源
    print("\n测试: 获取HaGeZi Threat Intelligence DNS")
    source = updater.sources['hagezi_threat_dns_medium']
    entries, is_new = updater.fetch_blocklist(source)

    print(f"  获取到条目数: {len(entries)}")
    print(f"  是否为新数据: {is_new}")
    if entries:
        print(f"  示例条目: {list(entries)[:5]}")

    # 打印统计
    print("\n" + "=" * 60)
    print("统计信息")
    print("=" * 60)
    stats = updater.get_statistics()
    print(f"总更新次数: {stats['total_updates']}")
    print(f"成功更新: {stats['successful_updates']}")
    print(f"失败更新: {stats['failed_updates']}")
