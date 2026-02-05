/**
 * HIDRS 语言管理器
 * 支持中英文切换
 */

const translations = {
    zh: {
        // 导航
        'nav.home': '首页',
        'nav.search': '搜索',
        'nav.network': '网络拓扑',
        'nav.dashboard': '仪表盘',
        'nav.feedback': '决策反馈',
        'nav.plugins': '插件管理',

        // 首页
        'home.title': '全息互联网动态实时搜索系统',
        'home.subtitle': '基于拉普拉斯矩阵谱分析和全息映射的高效信息检索平台',
        'home.feature1.title': '全息映射',
        'home.feature1.desc': '利用全息映射技术，将局部网络拓扑信息映射到全局表示，实现信息的高维压缩与一致性保持。',
        'home.feature1.btn': '查看网络拓扑',
        'home.feature2.title': '实时搜索',
        'home.feature2.desc': '基于Fiedler向量和谱聚类的高效索引结构，支持复杂语义查询和相似性搜索。',
        'home.feature2.btn': '开始搜索',
        'home.feature3.title': '智能决策',
        'home.feature3.desc': '通过实时监控拓扑变化和Fiedler值动态，自动生成爬取策略和系统优化建议。',
        'home.feature3.btn': '查看决策反馈',
        'home.copyright': '© 2026 全息互联网动态实时搜索系统',

        // 设置
        'settings.title': '设置',
        'settings.theme': '主题',
        'settings.theme.default': '默认主题',
        'settings.theme.dark': '深色主题',
        'settings.theme.blue': '蓝色主题',
        'settings.theme.purple': '紫色主题',
        'settings.theme.green': '绿色主题',
        'settings.background': '背景',
        'settings.bg.upload': '上传自定义背景',
        'settings.opacity': '内容透明度',
        'settings.glass-effect': '毛玻璃效果',
        'settings.language': '语言',

        // 搜索页
        'search.title': '搜索',
        'search.placeholder': '输入搜索关键词...',
        'search.button': '搜索',
        'search.advanced': '高级搜索',
        'search.cache': '使用缓存',
        'search.filter.time': '时间范围',
        'search.filter.time.1h': '过去1小时',
        'search.filter.time.24h': '过去24小时',
        'search.filter.time.7d': '过去7天',
        'search.filter.time.30d': '过去30天',
        'search.filter.time.custom': '自定义范围',
        'search.filter.platform': '数据源',
        'search.filter.platform.all': '全部',
        'search.results': '搜索结果',
        'search.no-results': '未找到结果',
        'search.loading': '搜索中...',

        // 插件管理
        'plugins.title': '插件管理',
        'plugins.subtitle': '管理和配置 HIDRS 插件系统',
        'plugins.stats.total': '总插件数',
        'plugins.stats.enabled': '已启用',
        'plugins.stats.loaded': '已加载',
        'plugins.stats.available': '可用插件',
        'plugins.empty.title': '暂无插件',
        'plugins.empty.message': '请在 plugins/ 目录下添加插件文件',

        // 本地文件搜索
        'nav.local-files': '本地文件',

        // 通用
        'common.loading': '加载中...',
        'common.error': '错误',
        'common.success': '成功',
        'common.cancel': '取消',
        'common.confirm': '确认',
        'common.save': '保存',
        'common.delete': '删除',
        'common.edit': '编辑',
        'common.export': '导出',
        'common.refresh': '刷新'
    },

    en: {
        // Navigation
        'nav.home': 'Home',
        'nav.search': 'Search',
        'nav.network': 'Network',
        'nav.dashboard': 'Dashboard',
        'nav.feedback': 'Feedback',
        'nav.plugins': 'Plugins',

        // Home
        'home.title': 'Holographic Internet Dynamic Real-time Search System',
        'home.subtitle': 'Efficient Information Retrieval Platform Based on Laplacian Matrix Spectral Analysis and Holographic Mapping',
        'home.feature1.title': 'Holographic Mapping',
        'home.feature1.desc': 'Utilizing holographic mapping technology to map local network topology information to global representation, achieving high-dimensional compression and consistency maintenance.',
        'home.feature1.btn': 'View Network',
        'home.feature2.title': 'Real-time Search',
        'home.feature2.desc': 'Efficient index structure based on Fiedler vectors and spectral clustering, supporting complex semantic queries and similarity search.',
        'home.feature2.btn': 'Start Search',
        'home.feature3.title': 'Intelligent Decision',
        'home.feature3.desc': 'Automatically generate crawling strategies and system optimization suggestions by monitoring topology changes and Fiedler value dynamics in real-time.',
        'home.feature3.btn': 'View Feedback',
        'home.copyright': '© 2026 Holographic Internet Dynamic Real-time Search System',

        // Settings
        'settings.title': 'Settings',
        'settings.theme': 'Theme',
        'settings.theme.default': 'Default Theme',
        'settings.theme.dark': 'Dark Theme',
        'settings.theme.blue': 'Blue Theme',
        'settings.theme.purple': 'Purple Theme',
        'settings.theme.green': 'Green Theme',
        'settings.background': 'Background',
        'settings.bg.upload': 'Upload Custom Background',
        'settings.opacity': 'Content Opacity',
        'settings.glass-effect': 'Glass Effect',
        'settings.language': 'Language',

        // Search
        'search.title': 'Search',
        'search.placeholder': 'Enter search keywords...',
        'search.button': 'Search',
        'search.advanced': 'Advanced Search',
        'search.cache': 'Use Cache',
        'search.filter.time': 'Time Range',
        'search.filter.time.1h': 'Last Hour',
        'search.filter.time.24h': 'Last 24 Hours',
        'search.filter.time.7d': 'Last 7 Days',
        'search.filter.time.30d': 'Last 30 Days',
        'search.filter.time.custom': 'Custom Range',
        'search.filter.platform': 'Data Source',
        'search.filter.platform.all': 'All',
        'search.results': 'Search Results',
        'search.no-results': 'No results found',
        'search.loading': 'Searching...',

        // Plugins
        'plugins.title': 'Plugin Management',
        'plugins.subtitle': 'Manage and configure HIDRS plugin system',
        'plugins.stats.total': 'Total Plugins',
        'plugins.stats.enabled': 'Enabled',
        'plugins.stats.loaded': 'Loaded',
        'plugins.stats.available': 'Available',
        'plugins.empty.title': 'No Plugins',
        'plugins.empty.message': 'Please add plugin files to the plugins/ directory',

        // Local File Search
        'nav.local-files': 'Local Files',

        // Common
        'common.loading': 'Loading...',
        'common.error': 'Error',
        'common.success': 'Success',
        'common.cancel': 'Cancel',
        'common.confirm': 'Confirm',
        'common.save': 'Save',
        'common.delete': 'Delete',
        'common.edit': 'Edit',
        'common.export': 'Export',
        'common.refresh': 'Refresh'
    }
};

class LanguageManager {
    constructor() {
        this.currentLang = localStorage.getItem('hidrs-language') || 'zh';
    }

    init() {
        this.applyLanguage();
        this.bindEvents();
        this.updateUI();
    }

    bindEvents() {
        // 语言切换按钮
        document.querySelectorAll('[data-lang]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const lang = e.target.dataset.lang;
                this.setLanguage(lang);
            });
        });
    }

    setLanguage(lang) {
        if (!translations[lang]) {
            console.error(`Language ${lang} not supported`);
            return;
        }

        this.currentLang = lang;
        localStorage.setItem('hidrs-language', lang);
        this.applyLanguage();
        this.updateUI();
    }

    applyLanguage() {
        // 更新所有带有 data-i18n 属性的元素
        document.querySelectorAll('[data-i18n]').forEach(element => {
            const key = element.dataset.i18n;
            const translation = this.t(key);
            if (translation) {
                // 根据元素类型更新内容
                if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
                    element.placeholder = translation;
                } else {
                    element.textContent = translation;
                }
            }
        });

        // 更新 HTML lang 属性
        document.documentElement.lang = this.currentLang;
    }

    t(key) {
        const keys = key.split('.');
        let value = translations[this.currentLang];

        for (const k of keys) {
            if (value && value[k]) {
                value = value[k];
            } else {
                console.warn(`Translation key not found: ${key}`);
                return key;
            }
        }

        return value;
    }

    updateUI() {
        // 更新语言选择器的激活状态
        document.querySelectorAll('[data-lang]').forEach(btn => {
            if (btn.dataset.lang === this.currentLang) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    }
}

// 初始化语言管理器
document.addEventListener('DOMContentLoaded', () => {
    window.languageManager = new LanguageManager();
    window.languageManager.init();
});
