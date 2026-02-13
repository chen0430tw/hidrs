<template>
  <div class="format-editor">
    <div class="editor-header">
      <h3>{{ isEdit ? '编辑格式模板' : '创建格式模板' }}</h3>
    </div>
    <div class="editor-body">
      <div class="form-group">
        <label>模板名称</label>
        <input type="text" v-model="template.name" class="fluent-input" placeholder="例如：邮箱密码格式"/>
      </div>
      <div class="form-group">
        <label>分隔符</label>
        <select v-model="template.separator" class="fluent-select" @change="onSeparatorChange">
          <option value="----">四横线 (----)</option>
          <option value=",">逗号 (,)</option>
          <option value="\t">制表符 (Tab)</option>
          <option value=":">冒号 (:)</option>
          <option value=";">分号 (;)</option>
          <option value="|">竖线 (|)</option>
          <option value="custom">自定义</option>
        </select>
        <input v-if="template.separator === 'custom'" v-model="template.customSeparator" class="fluent-input" placeholder="输入自定义分隔符" style="margin-top: 8px;"/>
      </div>
      <div class="form-group">
        <label>字段映射</label>
        <div class="fields-list">
          <div v-for="(field, index) in template.fields" :key="index" class="field-item">
            <span class="field-index">列 {{ index + 1 }}</span>
            <select v-model="field.name" class="fluent-select field-select">
              <option value="">-- 忽略 --</option>
              <option value="user">用户名</option>
              <option value="email">邮箱</option>
              <option value="password">密码</option>
              <option value="passwordHash">密码哈希</option>
              <option value="phone">手机号</option>
              <option value="name">姓名</option>
              <option value="idcard">身份证</option>
              <option value="source">来源</option>
              <option value="xtime">时间</option>
              <option value="custom">自定义字段</option>
            </select>
            <input v-if="field.name === 'custom'" v-model="field.customName" class="fluent-input" placeholder="字段名" style="width: 120px;"/>
            <button class="remove-btn" @click="removeField(index)" v-if="template.fields.length > 1">&times;</button>
          </div>
          <button class="add-field-btn" @click="addField">+ 添加字段</button>
        </div>
      </div>
      <div class="form-group">
        <label>自定义固定字段</label>
        <div class="custom-fields">
          <div v-for="(cf, index) in template.customFields" :key="index" class="custom-field-item">
            <input v-model="cf.key" class="fluent-input" placeholder="字段名"/>
            <input v-model="cf.value" class="fluent-input" placeholder="固定值"/>
            <button class="remove-btn" @click="template.customFields.splice(index, 1)">&times;</button>
          </div>
          <button class="add-field-btn" @click="template.customFields.push({key: '', value: ''})">+ 添加固定字段</button>
        </div>
      </div>
      <div class="form-group">
        <label>预览（粘贴一行样本数据）</label>
        <input type="text" v-model="sampleLine" class="fluent-input" placeholder="粘贴一行数据预览解析效果" @input="previewParse"/>
        <div class="preview-result" v-if="previewData">
          <div v-for="(value, key) in previewData" :key="key" class="preview-item">
            <span class="preview-key">{{ key }}:</span>
            <span class="preview-value">{{ value }}</span>
          </div>
        </div>
      </div>
    </div>
    <div class="editor-footer">
      <button class="fluent-button secondary" @click="$emit('cancel')">取消</button>
      <button class="fluent-button" @click="save">{{ isEdit ? '更新' : '保存' }}</button>
    </div>
  </div>
</template>

<script>
export default {
  name: 'FormatEditor',
  props: {
    editTemplate: { type: Object, default: null }
  },
  data() {
    return {
      isEdit: !!this.editTemplate,
      template: this.editTemplate ? { ...this.editTemplate } : {
        name: '',
        separator: '----',
        customSeparator: '',
        fields: [{ name: 'email' }, { name: 'password' }],
        customFields: [{ key: 'source', value: '' }],
        skipFirstLine: false,
        regex: {}
      },
      sampleLine: '',
      previewData: null
    }
  },
  methods: {
    addField() { this.template.fields.push({ name: '' }); },
    removeField(index) { this.template.fields.splice(index, 1); },
    onSeparatorChange() { this.previewParse(); },
    previewParse() {
      if (!this.sampleLine) { this.previewData = null; return; }
      const sep = this.template.separator === 'custom' ? this.template.customSeparator : this.template.separator;
      const parts = this.sampleLine.split(sep === '\\t' ? '\t' : sep);
      const result = {};
      this.template.fields.forEach((field, i) => {
        if (field.name && i < parts.length) {
          const name = field.name === 'custom' ? (field.customName || `field_${i}`) : field.name;
          result[name] = parts[i].trim();
        }
      });
      this.template.customFields.forEach(cf => {
        if (cf.key && cf.value) result[cf.key] = cf.value;
      });
      this.previewData = Object.keys(result).length > 0 ? result : null;
    },
    save() {
      if (!this.template.name) {
        this.$notify({ type: 'warning', title: '提示', message: '请输入模板名称' });
        return;
      }
      this.$emit('save', {
        ...this.template,
        split: this.template.separator === 'custom' ? this.template.customSeparator : this.template.separator,
        fields: this.template.fields.filter(f => f.name).map(f => f.name === 'custom' ? f.customName : f.name),
        custom_field: Object.fromEntries(this.template.customFields.filter(cf => cf.key).map(cf => [cf.key, cf.value]))
      });
    }
  }
}
</script>

<style scoped>
.format-editor { background: var(--card-bg-color); border-radius: 8px; box-shadow: 0 2px 8px var(--shadow-color); }
.editor-header { padding: 1.5rem; border-bottom: 1px solid var(--border-color); }
.editor-header h3 { margin: 0; color: var(--text-color); }
.editor-body { padding: 1.5rem; }
.editor-footer { padding: 1.5rem; border-top: 1px solid var(--border-color); display: flex; justify-content: flex-end; gap: 1rem; }
.form-group { margin-bottom: 1.5rem; }
.form-group label { display: block; margin-bottom: 0.5rem; font-weight: 500; color: var(--text-color); }
.form-group .fluent-input, .form-group .fluent-select { width: 100%; box-sizing: border-box; }
.fields-list { display: flex; flex-direction: column; gap: 8px; }
.field-item { display: flex; align-items: center; gap: 8px; }
.field-index { min-width: 50px; font-size: 13px; color: var(--text-light); }
.field-select { flex: 1; }
.remove-btn { background: none; border: none; color: #ef4444; font-size: 18px; cursor: pointer; padding: 4px 8px; }
.add-field-btn { background: none; border: 1px dashed var(--border-color); color: var(--primary-color); padding: 8px; border-radius: 4px; cursor: pointer; text-align: center; margin-top: 4px; }
.add-field-btn:hover { border-color: var(--primary-color); background: rgba(106, 121, 227, 0.05); }
.custom-fields { display: flex; flex-direction: column; gap: 8px; }
.custom-field-item { display: flex; gap: 8px; align-items: center; }
.custom-field-item .fluent-input { flex: 1; }
.preview-result { margin-top: 12px; padding: 12px; background: rgba(106, 121, 227, 0.05); border-radius: 6px; border: 1px solid rgba(106, 121, 227, 0.2); }
.preview-item { padding: 4px 0; }
.preview-key { font-weight: 600; color: var(--primary-color); margin-right: 8px; }
.preview-value { color: var(--text-color); }
</style>
