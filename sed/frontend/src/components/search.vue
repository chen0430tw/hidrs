<template>
  <div class="search">
    <div class="search-container">
      <div class="search-input-group">
        <div class="select-wrapper">
          <select v-model="selected" class="fluent-select">
            <option v-for="option in options" :key="option.value" :value="option.value">
              {{ option.text }}
            </option>
          </select>
          <span class="select-arrow">▼</span>
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
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M14.2939 13.2058L11.5998 10.5117C12.4546 9.47956 12.9456 8.17329 12.9456 6.77283C12.9456 3.70418 10.4414 1.2 7.37276 1.2C4.30411 1.2 1.79993 3.70418 1.79993 6.77283C1.79993 9.84149 4.30411 12.3457 7.37276 12.3457C8.77322 12.3457 10.0795 11.8547 11.1116 10.9998L13.8057 13.694C13.9332 13.8215 14.1664 13.8215 14.2939 13.694C14.4214 13.5664 14.4214 13.3333 14.2939 13.2058ZM2.76648 6.77283C2.76648 4.23869 4.83863 2.16655 7.37276 2.16655C9.9069 2.16655 11.979 4.23869 11.979 6.77283C11.979 9.30697 9.9069 11.3791 7.37276 11.3791C4.83863 11.3791 2.76648 9.30697 2.76648 6.77283Z" fill="currentColor"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <div v-if="isLoading" class="loading-indicator">
      <div class="spinner"></div>
      <span>正在搜索中...</span>
    </div>

    <div class="alert-error" v-if="errorinfo">{{ errorinfo }}</div>
    
    <div class="results-container" v-if="retItems && retItems.length > 0">
      <div class="results-table-wrapper">
        <table class="fluent-table">
          <thead>
            <tr>
              <th>用户名</th>
              <th>邮箱</th>
              <th>来源</th>
              <th>泄漏时间</th>
              <th>密码</th>
              <th>hash密码</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in retItems" :key="index">
              <td>{{ item.user || '无数据' }}</td>
              <td>{{ item.email || '无数据' }}</td>
              <td>{{ item.source || '无数据' }}</td>
              <td>{{ item.xtime || '无数据' }}</td>
              <td @click="togglePassword(index)" class="password-cell">
                {{ formatPassword(item.password, index) }}
                <span class="password-toggle-hint" v-if="item.password">点击切换显示</span>
              </td>
              <td>{{ item.passwordHash || '无数据' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="pagination-container" v-if="datacnts > 10">
        <div class="pagination-controls">
          <div class="pagination-select">
            <select class="fluent-select" @change="changepages" v-model="selectedP">
              <option v-for="opt in pageoptions" :key="opt.value" :value="opt.value">
                {{ opt.text }}
              </option>
            </select>
          </div>
          <div class="limit-control">
            <span>每页显示</span>
            <input 
              type="number"
              class="fluent-input limit-input" 
              v-model="limit"
              v-on:keyup.enter="changepages"
              min="1"
              max="100"
            />
            <span>条</span>
          </div>
        </div>
        <div class="data-count">查询结果共 {{ datacnts }} 条数据</div>
      </div>
      
      <!-- 当只有一条数据时也显示总数 -->
      <div class="data-count-single" v-else-if="datacnts > 0">
        查询结果共 {{ datacnts }} 条数据
      </div>
    </div>
    
    <!-- 增加一个没有找到数据的提示 -->
    <div class="no-results" v-if="searchPerformed && (!retItems || retItems.length === 0) && !isLoading && !errorinfo">
      <div class="no-results-icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z" stroke="#666" stroke-width="2"/>
          <path d="M12 8V12" stroke="#666" stroke-width="2" stroke-linecap="round"/>
          <circle cx="12" cy="16" r="1" fill="#666"/>
        </svg>
      </div>
      <p>未找到匹配数据</p>
    </div>
  </div>
</template>

<script>
export default {
  name: 'Search',
  data() {
    return {
      limit: 10,
      selected: 'user',
      selectedP: 1,
      searchStr: '',
      pageStr: '',
      errorinfo: '',
      datacnts: 0,
      isLoading: false,
      searchPerformed: false, // 新增：标记是否执行过搜索
      pageoptions: [],
      options: [
        { text: '用户名', value: 'user' },
        { text: '密码', value: 'password' },
        { text: '邮箱', value: 'email' },
        { text: '哈希密码', value: 'passwordHash' }
      ],
      retItems: [],
      showPasswords: {}, // 存储密码显示状态
    }
  },
  methods: {
    // 格式化密码显示
    formatPassword(password, index) {
      if (!password) return '无数据';
      
      // 如果设置为显示，则直接返回密码
      if (this.showPasswords[index]) return password;
      
      // 否则显示部分掩码密码
      if (password.length <= 4) return '*'.repeat(password.length);
      return password.substr(0, 2) + '*'.repeat(password.length - 4) + password.substr(password.length - 2);
    },
    
    // 切换密码显示/隐藏
    togglePassword(index) {
      // 使用Vue的$set方法确保响应性
      this.$set(this.showPasswords, index, !this.showPasswords[index]);
    },
    
    search() {
      // 重置状态
      this.pageoptions = [];
      this.limit = 10;
      this.selectedP = 1;
      this.errorinfo = '';
      this.isLoading = true;
      this.searchPerformed = true; // 标记已执行搜索
      this.showPasswords = {}; // 重置密码显示状态
      
      // 确保searchStr不为空
      if (!this.searchStr || this.searchStr.trim() === '') {
        this.errorinfo = '请输入搜索内容';
        this.isLoading = false;
        this.retItems = [];
        return;
      }
      
      console.log(`正在搜索 ${this.selected}: ${this.searchStr}`);
      
      window.axios.get(`/find/${this.selected}/${encodeURIComponent(this.searchStr)}`, {
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      })
      .then(response => {
        this.isLoading = false;
        console.log('API返回结果:', response.data);
        
        if (response.data.status === 'ok') {
          // 确保data字段是数组
          if (Array.isArray(response.data.data)) {
            this.retItems = response.data.data;
            this.pageStr = this.searchStr;
            this.searchStr = '';
            this.datacnts = response.data.datacounts || response.data.data.length;
            
            // 生成分页选项
            if (this.datacnts > this.limit) {
              const pageCount = Math.ceil(this.datacnts / this.limit);
              this.pageoptions = Array.from({length: pageCount}, (_, i) => ({
                text: `第 ${i + 1} 页`,
                value: i + 1
              }));
            }
          } else {
            console.error('API返回的data不是数组:', response.data.data);
            this.retItems = [];
            this.datacnts = 0;
            this.errorinfo = 'API返回数据格式错误';
          }
        } else {
          this.retItems = [];
          this.searchStr = '';
          this.datacnts = 0;
          this.errorinfo = response.data.message || '未找到匹配数据';
        }
      })
      .catch(error => {
        this.isLoading = false;
        console.error('搜索请求错误:', error);
        this.errorinfo = `请求错误: ${error.response ? error.response.status + ' - ' + error.response.statusText : error.message}`;
        this.retItems = [];
      });
    },
    
    changepages() {
      this.isLoading = true;
      this.showPasswords = {}; // 重置密码显示状态
      
      console.log(`加载第 ${this.selectedP} 页, 每页 ${this.limit} 条`);
      
      window.axios.get(`/find/${this.selected}/${encodeURIComponent(this.pageStr)}?limit=${this.limit}&skip=${this.limit * (this.selectedP - 1)}`, {
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      })
      .then(response => {
        this.isLoading = false;
        console.log('分页数据:', response.data);
        
        if (response.data.status === 'ok') {
          if (Array.isArray(response.data.data)) {
            this.retItems = response.data.data;
            
            // 重新计算分页选项
            if (this.datacnts > 0) {
              const pageCount = Math.ceil(this.datacnts / this.limit);
              this.pageoptions = Array.from({length: pageCount}, (_, i) => ({
                text: `第 ${i + 1} 页`,
                value: i + 1
              }));
            }
          } else {
            console.error('API返回的分页数据不是数组:', response.data.data);
            this.errorinfo = 'API返回数据格式错误';
          }
        } else {
          this.retItems = [];
          this.datacnts = 0;
          this.errorinfo = response.data.message || '加载页面数据失败';
        }
      })
      .catch(error => {
        this.isLoading = false;
        console.error('分页请求错误:', error);
        this.errorinfo = `请求错误: ${error.response ? error.response.status + ' - ' + error.response.statusText : error.message}`;
      });
    }
  }
}
</script>

<style>
.search {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 1rem;
}

.search-container {
  max-width: 800px;
  margin: 0 auto;
}

.search-input-group {
  display: flex;
  background: white;
  border-radius: 4px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
}

.select-wrapper {
  position: relative;
  width: 120px;
  border-right: 1px solid #eaeaea;
}

.select-arrow {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 12px;
  color: #666;
  pointer-events: none;
}

.search-input-wrapper {
  position: relative;
  flex: 1;
  display: flex;
}

.fluent-select {
  appearance: none;
  width: 100%;
  height: 50px;
  padding: 0 30px 0 15px;
  border: none;
  background: transparent;
  font-size: 14px;
  color: #333;
  cursor: pointer;
}

.fluent-input {
  flex: 1;
  height: 50px;
  padding: 0 60px 0 15px;
  border: none;
  font-size: 16px;
  outline: none;
}

.search-button {
  position: absolute;
  right: 0;
  top: 0;
  width: 50px;
  height: 50px;
  background: transparent;
  border: none;
  color: #4b9cd3;
  cursor: pointer;
  transition: background-color 0.2s;
}

.search-button:hover {
  background-color: rgba(75, 156, 211, 0.1);
}

.results-container {
  margin-top: 2rem;
  background: white;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.results-table-wrapper {
  overflow-x: auto;
}

.fluent-table {
  width: 100%;
  border-collapse: collapse;
}

.fluent-table th,
.fluent-table td {
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid #f0f0f0;
  color: #333; /* 确保文字颜色足够深，提高可读性 */
}

.fluent-table th {
  background-color: #f0f7ff; /* 使用浅蓝色的表头背景 */
  font-weight: 600;
  color: #333;
}

.fluent-table tr:last-child td {
  border-bottom: none;
}

.fluent-table tr:hover td {
  background-color: #f0f7ff;
}

.password-cell {
  cursor: pointer;
  position: relative;
}

.password-cell:hover {
  background-color: #e8f1fa !important;
}

.password-toggle-hint {
  position: absolute;
  bottom: 0;
  left: 16px;
  font-size: 10px;
  color: #999;
  opacity: 0;
  transition: opacity 0.2s;
}

.password-cell:hover .password-toggle-hint {
  opacity: 1;
}

.pagination-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-top: 1px solid #f0f0f0;
}

.pagination-controls {
  display: flex;
  align-items: center;
  gap: 16px;
}

.limit-control {
  display: flex;
  align-items: center;
  gap: 8px;
}

.limit-input {
  width: 50px;
  height: 36px;
  text-align: center;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.data-count, .data-count-single {
  color: #333;
  font-size: 14px;
  padding: 16px;
  font-weight: 500;
}

.alert-error {
  margin: 16px 0;
  padding: 12px 16px;
  background-color: #fdeded;
  color: #d13438;
  border-radius: 4px;
  border-left: 3px solid #d13438;
}

.loading-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 2rem 0;
  color: #4b9cd3;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid rgba(75, 156, 211, 0.2);
  border-top-color: #4b9cd3;
  border-radius: 50%;
  margin-right: 10px;
  animation: spin 1s linear infinite;
}

.no-results {
  margin: 3rem 0;
  text-align: center;
  color: #666;
}

.no-results-icon {
  margin-bottom: 1rem;
}

.no-results p {
  font-size: 16px;
  margin: 0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 768px) {
  .search-input-group {
    flex-direction: column;
  }
  
  .select-wrapper {
    width: 100%;
    border-right: none;
    border-bottom: 1px solid #eaeaea;
  }
  
  .pagination-container {
    flex-direction: column;
    gap: 16px;
  }
  
  .pagination-controls {
    width: 100%;
    flex-direction: column;
    gap: 16px;
  }
}
</style>