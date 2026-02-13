<template>
  <div class="tools-page">
    <div class="page-header">
      <h1>工具集</h1>
      <p>实用安全分析工具</p>
    </div>
    <div class="tools-grid">
      <router-link to="/tools/numlookup" class="tool-card">
        <div class="tool-icon">📱</div>
        <h3>号码归属地查询</h3>
        <p>手机号归属地和身份证地区查询</p>
      </router-link>
      <div class="tool-card disabled">
        <div class="tool-icon">🔍</div>
        <h3>模糊搜索</h3>
        <p>高级模糊匹配搜索（开发中）</p>
      </div>
      <div class="tool-card disabled">
        <div class="tool-icon">🤖</div>
        <h3>AI分析</h3>
        <p>大模型辅助数据分析（开发中）</p>
      </div>
      <div class="tool-card disabled">
        <div class="tool-icon">📊</div>
        <h3>密码分析</h3>
        <p>密码强度和模式分析（开发中）</p>
      </div>
    </div>
  </div>
</template>

<script>
export default { name: 'Tools' }
</script>

<style scoped>
.tools-page { max-width: 1200px; margin: 0 auto; padding: 0 1rem; }
.page-header { text-align: center; margin-bottom: 2rem; }
.page-header h1 { font-size: 2rem; color: var(--primary-color); margin: 0 0 0.5rem; }
.page-header p { color: var(--text-light); margin: 0; }
.tools-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1.5rem; }
.tool-card { background: var(--card-bg-color); border-radius: 8px; padding: 2rem; text-align: center; text-decoration: none; color: var(--text-color); box-shadow: 0 2px 8px var(--shadow-color); transition: all 0.2s; cursor: pointer; border: 2px solid transparent; }
.tool-card:hover { border-color: var(--primary-color); transform: translateY(-2px); box-shadow: 0 4px 16px var(--shadow-color); }
.tool-card.disabled { opacity: 0.5; cursor: not-allowed; }
.tool-card.disabled:hover { transform: none; border-color: transparent; }
.tool-icon { font-size: 3rem; margin-bottom: 1rem; }
.tool-card h3 { margin: 0 0 0.5rem; font-size: 1.2rem; }
.tool-card p { margin: 0; font-size: 0.9rem; color: var(--text-light); }
</style>
