"""
HIDRS 插件系统基础架构
参考：HIDRS-PLUGIN-SYSTEM-PLAN.md
"""

import os
import json
import logging
import importlib
import inspect
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class PluginBase(ABC):
    """插件基类"""

    def __init__(self):
        self.name = self.__class__.__name__
        self.version = "1.0.0"
        self.author = "Unknown"
        self.description = "No description"
        self.enabled = False
        self.config = {}

    @abstractmethod
    def on_load(self):
        """插件加载时调用"""
        pass

    @abstractmethod
    def on_unload(self):
        """插件卸载时调用"""
        pass

    def get_info(self) -> Dict:
        """获取插件信息"""
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "enabled": self.enabled
        }

    def set_config(self, config: Dict):
        """设置插件配置"""
        self.config = config

    def get_config(self) -> Dict:
        """获取插件配置"""
        return self.config


class PluginManager:
    """插件管理器"""

    def __init__(self, plugin_dir: str = "plugins", config_file: str = "config/plugin_config.json"):
        self.plugin_dir = Path(plugin_dir)
        self.config_file = Path(config_file)
        self.plugins: Dict[str, PluginBase] = {}
        self.hooks: Dict[str, List[Callable]] = {}

        # 确保目录存在
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        # 加载配置
        self.config = self._load_config()

        logger.info(f"插件管理器已初始化，插件目录: {self.plugin_dir}")

    def _load_config(self) -> Dict:
        """加载插件配置"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载插件配置失败: {e}")

        return {"plugins": {}, "enabled_plugins": []}

    def _save_config(self):
        """保存插件配置"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存插件配置失败: {e}")

    def discover_plugins(self) -> List[str]:
        """发现所有可用插件"""
        plugin_files = []

        for file in self.plugin_dir.glob("*.py"):
            if file.stem != "__init__":
                plugin_files.append(file.stem)

        logger.info(f"发现 {len(plugin_files)} 个插件文件: {plugin_files}")
        return plugin_files

    def load_plugin(self, plugin_name: str) -> bool:
        """加载插件"""
        if plugin_name in self.plugins:
            logger.warning(f"插件 {plugin_name} 已经加载")
            return True

        try:
            # 动态导入插件模块
            module_path = f"{self.plugin_dir.stem}.{plugin_name}"
            module = importlib.import_module(module_path)

            # 查找插件类
            plugin_class = None
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and issubclass(obj, PluginBase) and obj != PluginBase:
                    plugin_class = obj
                    break

            if not plugin_class:
                logger.error(f"插件 {plugin_name} 中未找到有效的插件类")
                return False

            # 实例化插件
            plugin_instance = plugin_class()

            # 加载配置
            if plugin_name in self.config.get("plugins", {}):
                plugin_instance.set_config(self.config["plugins"][plugin_name])

            # 调用加载钩子
            plugin_instance.on_load()

            # 注册插件
            self.plugins[plugin_name] = plugin_instance

            logger.info(f"插件 {plugin_name} 加载成功")
            return True

        except Exception as e:
            logger.error(f"加载插件 {plugin_name} 失败: {e}")
            return False

    def unload_plugin(self, plugin_name: str) -> bool:
        """卸载插件"""
        if plugin_name not in self.plugins:
            logger.warning(f"插件 {plugin_name} 未加载")
            return False

        try:
            plugin = self.plugins[plugin_name]
            plugin.on_unload()
            del self.plugins[plugin_name]

            logger.info(f"插件 {plugin_name} 卸载成功")
            return True

        except Exception as e:
            logger.error(f"卸载插件 {plugin_name} 失败: {e}")
            return False

    def enable_plugin(self, plugin_name: str) -> bool:
        """启用插件"""
        if plugin_name not in self.plugins:
            # 如果未加载，先加载
            if not self.load_plugin(plugin_name):
                return False

        plugin = self.plugins[plugin_name]
        plugin.enabled = True

        # 更新配置
        if "enabled_plugins" not in self.config:
            self.config["enabled_plugins"] = []

        if plugin_name not in self.config["enabled_plugins"]:
            self.config["enabled_plugins"].append(plugin_name)

        self._save_config()

        logger.info(f"插件 {plugin_name} 已启用")
        return True

    def disable_plugin(self, plugin_name: str) -> bool:
        """禁用插件"""
        if plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
            plugin.enabled = False

        # 更新配置
        if "enabled_plugins" in self.config and plugin_name in self.config["enabled_plugins"]:
            self.config["enabled_plugins"].remove(plugin_name)

        self._save_config()

        logger.info(f"插件 {plugin_name} 已禁用")
        return True

    def get_plugin(self, plugin_name: str) -> Optional[PluginBase]:
        """获取插件实例"""
        return self.plugins.get(plugin_name)

    def list_plugins(self) -> List[Dict]:
        """列出所有插件"""
        plugins_info = []

        for plugin_name, plugin in self.plugins.items():
            info = plugin.get_info()
            info["loaded"] = True
            plugins_info.append(info)

        # 添加未加载的插件
        discovered = self.discover_plugins()
        for plugin_name in discovered:
            if plugin_name not in self.plugins:
                plugins_info.append({
                    "name": plugin_name,
                    "version": "Unknown",
                    "author": "Unknown",
                    "description": "未加载",
                    "enabled": False,
                    "loaded": False
                })

        return plugins_info

    def register_hook(self, hook_name: str, callback: Callable):
        """注册钩子函数"""
        if hook_name not in self.hooks:
            self.hooks[hook_name] = []

        self.hooks[hook_name].append(callback)
        logger.debug(f"已注册钩子: {hook_name}")

    def trigger_hook(self, hook_name: str, *args, **kwargs) -> List[Any]:
        """触发钩子"""
        results = []

        if hook_name in self.hooks:
            for callback in self.hooks[hook_name]:
                try:
                    result = callback(*args, **kwargs)
                    results.append(result)
                except Exception as e:
                    logger.error(f"钩子 {hook_name} 执行失败: {e}")

        return results

    def load_all_enabled(self):
        """加载所有已启用的插件"""
        enabled_plugins = self.config.get("enabled_plugins", [])

        for plugin_name in enabled_plugins:
            self.load_plugin(plugin_name)
            if plugin_name in self.plugins:
                self.plugins[plugin_name].enabled = True

        logger.info(f"已加载 {len(enabled_plugins)} 个启用的插件")


# 全局插件管理器实例
_plugin_manager = None


def get_plugin_manager() -> PluginManager:
    """获取全局插件管理器实例"""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager
