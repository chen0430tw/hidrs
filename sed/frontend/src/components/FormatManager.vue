<template>
  <div class="format-manager">
    <div class="manager-header">
      <h3>格式模板管理</h3>
      <button class="fluent-button" @click="showEditor = true">新建模板</button>
    </div>
    <div class="templates-grid">
      <div v-for="tpl in templates" :key="tpl.id" class="template-card" :class="{ selected: selectedId === tpl.id }" @click="selectTemplate(tpl)">
        <div class="template-name">{{ tpl.name }}</div>
        <div class="template-info">
          <span>分隔符: {{ tpl.split || '----' }}</span>
          <span>字段: {{ (tpl.fields || []).join(', ') }}</span>
        </div>
        <div class="template-actions">
          <button class="action-btn edit" @click.stop="editTemplate(tpl)">编辑</button>
          <button class="action-btn delete" @click.stop="deleteTemplate(tpl.id)">删除</button>
        </div>
      </div>
      <div v-if="templates.length === 0" class="empty-state">
        <p>暂无格式模板，点击"新建模板"创建</p>
      </div>
    </div>
    <FormatEditor v-if="showEditor" :editTemplate="editingTemplate" @save="handleSave" @cancel="closeEditor"/>
  </div>
</template>

<script>
import FormatEditor from './FormatEditor.vue'

export default {
  name: 'FormatManager',
  components: { FormatEditor },
  data() {
    return {
      templates: [],
      selectedId: null,
      showEditor: false,
      editingTemplate: null
    }
  },
  methods: {
    async loadTemplates() {
      try {
        const res = await axios.get('/admin/config/templates');
        if (res.data.status === 'ok') this.templates = res.data.data || [];
      } catch (e) { console.error('加载模板失败:', e); }
    },
    selectTemplate(tpl) {
      this.selectedId = tpl.id;
      this.$emit('select', tpl);
    },
    editTemplate(tpl) {
      this.editingTemplate = { ...tpl };
      this.showEditor = true;
    },
    closeEditor() {
      this.showEditor = false;
      this.editingTemplate = null;
    },
    async handleSave(template) {
      try {
        const method = template.id ? 'put' : 'post';
        const url = template.id ? `/admin/config/templates/${template.id}` : '/admin/config/templates';
        const res = await axios[method](url, template);
        if (res.data.status === 'ok') {
          this.$notify({ type: 'success', title: '成功', message: '模板已保存' });
          this.closeEditor();
          this.loadTemplates();
        }
      } catch (e) {
        this.$notify({ type: 'error', title: '错误', message: '保存模板失败: ' + e.message });
      }
    },
    async deleteTemplate(id) {
      if (!confirm('确定要删除此模板吗？')) return;
      try {
        const res = await axios.delete(`/admin/config/templates/${id}`);
        if (res.data.status === 'ok') {
          this.$notify({ type: 'success', title: '成功', message: '模板已删除' });
          this.loadTemplates();
        }
      } catch (e) {
        this.$notify({ type: 'error', title: '错误', message: '删除失败: ' + e.message });
      }
    }
  },
  mounted() { this.loadTemplates(); }
}
</script>

<style scoped>
.format-manager { padding: 1.5rem; }
.manager-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; }
.manager-header h3 { margin: 0; color: var(--text-color); }
.templates-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
.template-card { background: var(--card-bg-color); border: 2px solid var(--border-color); border-radius: 8px; padding: 1rem; cursor: pointer; transition: all 0.2s; }
.template-card:hover { border-color: var(--primary-color); box-shadow: 0 2px 8px var(--shadow-color); }
.template-card.selected { border-color: var(--primary-color); background: rgba(106, 121, 227, 0.05); }
.template-name { font-weight: 600; font-size: 1.1rem; color: var(--text-color); margin-bottom: 0.5rem; }
.template-info { font-size: 0.85rem; color: var(--text-light); display: flex; flex-direction: column; gap: 4px; margin-bottom: 0.75rem; }
.template-actions { display: flex; gap: 8px; }
.action-btn { padding: 4px 12px; border: 1px solid var(--border-color); border-radius: 4px; background: transparent; cursor: pointer; font-size: 12px; }
.action-btn.edit { color: var(--primary-color); border-color: var(--primary-color); }
.action-btn.delete { color: #ef4444; border-color: #ef4444; }
.empty-state { grid-column: 1 / -1; text-align: center; color: var(--text-light); padding: 2rem; }
</style>
