/**
 * FAIRY-DESK 核心 JavaScript
 * 事件总线、Tab 管理、配置管理
 */

// ============================================================
// 全局配置
// ============================================================

const FairyDesk = {
  config: null,
  hidrsConnected: false,
  activeTab: null,
  tabIframes: {},  // Tab iframe 缓存
  eventSource: null,
  clockInterval: null
};

// API 基础路径
const API_BASE = '';

// ============================================================
// 初始化
// ============================================================

document.addEventListener('DOMContentLoaded', async () => {
  // 加载配置
  await loadConfig();

  // 启动时钟
  startClock();

  // 检测 HIDRS
  checkHIDRSStatus();
  setInterval(checkHIDRSStatus, 30000);

  // 页面特定初始化
  const page = document.body.dataset.page;
  if (page === 'left') initLeftScreen();
  if (page === 'center') initCenterScreen();
  if (page === 'right') initRightScreen();
  if (page === 'settings') initSettingsPage();

  console.log('FAIRY-DESK 初始化完成');
});

// ============================================================
// 配置管理
// ============================================================

async function loadConfig() {
  try {
    const resp = await fetch(`${API_BASE}/api/config`);
    if (!resp.ok) throw new Error('配置加载失败');
    FairyDesk.config = await resp.json();
    // 应用主题
    applyTheme(FairyDesk.config?.theme?.name);
    return FairyDesk.config;
  } catch (err) {
    console.error('加载配置失败:', err);
    return null;
  }
}

