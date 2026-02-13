import Vue from 'vue'
import Vuex from 'vuex'

Vue.use(Vuex)

// 主题预设
const themePresets = {
  // 银狼主题 (紫色)
  'silver-wolf': {
    id: 'silver-wolf',
    name: '银狼 Silver Wolf',
    primaryColor: '#6A79E3',
    primaryDark: '#4856C7',
    primaryLight: '#8089E8',
    secondaryColor: '#8089E8',
    backgroundColor: '#f5f5f5',
    cardBgColor: '#ffffff',
    textColor: '#323130',
    textLight: '#666666',
    borderColor: '#e0e0e0',
    chartColors: [
      '#6A79E3', '#8089E8', '#9BA3ED', '#B5BBF2', '#CED2F7',
      '#4856C7', '#5F6DD5', '#7784DE', '#A0A8EB', '#D8DBF9'
    ],
    // 暗黑模式变体
    dark: {
      primaryColor: '#5968D2',
      backgroundColor: '#1e1e1e',
      cardBgColor: '#2d2d2d',
      textColor: '#e0e0e0',
      textLight: '#b0b0b0',
      borderColor: '#444444'
    }
  },
  // SED 原版主题 (蓝色)
  'sed-classic': {
    id: 'sed-classic',
    name: 'SED 经典',
    primaryColor: '#4b9cd3',
    primaryDark: '#3a7bb0',
    primaryLight: '#5dadec',
    secondaryColor: '#5dadec',
    backgroundColor: '#f5f5f5',
    cardBgColor: '#ffffff',
    textColor: '#323130',
    textLight: '#666666',
    borderColor: '#e0e0e0',
    chartColors: [
      '#4b9cd3', '#5dadec', '#7ec8e3', '#9dd9f3', '#bee9ff',
      '#3a7bb0', '#4a8bc0', '#5a9bd0', '#6aabe0', '#7abbf0'
    ],
    dark: {
      primaryColor: '#3a8bc3',
      backgroundColor: '#1a1f25',
      cardBgColor: '#252a32',
      textColor: '#e0e0e0',
      textLight: '#b0b0b0',
      borderColor: '#3a4550'
    }
  },
  // 赛博朋克主题 (青/粉)
  'cyberpunk': {
    id: 'cyberpunk',
    name: '赛博朋克',
    primaryColor: '#00d4ff',
    primaryDark: '#00a8cc',
    primaryLight: '#33ddff',
    secondaryColor: '#ff00aa',
    backgroundColor: '#0a0a0f',
    cardBgColor: '#12121a',
    textColor: '#e0e0e0',
    textLight: '#a0a0a0',
    borderColor: '#2a2a3a',
    chartColors: [
      '#00d4ff', '#ff00aa', '#00ff88', '#ffaa00', '#aa00ff',
      '#00ffff', '#ff0066', '#66ff00', '#ff6600', '#6600ff'
    ],
    dark: {
      primaryColor: '#00d4ff',
      backgroundColor: '#050508',
      cardBgColor: '#0a0a12',
      textColor: '#e0e0e0',
      textLight: '#808080',
      borderColor: '#1a1a2a'
    }
  },
  // 暗夜猎手主题 (暗红)
  'night-hunter': {
    id: 'night-hunter',
    name: '暗夜猎手',
    primaryColor: '#dc143c',
    primaryDark: '#b01030',
    primaryLight: '#e63950',
    secondaryColor: '#8b0000',
    backgroundColor: '#1a1a1a',
    cardBgColor: '#252525',
    textColor: '#e0e0e0',
    textLight: '#a0a0a0',
    borderColor: '#333333',
    chartColors: [
      '#dc143c', '#ff4500', '#ff6347', '#ff7f50', '#ffa07a',
      '#8b0000', '#b22222', '#cd5c5c', '#f08080', '#fa8072'
    ],
    dark: {
      primaryColor: '#dc143c',
      backgroundColor: '#0f0f0f',
      cardBgColor: '#1a1a1a',
      textColor: '#e0e0e0',
      textLight: '#808080',
      borderColor: '#2a2a2a'
    }
  }
}

function applyThemeToCSS(theme, isDark = false) {
  const root = document.documentElement
  const colors = isDark && theme.dark ? { ...theme, ...theme.dark } : theme

  root.style.setProperty('--primary-color', colors.primaryColor)
  root.style.setProperty('--primary-dark', colors.primaryDark || colors.primaryColor)
  root.style.setProperty('--primary-light', colors.primaryLight || colors.primaryColor)
  root.style.setProperty('--secondary-color', colors.secondaryColor)
  root.style.setProperty('--background-color', colors.backgroundColor)
  root.style.setProperty('--card-bg-color', colors.cardBgColor)
  root.style.setProperty('--text-color', colors.textColor)
  root.style.setProperty('--text-light', colors.textLight)
  root.style.setProperty('--border-color', colors.borderColor)

  // 应用图表颜色
  if (colors.chartColors) {
    colors.chartColors.forEach((color, i) => {
      root.style.setProperty(`--chart-color-${i + 1}`, color)
    })
  }
}

