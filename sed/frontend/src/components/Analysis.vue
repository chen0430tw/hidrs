<template>
  <div class="analysis-section">
    <div class="analysis-container">
      <div class="section-title">
        <h2>数据分析</h2>
        <p class="subtitle">查看数据统计信息</p>
      </div>
      <div class="analysis-controls">
        <button v-for="item in analysisItems" :key="item.value"
          :class="['fluent-button', activeAnalysis === item.value ? 'active' : '']"
          @click="loadAnalysis(item.value, item.text)">
          {{ item.text }}
        </button>
      </div>
      <div class="chart-container">
        <div id="chartArea" class="chart-area"></div>
        <div v-if="isLoading" class="loading-overlay">
          <div class="spinner"></div>
          <div class="loading-text">数据加载中...</div>
        </div>
      </div>
      <div class="data-table-container" v-if="chartData.length > 0">
        <h3>数据明细</h3>
        <table class="fluent-table">
          <thead>
            <tr><th>{{ dataColumnName }}</th><th>数量</th><th>占比</th></tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in chartData" :key="index">
              <td>{{ item.name || '未知' }}</td>
              <td>{{ item.value }}</td>
              <td>{{ getPercentage(item.value) }}%</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'Analysis',
  data() {
    return {
      analysisItems: [
        { text: '来源分布', value: 'source' },
        { text: '泄露时间', value: 'xtime' },
        { text: '邮箱类型', value: 'suffix_email' },
        { text: '导入时间', value: 'create_time' }
      ],
      activeAnalysis: '', chartData: [], totalCount: 0,
      isLoading: false, chartInstance: null, dataColumnName: '类别'
    }
  },
  computed: {
    chartColors() {
      return this.$store.state.theme.chartColors || [
        '#6A79E3', '#8089E8', '#9BA3ED', '#B5BBF2', '#CED2F7',
        '#4856C7', '#5F6DD5', '#7784DE', '#A0A8EB', '#D8DBF9'
      ];
    }
  },
  methods: {
    loadAnalysis(type, title) {
      this.isLoading = true;
      this.activeAnalysis = type;
      const columnMap = { 'source': '来源', 'xtime': '时间', 'suffix_email': '邮箱类型', 'create_time': '导入时间' };
      this.dataColumnName = columnMap[type] || '类别';

      axios.get(`/analysis/${type}`)
        .then(response => {
          this.isLoading = false;
          if (response.data.status === 'ok') {
            this.chartData = [];
            this.totalCount = 0;
            response.data.data.forEach(item => {
              this.chartData.push({ name: item._id || '未知', value: item.sum });
              this.totalCount += item.sum;
            });
            if (this.chartData.length > 10) {
              this.chartData.sort((a, b) => b.value - a.value);
              const top = this.chartData.slice(0, 9);
              const otherSum = this.chartData.slice(9).reduce((s, i) => s + i.value, 0);
              top.push({ name: '其他', value: otherSum });
              this.chartData = top;
            }
            this.renderChart(title);
          }
        })
        .catch(error => {
          this.isLoading = false;
          console.error('获取分析数据失败:', error);
        });
    },
    renderChart(title) {
      const chartDom = document.getElementById('chartArea');
      if (!chartDom) return;
      if (!this.chartInstance) {
        this.chartInstance = window.echarts ? window.echarts.init(chartDom) : null;
      }
      if (!this.chartInstance) return;
      this.chartInstance.clear();
      const data = this.chartData.map(i => ({ name: i.name, value: i.value }));
      this.chartInstance.setOption({
        color: this.chartColors,
        title: { text: title, left: 'center', textStyle: { color: getComputedStyle(document.documentElement).getPropertyValue('--text-color').trim() || '#333' } },
        tooltip: { trigger: 'item', formatter: '{a} <br/>{b}: {c} ({d}%)' },
        legend: { type: 'scroll', orient: 'horizontal', bottom: 10, left: 'center', data: data.map(i => i.name) },
        series: [{
          name: title, type: 'pie', radius: ['40%', '70%'], avoidLabelOverlap: true,
          itemStyle: { borderRadius: 4, borderColor: getComputedStyle(document.documentElement).getPropertyValue('--card-bg-color').trim() || '#fff', borderWidth: 2 },
          label: { show: false, position: 'center' },
          emphasis: { label: { show: true, fontSize: '18', fontWeight: 'bold' } },
          labelLine: { show: false },
          data: data
        }]
      });
    },
    getPercentage(value) {
      if (!this.totalCount) return '0.00';
      return ((value / this.totalCount) * 100).toFixed(2);
    },
    handleResize() { if (this.chartInstance) this.chartInstance.resize(); }
  },
  mounted() {
    this.loadAnalysis('source', '来源分布');
    window.addEventListener('resize', this.handleResize);
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.handleResize);
    if (this.chartInstance) { this.chartInstance.dispose(); this.chartInstance = null; }
  }
}
</script>

<style scoped>
.analysis-section { margin-top: 2rem; padding: 2rem 0; }
.analysis-container { background-color: var(--card-bg-color); border-radius: 8px; box-shadow: 0 2px 8px var(--shadow-color); padding: 2rem; }
.section-title { text-align: center; margin-bottom: 2rem; }
.section-title h2 { font-size: 2rem; font-weight: 600; color: var(--text-color); margin: 0; }
.subtitle { font-size: 1rem; color: var(--text-light); margin-top: 0.5rem; }
.analysis-controls { display: flex; justify-content: center; flex-wrap: wrap; gap: 12px; margin-bottom: 2rem; }
.fluent-button { padding: 10px 18px; background-color: var(--card-bg-color); border: 1px solid var(--border-color); border-radius: 4px; font-size: 14px; color: var(--text-color); cursor: pointer; transition: all 0.2s; }
.fluent-button:hover { background-color: rgba(106, 121, 227, 0.1); border-color: var(--primary-color); }
.fluent-button.active { background-color: var(--primary-color); color: white; border-color: var(--primary-color); }
.chart-container { position: relative; background-color: var(--card-bg-color); border-radius: 8px; border: 1px solid var(--border-color); padding: 1rem; margin: 0 auto 2rem; }
.chart-area { height: 400px; width: 100%; }
.loading-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; flex-direction: column; justify-content: center; align-items: center; background-color: rgba(255,255,255,0.9); border-radius: 8px; z-index: 10; }
.spinner { width: 40px; height: 40px; border: 4px solid rgba(106, 121, 227, 0.2); border-top-color: var(--primary-color); border-radius: 50%; animation: spin 1s ease-in-out infinite; }
.loading-text { margin-top: 12px; color: var(--primary-color); font-size: 14px; }
.data-table-container { margin-top: 2rem; }
.data-table-container h3 { font-size: 1.2rem; color: var(--text-color); margin-bottom: 1rem; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 768px) {
  .chart-area { height: 300px; }
  .analysis-controls { flex-direction: column; align-items: stretch; }
  .fluent-button { width: 100%; padding: 12px; }
}
</style>