function applyTheme(themeName) {
  if (themeName && themeName !== 'cyberpunk') {
    document.documentElement.setAttribute('data-theme', themeName);
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
}

async function saveConfig(config) {
  try {
    const resp = await fetch(`${API_BASE}/api/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    });
    if (!resp.ok) throw new Error('配置保存失败');
    FairyDesk.config = config;
    return true;
  } catch (err) {
    console.error('保存配置失败:', err);
    showNotification('配置保存失败', 'error');
    return false;
  }
}

// ============================================================
// 时钟
// ============================================================

function startClock() {
  const clockEl = document.getElementById('clock');
  if (!clockEl) return;

  function updateClock() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString('zh-CN', { hour12: false });
    const dateStr = now.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    });
    clockEl.textContent = `${dateStr} ${timeStr}`;
  }

  updateClock();
  FairyDesk.clockInterval = setInterval(updateClock, 1000);
}

// ============================================================
// HIDRS 检测
// ============================================================

async function checkHIDRSStatus() {
  const statusEl = document.getElementById('hidrs-status');
  if (!statusEl) return;

  try {
    const resp = await fetch(`${API_BASE}/api/hidrs/status`);
    const data = await resp.json();

    FairyDesk.hidrsConnected = data.connected;

    if (data.connected) {
      statusEl.className = 'hidrs-status connected';
      statusEl.innerHTML = '🟢 HIDRS';
    } else {
      statusEl.className = 'hidrs-status disconnected';
      statusEl.innerHTML = '🔴 HIDRS';
    }

    // 更新 HIDRS 提示区域
    const hintEl = document.getElementById('hidrs-hint');
    if (hintEl) {
      hintEl.style.display = data.connected ? 'none' : 'block';
    }

  } catch (err) {
    FairyDesk.hidrsConnected = false;
    if (statusEl) {
      statusEl.className = 'hidrs-status disconnected';
      statusEl.innerHTML = '🔴 HIDRS';
    }
  }
}

// ============================================================
// 左屏 Tab 系统
// ============================================================

function initLeftScreen() {
  const tabs = FairyDesk.config?.left_screen?.tabs || [];
  const defaultTab = FairyDesk.config?.left_screen?.default_tab || tabs[0]?.id;

  renderTabs(tabs);

  if (defaultTab) {
    switchTab(defaultTab);
  }
}

function renderTabs(tabs) {
  const tabBar = document.getElementById('tab-bar');
  if (!tabBar) return;

  tabBar.innerHTML = '';

  tabs.forEach(tab => {
    const tabEl = document.createElement('button');
    tabEl.className = 'tab-item';
    tabEl.dataset.tabId = tab.id;
    tabEl.innerHTML = `
      <span class="tab-icon">${tab.icon}</span>
      <span class="tab-name">${tab.name}</span>
      ${!tab.builtIn ? '<span class="tab-close" onclick="event.stopPropagation(); deleteTab(\'' + tab.id + '\')">×</span>' : ''}
    `;
    tabEl.onclick = () => switchTab(tab.id);

    // 右键菜单
    tabEl.oncontextmenu = (e) => {
      e.preventDefault();
      showTabContextMenu(e, tab);
    };

    tabBar.appendChild(tabEl);
  });

  // 添加按钮
  const addBtn = document.createElement('button');
  addBtn.className = 'tab-add';
  addBtn.innerHTML = '+';
  addBtn.onclick = showAddTabModal;
  addBtn.title = '添加新分页';
  tabBar.appendChild(addBtn);
}

function switchTab(tabId) {
  const tabs = FairyDesk.config?.left_screen?.tabs || [];
  const tab = tabs.find(t => t.id === tabId);
  if (!tab) return;

  // 更新 Tab 样式
  document.querySelectorAll('.tab-item').forEach(el => {
    el.classList.toggle('active', el.dataset.tabId === tabId);
  });

  // 更新内容区
  const contentArea = document.getElementById('tab-content');
  if (!contentArea) return;

  FairyDesk.activeTab = tabId;

  // 根据加载策略处理 iframe
  if (tab.loadStrategy === 'background') {
    // 背景同步：保持所有 background 策略的 iframe
    showOrCreateIframe(tab, contentArea);
  } else {
    // 懒加载：只显示当前 Tab 的 iframe
    contentArea.innerHTML = '';
    createIframe(tab, contentArea);
  }

  // 更新底部信息
  const sourceInfo = document.getElementById('source-info');
  if (sourceInfo) {
    sourceInfo.textContent = `${tab.icon} ${tab.name} - ${new URL(tab.url).hostname}`;
  }
}

function showOrCreateIframe(tab, container) {
  // 隐藏所有 iframe
  container.querySelectorAll('.tab-pane').forEach(pane => {
    pane.classList.remove('active');
  });

  // 查找或创建当前 Tab 的 iframe
  let pane = container.querySelector(`[data-tab-id="${tab.id}"]`);
  if (!pane) {
    pane = document.createElement('div');
    pane.className = 'tab-pane';
    pane.dataset.tabId = tab.id;
    const iframe = document.createElement('iframe');
    iframe.src = tab.url;
    iframe.setAttribute('loading', 'lazy');
    iframe.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-popups allow-forms');
    pane.appendChild(iframe);
    container.appendChild(pane);
  }
  pane.classList.add('active');
}

function createIframe(tab, container) {
  const pane = document.createElement('div');
  pane.className = 'tab-pane active';
  pane.dataset.tabId = tab.id;
  const iframe = document.createElement('iframe');
  iframe.src = tab.url;
  iframe.setAttribute('loading', 'lazy');
  iframe.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-popups allow-forms');
  pane.appendChild(iframe);
  container.appendChild(pane);
}

// Tab 右键菜单
function showTabContextMenu(e, tab) {
  // 移除已存在的菜单
  document.querySelectorAll('.context-menu').forEach(m => m.remove());

  const menu = document.createElement('div');
  menu.className = 'context-menu';
  menu.style.cssText = `
    position: fixed;
    left: ${e.clientX}px;
    top: ${e.clientY}px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    padding: 4px 0;
    min-width: 150px;
    z-index: 1000;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  `;

  const items = [
    { icon: '🔄', text: '刷新', action: () => refreshTab(tab.id) },
    { icon: '⚡', text: '背景同步', action: () => setTabStrategy(tab.id, 'background') },
    { icon: '💤', text: '懒加载', action: () => setTabStrategy(tab.id, 'lazy') },
    { icon: '🧠', text: '智能休眠', action: () => setTabStrategy(tab.id, 'smart') },
    { divider: true },
    { icon: '✏️', text: '编辑', action: () => showEditTabModal(tab) },
    { icon: '🔗', text: '新窗口打开', action: () => window.open(tab.url, '_blank') },
  ];

  if (!tab.builtIn) {
    items.push({ divider: true });
    items.push({ icon: '❌', text: '删除', action: () => deleteTab(tab.id), danger: true });
  }

  items.forEach(item => {
    if (item.divider) {
      const hr = document.createElement('hr');
      hr.style.cssText = 'border: none; border-top: 1px solid var(--border-color); margin: 4px 0;';
      menu.appendChild(hr);
    } else {
      const menuItem = document.createElement('div');
      menuItem.style.cssText = `
        padding: 8px 12px;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 13px;
        color: ${item.danger ? 'var(--status-danger)' : 'var(--text-primary)'};
      `;
      menuItem.innerHTML = `<span>${item.icon}</span><span>${item.text}</span>`;
      menuItem.onmouseenter = () => menuItem.style.background = 'rgba(0,240,255,0.1)';
      menuItem.onmouseleave = () => menuItem.style.background = 'transparent';
      menuItem.onclick = () => {
        item.action();
        menu.remove();
      };
      menu.appendChild(menuItem);
    }
  });

  document.body.appendChild(menu);

  // 点击其他地方关闭
  setTimeout(() => {
    document.addEventListener('click', function closeMenu() {
      menu.remove();
      document.removeEventListener('click', closeMenu);
    }, { once: true });
  }, 0);
}

function refreshTab(tabId) {
  const iframe = document.querySelector(`.tab-pane[data-tab-id="${tabId}"] iframe`);
  if (iframe) {
    iframe.src = iframe.src;
  }
}

async function setTabStrategy(tabId, strategy) {
  const tabs = FairyDesk.config.left_screen.tabs;
  const tab = tabs.find(t => t.id === tabId);
  if (tab) {
    tab.loadStrategy = strategy;
    await saveConfig(FairyDesk.config);
    showNotification(`已设置为${strategy === 'background' ? '背景同步' : strategy === 'lazy' ? '懒加载' : '智能休眠'}`, 'success');
  }
}

async function deleteTab(tabId) {
  if (!confirm('确定删除此分页？')) return;

  try {
    const resp = await fetch(`${API_BASE}/api/config/tabs/${tabId}`, {
      method: 'DELETE'
    });
    if (!resp.ok) throw new Error('删除失败');

    await loadConfig();
    renderTabs(FairyDesk.config.left_screen.tabs);
    showNotification('分页已删除', 'success');
  } catch (err) {
    showNotification('删除失败: ' + err.message, 'error');
  }
}

// 添加新 Tab 模态框
function showAddTabModal() {
  showModal('添加新分页', `
    <div class="form-group">
      <label class="form-label">名称</label>
      <input type="text" id="new-tab-name" class="form-input" placeholder="例如: YouTube">
    </div>
    <div class="form-group">
      <label class="form-label">图标 (Emoji)</label>
      <input type="text" id="new-tab-icon" class="form-input" placeholder="例如: 📺" maxlength="4">
    </div>
    <div class="form-group">
      <label class="form-label">URL</label>
      <input type="url" id="new-tab-url" class="form-input" placeholder="https://...">
    </div>
    <div class="form-group">
      <label class="form-label">加载策略</label>
      <select id="new-tab-strategy" class="form-input form-select">
        <option value="lazy">懒加载 (推荐)</option>
        <option value="background">背景同步</option>
        <option value="smart">智能休眠</option>
      </select>
    </div>
  `, async () => {
    const name = document.getElementById('new-tab-name').value.trim();
    const icon = document.getElementById('new-tab-icon').value.trim() || '🌐';
    const url = document.getElementById('new-tab-url').value.trim();
    const strategy = document.getElementById('new-tab-strategy').value;

    if (!name || !url) {
      showNotification('请填写名称和 URL', 'error');
      return false;
    }

    try {
      const resp = await fetch(`${API_BASE}/api/config/tabs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, icon, url, loadStrategy: strategy })
      });

      if (!resp.ok) throw new Error('添加失败');

      await loadConfig();
      renderTabs(FairyDesk.config.left_screen.tabs);
      showNotification('分页已添加', 'success');
      return true;
    } catch (err) {
      showNotification('添加失败: ' + err.message, 'error');
      return false;
    }
  });
}

