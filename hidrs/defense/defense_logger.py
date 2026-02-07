"""
AEGIS-HIDRS 增强型防御日志系统
Enhanced Hierarchical Defense Logger

功能：
1. 树形结构日志（层级显示）
2. Emoji图标支持
3. 节点ID标识
4. 多级缩进
5. 彩色输出（终端支持）
6. 统一日志格式

By: Claude + 430
"""

import logging
import sys
import os
from typing import List, Optional, Any, Dict
from datetime import datetime
from enum import Enum
from contextlib import contextmanager


class LogLevel(Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class DefenseLogger:
    """
    AEGIS-HIDRS防御日志器

    支持树形结构的层级日志输出

    示例:
        [AEGIS Node-US-West-01] 🛡️ 检测到异常流量
          ├─ 源IP: 45.123.67.89
          ├─ 请求速率: 100,000 req/s
          ├─ 威胁级别: CRITICAL
          └─ 决策: 立即启动防御
            ├─ 快速过滤: ✅ 阻断
            ├─ HLIG分析: ✅ 异常
            └─ 全局同步: ✅ 0.1秒完成
    """

    # 树形字符
    TREE_BRANCH = "├─"      # 分支
    TREE_LAST = "└─"        # 最后一个分支
    TREE_VERTICAL = "│"     # 垂直线
    TREE_SPACE = "  "       # 缩进空格

    # Emoji图标
    EMOJI = {
        'shield': '🛡️',
        'warning': '⚠️',
        'error': '❌',
        'success': '✅',
        'info': 'ℹ️',
        'fire': '🔥',
        'target': '🎯',
        'lock': '🔒',
        'unlock': '🔓',
        'attack': '⚔️',
        'defense': '🛡️',
        'sync': '🔄',
        'globe': '🌐',
        'alert': '🚨',
        'chart': '📊',
        'clock': '⏱️',
        'memory': '🧠',
        'cpu': '⚙️',
        'network': '🌐',
        'mail': '📧',
        'phishing': '🎣',
        'dns': '🌐',
        'ip': '📍',
    }

    # 颜色代码（ANSI）
    COLORS = {
        'reset': '\033[0m',
        'bold': '\033[1m',
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'magenta': '\033[95m',
        'cyan': '\033[96m',
        'white': '\033[97m',
        'gray': '\033[90m',
    }

    def __init__(
        self,
        node_id: str = "Node-Default",
        use_colors: bool = True,
        use_emoji: bool = True,
        base_logger: Optional[logging.Logger] = None
    ):
        """
        初始化防御日志器

        参数:
            node_id: 节点ID（如: "Node-US-West-01"）
            use_colors: 是否使用颜色
            use_emoji: 是否使用emoji
            base_logger: 基础logger（可选，如果不提供则创建新的）
        """
        self.node_id = node_id
        self.use_colors = use_colors and self._supports_color()
        self.use_emoji = use_emoji

        # 获取或创建logger
        if base_logger:
            self.logger = base_logger
        else:
            self.logger = logging.getLogger(f"AEGIS.{node_id}")
            if not self.logger.handlers:
                handler = logging.StreamHandler(sys.stdout)
                formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
                self.logger.setLevel(logging.INFO)

        # 当前缩进级别
        self._indent_level = 0
        self._indent_stack = []  # 存储每级的是否是最后一项

    def _supports_color(self) -> bool:
        """检测终端是否支持颜色"""
        # Windows终端支持检查
        if sys.platform == 'win32':
            return os.environ.get('TERM') or sys.stdout.isatty()

        # Unix-like系统
        return sys.stdout.isatty()

    def _colorize(self, text: str, color: str) -> str:
        """给文本添加颜色"""
        if not self.use_colors:
            return text

        color_code = self.COLORS.get(color, '')
        reset = self.COLORS['reset']
        return f"{color_code}{text}{reset}"

    def _get_emoji(self, name: str) -> str:
        """获取emoji图标"""
        if not self.use_emoji:
            return ''
        return self.EMOJI.get(name, '')

    def _format_prefix(self) -> str:
        """生成缩进前缀"""
        if self._indent_level == 0:
            return f"[AEGIS {self.node_id}]"

        # 构建缩进前缀
        prefix_parts = []
        for i, is_last in enumerate(self._indent_stack[:-1]):
            if is_last:
                prefix_parts.append(self.TREE_SPACE)
            else:
                prefix_parts.append(self.TREE_VERTICAL + " ")

        # 最后一级
        if self._indent_stack:
            if self._indent_stack[-1]:
                prefix_parts.append(self.TREE_LAST + " ")
            else:
                prefix_parts.append(self.TREE_BRANCH + " ")

        return "".join(prefix_parts)

    def log(
        self,
        message: str,
        level: str = "INFO",
        emoji: Optional[str] = None,
        color: Optional[str] = None,
        is_last: bool = False
    ):
        """
        输出日志

        参数:
            message: 日志消息
            level: 日志级别
            emoji: emoji名称
            color: 颜色名称
            is_last: 是否是当前级别的最后一项
        """
        # 获取前缀
        prefix = self._format_prefix()

        # 添加emoji
        if emoji:
            emoji_icon = self._get_emoji(emoji) + " "
        else:
            emoji_icon = ""

        # 组合消息
        full_message = f"{prefix} {emoji_icon}{message}"

        # 添加颜色
        if color:
            full_message = self._colorize(full_message, color)

        # 输出到logger
        level_upper = level.upper()
        if level_upper == "DEBUG":
            self.logger.debug(full_message)
        elif level_upper == "INFO":
            self.logger.info(full_message)
        elif level_upper == "WARNING":
            self.logger.warning(full_message)
        elif level_upper == "ERROR":
            self.logger.error(full_message)
        elif level_upper == "CRITICAL":
            self.logger.critical(full_message)
        else:
            self.logger.info(full_message)

    @contextmanager
    def indent(self, is_last: bool = False):
        """
        缩进上下文管理器

        使用方法:
            with logger.indent():
                logger.log("子项1")
                logger.log("子项2", is_last=True)
        """
        self._indent_level += 1
        self._indent_stack.append(is_last)
        try:
            yield
        finally:
            self._indent_level -= 1
            self._indent_stack.pop()

    # 便捷方法
    def info(self, message: str, emoji: Optional[str] = None, is_last: bool = False):
        """INFO级别日志"""
        self.log(message, level="INFO", emoji=emoji, is_last=is_last)

    def warning(self, message: str, emoji: Optional[str] = 'warning', is_last: bool = False):
        """WARNING级别日志"""
        self.log(message, level="WARNING", emoji=emoji, color='yellow', is_last=is_last)

    def error(self, message: str, emoji: Optional[str] = 'error', is_last: bool = False):
        """ERROR级别日志"""
        self.log(message, level="ERROR", emoji=emoji, color='red', is_last=is_last)

    def success(self, message: str, emoji: Optional[str] = 'success', is_last: bool = False):
        """成功日志"""
        self.log(message, level="INFO", emoji=emoji, color='green', is_last=is_last)

    def attack_detected(
        self,
        src_ip: str,
        attack_type: str,
        threat_level: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        攻击检测日志（预定义格式）

        示例输出:
            [AEGIS Node-US-West-01] 🛡️ 检测到异常流量
              ├─ 源IP: 45.123.67.89
              ├─ 攻击类型: DDoS
              ├─ 威胁级别: CRITICAL
              └─ 决策: 立即启动防御
        """
        self.log(
            f"检测到异常流量",
            level="WARNING",
            emoji='shield',
            color='yellow'
        )

        with self.indent():
            self.log(f"源IP: {src_ip}", emoji='ip')
            self.log(f"攻击类型: {attack_type}", emoji='attack')

            # 威胁级别颜色
            threat_color = {
                'LOW': 'green',
                'MEDIUM': 'yellow',
                'HIGH': 'yellow',
                'CRITICAL': 'red'
            }.get(threat_level, 'white')

            self.log(
                f"威胁级别: {threat_level}",
                emoji='fire',
                color=threat_color
            )

            # 额外详情
            if details:
                for key, value in details.items():
                    self.log(f"{key}: {value}")

    def defense_action(
        self,
        action: str,
        result: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        防御动作日志（预定义格式）

        示例输出:
            [AEGIS Node-US-West-01] 🎯 决策: 立即启动防御
              ├─ 快速过滤: ✅ 阻断
              ├─ HLIG分析: ✅ 异常
              └─ 全局同步: ✅ 0.1秒完成
        """
        self.log(f"决策: {action}", emoji='target', color='cyan')

        if details:
            with self.indent():
                items = list(details.items())
                for i, (key, value) in enumerate(items):
                    is_last = (i == len(items) - 1)

                    # 判断是否成功
                    if '✅' in str(value) or 'success' in str(value).lower():
                        emoji = 'success'
                        color = 'green'
                    elif '❌' in str(value) or 'fail' in str(value).lower():
                        emoji = 'error'
                        color = 'red'
                    else:
                        emoji = None
                        color = None

                    self.log(f"{key}: {value}", emoji=emoji, color=color, is_last=is_last)

    def performance_metrics(
        self,
        metrics: Dict[str, Any],
        title: str = "性能指标"
    ):
        """
        性能指标日志（预定义格式）

        示例输出:
            [AEGIS Node-US-West-01] 📊 性能指标
              ├─ 处理包数: 1,000,000
              ├─ 阻断数: 127,439
              ├─ CPU使用率: 43%
              └─ 平均延迟: 0.3ms
        """
        self.log(title, emoji='chart', color='blue')

        with self.indent():
            items = list(metrics.items())
            for i, (key, value) in enumerate(items):
                is_last = (i == len(items) - 1)
                self.log(f"{key}: {value}", is_last=is_last)

    def sync_status(
        self,
        node_count: int,
        sync_method: str,
        latency: float,
        status: str = "SUCCESS"
    ):
        """
        同步状态日志（预定义格式）

        示例输出:
            [AEGIS Node-US-West-01] 🔄 全球同步
              ├─ 节点数: 2,000
              ├─ 同步方式: Redis Pub/Sub
              ├─ 延迟: 0.1秒
              └─ 状态: ✅ 同步完成
        """
        self.log("全球同步", emoji='sync', color='cyan')

        with self.indent():
            self.log(f"节点数: {node_count:,}")
            self.log(f"同步方式: {sync_method}")
            self.log(f"延迟: {latency:.2f}秒", emoji='clock')

            if status == "SUCCESS":
                self.log(f"状态: ✅ 同步完成", color='green', is_last=True)
            else:
                self.log(f"状态: ❌ 同步失败", color='red', is_last=True)


# 全局默认logger实例
_default_logger = None


def get_defense_logger(
    node_id: str = "Node-Default",
    use_colors: bool = True,
    use_emoji: bool = True
) -> DefenseLogger:
    """
    获取防御日志器实例

    参数:
        node_id: 节点ID
        use_colors: 是否使用颜色
        use_emoji: 是否使用emoji

    返回:
        DefenseLogger实例
    """
    return DefenseLogger(
        node_id=node_id,
        use_colors=use_colors,
        use_emoji=use_emoji
    )


def set_default_logger(logger: DefenseLogger):
    """设置全局默认logger"""
    global _default_logger
    _default_logger = logger


def get_default_logger() -> DefenseLogger:
    """获取全局默认logger"""
    global _default_logger
    if _default_logger is None:
        _default_logger = get_defense_logger()
    return _default_logger


if __name__ == "__main__":
    # 演示用法
    print("=" * 60)
    print("AEGIS-HIDRS 增强型日志系统演示")
    print("=" * 60)
    print()

    # 创建logger
    logger = get_defense_logger(node_id="Node-US-West-01")

    # 示例1: 攻击检测
    print("示例1: 攻击检测日志")
    print("-" * 60)
    logger.attack_detected(
        src_ip="45.123.67.89",
        attack_type="DDoS",
        threat_level="CRITICAL",
        details={
            "请求速率": "100,000 req/s",
            "目标端口": "80, 443",
        }
    )
    print()

    # 示例2: 防御动作
    print("示例2: 防御动作日志")
    print("-" * 60)
    logger.defense_action(
        action="立即启动防御",
        result="SUCCESS",
        details={
            "快速过滤": "✅ 阻断",
            "HLIG分析": "✅ 异常",
            "SOSA记忆": "✅ 已识别",
            "全局同步": "✅ 0.1秒完成"
        }
    )
    print()

    # 示例3: 性能指标
    print("示例3: 性能指标日志")
    print("-" * 60)
    logger.performance_metrics({
        "处理包数": "1,000,000",
        "阻断数": "127,439",
        "CPU使用率": "43%",
        "内存使用": "2.3 GB",
        "平均延迟": "0.3ms"
    })
    print()

    # 示例4: 全球同步
    print("示例4: 全球同步日志")
    print("-" * 60)
    logger.sync_status(
        node_count=2000,
        sync_method="Redis Pub/Sub",
        latency=0.1,
        status="SUCCESS"
    )
    print()

    # 示例5: 复杂嵌套结构
    print("示例5: 复杂嵌套日志")
    print("-" * 60)
    logger.log("全球协同防御启动", emoji='globe', color='cyan')
    with logger.indent():
        logger.log("阶段1: 威胁情报收集", emoji='info')
        with logger.indent():
            logger.log("HaGeZi DNS: ✅ 127,439个域名", emoji='success')
            logger.log("URLhaus: ✅ 3,421个URL", emoji='success')
            logger.log("Spamhaus: ✅ 89,127个IP", emoji='success', is_last=True)

        logger.log("阶段2: HLIG图谱分析", emoji='chart')
        with logger.indent():
            logger.log("拉普拉斯矩阵计算: 完成 (0.3秒)")
            logger.log("Fiedler向量分析: ✅ 识别C&C", emoji='success')
            logger.log("关联节点: 1,247个僵尸主机", is_last=True)

        logger.log("阶段3: 全球封锁执行", emoji='lock', is_last=True)
        with logger.indent():
            logger.log("2,000节点同步: ✅ 0.1秒", emoji='sync', color='green')
            logger.log("防火墙规则部署: ✅ 完成", emoji='success', color='green')
            logger.log("攻击流量: ✅ 100%阻断", emoji='shield', color='green', is_last=True)

    print()
    print("=" * 60)
    print("演示完成！")
    print("=" * 60)
