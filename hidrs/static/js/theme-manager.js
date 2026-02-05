/**
 * HIDRS 主题管理器
 * 管理主题、背景、透明度设置
 */

class ThemeManager {
    constructor() {
        this.themes = ['theme-default', 'theme-dark', 'theme-blue', 'theme-purple', 'theme-green'];
        this.backgrounds = ['bg-image-none', 'bg-image-anime1', 'bg-image-anime2', 'bg-image-abstract', 'bg-image-tech', 'bg-image-custom'];
        this.opacities = ['content-opacity-100', 'content-opacity-90', 'content-opacity-80', 'content-opacity-70'];

        this.currentTheme = localStorage.getItem('hidrs-theme') || 'theme-default';
        this.currentBg = localStorage.getItem('hidrs-background') || 'bg-image-none';
        this.currentOpacity = localStorage.getItem('hidrs-opacity') || 'content-opacity-100';
        this.glassEffect = localStorage.getItem('hidrs-glass-effect') === 'true';
        this.customBgUrl = localStorage.getItem('hidrs-custom-bg');
    }

    init() {
        this.applyTheme();
        this.applyBackground();
        this.applyOpacity();
        this.applyGlassEffect();
        this.bindEvents();
        this.updateUI();
    }

    bindEvents() {
        // 主题选择器
        const themeSelector = document.getElementById('theme-selector');
        if (themeSelector) {
            themeSelector.value = this.currentTheme;
            themeSelector.addEventListener('change', (e) => {
                this.setTheme(e.target.value);
            });
        }

        // 背景选项
        document.querySelectorAll('.bg-option').forEach(option => {
            option.addEventListener('click', (e) => {
                const bg = e.currentTarget.dataset.bg;
                if (bg === 'bg-image-custom') {
                    document.getElementById('custom-bg-upload').click();
                } else {
                    this.setBackground(bg);
                }
            });
        });

        // 自定义背景上传
        const customBgUpload = document.getElementById('custom-bg-upload');
        if (customBgUpload) {
            customBgUpload.addEventListener('change', (e) => {
                const file = e.target.files[0];
                if (file) {
                    this.uploadCustomBackground(file);
                }
            });
        }

        // 透明度选项
        document.querySelectorAll('.opacity-option').forEach(option => {
            option.addEventListener('click', (e) => {
                const opacity = e.currentTarget.dataset.opacity;
                this.setOpacity(opacity);
            });
        });

        // 毛玻璃效果
        const glassEffectToggle = document.getElementById('glass-effect-toggle');
        if (glassEffectToggle) {
            glassEffectToggle.checked = this.glassEffect;
            glassEffectToggle.addEventListener('change', (e) => {
                this.setGlassEffect(e.target.checked);
            });
        }
    }

    setTheme(theme) {
        // 移除所有主题类
        this.themes.forEach(t => document.body.classList.remove(t));
        // 应用新主题
        document.body.classList.add(theme);
        this.currentTheme = theme;
        localStorage.setItem('hidrs-theme', theme);
        this.updateThemeIcon();
    }

    setBackground(bg) {
        // 移除所有背景类
        this.backgrounds.forEach(b => document.body.classList.remove(b));
        // 应用新背景
        document.body.classList.add(bg);
        this.currentBg = bg;
        localStorage.setItem('hidrs-background', bg);
        this.updateUI();
    }

    setOpacity(opacity) {
        // 移除所有透明度类
        this.opacities.forEach(o => document.body.classList.remove(o));
        // 应用新透明度
        document.body.classList.add(opacity);
        this.currentOpacity = opacity;
        localStorage.setItem('hidrs-opacity', opacity);
        this.updateUI();
    }

    setGlassEffect(enabled) {
        if (enabled) {
            document.body.classList.add('glass-effect');
        } else {
            document.body.classList.remove('glass-effect');
        }
        this.glassEffect = enabled;
        localStorage.setItem('hidrs-glass-effect', enabled);
    }

    uploadCustomBackground(file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            const dataUrl = e.target.result;
            this.customBgUrl = dataUrl;
            localStorage.setItem('hidrs-custom-bg', dataUrl);
            document.body.style.backgroundImage = `url(${dataUrl})`;
            this.setBackground('bg-image-custom');
        };
        reader.readAsDataURL(file);
    }

    applyTheme() {
        document.body.classList.add(this.currentTheme);
    }

    applyBackground() {
        document.body.classList.add(this.currentBg);
        if (this.currentBg === 'bg-image-custom' && this.customBgUrl) {
            document.body.style.backgroundImage = `url(${this.customBgUrl})`;
        }
    }

    applyOpacity() {
        document.body.classList.add(this.currentOpacity);
    }

    applyGlassEffect() {
        if (this.glassEffect) {
            document.body.classList.add('glass-effect');
        }
    }

    updateUI() {
        // 更新背景选项的激活状态
        document.querySelectorAll('.bg-option').forEach(option => {
            const bg = option.dataset.bg;
            if (bg === this.currentBg) {
                option.classList.add('active');
            } else {
                option.classList.remove('active');
            }
        });

        // 更新透明度选项的激活状态
        document.querySelectorAll('.opacity-option').forEach(option => {
            const opacity = option.dataset.opacity;
            if (opacity === this.currentOpacity) {
                option.classList.add('active');
            } else {
                option.classList.remove('active');
            }
        });
    }

    updateThemeIcon() {
        const icon = document.querySelector('.theme-icon');
        if (!icon) return;

        const icons = {
            'theme-default': '☀️',
            'theme-dark': '🌙',
            'theme-blue': '🌊',
            'theme-purple': '🔮',
            'theme-green': '🌲'
        };

        icon.textContent = icons[this.currentTheme] || '☀️';
    }
}

// 初始化主题管理器
document.addEventListener('DOMContentLoaded', () => {
    window.themeManager = new ThemeManager();
    window.themeManager.init();
});
