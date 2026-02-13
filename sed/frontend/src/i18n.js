/**
 * 银狼数据安全平台 - 国际化配置
 */
const messages = {
  zh: {
    nav: {
      home: '首页',
      import: '数据导入',
      tools: '工具集',
      admin: '系统管理'
    },
    search: {
      placeholder: '请输入并按下回车进行搜索',
      button: '搜索',
      loading: '正在搜索中...',
      noResults: '未找到匹配数据',
      total: '共 {count} 条数据',
      fields: {
        user: '用户名',
        email: '邮箱',
        password: '密码',
        passwordHash: '密码哈希',
        source: '来源',
        xtime: '泄漏时间'
      }
    },
    analysis: {
      title: '数据分析',
      source: '来源分布',
      xtime: '泄露时间',
      suffix_email: '邮箱类型',
      create_time: '导入时间'
    },
    admin: {
      title: '系统管理',
      theme: '界面主题',
      plugins: '插件管理',
      importSettings: '导入设置'
    },
    common: {
      save: '保存',
      cancel: '取消',
      delete: '删除',
      edit: '编辑',
      confirm: '确认',
      close: '关闭',
      loading: '加载中...',
      success: '成功',
      error: '错误',
      warning: '警告'
    }
  },
  en: {
    nav: {
      home: 'Home',
      import: 'Import',
      tools: 'Tools',
      admin: 'Admin'
    },
    search: {
      placeholder: 'Enter search term and press Enter',
      button: 'Search',
      loading: 'Searching...',
      noResults: 'No results found',
      total: '{count} records total',
      fields: {
        user: 'Username',
        email: 'Email',
        password: 'Password',
        passwordHash: 'Hash',
        source: 'Source',
        xtime: 'Leak Time'
      }
    },
    analysis: {
      title: 'Data Analysis',
      source: 'Source Distribution',
      xtime: 'Leak Timeline',
      suffix_email: 'Email Domains',
      create_time: 'Import Timeline'
    },
    admin: {
      title: 'Administration',
      theme: 'Theme',
      plugins: 'Plugins',
      importSettings: 'Import Settings'
    },
    common: {
      save: 'Save',
      cancel: 'Cancel',
      delete: 'Delete',
      edit: 'Edit',
      confirm: 'Confirm',
      close: 'Close',
      loading: 'Loading...',
      success: 'Success',
      error: 'Error',
      warning: 'Warning'
    }
  }
}

export default messages
