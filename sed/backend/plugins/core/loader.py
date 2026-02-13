"""
银狼数据安全平台 - 后端插件加载器
"""
import os
import importlib
import logging

logger = logging.getLogger(__name__)


class PluginLoader:
    """插件加载器"""
    
    def __init__(self):
        self.plugins = {}
        self.load_order = []
    
    def discover(self, plugin_dir=None):
        """发现插件"""
        if plugin_dir is None:
            plugin_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'plugins', 'modules')
        
        if not os.path.exists(plugin_dir):
            logger.info(f"插件目录不存在: {plugin_dir}")
            return
        
        for name in os.listdir(plugin_dir):
            plugin_path = os.path.join(plugin_dir, name)
            if os.path.isdir(plugin_path) and os.path.exists(os.path.join(plugin_path, '__init__.py')):
                try:
                    module = importlib.import_module(f'plugins.modules.{name}')
                    if hasattr(module, 'Plugin'):
                        plugin = module.Plugin()
                        self.plugins[plugin.id] = plugin
                        logger.info(f"发现插件: {plugin.name} ({plugin.id})")
                except Exception as e:
                    logger.error(f"加载插件 {name} 失败: {e}")
    
    def resolve_order(self):
        """拓扑排序解析依赖"""
        resolved = []
        visited = set()
        visiting = set()
        
        def visit(plugin_id):
            if plugin_id in visited:
                return
            if plugin_id in visiting:
                logger.error(f"插件循环依赖: {plugin_id}")
                return
            visiting.add(plugin_id)
            plugin = self.plugins.get(plugin_id)
            if plugin:
                for dep in plugin.requires:
                    if dep in self.plugins:
                        visit(dep)
            visiting.discard(plugin_id)
            visited.add(plugin_id)
            resolved.append(plugin_id)
        
        for pid in self.plugins:
            visit(pid)
        
        self.load_order = resolved
        return resolved
    
    def install_all(self, app):
        """安装所有已启用插件"""
        self.resolve_order()
        for pid in self.load_order:
            plugin = self.plugins[pid]
            if plugin.enabled:
                try:
                    plugin.init_app(app)
                    logger.info(f"插件 {plugin.name} 已安装")
                except Exception as e:
                    logger.error(f"安装插件 {pid} 失败: {e}")
    
    def get_all(self):
        return [p.to_dict() for p in self.plugins.values()]
    
    def toggle(self, plugin_id):
        plugin = self.plugins.get(plugin_id)
        if plugin:
            plugin.enabled = not plugin.enabled
            return plugin.enabled
        return None


plugin_loader = PluginLoader()
