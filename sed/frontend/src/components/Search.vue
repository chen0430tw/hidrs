<template>
  <div class="search-section">
    <div class="search-container">
      <div class="search-input-group">
        <div class="select-wrapper">
          <select v-model="selected" class="fluent-select">
            <option v-for="option in options" :key="option.value" :value="option.value">
              {{ option.text }}
            </option>
          </select>
        </div>
        <div class="search-input-wrapper">
          <input
            placeholder="请输入并按下回车进行搜索"
            type="text"
            class="fluent-input"
            v-model="searchStr"
            v-on:keyup.enter="search"
          />
          <button class="search-button" @click="search">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path d="M21 21L15 15M17 10C17 13.866 13.866 17 10 17C6.13401 17 3 13.866 3 10C3 6.13401 6.13401 3 10 3C13.866 3 17 6.13401 17 10Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <div v-if="isLoading" class="loading-indicator">
      <div class="spinner"></div>
      <span>正在搜索中...</span>
    </div>

    <div class="alert-error" v-if="errorInfo">{{ errorInfo }}</div>

    <div class="results-container" v-if="results && results.length > 0">
      <div class="results-table-wrapper">
        <table class="fluent-table">
          <thead>
            <tr>
              <th>用户名</th>
              <th>邮箱</th>
              <th>来源</th>
              <th>泄漏时间</th>
              <th>密码</th>
              <th>密码哈希</th>
              <th v-if="hasReference">引用</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in results" :key="index">
              <td>{{ item.user || '无数据' }}</td>
              <td>{{ item.email || '无数据' }}</td>
              <td>{{ item.source || '无数据' }}</td>
              <td>{{ item.xtime || '无数据' }}</td>
              <td @click="togglePassword(index)" class="password-cell">
                {{ formatPassword(item.password, index) }}
                <span class="password-toggle-hint" v-if="item.password">点击切换</span>
              </td>
              <td>{{ item.passwordHash || '无数据' }}</td>
              <td v-if="hasReference && item.reference">
                <button class="view-detail-btn" @click="viewDetail(item.reference.file, item.reference.line)">
                  详情
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="pagination-container" v-if="total > limit">
        <div class="pagination-controls">
          <select class="fluent-select" @change="changePage" v-model="currentPage">
            <option v-for="page in pages" :key="page" :value="page">第 {{ page }} 页</option>
          </select>
          <div class="limit-control">
            <span>每页</span>
            <input type="number" class="fluent-input limit-input" v-model.number="limit" v-on:keyup.enter="changePage" min="1" max="100"/>
            <span>条</span>
          </div>
        </div>
        <div class="data-count">共 {{ total }} 条数据</div>
      </div>
      <div class="data-count-single" v-else-if="total > 0">共 {{ total }} 条数据</div>
    </div>

    <div class="no-results" v-if="searchPerformed && (!results || results.length === 0) && !isLoading && !errorInfo">
      <p>未找到匹配数据</p>
    </div>

    <!-- 详情弹窗 -->
    <div class="modal-overlay" v-if="showDetailModal" @click="showDetailModal = false">
      <div class="modal-container" @click.stop>
        <div class="modal-header">
          <h3>完整记录详情</h3>
          <button class="modal-close" @click="showDetailModal = false">&times;</button>
        </div>
        <div class="modal-body">
          <div class="detail-loading" v-if="detailLoading">
            <div class="spinner"></div><span>加载中...</span>
          </div>
          <div class="detail-content" v-else>
            <div v-if="detailData">
              <div class="detail-item" v-for="(value, key) in detailData" :key="key">
                <div class="detail-label">{{ formatFieldName(key) }}</div>
                <div class="detail-value" :class="{'password-value': key === 'password'}" @click="key === 'password' ? toggleDetailPassword() : null">
                  {{ key === 'password' && !showDetailPassword ? '******' : value }}
                </div>
              </div>
            </div>
            <div class="detail-error" v-else>无法加载详细信息</div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="fluent-button" @click="showDetailModal = false">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'Search',
  data() {
    return {
      limit: 10, selected: 'user', currentPage: 1, searchStr: '', lastSearchTerm: '',
      errorInfo: '', isLoading: false, searchPerformed: false,
      results: [], total: 0, showPasswords: {},
      showDetailModal: false, detailLoading: false, detailData: null,
      showDetailPassword: false,
      options: [
        { text: '用户名', value: 'user' },
        { text: '密码', value: 'password' },
        { text: '邮箱', value: 'email' },
        { text: '哈希密码', value: 'passwordHash' },
        { text: '来源', value: 'source' },
        { text: '时间', value: 'xtime' }
      ]
    }
  },
  computed: {
    pages() {
      return Array.from({ length: Math.ceil(this.total / this.limit) }, (_, i) => i + 1);
    },
    hasReference() {
      return this.results.some(item => item.reference && item.reference.file);
    }
  },
  methods: {
    formatPassword(password, index) {
      if (!password) return '无数据';
      if (this.showPasswords[index]) return password;
      if (password.length <= 4) return '*'.repeat(password.length);
      return password.substr(0, 2) + '*'.repeat(password.length - 4) + password.substr(password.length - 2);
    },
    togglePassword(index) {
      this.$set(this.showPasswords, index, !this.showPasswords[index]);
    },
    search() {
      this.currentPage = 1;
      this.errorInfo = '';
      this.isLoading = true;
      this.searchPerformed = true;
      this.showPasswords = {};
      if (!this.searchStr || this.searchStr.trim() === '') {
        this.errorInfo = '请输入搜索内容';
        this.isLoading = false;
        this.results = [];
        this.total = 0;
        return;
      }
      this.lastSearchTerm = this.searchStr;
      axios.get(`/find/${this.selected}/${encodeURIComponent(this.searchStr)}?limit=${this.limit}&skip=0`)
        .then(response => {
          this.isLoading = false;
          if (response.data.status === 'ok') {
            this.results = response.data.data;
            this.total = response.data.datacounts;
            this.searchStr = '';
          } else {
            this.results = [];
            this.total = 0;
            this.errorInfo = response.data.message || '未找到匹配数据';
          }
        })
        .catch(error => {
          this.isLoading = false;
          this.errorInfo = `请求错误: ${error.message}`;
          this.results = [];
          this.total = 0;
        });
    },
    changePage() {
      this.isLoading = true;
      this.showPasswords = {};
      const skip = this.limit * (this.currentPage - 1);
      axios.get(`/find/${this.selected}/${encodeURIComponent(this.lastSearchTerm)}?limit=${this.limit}&skip=${skip}`)
        .then(response => {
          this.isLoading = false;
          if (response.data.status === 'ok') { this.results = response.data.data; }
          else { this.errorInfo = response.data.message || '加载失败'; }
        })
        .catch(error => { this.isLoading = false; this.errorInfo = `请求错误: ${error.message}`; });
    },
    viewDetail(file, line) {
      this.detailData = null;
      this.showDetailPassword = false;
      this.detailLoading = true;
      this.showDetailModal = true;
      axios.get(`/detail?file=${encodeURIComponent(file)}&line=${line}`)
        .then(response => {
          this.detailLoading = false;
          if (response.data.status === 'ok') { this.detailData = response.data.data; }
        })
        .catch(() => { this.detailLoading = false; });
    },
    toggleDetailPassword() { this.showDetailPassword = !this.showDetailPassword; },
    formatFieldName(key) {
      const map = { 'user': '用户名', 'email': '邮箱', 'password': '密码', 'passwordHash': '密码哈希', 'source': '来源', 'xtime': '泄漏时间', 'suffix_email': '邮箱后缀', 'create_time': '创建时间', 'reference': '引用' };
      return map[key] || key;
    }
  }
}
</script>

