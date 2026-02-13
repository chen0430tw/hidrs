<template>
  <div class="import-wizard">
    <div class="wizard-steps">
      <div v-for="(step, i) in steps" :key="i" :class="['step', { active: currentStep === i, done: currentStep > i }]">
        <span class="step-num">{{ i + 1 }}</span>
        <span class="step-label">{{ step }}</span>
      </div>
    </div>

    <!-- Step 1: 选择文件 -->
    <div class="wizard-content" v-if="currentStep === 0">
      <h3>选择数据文件</h3>
      <div class="file-upload-area" @dragover.prevent @drop.prevent="handleDrop" @click="$refs.fileInput.click()">
        <input type="file" ref="fileInput" @change="handleFileSelect" accept=".txt,.csv,.xls,.xlsx,.sql,.log,.bak" style="display:none"/>
        <div class="upload-icon">📁</div>
        <p>拖拽文件到此处，或点击选择文件</p>
        <p class="file-types">支持格式: TXT, CSV, XLS, XLSX, SQL, LOG</p>
      </div>
      <div v-if="selectedFile" class="file-info">
        <span>{{ selectedFile.name }}</span>
        <span class="file-size">{{ formatSize(selectedFile.size) }}</span>
      </div>
    </div>

    <!-- Step 2: 选择模板 -->
    <div class="wizard-content" v-if="currentStep === 1">
      <h3>选择格式模板</h3>
      <FormatManager @select="onTemplateSelect"/>
      <div v-if="sampleLines.length > 0" class="sample-preview">
        <h4>文件预览（前5行）</h4>
        <div class="sample-line" v-for="(line, i) in sampleLines" :key="i">{{ line }}</div>
      </div>
    </div>

    <!-- Step 3: 确认导入 -->
    <div class="wizard-content" v-if="currentStep === 2">
      <h3>确认导入设置</h3>
      <div class="confirm-info">
        <div class="info-row"><span>文件:</span><strong>{{ selectedFile ? selectedFile.name : '' }}</strong></div>
        <div class="info-row"><span>大小:</span><strong>{{ selectedFile ? formatSize(selectedFile.size) : '' }}</strong></div>
        <div class="info-row"><span>模板:</span><strong>{{ selectedTemplate ? selectedTemplate.name : '默认' }}</strong></div>
        <div class="info-row"><span>分隔符:</span><strong>{{ selectedTemplate ? selectedTemplate.split : '----' }}</strong></div>
        <div class="info-row"><span>字段:</span><strong>{{ selectedTemplate ? selectedTemplate.fields.join(', ') : 'email, password' }}</strong></div>
      </div>
      <div class="import-options">
        <label class="checkbox-label"><input type="checkbox" v-model="skipFirstLine"/><span>跳过首行（标题行）</span></label>
        <label class="checkbox-label"><input type="checkbox" v-model="useMSN"/><span>使用模块化收缩数优化</span></label>
      </div>
    </div>

    <!-- Step 4: 导入进度 -->
    <div class="wizard-content" v-if="currentStep === 3">
      <h3>导入进度</h3>
      <div class="progress-container">
        <div class="progress-bar"><div class="progress-fill" :style="{ width: progress + '%' }"></div></div>
        <div class="progress-text">{{ progress }}% - {{ progressMsg }}</div>
      </div>
      <div class="import-result" v-if="importDone">
        <div class="result-item success">成功: {{ importResult.success }} 条</div>
        <div class="result-item error">失败: {{ importResult.error }} 条</div>
      </div>
    </div>

    <div class="wizard-footer">
      <button class="fluent-button secondary" v-if="currentStep > 0 && currentStep < 3" @click="currentStep--">上一步</button>
      <button class="fluent-button" v-if="currentStep < 2" @click="nextStep" :disabled="!canNext">下一步</button>
      <button class="fluent-button" v-if="currentStep === 2" @click="startImport" :disabled="isImporting">开始导入</button>
      <button class="fluent-button" v-if="currentStep === 3 && importDone" @click="reset">完成</button>
    </div>
  </div>
</template>

<script>
import FormatManager from './FormatManager.vue'

