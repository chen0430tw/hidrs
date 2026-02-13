<template>
  <div class="admin-page">
    <div class="admin-header">
      <h1>系统管理</h1>
      <p class="subtitle">配置系统参数与界面主题</p>
    </div>
    <div class="admin-content">
      <!-- 系统信息 -->
      <div class="admin-card">
        <div class="card-header"><h2>系统状态</h2><button class="refresh-button" @click="loadSystemStats">↻</button></div>
        <div class="card-body">
          <div class="system-info-grid">
            <div class="info-item"><div class="info-label">运行模式</div><div class="info-value">{{ $store.state.apiStatus.mode || '未知' }}</div></div>
            <div class="info-item"><div class="info-label">总记录数</div><div class="info-value">{{ formatNumber(systemStats.total_records) }}</div></div>
            <div class="info-item"><div class="info-label">索引大小</div><div class="info-value">{{ systemStats.index_size_mb || 0 }} MB</div></div>
            <div class="info-item"><div class="info-label">存储模式</div><div class="info-value">{{ systemStats.storage_mode || 'reference' }}</div></div>
            <div class="info-item"><div class="info-label">分区策略</div><div class="info-value">{{ systemStats.partitioning ? '已启用' : '未启用' }}</div></div>
            <div class="info-item"><div class="info-label">索引数量</div><div class="info-value">{{ systemStats.indices_count || 0 }}</div></div>
          </div>
        </div>
      </div>
      <!-- 主题设置 -->
      <div class="admin-card">
        <div class="card-header"><h2>界面主题</h2></div>
        <div class="card-body">
          <div class="theme-grid">
            <div class="form-group">
              <label>主色调</label>
              <div class="color-picker-wrapper"><input type="color" v-model="themeSettings.primaryColor"/><input type="text" v-model="themeSettings.primaryColor"/></div>
            </div>
            <div class="form-group">
              <label>次要色调</label>
              <div class="color-picker-wrapper"><input type="color" v-model="themeSettings.secondaryColor"/><input type="text" v-model="themeSettings.secondaryColor"/></div>
            </div>
            <div class="form-group">
              <label>背景色</label>
              <div class="color-picker-wrapper"><input type="color" v-model="themeSettings.backgroundColor"/><input type="text" v-model="themeSettings.backgroundColor"/></div>
            </div>
            <div class="form-group">
              <label>文字颜色</label>
              <div class="color-picker-wrapper"><input type="color" v-model="themeSettings.textColor"/><input type="text" v-model="themeSettings.textColor"/></div>
            </div>
          </div>
          <div class="theme-actions">
            <button class="fluent-button secondary" @click="resetTheme">重置</button>
            <button class="fluent-button" @click="saveTheme">保存设置</button>
          </div>
        </div>
      </div>
      <!-- 导入设置 -->
      <div class="admin-card" v-if="$store.state.systemMode === 'local'">
        <div class="card-header"><h2>导入设置</h2></div>
        <div class="card-body">
          <div class="form-group">
            <label>批量大小</label>
            <input type="number" v-model.number="importSettings.batchSize" class="fluent-input" min="100" max="10000"/>
          </div>
          <div class="form-group">
            <label>存储模式</label>
            <select v-model="importSettings.storageMode" class="fluent-select">
              <option value="reference">引用模式（推荐）</option>
              <option value="duplicate">复制模式</option>
            </select>
          </div>
          <div class="form-group">
            <label class="checkbox-label"><input type="checkbox" v-model="importSettings.useMSNumber"/><span>使用模块化收缩数优化</span></label>
          </div>
          <button class="fluent-button" @click="saveImportSettings">保存设置</button>
        </div>
      </div>
      <!-- 插件管理 -->
      <div class="admin-card">
        <div class="card-header"><h2>插件管理</h2></div>
        <div class="card-body">
          <div class="plugins-list">
            <div v-for="plugin in plugins" :key="plugin.id" class="plugin-item">
              <div class="plugin-info">
                <div class="plugin-name">{{ plugin.name }} <span class="plugin-version">v{{ plugin.version }}</span></div>
                <div class="plugin-desc">{{ plugin.description }}</div>
              </div>
              <div class="plugin-toggle">
                <label class="switch">
                  <input type="checkbox" :checked="plugin.enabled" @change="togglePlugin(plugin)"/>
                  <span class="slider"></span>
                </label>
              </div>
            </div>
            <div v-if="plugins.length === 0" class="empty-state">暂无已安装插件</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'Admin',
  data() {
    return {
      systemStats: { total_records: 0, index_size_mb: 0, storage_mode: '', partitioning: false, indices_count: 0 },
      themeSettings: { primaryColor: '#6A79E3', secondaryColor: '#8089E8', backgroundColor: '#f5f5f5', textColor: '#323130' },
      importSettings: { batchSize: 1000, storageMode: 'reference', useMSNumber: true },
      plugins: []
    }
  },
  methods: {
    async loadSystemStats() {
      try {
        const res = await axios.get('/stats');
        if (res.data.status === 'ok') this.systemStats = res.data.data;
      } catch (e) { console.error('加载统计失败:', e); }
    },
    saveTheme() {
      this.$store.dispatch('updateTheme', this.themeSettings);
      this.$notify({ type: 'success', title: '成功', message: '主题已保存' });
    },
    resetTheme() {
      this.themeSettings = { primaryColor: '#6A79E3', secondaryColor: '#8089E8', backgroundColor: '#f5f5f5', textColor: '#323130' };
    },
    async saveImportSettings() {
      try {
        const res = await axios.post('/admin/config/import', this.importSettings);
        if (res.data.status === 'ok') this.$notify({ type: 'success', title: '成功', message: '设置已保存' });
      } catch (e) { this.$notify({ type: 'error', title: '错误', message: '保存失败' }); }
    },
    async loadPlugins() {
      try {
        const res = await axios.get('/admin/plugins');
        if (res.data.status === 'ok') this.plugins = res.data.data || [];
      } catch (e) { console.error('加载插件列表失败:', e); }
    },
    async togglePlugin(plugin) {
      try {
        await axios.post(`/admin/plugins/${plugin.id}/toggle`);
        this.loadPlugins();
      } catch (e) { console.error('切换插件状态失败:', e); }
    },
    formatNumber(num) {
      if (!num) return '0';
      return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    }
  },
  mounted() {
    this.loadSystemStats();
    this.loadPlugins();
    this.themeSettings = { ...this.$store.state.theme };
  }
}
</script>

