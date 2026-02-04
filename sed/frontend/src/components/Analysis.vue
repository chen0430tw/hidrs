<template>
  <div class="analysis-section">
    <div class="analysis-container">
      <div class="section-title">
        <h2>数据分析</h2>
        <p class="subtitle">查看数据库统计信息</p>
      </div>
      
      <div class="analysis-controls">
        <button 
          v-for="key in analysisItems" 
          :key="key.value"
          :class="['fluent-button', activeAnalysis === key.value ? 'active' : '']"
          @click="flashAnalysis(key.value, key.text)"
        >
          {{ key.text }}
        </button>
      </div>
      
      <div class="chart-container">
        <div id="chartArea" class="chart-area"></div>
        <div v-if="isLoading" class="loading-overlay">
          <div class="spinner"></div>
          <div class="loading-text">数据加载中...</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
// 使用window.axios和window.echarts
var myChart = null;

export default {
  name: 'analysis',
  data() {
    return {
      analysisData: [],
      legendData: [],
      isLoading: false,
      activeAnalysis: '',
      analysisItems: [
        { text: '来源分布', value: 'source' },
        { text: '泄露时间', value: 'xtime' },
        { text: '邮箱类型', value: 'suffix_email' },
        { text: '导入时间', value: 'create_time' }
      ]
    }
  },
  methods: {
    flashAnalysis(value, vtext) {
      this.isLoading = true;
      this.activeAnalysis = value;
      
      // ECharts显示加载动画
      if (myChart) {
        myChart.clear();
      }
      
      // 修复: 使用完整的API路径（添加/api/前缀）
      window.axios.get('/api/analysis/' + value, {
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      }).then(response => {
        this.isLoading = false;
        if (response.data.status === 'ok') {
          this.analysisData = [];
          this.legendData = [];
          for (var key in response.data.data) {
            var item = response.data.data[key];
            this.analysisData.push({
              "value": item["sum"],
              "name": item["_id"] || '未知'
            });
            this.legendData.push(item["_id"] || '未知');
          }
          
          this.renderChart(vtext);
        }
      })
      .catch(error => {
        this.isLoading = false;
        console.log('分析错误:', error.response ? error.response.data : error);
      });
    },
    
    renderChart(title) {
      if (!myChart) return;
      
      // 定义蓝色主题的颜色
      const colors = [
        '#4b9cd3', '#5dadec', '#77c3f6', '#99d2f7', '#bce1f7', 
        '#3689c2', '#5fa5d4', '#7eb8df', '#9ccbf2', '#b9def4'
      ];
      
      myChart.setOption({
        color: colors,
        title: {
          text: title,
          left: 'center',
          top: 0,
          textStyle: {
            fontSize: 18,
            fontWeight: 'normal',
            color: '#333'
          }
        },
        tooltip: {
          trigger: 'item',
          formatter: "{a} <br/>{b}: {c} ({d}%)",
          backgroundColor: 'rgba(255, 255, 255, 0.9)',
          borderColor: '#e2e2e2',
          borderWidth: 1,
          textStyle: {
            color: '#333'
          },
          extraCssText: 'box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);'
        },
        legend: {
          orient: 'horizontal',
          bottom: 0,
          left: 'center',
          data: this.legendData,
          textStyle: {
            color: '#333'  // 确保图例颜色足够深
          },
          itemWidth: 10,
          itemHeight: 10,
          itemGap: 15
        },
        series: [{
          name: title,
          type: 'pie',
          radius: ['40%', '70%'],
          center: ['50%', '50%'],
          avoidLabelOverlap: true,
          itemStyle: {
            borderRadius: 6,
            borderWidth: 2,
            borderColor: '#fff'
          },
          label: {
            show: true,
            position: 'outside',
            formatter: '{b}: {c} ({d}%)',
            color: '#333'  // 确保标签颜色足够深
          },
          emphasis: {
            label: {
              show: true,
              fontWeight: 'bold',
              fontSize: 14
            },
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor: 'rgba(0, 0, 0, 0.2)'
            }
          },
          labelLine: {
            show: true,
            length: 10,
            length2: 15
          },
          data: this.analysisData
        }]
      });
    }
  },
  mounted() {
    // 初始化ECharts
    myChart = window.echarts.init(document.getElementById('chartArea'));
    
    // 默认加载第一个分析项
    if (this.analysisItems.length > 0) {
      setTimeout(() => {
        this.flashAnalysis(this.analysisItems[0].value, this.analysisItems[0].text);
      }, 500);
    }
    
    // 响应式调整图表大小
    window.addEventListener('resize', () => {
      if (myChart) myChart.resize();
    });
  },
  beforeDestroy() {
    window.removeEventListener('resize', () => {
      if (myChart) myChart.resize();
    });
  }
}
</script>

<style>
.analysis-section {
  padding: 2rem 1rem;
  background-color: #f9f9f9;
}

.analysis-container {
  max-width: 1200px;
  margin: 0 auto;
}

.section-title {
  text-align: center;
  margin-bottom: 2rem;
}

.section-title h2 {
  font-size: 2rem;
  font-weight: 600;
  color: #323130;
  margin: 0;
}

.subtitle {
  font-size: 1rem;
  color: #333;  /* 深色字体，提高可读性 */
  margin-top: 0.5rem;
}

.analysis-controls {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 2rem;
}

.fluent-button {
  padding: 10px 18px;
  background-color: white;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 500;
  color: #333;  /* 深色按钮文字 */
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.fluent-button:hover {
  background-color: #f0f7ff;
  border-color: #4b9cd3;
}

.fluent-button.active {
  background-color: #4b9cd3;  /* 浅蓝色活动按钮 */
  color: white;
  border-color: #4b9cd3;
}

.chart-container {
  position: relative;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  padding: 1.5rem;
  margin: 0 auto;
  max-width: 900px;
}

.chart-area {
  height: 400px;
  width: 100%;
}

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  background-color: rgba(255, 255, 255, 0.9);
  border-radius: 8px;
  z-index: 10;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid rgba(75, 156, 211, 0.2);
  border-top-color: #4b9cd3;
  border-radius: 50%;
  animation: spin 1s ease-in-out infinite;
}

.loading-text {
  margin-top: 12px;
  color: #4b9cd3;
  font-size: 14px;
  font-weight: 500;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 768px) {
  .chart-area {
    height: 300px;
  }
  
  .analysis-controls {
    flex-direction: column;
    align-items: stretch;
  }
  
  .fluent-button {
    width: 100%;
    padding: 12px;
  }
}
</style>