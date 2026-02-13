<template>
  <div class="login-page">
    <div class="login-container">
      <div class="login-header">
        <h1>银狼数据安全平台</h1>
        <p>Silver Wolf Security Platform</p>
      </div>
      <div class="login-form">
        <div class="form-group">
          <label for="username">用户名</label>
          <input type="text" id="username" v-model="username" placeholder="请输入用户名" class="fluent-input" @keyup.enter="handleLogin"/>
        </div>
        <div class="form-group">
          <label for="password">密码</label>
          <input type="password" id="password" v-model="password" placeholder="请输入密码" class="fluent-input" @keyup.enter="handleLogin"/>
        </div>
        <div class="error-message" v-if="errorMsg">{{ errorMsg }}</div>
        <button class="login-button" @click="handleLogin" :disabled="isLoading">
          {{ isLoading ? '登录中...' : '登录' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'Login',
  data() {
    return { username: '', password: '', errorMsg: '', isLoading: false }
  },
  methods: {
    async handleLogin() {
      if (!this.username || !this.password) {
        this.errorMsg = '请输入用户名和密码';
        return;
      }
      this.isLoading = true;
      this.errorMsg = '';
      try {
        const response = await axios.post('/auth/login', { username: this.username, password: this.password });
        if (response.data.status === 'ok') {
          localStorage.setItem('token', response.data.token);
          this.$router.push('/');
        } else {
          this.errorMsg = response.data.message || '登录失败';
        }
      } catch (error) {
        this.errorMsg = '登录请求失败: ' + error.message;
      } finally {
        this.isLoading = false;
      }
    }
  }
}
</script>

<style scoped>
.login-page { display: flex; justify-content: center; align-items: center; min-height: 100vh; background: linear-gradient(135deg, #6A79E3, #4856C7); }
.login-container { background: white; border-radius: 12px; padding: 3rem; width: 400px; max-width: 90%; box-shadow: 0 8px 32px rgba(0,0,0,0.2); }
.login-header { text-align: center; margin-bottom: 2rem; }
.login-header h1 { color: #6A79E3; font-size: 1.8rem; margin: 0 0 0.5rem; }
.login-header p { color: #999; font-size: 0.9rem; margin: 0; }
.form-group { margin-bottom: 1.5rem; }
.form-group label { display: block; margin-bottom: 0.5rem; font-weight: 500; color: #333; }
.form-group .fluent-input { width: 100%; padding: 12px; border: 1px solid #e0e0e0; border-radius: 6px; font-size: 14px; box-sizing: border-box; }
.error-message { color: #ef4444; font-size: 14px; margin-bottom: 1rem; }
.login-button { width: 100%; padding: 12px; background: #6A79E3; color: white; border: none; border-radius: 6px; font-size: 16px; cursor: pointer; transition: background 0.2s; }
.login-button:hover { background: #4856C7; }
.login-button:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
