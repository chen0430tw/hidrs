<template>
  <div class="fluent-app">
    <div class="header">
      <div class="header-content">
        <h1>数据安全中心</h1>
        <h2>社会工程学数据库</h2>
        <search></search>
        <div v-if="showKibanaLink" class="kibana-link">
          <a :href="kibanaUrl" target="_blank" class="kibana-button">打开Kibana仪表盘</a>
        </div>
      </div>
      <div class="header-backdrop"></div>
    </div>
    <Analysis></Analysis>
  </div>
</template>

<script>
import search from './components/search.vue'
import Analysis from './components/Analysis.vue'

export default {
  components: {
    search,
    Analysis
  },
  data() {
    return {
      showKibanaLink: true,
      kibanaUrl: 'http://localhost:5601/app/kibana#/dashboard/socialdb-dashboard'
    }
  },
  mounted() {
    // 配置全局axios实例
    window.axios.defaults.baseURL = 'http://127.0.0.1:5000/api';
    
    // 在组件挂载时验证axios是否正确加载
    if (typeof window.axios === 'undefined') {
      console.error('Axios is not defined! CDN might not be loading properly.');
    } else {
      console.log('Axios is loaded successfully.');
      
      // 测试API连接
      this.testApiConnection();
    }
  },
  methods: {
    // 测试API连接
    testApiConnection() {
      window.axios.get('/test')
        .then(response => {
          console.log('API connection successful:', response.data);
          if (response.data.engine === 'Elasticsearch') {
            console.log('Backend using Elasticsearch confirmed');
          }
        })
        .catch(error => {
          console.error('API connection failed:', error);
          this.showKibanaLink = false;
        });
    }
  }
}
</script>

<style>
body {
  margin: 0;
  padding: 0;
  font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
  background-color: #f5f5f5;
  color: #323130;
}

.fluent-app {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.header {
  position: relative;
  padding: 2rem 0 4rem;
  overflow: hidden;
}

.header-backdrop {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: -1;
  /* 浅蓝色背景 */
  background: linear-gradient(135deg, #4b9cd3, #5dadec);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.header-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 2rem;
  color: white;
  text-align: center;
}

h1 {
  font-size: 3.5rem;
  font-weight: 600;
  margin: 0.5rem 0;
  letter-spacing: -0.025em;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
}

h2 {
  font-size: 1.5rem;
  font-weight: 400;
  margin: 0.5rem 0 2rem;
  opacity: 0.9;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

.kibana-button {
  display: inline-block;
  background-color: #fff;
  color: #4b9cd3;
  padding: 10px 20px;
  border-radius: 4px;
  text-decoration: none;
  font-weight: bold;
  transition: all 0.2s ease;
  border: none;
  cursor: pointer;
  margin-top: 20px;
  font-size: 14px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
}

.kibana-button:hover {
  background-color: rgba(255, 255, 255, 0.9);
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
}

.kibana-link {
  margin-top: 20px;
}

/* 添加响应式设计 */
@media (max-width: 768px) {
  h1 {
    font-size: 2.5rem;
  }
  
  h2 {
    font-size: 1.2rem;
  }
}
</style>