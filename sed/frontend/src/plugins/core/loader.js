/**
 * 银狼数据安全平台 - 插件加载器
 * 支持动态发现、注册和依赖管理
 */

class PluginLoader {
  constructor() {
    this.plugins = new Map();
    this.loadOrder = [];
  }

  register(plugin) {
    if (this.plugins.has(plugin.id)) {
      console.warn(`插件 ${plugin.id} 已注册，跳过`);
      return;
    }
    this.plugins.set(plugin.id, plugin);
  }

  resolveOrder() {
    const resolved = [];
    const visited = new Set();
    const visiting = new Set();

    const visit = (pluginId) => {
      if (visited.has(pluginId)) return;
      if (visiting.has(pluginId)) {
        console.error(`插件循环依赖: ${pluginId}`);
        return;
      }
      visiting.add(pluginId);
      const plugin = this.plugins.get(pluginId);
      if (plugin && plugin.requires) {
        plugin.requires.forEach(dep => {
          if (this.plugins.has(dep)) visit(dep);
          else console.warn(`缺少依赖: ${dep} (被 ${pluginId} 需要)`);
        });
      }
      visiting.delete(pluginId);
      visited.add(pluginId);
      resolved.push(pluginId);
    };

    this.plugins.forEach((_, id) => visit(id));
    this.loadOrder = resolved;
    return resolved;
  }

  installAll(Vue, context) {
    this.resolveOrder();
    this.loadOrder.forEach(id => {
      const plugin = this.plugins.get(id);
      if (plugin && plugin.enabled) {
        try {
          plugin.install(Vue, context);
          console.log(`插件 ${plugin.name} (${id}) 已加载`);
        } catch (e) {
          console.error(`插件 ${id} 加载失败:`, e);
        }
      }
    });
  }

  getPlugin(id) { return this.plugins.get(id); }
  getAll() { return Array.from(this.plugins.values()); }
  getEnabled() { return this.getAll().filter(p => p.enabled); }
}

export default new PluginLoader();
