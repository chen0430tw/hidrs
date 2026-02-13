<template>
  <div class="numlookup-page">
    <div class="page-header">
      <h1>号码归属地查询</h1>
      <p>支持手机号归属地和身份证查询（大陆/香港/澳门/台湾）</p>
    </div>

    <div class="lookup-container">
      <div class="input-section">
        <div class="type-tabs">
          <button :class="['tab-btn', { active: queryType === 'auto' }]" @click="queryType = 'auto'">智能识别</button>
          <button :class="['tab-btn', { active: queryType === 'mobile' }]" @click="queryType = 'mobile'">手机号</button>
          <button :class="['tab-btn', { active: queryType === 'idcard' }]" @click="queryType = 'idcard'">身份证</button>
        </div>
        <div class="search-box">
          <input type="text" v-model="queryInput" :placeholder="placeholderText" class="fluent-input" @keyup.enter="doLookup"/>
          <button class="fluent-button" @click="doLookup" :disabled="isLoading">
            {{ isLoading ? '查询中...' : '查询' }}
          </button>
        </div>
      </div>

      <div class="result-section" v-if="result">
        <div class="result-card">
          <h3>查询结果</h3>
          <div class="result-grid">
            <template v-if="result.type === 'mobile'">
              <div class="result-item"><span class="label">号码</span><span class="value">{{ result.number }}</span></div>
              <div class="result-item"><span class="label">归属地</span><span class="value">{{ result.province }} {{ result.city }}</span></div>
              <div class="result-item"><span class="label">运营商</span><span class="value">{{ result.carrier }}</span></div>
              <div class="result-item"><span class="label">号段</span><span class="value">{{ result.prefix }}</span></div>
              <div class="result-item" v-if="result.areaCode"><span class="label">区号</span><span class="value">{{ result.areaCode }}</span></div>
              <div class="result-item" v-if="result.zipCode"><span class="label">邮编</span><span class="value">{{ result.zipCode }}</span></div>
            </template>
            <!-- 大陆身份证 -->
            <template v-else-if="result.idType === 'CN'">
              <div class="result-item"><span class="label">证件类型</span><span class="value">{{ result.typeName }}</span></div>
              <div class="result-item"><span class="label">身份证号</span><span class="value">{{ result.number }}</span></div>
              <div class="result-item"><span class="label">地区</span><span class="value">{{ result.province }} {{ result.city }} {{ result.district }}</span></div>
              <div class="result-item"><span class="label">出生日期</span><span class="value">{{ result.birthday }}</span></div>
              <div class="result-item"><span class="label">性别</span><span class="value">{{ result.gender }}</span></div>
              <div class="result-item"><span class="label">年龄</span><span class="value">{{ result.age }} 岁</span></div>
              <div class="result-item" v-if="result.constellation"><span class="label">星座</span><span class="value">{{ result.constellation }}</span></div>
              <div class="result-item" v-if="result.zodiac"><span class="label">生肖</span><span class="value">{{ result.zodiac }}</span></div>
            </template>
            <!-- 香港身份证 -->
            <template v-else-if="result.idType === 'HK'">
              <div class="result-item"><span class="label">证件类型</span><span class="value">{{ result.typeName }}</span></div>
              <div class="result-item"><span class="label">证件号码</span><span class="value">{{ result.formatted || result.number }}</span></div>
              <div class="result-item"><span class="label">地区</span><span class="value">{{ result.region }}</span></div>
              <div class="result-item"><span class="label">字母前缀</span><span class="value">{{ result.prefix }}</span></div>
              <div class="result-item"><span class="label">校验码</span><span class="value">{{ result.checkDigit }}</span></div>
            </template>
            <!-- 台湾身份证 -->
            <template v-else-if="result.idType === 'TW'">
              <div class="result-item"><span class="label">证件类型</span><span class="value">{{ result.typeName }}</span></div>
              <div class="result-item"><span class="label">证件号码</span><span class="value">{{ result.number }}</span></div>
              <div class="result-item"><span class="label">户籍地</span><span class="value">{{ result.region }}</span></div>
              <div class="result-item"><span class="label">性别</span><span class="value">{{ result.gender }}</span></div>
            </template>
            <!-- 澳门身份证 -->
            <template v-else-if="result.idType === 'MO'">
              <div class="result-item"><span class="label">证件类型</span><span class="value">{{ result.typeName }}</span></div>
              <div class="result-item"><span class="label">证件号码</span><span class="value">{{ result.formatted || result.number }}</span></div>
              <div class="result-item"><span class="label">地区</span><span class="value">{{ result.region }}</span></div>
              <div class="result-item"><span class="label">首位含义</span><span class="value">{{ result.firstDigitMeaning }}</span></div>
            </template>
            <!-- 兼容旧格式 -->
            <template v-else-if="result.type === 'idcard'">
              <div class="result-item"><span class="label">身份证号</span><span class="value">{{ result.number }}</span></div>
              <div class="result-item"><span class="label">地区</span><span class="value">{{ result.province }} {{ result.city }} {{ result.district }}</span></div>
              <div class="result-item"><span class="label">出生日期</span><span class="value">{{ result.birthday }}</span></div>
              <div class="result-item"><span class="label">性别</span><span class="value">{{ result.gender }}</span></div>
              <div class="result-item"><span class="label">年龄</span><span class="value">{{ result.age }} 岁</span></div>
            </template>
          </div>
        </div>
      </div>

      <div class="error-message" v-if="errorMsg">{{ errorMsg }}</div>

      <!-- 批量查询 -->
      <div class="batch-section">
        <h3>批量查询</h3>
        <div class="batch-upload" @click="$refs.batchFile.click()">
          <input type="file" ref="batchFile" @change="handleBatchFile" accept=".txt,.csv" style="display:none"/>
          <p>点击上传TXT/CSV文件进行批量查询</p>
        </div>
        <div v-if="batchResults.length > 0" class="batch-results">
          <div class="batch-header">
            <span>共 {{ batchResults.length }} 条结果</span>
            <button class="fluent-button secondary" @click="exportResults">导出结果</button>
          </div>
          <table class="fluent-table">
            <thead><tr><th>号码</th><th>类型</th><th>地区</th><th>详情</th></tr></thead>
            <tbody>
              <tr v-for="(item, i) in batchResults.slice(0, 50)" :key="i">
                <td>{{ item.number }}</td>
                <td>{{ item.type === 'mobile' ? '手机号' : (item.typeName || '身份证') }}</td>
                <td>{{ item.type === 'mobile' ? `${item.province} ${item.city}` : (item.idType === 'CN' ? `${item.province} ${item.city}` : item.region) }}</td>
                <td>{{ item.type === 'mobile' ? item.carrier : (item.gender || item.firstDigitMeaning || item.district || '') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 查询历史 -->
      <div class="history-section" v-if="queryHistory.length > 0">
        <h3>查询历史</h3>
        <div class="history-list">
          <div v-for="(item, i) in queryHistory.slice(0, 10)" :key="i" class="history-item" @click="queryInput = item.input; doLookup()">
            <span class="history-input">{{ item.input }}</span>
            <span class="history-result">{{ item.summary }}</span>
            <span class="history-time">{{ item.time }}</span>
          </div>
        </div>
        <button class="fluent-button secondary" @click="clearHistory" style="margin-top: 8px;">清除历史</button>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'NumLookupView',
  data() {
    return {
      queryType: 'auto',
      queryInput: '',
      result: null,
      errorMsg: '',
      isLoading: false,
      batchResults: [],
      queryHistory: JSON.parse(localStorage.getItem('numlookup_history') || '[]')
    }
  },
  computed: {
    placeholderText() {
      if (this.queryType === 'mobile') return '请输入手机号码';
      if (this.queryType === 'idcard') return '请输入身份证号码';
      return '输入手机号或身份证号，自动识别';
    }
  },
  methods: {
    async doLookup() {
      const input = this.queryInput.trim();
      if (!input) { this.errorMsg = '请输入查询内容'; return; }
      this.errorMsg = '';
      this.isLoading = true;
      this.result = null;

      let type = this.queryType;
      if (type === 'auto') {
        type = input.length >= 15 ? 'idcard' : 'mobile';
      }

      try {
        const endpoint = type === 'mobile' ? '/tools/mobile/lookup' : '/tools/idcard/lookup';
        const res = await axios.post(endpoint, { number: input });
        if (res.data.status === 'ok') {
          // 保留后端返回的type作为idType，前端type用于区分手机/身份证
          this.result = { ...res.data.data, type, idType: res.data.data.type };
          this.addHistory(input, this.result);
        } else {
          this.errorMsg = res.data.message || '查询失败';
        }
      } catch (e) {
        this.errorMsg = '查询请求失败: ' + e.message;
      } finally {
        this.isLoading = false;
      }
    },
    addHistory(input, result) {
      let summary;
      if (result.type === 'mobile') {
        summary = `${result.province} ${result.city} ${result.carrier || ''}`;
      } else if (result.idType === 'CN') {
        summary = `${result.province} ${result.city} ${result.district || ''}`;
      } else {
        // 港澳台使用 region 字段
        summary = `${result.typeName || ''} ${result.region || ''}`;
      }
      this.queryHistory.unshift({
        input, summary,
        time: new Date().toLocaleString()
      });
      if (this.queryHistory.length > 50) this.queryHistory = this.queryHistory.slice(0, 50);
      localStorage.setItem('numlookup_history', JSON.stringify(this.queryHistory));
    },
    clearHistory() {
      this.queryHistory = [];
      localStorage.removeItem('numlookup_history');
    },
    async handleBatchFile(e) {
      const file = e.target.files[0];
      if (!file) return;
      const text = await file.text();
      const numbers = text.split(/[\n,;\t]+/).map(n => n.trim()).filter(n => n);
      this.batchResults = [];

      for (const num of numbers.slice(0, 500)) {
        const type = num.length >= 15 ? 'idcard' : 'mobile';
        try {
          const endpoint = type === 'mobile' ? '/tools/mobile/lookup' : '/tools/idcard/lookup';
          const res = await axios.post(endpoint, { number: num });
          if (res.data.status === 'ok') {
            this.batchResults.push({ ...res.data.data, type, idType: res.data.data.type, number: num });
          }
        } catch (e) { /* skip errors */ }
      }
    },
    exportResults() {
      const headers = ['号码', '类型', '地区', '详情'];
      const rows = this.batchResults.map(r => {
        let typeLabel = r.type === 'mobile' ? '手机号' : (r.typeName || '身份证');
        let region = r.type === 'mobile'
          ? `${r.province || ''} ${r.city || ''}`.trim()
          : (r.idType === 'CN' ? `${r.province || ''} ${r.city || ''} ${r.district || ''}`.trim() : (r.region || ''));
        let detail = r.type === 'mobile' ? (r.carrier || '') : (r.gender || r.firstDigitMeaning || '');
        return [r.number, typeLabel, region, detail];
      });
      const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
      const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'lookup_results.csv';
      link.click();
    }
  }
}
</script>

<style scoped>
.numlookup-page { max-width: 900px; margin: 0 auto; padding: 0 1rem; }
.page-header { text-align: center; margin-bottom: 2rem; }
.page-header h1 { font-size: 2rem; color: var(--primary-color); margin: 0 0 0.5rem; }
.page-header p { color: var(--text-light); margin: 0; }
.lookup-container { display: flex; flex-direction: column; gap: 2rem; }
.input-section { background: var(--card-bg-color); border-radius: 8px; box-shadow: 0 2px 8px var(--shadow-color); padding: 1.5rem; }
.type-tabs { display: flex; gap: 4px; margin-bottom: 1rem; }
.tab-btn { padding: 8px 16px; border: 1px solid var(--border-color); background: transparent; color: var(--text-color); cursor: pointer; border-radius: 4px; font-size: 13px; transition: all 0.2s; }
.tab-btn.active { background: var(--primary-color); color: white; border-color: var(--primary-color); }
.search-box { display: flex; gap: 12px; }
.search-box .fluent-input { flex: 1; padding: 12px; font-size: 16px; }
.search-box .fluent-button { padding: 12px 24px; }
.result-card { background: var(--card-bg-color); border-radius: 8px; box-shadow: 0 2px 8px var(--shadow-color); padding: 1.5rem; }
.result-card h3 { margin: 0 0 1rem; color: var(--text-color); }
.result-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.result-item { padding: 12px; background: rgba(106, 121, 227, 0.05); border-radius: 6px; }
.result-item .label { display: block; font-size: 12px; color: var(--text-light); margin-bottom: 4px; }
.result-item .value { font-size: 16px; font-weight: 600; color: var(--text-color); }
.error-message { padding: 12px; background: rgba(239, 68, 68, 0.1); color: #ef4444; border-radius: 8px; text-align: center; }
.batch-section, .history-section { background: var(--card-bg-color); border-radius: 8px; box-shadow: 0 2px 8px var(--shadow-color); padding: 1.5rem; }
.batch-section h3, .history-section h3 { margin: 0 0 1rem; color: var(--text-color); }
.batch-upload { border: 2px dashed var(--border-color); border-radius: 8px; padding: 2rem; text-align: center; cursor: pointer; color: var(--text-light); transition: all 0.2s; }
.batch-upload:hover { border-color: var(--primary-color); }
.batch-header { display: flex; justify-content: space-between; align-items: center; margin: 1rem 0; }
.history-list { display: flex; flex-direction: column; gap: 4px; }
.history-item { display: flex; gap: 12px; padding: 8px 12px; border-radius: 4px; cursor: pointer; transition: background 0.2s; font-size: 13px; }
.history-item:hover { background: rgba(106, 121, 227, 0.1); }
.history-input { font-weight: 600; color: var(--primary-color); min-width: 140px; }
.history-result { color: var(--text-color); flex: 1; }
.history-time { color: var(--text-lighter); font-size: 12px; }
</style>