export default new Vuex.Store({
  state: {
    systemMode: process.env.VUE_APP_MODE || 'local',
    remoteApiUrl: process.env.VUE_APP_REMOTE_API || '',
    // 主题系统
    currentThemeId: 'silver-wolf',
    isDarkMode: false,
    themePresets: themePresets,
    // 当前主题配置
    theme: { ...themePresets['silver-wolf'] },
    // API 状态
    apiConnected: false,
    apiStatus: {},
    // 搜索状态
    searchResults: [],
    searchTotal: 0,
    searchLoading: false,
    error: null,
    // 插件
    plugins: []
  },

  getters: {
    currentTheme: state => state.theme,
    availableThemes: state => Object.values(state.themePresets),
    chartColors: state => state.theme.chartColors || []
  },

  mutations: {
    SET_THEME_ID(state, themeId) {
      if (themePresets[themeId]) {
        state.currentThemeId = themeId
        state.theme = { ...themePresets[themeId] }
        applyThemeToCSS(state.theme, state.isDarkMode)
      }
    },
    SET_DARK_MODE(state, isDark) {
      state.isDarkMode = isDark
      document.body.classList.toggle('dark-mode', isDark)
      applyThemeToCSS(state.theme, isDark)
    },
    SET_CUSTOM_THEME(state, customTheme) {
      state.theme = { ...state.theme, ...customTheme }
      applyThemeToCSS(state.theme, state.isDarkMode)
    },
    SET_API_STATUS(state, status) {
      state.apiConnected = status.connected || false
      state.apiStatus = status
    },
    SET_SEARCH_RESULTS(state, { results, total }) {
      state.searchResults = results
      state.searchTotal = total
    },
    SET_SEARCH_LOADING(state, loading) {
      state.searchLoading = loading
    },
    SET_ERROR(state, error) {
      state.error = error
    },
    SET_PLUGINS(state, plugins) {
      state.plugins = plugins
    }
  },

  actions: {
    async initializeApp({ commit, dispatch }) {
      try {
        const response = await window.axios.get('/test')
        commit('SET_API_STATUS', {
          connected: true,
          mode: response.data.mode,
          version: response.data.version
        })
        dispatch('loadSystemStats')
      } catch (error) {
        console.error('API连接错误:', error)
        commit('SET_API_STATUS', { connected: false })
        commit('SET_ERROR', '无法连接到API服务')
      }
    },

    async loadSystemStats({ commit, state }) {
      try {
        const response = await window.axios.get('/stats')
        if (response.data.status === 'ok') {
          commit('SET_API_STATUS', {
            ...state.apiStatus,
            stats: response.data.data
          })
        }
      } catch (error) {
        console.error('加载系统统计失败:', error)
      }
    },

    async search({ commit }, { field, value, limit = 10, skip = 0 }) {
      commit('SET_SEARCH_LOADING', true)
      commit('SET_ERROR', null)
      try {
        const response = await window.axios.get(`/find/${field}/${encodeURIComponent(value)}?limit=${limit}&skip=${skip}`)
        if (response.data.status === 'ok') {
          commit('SET_SEARCH_RESULTS', {
            results: response.data.data,
            total: response.data.datacounts
          })
        } else {
          commit('SET_SEARCH_RESULTS', { results: [], total: 0 })
          if (response.data.status === 'error') {
            commit('SET_ERROR', response.data.message)
          }
        }
      } catch (error) {
        commit('SET_SEARCH_RESULTS', { results: [], total: 0 })
        commit('SET_ERROR', `搜索请求错误: ${error.message}`)
      } finally {
        commit('SET_SEARCH_LOADING', false)
      }
    },

    // 切换主题
    switchTheme({ commit, state }, themeId) {
      commit('SET_THEME_ID', themeId)
      localStorage.setItem('sed_theme_id', themeId)
      localStorage.setItem('sed_dark_mode', state.isDarkMode ? 'true' : 'false')
    },

    // 切换暗黑模式
    toggleDarkMode({ commit, state }) {
      const newDarkMode = !state.isDarkMode
      commit('SET_DARK_MODE', newDarkMode)
      localStorage.setItem('sed_dark_mode', newDarkMode ? 'true' : 'false')
    },

    // 加载保存的主题设置
    loadTheme({ commit }) {
      const savedThemeId = localStorage.getItem('sed_theme_id')
      const savedDarkMode = localStorage.getItem('sed_dark_mode')

      if (savedThemeId && themePresets[savedThemeId]) {
        commit('SET_THEME_ID', savedThemeId)
      } else {
        commit('SET_THEME_ID', 'silver-wolf')
      }

      if (savedDarkMode === 'true') {
        commit('SET_DARK_MODE', true)
      }
    },

    // 自定义主题颜色
    customizeTheme({ commit, state }, customColors) {
      commit('SET_CUSTOM_THEME', customColors)
      localStorage.setItem('sed_custom_theme', JSON.stringify({
        ...state.theme,
        ...customColors
      }))
    }
  }
})