function showEditTabModal(tab) {
  showModal('编辑分页', `
    <div class="form-group">
      <label class="form-label">名称</label>
      <input type="text" id="edit-tab-name" class="form-input" value="${tab.name}">
    </div>
    <div class="form-group">
      <label class="form-label">图标 (Emoji)</label>
      <input type="text" id="edit-tab-icon" class="form-input" value="${tab.icon}" maxlength="4">
    </div>
    <div class="form-group">
      <label class="form-label">URL</label>
      <input type="url" id="edit-tab-url" class="form-input" value="${tab.url}">
    </div>
    <div class="form-group">
      <label class="form-label">加载策略</label>
      <select id="edit-tab-strategy" class="form-input form-select">
        <option value="lazy" ${tab.loadStrategy === 'lazy' ? 'selected' : ''}>懒加载</option>
        <option value="background" ${tab.loadStrategy === 'background' ? 'selected' : ''}>背景同步</option>
        <option value="smart" ${tab.loadStrategy === 'smart' ? 'selected' : ''}>智能休眠</option>
      </select>
    </div>
  `, async () => {
    const name = document.getElementById('edit-tab-name').value.trim();
    const icon = document.getElementById('edit-tab-icon').value.trim();
    const url = document.getElementById('edit-tab-url').value.trim();
    const strategy = document.getElementById('edit-tab-strategy').value;

    if (!name || !url) {
      showNotification('请填写名称和 URL', 'error');
      return false;
    }

    try {
      const resp = await fetch(`${API_BASE}/api/config/tabs/${tab.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, icon, url, loadStrategy: strategy })
      });

      if (!resp.ok) throw new Error('更新失败');

      await loadConfig();
      renderTabs(FairyDesk.config.left_screen.tabs);
      showNotification('分页已更新', 'success');
      return true;
    } catch (err) {
      showNotification('更新失败: ' + err.message, 'error');
      return false;
    }
  });
}

// ============================================================
// 中屏控制台
// ============================================================

function initCenterScreen() {
  // 系统监控
  updateSystemStats();
  setInterval(updateSystemStats, FairyDesk.config?.center_screen?.refresh_interval * 1000 || 5000);

  // 系统日志
  initSystemLogs();
}

async function updateSystemStats() {
  try {
    const resp = await fetch(`${API_BASE}/api/system/stats`);
    if (!resp.ok) return;
    const stats = await resp.json();

    // CPU
    updateMetric('cpu', stats.cpu.percent, '%');

    // 内存
    updateMetric('memory', stats.memory.percent, '%',
      `${stats.memory.used_gb}/${stats.memory.total_gb} GB`);

    // 网络
    const netMB = (stats.network.bytes_recv / 1024 / 1024).toFixed(1);
    updateMetric('network', Math.min(netMB, 100), '',
      `${stats.network.connections} 连接`);

    // GPU
    if (stats.gpu) {
      updateMetric('gpu', stats.gpu.util_percent, '%',
        `${stats.gpu.memory_used_mb}/${stats.gpu.memory_total_mb} MB`);
    }

  } catch (err) {
    console.error('获取系统状态失败:', err);
  }
}

function updateMetric(id, value, suffix = '', extra = '') {
  const card = document.getElementById(`metric-${id}`);
  if (!card) return;

  const valueEl = card.querySelector('.metric-value');
  const barEl = card.querySelector('.metric-bar-fill');
  const extraEl = card.querySelector('.metric-extra');

  if (valueEl) valueEl.textContent = `${Math.round(value)}${suffix}`;
  if (barEl) barEl.style.width = `${Math.min(value, 100)}%`;
  if (extraEl && extra) extraEl.textContent = extra;

  // 状态颜色
  card.classList.remove('warning', 'danger');
  if (value > 90) card.classList.add('danger');
  else if (value > 70) card.classList.add('warning');
}

function initSystemLogs() {
  const logContainer = document.getElementById('system-logs');
  if (!logContainer) return;

  // 添加欢迎横幅
  if (!logContainer.dataset.initialized) {
    const banner = document.createElement('div');
    banner.className = 'terminal-line';
    banner.style.color = 'var(--neon-cyan)';
    banner.textContent = '═══ FAIRY-DESK 系统控制台 ═══';
    logContainer.appendChild(banner);
    logContainer.dataset.initialized = 'true';
  }

  // 加载历史日志
  fetch(`${API_BASE}/api/system/logs/history?limit=30`)
    .then(resp => resp.json())
    .then(logs => {
      logs.forEach(log => appendLog(log, logContainer));
      logContainer.scrollTop = logContainer.scrollHeight;
    })
    .catch(err => console.error('加载日志失败:', err));

  // SSE 实时日志
  const eventSource = new EventSource(`${API_BASE}/api/system/logs`);
  eventSource.onmessage = (e) => {
    const log = JSON.parse(e.data);
    appendLog(log, logContainer);
    logContainer.scrollTop = logContainer.scrollHeight;
  };
  eventSource.onerror = () => {
    console.warn('日志 SSE 连接断开');
  };
}

function appendLog(log, container) {
  const line = document.createElement('div');
  line.className = `terminal-line ${log.level}`;
  const time = new Date(log.time).toLocaleTimeString('zh-CN', { hour12: false });
  line.innerHTML = `<span class="time">${time}</span>${escapeHtml(log.message)}`;
  container.appendChild(line);

  // 限制日志条数
  while (container.children.length > 100) {
    container.removeChild(container.firstChild);
  }
}

// ============================================================
// 右屏情报视窗
// ============================================================

function initRightScreen() {
  // 新闻 RSS
  loadNewsFeeds();
  setInterval(loadNewsFeeds, 60000);

  // 告警流
  initAlertStream();

  // HIDRS 状态
  checkHIDRSStatus();
}

async function loadNewsFeeds() {
  const container = document.getElementById('news-feed');
  if (!container) return;

  try {
    const resp = await fetch(`${API_BASE}/api/feeds/news?limit=20`);
    if (!resp.ok) return;
    const items = await resp.json();

    const keywords = FairyDesk.config?.right_screen?.news?.highlight_keywords || [];

    container.innerHTML = items.map(item => {
      const isHighlight = keywords.some(kw =>
        item.title.toLowerCase().includes(kw.toLowerCase())
      );
      return `
        <div class="feed-item ${isHighlight ? 'highlight' : ''}" onclick="window.open('${escapeHtml(item.link)}', '_blank')">
          <div class="feed-source">${escapeHtml(item.source)}</div>
          <div class="feed-title">${escapeHtml(item.title)}</div>
          <div class="feed-time">${item.published || ''}</div>
        </div>
      `;
    }).join('');

  } catch (err) {
    console.error('加载新闻失败:', err);
  }
}

function initAlertStream() {
  const container = document.getElementById('alert-feed');
  if (!container) return;

  // 加载历史事件
  fetch(`${API_BASE}/api/events/history?limit=30`)
    .then(resp => resp.json())
    .then(events => {
      events.forEach(event => appendAlert(event, container));
    })
    .catch(err => console.error('加载事件失败:', err));

  // SSE 实时事件
  const eventSource = new EventSource(`${API_BASE}/api/events/stream`);
  eventSource.onmessage = (e) => {
    const event = JSON.parse(e.data);
    appendAlert(event, container, true);
  };
}

function appendAlert(event, container, prepend = false) {
  const iconMap = {
    'critical': '🔴',
    'warning': '🟡',
    'info': '🔵'
  };

  const item = document.createElement('div');
  item.className = `alert-item ${event.type || 'info'}`;
  item.innerHTML = `
    <span class="alert-icon">${iconMap[event.type] || '🔵'}</span>
    <div class="alert-content">
      <div class="alert-message">${escapeHtml(event.message || event.title || '')}</div>
      <div class="alert-time">${new Date(event.timestamp).toLocaleTimeString('zh-CN', { hour12: false })}</div>
    </div>
  `;

  if (prepend && container.firstChild) {
    container.insertBefore(item, container.firstChild);
  } else {
    container.appendChild(item);
  }

  // 限制条数
  const maxItems = FairyDesk.config?.right_screen?.alerts?.max_items || 50;
  while (container.children.length > maxItems) {
    container.removeChild(container.lastChild);
  }
}

// ============================================================
// 设置页面
// ============================================================

function initSettingsPage() {
  // 填充当前配置到表单
  populateSettingsForm();
}

function populateSettingsForm() {
  // 实现设置页面的表单填充
  // 这里简化处理，实际需要根据设置页面的 HTML 结构来实现
}

async function saveSettings() {
  // 收集表单数据并保存
  // 实现略
}

// ============================================================
// 工具函数
// ============================================================

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function showNotification(message, type = 'info') {
  // 简单的通知提示
  const noti = document.createElement('div');
  noti.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    padding: 12px 20px;
    background: var(--bg-secondary);
    border: 1px solid ${type === 'error' ? 'var(--status-danger)' : type === 'success' ? 'var(--status-success)' : 'var(--neon-cyan)'};
    border-radius: 4px;
    color: var(--text-primary);
    font-size: 14px;
    z-index: 9999;
    animation: slideIn 0.3s ease;
  `;
  noti.textContent = message;
  document.body.appendChild(noti);

  setTimeout(() => {
    noti.style.animation = 'slideOut 0.3s ease';
    setTimeout(() => noti.remove(), 300);
  }, 3000);
}

function showModal(title, content, onConfirm) {
  // 移除已存在的模态框
  document.querySelectorAll('.modal-overlay').forEach(m => m.remove());

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <div class="modal-header">
        <span class="modal-title">${title}</span>
        <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">×</button>
      </div>
      <div class="modal-body">${content}</div>
      <div class="modal-footer">
        <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">取消</button>
        <button class="btn btn-primary" id="modal-confirm">确定</button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  // 触发动画
  requestAnimationFrame(() => overlay.classList.add('active'));

  // 确认按钮
  const confirmBtn = overlay.querySelector('#modal-confirm');
  confirmBtn.onclick = async () => {
    const result = await onConfirm();
    if (result !== false) {
      overlay.remove();
    }
  };

  // 点击背景关闭
  overlay.onclick = (e) => {
    if (e.target === overlay) overlay.remove();
  };
}

// 添加动画样式
const style = document.createElement('style');
style.textContent = `
  @keyframes slideIn {
    from { transform: translateX(100%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
  }
  @keyframes slideOut {
    from { transform: translateX(0); opacity: 1; }
    to { transform: translateX(100%); opacity: 0; }
  }
`;
document.head.appendChild(style);
