<template>
  <div class="import-page">
    <div class="page-header">
      <h1>数据导入</h1>
      <p>支持多种格式的数据导入和管理</p>
    </div>
    <div class="tab-nav">
      <button v-for="tab in tabs" :key="tab.key" :class="['tab-btn', { active: activeTab === tab.key }]" @click="activeTab = tab.key">
        {{ tab.label }}
      </button>
    </div>
    <div class="tab-content">
      <ImportWithTemplate v-if="activeTab === 'import'"/>
      <FormatManager v-if="activeTab === 'templates'"/>
      <div v-if="activeTab === 'history'" class="history-section">
        <h3>导入历史</h3>
        <table class="fluent-table" v-if="importHistory.length > 0">
          <thead><tr><th>文件名</th><th>时间</th><th>成功</th><th>失败</th><th>状态</th></tr></thead>
          <tbody>
            <tr v-for="(item, i) in importHistory" :key="i">
              <td>{{ item.filename }}</td>
              <td>{{ item.time }}</td>
              <td>{{ item.success }}</td>
              <td>{{ item.error }}</td>
              <td><span :class="['status-badge', item.status]">{{ item.status === 'done' ? '完成' : '失败' }}</span></td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state"><p>暂无导入记录</p></div>
      </div>
    </div>
  </div>
</template>

<script>
import ImportWithTemplate from '@/components/ImportWithTemplate.vue'
import FormatManager from '@/components/FormatManager.vue'

export default {
  name: 'Import',
  components: { ImportWithTemplate, FormatManager },
  data() {
    return {
      activeTab: 'import',
      tabs: [
        { key: 'import', label: '数据导入' },
        { key: 'templates', label: '格式模板' },
        { key: 'history', label: '导入历史' }
      ],
      importHistory: []
    }
  },
  mounted() {
    this.loadHistory();
  },
  methods: {
    async loadHistory() {
      try {
        const res = await axios.get('/import/history');
        if (res.data.status === 'ok') this.importHistory = res.data.data || [];
      } catch (e) { console.error('加载导入历史失败:', e); }
    }
  }
}
</script>

<style scoped>
.import-page { max-width: 1200px; margin: 0 auto; padding: 0 1rem; }
.page-header { text-align: center; margin-bottom: 2rem; }
.page-header h1 { font-size: 2rem; color: var(--primary-color); margin: 0 0 0.5rem; }
.page-header p { color: var(--text-light); margin: 0; }
.tab-nav { display: flex; justify-content: center; gap: 4px; margin-bottom: 2rem; background: var(--card-bg-color); border-radius: 8px; padding: 4px; box-shadow: 0 1px 4px var(--shadow-color); }
.tab-btn { padding: 10px 24px; border: none; background: transparent; color: var(--text-color); cursor: pointer; border-radius: 6px; font-size: 14px; font-weight: 500; transition: all 0.2s; }
.tab-btn.active { background: var(--primary-color); color: white; }
.tab-btn:hover:not(.active) { background: rgba(106, 121, 227, 0.1); }
.history-section { background: var(--card-bg-color); border-radius: 8px; box-shadow: 0 2px 8px var(--shadow-color); padding: 1.5rem; }
.history-section h3 { margin: 0 0 1rem; color: var(--text-color); }
.status-badge { padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; }
.status-badge.done { background: rgba(16, 185, 129, 0.1); color: #10b981; }
.status-badge.failed { background: rgba(239, 68, 68, 0.1); color: #ef4444; }
.empty-state { text-align: center; color: var(--text-light); padding: 2rem; }
</style>