<style scoped>
.admin-page { max-width: 1200px; margin: 0 auto; padding: 0 1rem; }
.admin-header { text-align: center; margin-bottom: 2rem; }
.admin-header h1 { font-size: 2rem; color: var(--primary-color); margin: 0 0 0.5rem; }
.subtitle { color: var(--text-light); margin: 0; }
.admin-content { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 2rem; }
.admin-card { background: var(--card-bg-color); border-radius: 8px; box-shadow: 0 2px 8px var(--shadow-color); overflow: hidden; }
.card-header { background: var(--primary-color); color: white; padding: 1rem 1.5rem; display: flex; justify-content: space-between; align-items: center; }
.card-header h2 { margin: 0; font-size: 1.3rem; }
.card-body { padding: 1.5rem; }
.refresh-button { background: none; border: none; color: white; cursor: pointer; font-size: 1.2rem; }
.system-info-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; }
.info-item { background: rgba(106, 121, 227, 0.05); padding: 1rem; border-radius: 6px; }
.info-label { font-size: 0.8rem; color: var(--text-light); margin-bottom: 4px; }
.info-value { font-size: 1.2rem; font-weight: 600; color: var(--text-color); }
.form-group { margin-bottom: 1.5rem; }
.form-group label { display: block; margin-bottom: 0.5rem; font-weight: 500; color: var(--text-color); }
.form-group .fluent-input, .form-group .fluent-select { width: 100%; padding: 10px; box-sizing: border-box; }
.theme-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1.5rem; margin-bottom: 1.5rem; }
.color-picker-wrapper { display: flex; align-items: center; gap: 0.5rem; }
.color-picker-wrapper input[type="color"] { width: 40px; height: 40px; border: none; border-radius: 4px; cursor: pointer; }
.color-picker-wrapper input[type="text"] { flex: 1; padding: 8px; border: 1px solid var(--border-color); border-radius: 4px; }
.theme-actions { display: flex; justify-content: flex-end; gap: 1rem; }
.checkbox-label { display: flex; align-items: center; gap: 0.5rem; cursor: pointer; }
.plugins-list { display: flex; flex-direction: column; gap: 12px; }
.plugin-item { display: flex; justify-content: space-between; align-items: center; padding: 12px; border: 1px solid var(--border-color); border-radius: 6px; }
.plugin-name { font-weight: 600; color: var(--text-color); }
.plugin-version { font-size: 12px; color: var(--text-light); font-weight: normal; }
.plugin-desc { font-size: 13px; color: var(--text-light); margin-top: 4px; }
.switch { position: relative; display: inline-block; width: 44px; height: 24px; }
.switch input { opacity: 0; width: 0; height: 0; }
.slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #ccc; transition: 0.3s; border-radius: 24px; }
.slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px; background-color: white; transition: 0.3s; border-radius: 50%; }
input:checked + .slider { background-color: var(--primary-color); }
input:checked + .slider:before { transform: translateX(20px); }
.empty-state { text-align: center; color: var(--text-light); padding: 1rem; }
@media (max-width: 768px) { .admin-content { grid-template-columns: 1fr; } .theme-grid, .system-info-grid { grid-template-columns: 1fr; } }
</style>
