/**
 * 银狼数据安全平台 - 插件基类
 */
export default class PluginBase {
  constructor(options = {}) {
    this.id = options.id || '';
    this.name = options.name || '';
    this.version = options.version || '1.0.0';
    this.description = options.description || '';
    this.author = options.author || '';
    this.requires = options.requires || [];
    this.enabled = options.enabled !== false;
    this.routes = [];
    this.navItems = [];
  }

  install(Vue, { router, store }) {
    if (this.routes.length > 0 && router) {
      this.routes.forEach(route => router.addRoute(route));
    }
    if (this.navItems.length > 0 && store) {
      store.commit('ADD_NAV_ITEMS', this.navItems);
    }
  }

  activate() { this.enabled = true; }
  deactivate() { this.enabled = false; }
}