export default {
  name: 'ImportWithTemplate',
  components: { FormatManager },
  data() {
    return {
      steps: ['选择文件', '选择模板', '确认设置', '导入'],
      currentStep: 0,
      selectedFile: null,
      selectedTemplate: null,
      sampleLines: [],
      skipFirstLine: false,
      useMSN: true,
      isImporting: false,
      importDone: false,
      progress: 0,
      progressMsg: '准备中...',
      importResult: { success: 0, error: 0 }
    }
  },
  computed: {
    canNext() {
      if (this.currentStep === 0) return !!this.selectedFile;
      if (this.currentStep === 1) return true;
      return true;
    }
  },
  methods: {
    handleFileSelect(e) {
      this.selectedFile = e.target.files[0];
      this.loadSample();
    },
    handleDrop(e) {
      this.selectedFile = e.dataTransfer.files[0];
      this.loadSample();
    },
    loadSample() {
      if (!this.selectedFile) return;
      const reader = new FileReader();
      reader.onload = (e) => {
        const lines = e.target.result.split('\n').filter(l => l.trim()).slice(0, 5);
        this.sampleLines = lines;
      };
      reader.readAsText(this.selectedFile.slice(0, 4096));
    },
    nextStep() {
      if (this.canNext) this.currentStep++;
    },
    onTemplateSelect(tpl) { this.selectedTemplate = tpl; },
    async startImport() {
      this.isImporting = true;
      this.currentStep = 3;
      this.progress = 0;
      this.progressMsg = '上传文件中...';

      const formData = new FormData();
      formData.append('file', this.selectedFile);
      if (this.selectedTemplate) formData.append('template_id', this.selectedTemplate.id);
      formData.append('skip_first_line', this.skipFirstLine);
      formData.append('use_msn', this.useMSN);

      try {
        const res = await axios.post('/import/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
          onUploadProgress: (e) => {
            if (e.total) this.progress = Math.round((e.loaded / e.total) * 50);
          }
        });

        if (res.data.status === 'ok') {
          this.progress = 100;
          this.progressMsg = '导入完成！';
          this.importResult = { success: res.data.success || 0, error: res.data.error || 0 };
        } else {
          this.progressMsg = '导入失败: ' + (res.data.message || '未知错误');
        }
      } catch (e) {
        this.progressMsg = '导入失败: ' + e.message;
      } finally {
        this.isImporting = false;
        this.importDone = true;
      }
    },
    reset() {
      this.currentStep = 0;
      this.selectedFile = null;
      this.selectedTemplate = null;
      this.sampleLines = [];
      this.importDone = false;
      this.progress = 0;
    },
    formatSize(bytes) {
      if (bytes < 1024) return bytes + ' B';
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
      return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }
  }
}
</script>

<style scoped>
.import-wizard { background: var(--card-bg-color); border-radius: 8px; box-shadow: 0 2px 8px var(--shadow-color); padding: 2rem; }
.wizard-steps { display: flex; justify-content: center; gap: 2rem; margin-bottom: 2rem; }
.step { display: flex; align-items: center; gap: 8px; color: var(--text-light); font-size: 14px; }
.step.active { color: var(--primary-color); font-weight: 600; }
.step.done { color: var(--success-color, #10b981); }
.step-num { width: 28px; height: 28px; border-radius: 50%; border: 2px solid currentColor; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 600; }
.step.active .step-num { background: var(--primary-color); color: white; border-color: var(--primary-color); }
.step.done .step-num { background: var(--success-color, #10b981); color: white; border-color: var(--success-color, #10b981); }
.wizard-content { min-height: 300px; }
.wizard-content h3 { color: var(--text-color); margin-bottom: 1.5rem; }
.wizard-footer { display: flex; justify-content: flex-end; gap: 1rem; margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid var(--border-color); }
.file-upload-area { border: 2px dashed var(--border-color); border-radius: 8px; padding: 3rem; text-align: center; cursor: pointer; transition: all 0.2s; }
.file-upload-area:hover { border-color: var(--primary-color); background: rgba(106, 121, 227, 0.05); }
.upload-icon { font-size: 3rem; margin-bottom: 1rem; }
.file-types { font-size: 12px; color: var(--text-lighter); margin-top: 8px; }
.file-info { display: flex; justify-content: space-between; padding: 12px; margin-top: 1rem; background: rgba(106, 121, 227, 0.05); border-radius: 6px; }
.file-size { color: var(--text-light); font-size: 13px; }
.sample-preview { margin-top: 1.5rem; }
.sample-preview h4 { margin-bottom: 0.5rem; color: var(--text-color); }
.sample-line { padding: 6px 12px; font-family: 'Consolas', monospace; font-size: 13px; background: var(--input-bg); border-bottom: 1px solid var(--border-color); color: var(--text-color); white-space: nowrap; overflow-x: auto; }
.confirm-info { display: flex; flex-direction: column; gap: 12px; margin-bottom: 1.5rem; }
.info-row { display: flex; gap: 12px; }
.info-row span { color: var(--text-light); min-width: 80px; }
.info-row strong { color: var(--text-color); }
.import-options { display: flex; flex-direction: column; gap: 12px; }
.checkbox-label { display: flex; align-items: center; gap: 8px; cursor: pointer; color: var(--text-color); }
.progress-container { margin: 2rem 0; }
.progress-bar { height: 12px; background: var(--border-color); border-radius: 6px; overflow: hidden; }
.progress-fill { height: 100%; background: linear-gradient(90deg, var(--primary-color), var(--primary-light)); border-radius: 6px; transition: width 0.3s; }
.progress-text { text-align: center; margin-top: 12px; color: var(--text-color); }
.import-result { display: flex; gap: 2rem; justify-content: center; margin-top: 1.5rem; }
.result-item { font-size: 1.2rem; font-weight: 600; }
.result-item.success { color: var(--success-color, #10b981); }
.result-item.error { color: var(--error-color, #ef4444); }
</style>
