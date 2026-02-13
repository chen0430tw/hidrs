import Vue from 'vue'
import App from './App.vue'
import router from './router'
import store from './store'
import axios from 'axios'
import './styles/theme.css'

Vue.config.productionTip = false

// 设置全局axios
window.axios = axios;
axios.defaults.baseURL = process.env.VUE_APP_API_URL || 'http://localhost:5000/api';

// 简单的通知组件
Vue.prototype.$notify = function(config) {
  const notification = document.createElement('div');
  notification.className = `notification notification-${config.type || 'info'}`;
  notification.innerHTML = `
    <div class="notification-title">${config.title || ''}</div>
    <div class="notification-message">${config.message || ''}</div>
  `;

  const container = document.querySelector('.notifications-container') || document.body;
  container.appendChild(notification);

  setTimeout(() => {
    notification.classList.add('show');
  }, 10);

  setTimeout(() => {
    notification.classList.remove('show');
    setTimeout(() => {
      if (notification.parentNode) {
        notification.parentNode.removeChild(notification);
      }
    }, 300);
  }, 3000);
};

// 移除加载屏幕
Vue.prototype.$removeLoading = function() {
  const loadingContainer = document.querySelector('.loading-container');
  if (loadingContainer) {
    loadingContainer.classList.add('fade-out');
    setTimeout(() => {
      if (loadingContainer.parentNode) {
        loadingContainer.parentNode.removeChild(loadingContainer);
      }
    }, 500);
  }
};

// 加载主题
store.dispatch('loadTheme');

// 初始化应用
store.dispatch('initializeApp').then(() => {
  new Vue({
    router,
    store,
    render: h => h(App),
    mounted() {
      this.$removeLoading();
    }
  }).$mount('#app');
});

// 添加淡出动画样式
const style = document.createElement('style');
style.innerHTML = `
  .fade-out {
    opacity: 0;
    transition: opacity 0.5s ease;
  }
`;
document.head.appendChild(style);
