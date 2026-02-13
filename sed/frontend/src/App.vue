<template>
  <div id="app" :class="{'dark-mode': isDarkMode}">
    <header class="app-header">
      <div class="header-content">
        <h1>{{ currentTheme.name === '银狼 Silver Wolf' ? '银狼数据安全平台' : '数据安全中心' }}</h1>
        <h2>{{ currentTheme.name === '银狼 Silver Wolf' ? 'Silver Wolf Security Platform' : '社会工程学数据库' }}</h2>

        <nav class="main-nav">
          <router-link to="/" class="nav-link">首页</router-link>
          <router-link to="/import" class="nav-link">数据导入</router-link>
          <router-link to="/tools" class="nav-link">工具集</router-link>
          <router-link to="/admin" class="nav-link">系统管理</router-link>
        </nav>

        <div v-if="showKibanaLink && systemMode === 'local'" class="kibana-link">
          <a :href="kibanaUrl" target="_blank" class="kibana-button">
            打开Kibana仪表盘
          </a>
        </div>

        <div class="mode-indicator">
          运行模式: {{ systemMode }}
          <span v-if="apiStatus.connected" class="status-badge connected">已连接</span>
          <span v-else class="status-badge disconnected">未连接</span>
        </div>
      </div>
    </header>

    <main class="app-content">
      <router-view/>
    </main>

    <footer class="app-footer">
      <div class="footer-content">
        <p>&copy; 2025 {{ currentTheme.name }} | 总记录数: {{ formatNumber(totalRecords) }}</p>

        <div class="footer-controls">
          <!-- 主题选择器 -->
          <div class="theme-selector">
            <label>主题:</label>
            <select v-model="selectedTheme" @change="onThemeChange">
              <option v-for="theme in availableThemes" :key="theme.id" :value="theme.id">
                {{ theme.name }}
              </option>
            </select>
          </div>

          <button class="theme-toggle" @click="toggleDarkMode">
            {{ isDarkMode ? '☀️ 日间' : '🌙 暗黑' }}
          </button>
        </div>
      </div>
    </footer>

    <div class="notifications-container"></div>
  </div>
</template>

<script>
import { mapState, mapGetters, mapActions } from 'vuex'

export default {
  name: 'App',
  data() {
    return {
      showKibanaLink: true,
      kibanaUrl: process.env.VUE_APP_KIBANA_URL || 'http://localhost:5601',
      selectedTheme: 'silver-wolf'
    }
  },
  computed: {
    ...mapState({
      apiStatus: state => state.apiStatus,
      systemMode: state => state.apiStatus.mode || '未知',
      totalRecords: state => state.apiStatus.stats?.total_records || 0,
      isDarkMode: state => state.isDarkMode,
      currentThemeId: state => state.currentThemeId
    }),
    ...mapGetters(['currentTheme', 'availableThemes'])
  },
  watch: {
    currentThemeId(newId) {
      this.selectedTheme = newId
    }
  },
  methods: {
    ...mapActions(['switchTheme', 'toggleDarkMode']),
    formatNumber(num) {
      if (num === undefined || num === null) return '0'
      return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",")
    },
    onThemeChange() {
      this.switchTheme(this.selectedTheme)
    }
  },
  mounted() {
    this.selectedTheme = this.currentThemeId
  }
}
</script>

<style>
:root {
  --primary-color: #6A79E3;
  --primary-dark: #4856C7;
  --primary-light: #8089E8;
  --secondary-color: #8089E8;
  --background-color: #f5f5f5;
  --text-color: #323130;
  --text-light: #666666;
  --text-lighter: #999999;
  --card-bg-color: #ffffff;
  --border-color: #e0e0e0;
  --shadow-color: rgba(0, 0, 0, 0.1);
  --input-bg: white;
  --input-border: #e0e0e0;
  --input-text: #333333;
  --transition-speed: 0.3s;
}

body {
  margin: 0;
  padding: 0;
  font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
  background-color: var(--background-color);
  color: var(--text-color);
  transition: background-color var(--transition-speed), color var(--transition-speed);
}

#app {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.app-header {
  position: relative;
  padding: 2rem 0 4rem;
  overflow: hidden;
  background: linear-gradient(135deg, var(--primary-color), var(--primary-dark));
  box-shadow: 0 2px 8px var(--shadow-color);
}

.header-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 2rem;
  color: white;
  text-align: center;
  position: relative;
}

.app-content {
  flex: 1;
  padding: 2rem 0;
}

.app-footer {
  background-color: var(--card-bg-color);
  padding: 1.5rem;
  text-align: center;
  border-top: 1px solid var(--border-color);
  box-shadow: 0 -2px 8px var(--shadow-color);
}

.footer-content {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
}

.footer-controls {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.theme-selector {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.theme-selector label {
  color: var(--text-light);
  font-size: 0.875rem;
}

.theme-selector select {
  background-color: var(--card-bg-color);
  color: var(--text-color);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  padding: 0.35rem 0.75rem;
  font-size: 0.875rem;
  cursor: pointer;
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

.main-nav {
  margin: 1rem 0;
}

.nav-link {
  color: white;
  text-decoration: none;
  padding: 0.5rem 1rem;
  margin: 0 0.5rem;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.nav-link:hover,
.nav-link.router-link-active {
  background-color: rgba(255, 255, 255, 0.2);
}

.kibana-button {
  display: inline-block;
  background-color: #fff;
  color: var(--primary-color);
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

.mode-indicator {
  position: absolute;
  top: 1rem;
  right: 2rem;
  font-size: 0.875rem;
  color: white;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-badge {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: bold;
}

.status-badge.connected { background-color: #10b981; }
.status-badge.disconnected { background-color: #ef4444; }

.theme-toggle {
  background-color: var(--card-bg-color);
  color: var(--text-color);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  padding: 0.5rem 1rem;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 0.875rem;
}

.theme-toggle:hover {
  background-color: var(--primary-color);
  color: white;
}

.notifications-container {
  position: fixed;
  top: 1rem;
  right: 1rem;
  z-index: 9999;
}

.notification {
  background-color: var(--card-bg-color);
  color: var(--text-color);
  border-left: 4px solid var(--primary-color);
  border-radius: 4px;
  padding: 1rem;
  margin-bottom: 1rem;
  box-shadow: 0 2px 8px var(--shadow-color);
  transform: translateX(100%);
  opacity: 0;
  transition: transform 0.3s, opacity 0.3s;
}

.notification.show { transform: translateX(0); opacity: 1; }
.notification-title { font-weight: bold; margin-bottom: 0.5rem; }
.notification-success { border-left-color: #10b981; }
.notification-error { border-left-color: #ef4444; }
.notification-warning { border-left-color: #f59e0b; }

@media (max-width: 768px) {
  h1 { font-size: 2.5rem; }
  h2 { font-size: 1.2rem; }
  .mode-indicator { position: static; margin-top: 1rem; justify-content: center; }
  .footer-content { flex-direction: column; gap: 1rem; }
}
</style>