<style scoped>
.search-section { margin-bottom: 3rem; }
.search-container { max-width: 800px; margin: 0 auto 2rem; }
.search-input-group { display: flex; background-color: var(--card-bg-color); border-radius: 8px; overflow: hidden; box-shadow: 0 2px 12px var(--shadow-color); }
.select-wrapper { width: 120px; border-right: 1px solid var(--border-color); }
.search-input-wrapper { position: relative; flex: 1; display: flex; }
.fluent-select { width: 100%; height: 50px; padding: 0 15px; border: none; background-color: transparent; color: var(--text-color); font-size: 14px; cursor: pointer; }
.fluent-input { flex: 1; height: 50px; padding: 0 60px 0 15px; border: none; font-size: 16px; background-color: transparent; color: var(--text-color); }
.search-button { position: absolute; right: 0; top: 0; width: 50px; height: 50px; background-color: transparent; border: none; color: var(--primary-color); cursor: pointer; display: flex; align-items: center; justify-content: center; }
.search-button:hover { background-color: rgba(106, 121, 227, 0.1); }
.results-container { background-color: var(--card-bg-color); border-radius: 8px; box-shadow: 0 2px 8px var(--shadow-color); overflow: hidden; }
.results-table-wrapper { overflow-x: auto; }
.password-cell { cursor: pointer; position: relative; }
.password-cell:hover { background-color: rgba(106, 121, 227, 0.2) !important; }
.password-toggle-hint { position: absolute; bottom: 0; left: 16px; font-size: 10px; color: var(--text-lighter); opacity: 0; transition: opacity 0.2s; }
.password-cell:hover .password-toggle-hint { opacity: 1; }
.pagination-container { display: flex; justify-content: space-between; align-items: center; padding: 16px; border-top: 1px solid var(--border-color); }
.pagination-controls { display: flex; align-items: center; gap: 16px; }
.limit-control { display: flex; align-items: center; gap: 8px; color: var(--text-color); }
.limit-input { width: 50px; height: 36px; text-align: center; border: 1px solid var(--border-color); border-radius: 4px; }
.data-count, .data-count-single { color: var(--text-color); font-size: 14px; padding: 16px; font-weight: 500; }
.data-count-single { text-align: center; }
.alert-error { margin: 16px 0; padding: 12px 16px; background-color: rgba(239, 68, 68, 0.1); color: #ef4444; border-radius: 8px; border-left: 3px solid #ef4444; }
.loading-indicator { display: flex; align-items: center; justify-content: center; margin: 2rem 0; color: var(--primary-color); }
.spinner { width: 24px; height: 24px; border: 3px solid rgba(106, 121, 227, 0.2); border-top-color: var(--primary-color); border-radius: 50%; margin-right: 10px; animation: spin 1s linear infinite; }
.no-results { margin: 3rem 0; text-align: center; color: var(--text-light); font-size: 16px; }
.view-detail-btn { background-color: var(--primary-color); color: white; border: none; border-radius: 4px; padding: 4px 8px; font-size: 12px; cursor: pointer; }
.view-detail-btn:hover { background-color: var(--primary-dark); }
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background-color: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-container { background-color: var(--card-bg-color); border-radius: 8px; max-width: 600px; width: 100%; max-height: 90vh; box-shadow: 0 4px 16px var(--shadow-color); display: flex; flex-direction: column; }
.modal-header { padding: 16px; border-bottom: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; }
.modal-header h3 { margin: 0; color: var(--text-color); }
.modal-close { background: none; border: none; font-size: 24px; color: var(--text-light); cursor: pointer; }
.modal-body { padding: 16px; overflow-y: auto; flex: 1; }
.modal-footer { padding: 16px; border-top: 1px solid var(--border-color); display: flex; justify-content: flex-end; }
.detail-loading { display: flex; align-items: center; justify-content: center; padding: 32px; }
.detail-item { margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px dashed var(--border-color); }
.detail-label { font-weight: bold; margin-bottom: 4px; color: var(--text-color); }
.detail-value { word-break: break-all; color: var(--text-color); }
.password-value { cursor: pointer; padding: 4px; border-radius: 4px; }
.password-value:hover { background-color: rgba(106, 121, 227, 0.1); }
.detail-error { color: #ef4444; text-align: center; padding: 16px; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 768px) {
  .search-input-group { flex-direction: column; }
  .select-wrapper { width: 100%; border-right: none; border-bottom: 1px solid var(--border-color); }
  .pagination-container { flex-direction: column; gap: 16px; }
  .modal-container { width: 90%; }
}
</style>
