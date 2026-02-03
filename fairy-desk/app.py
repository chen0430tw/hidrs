#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FAIRY-DESK - 妖精桌面情报台
三联屏网页化指挥桌面 + Agent

独立运行，HIDRS 作为可选增强模块
"""

import json
import os
import time
import shutil
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import psutil
import requests
import feedparser
from flask import Flask, render_template, jsonify, request, Response
from flask_cors import CORS

# ============================================================
# 配置与初始化
# ============================================================

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Flask 应用
app = Flask(__name__)
CORS(app)

# 配置文件路径
CONFIG_PATH = Path(__file__).parent / 'config.json'

# 全局配置
config = {}

# 系统日志缓存（用于 SSE）
system_logs = []
MAX_LOG_ENTRIES = 100


def load_config():
    """加载配置文件"""
    global config
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger.info("配置文件加载成功")
    except FileNotFoundError:
        logger.warning("配置文件不存在，使用默认配置")
        config = get_default_config()
        save_config()
    except json.JSONDecodeError as e:
        logger.error(f"配置文件解析失败: {e}")
        config = get_default_config()
    return config


def save_config():
    """保存配置文件"""
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info("配置文件保存成功")
        return True
    except Exception as e:
        logger.error(f"配置文件保存失败: {e}")
        return False


def get_default_config():
    """返回默认配置"""
    return {
        "server": {"host": "0.0.0.0", "port": 38080, "debug": True},
        "hidrs": {"endpoint": "http://localhost:5000", "auto_detect": True, "check_interval": 30},
        "left_screen": {"default_tab": "cctv", "tabs": []},
        "center_screen": {"terminal_command": "claude", "refresh_interval": 5},
        "right_screen": {
            "social": {"url": "https://x.com/home"},
            "news": {"feeds": [], "refresh_interval": 60},
            "stocks": {"provider": "tradingview", "symbols": ["AAPL", "BTCUSD"]},
            "alerts": {"max_items": 50}
        },
        "theme": {"name": "cyberpunk", "primary_color": "#00f0ff"}
    }


def add_system_log(level, message):
    """添加系统日志"""
    global system_logs
    entry = {
        "time": datetime.now().isoformat(),
        "level": level,
        "message": message
    }
    system_logs.append(entry)
    if len(system_logs) > MAX_LOG_ENTRIES:
        system_logs = system_logs[-MAX_LOG_ENTRIES:]
    logger.log(getattr(logging, level.upper(), logging.INFO), message)


# ============================================================
# 页面路由
# ============================================================

@app.route('/')
def index():
    """主入口页面"""
    return render_template('index.html', config=config)


@app.route('/left')
def left_screen():
    """左屏：态势监控"""
    return render_template('left.html', config=config)


@app.route('/center')
def center_screen():
    """中屏：控制台"""
    return render_template('center.html', config=config)


@app.route('/right')
def right_screen():
    """右屏：情报视窗"""
    return render_template('right.html', config=config)


@app.route('/settings')
def settings_page():
    """设置页面"""
    return render_template('settings.html', config=config)


@app.route('/preview')
def preview_page():
    """三联屏预览模式"""
    return render_template('preview.html', config=config)


# ============================================================
# 内置小组件路由（解决 X-Frame-Options 问题）
# ============================================================

@app.route('/widget/map')
def widget_map():
    """内置地图小组件（Leaflet + OpenStreetMap 图层）"""
    return render_template('widgets/map.html')


@app.route('/widget/marine')
def widget_marine():
    """内置船舶追踪小组件"""
    return render_template('widgets/marine.html')


@app.route('/widget/social')
def widget_social():
    """内置社交媒体小组件（X/Threads/Bluesky/Mastodon/Reddit 轮播）"""
    return render_template('widgets/social.html')


@app.route('/widget/terminal')
def widget_terminal():
    """内置终端小组件（连接 claude-code-web）"""
    return render_template('widgets/terminal.html')


@app.route('/widget/cctv')
def widget_cctv():
    """内置 CCTV 多路监控小组件"""
    return render_template('widgets/cctv.html')


# ============================================================
# 系统监控 API
# ============================================================

@app.route('/api/system/stats')
def system_stats():
    """获取系统状态（CPU/内存/网络/GPU）"""
    try:
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()

        # 内存
        memory = psutil.virtual_memory()

        # 网络
        net_io = psutil.net_io_counters()
        net_connections = len(psutil.net_connections())

        # 磁盘
        disk = psutil.disk_usage('/')

        result = {
            "cpu": {
                "percent": cpu_percent,
                "cores": cpu_count,
                "freq_mhz": cpu_freq.current if cpu_freq else 0
            },
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2),
                "used_gb": round(memory.used / (1024**3), 2),
                "percent": memory.percent
            },
            "network": {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "connections": net_connections
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2),
                "used_gb": round(disk.used / (1024**3), 2),
                "percent": round(disk.percent, 1)
            },
            "timestamp": datetime.now().isoformat()
        }

        # GPU（可选）
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                result["gpu"] = {
                    "name": gpu.name,
                    "util_percent": gpu.load * 100,
                    "memory_used_mb": gpu.memoryUsed,
                    "memory_total_mb": gpu.memoryTotal,
                    "temperature": gpu.temperature
                }
        except ImportError:
            result["gpu"] = None
        except Exception:
            result["gpu"] = None

        return jsonify(result)

    except Exception as e:
        logger.error(f"获取系统状态失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/system/logs')
def system_logs_sse():
    """系统日志 SSE 流"""
    def generate():
        last_index = 0
        while True:
            if len(system_logs) > last_index:
                for log in system_logs[last_index:]:
                    yield f"data: {json.dumps(log, ensure_ascii=False)}\n\n"
                last_index = len(system_logs)
            time.sleep(1)

    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/system/logs/history')
def system_logs_history():
    """获取历史日志"""
    limit = request.args.get('limit', 50, type=int)
    return jsonify(system_logs[-limit:])


# ============================================================
# HIDRS 集成 API
# ============================================================

@app.route('/api/hidrs/status')
def hidrs_status():
    """检测 HIDRS 连接状态"""
    endpoint = config.get('hidrs', {}).get('endpoint', 'http://localhost:5000')
    try:
        resp = requests.get(f"{endpoint}/health", timeout=3)
        if resp.ok:
            return jsonify({
                "connected": True,
                "endpoint": endpoint,
                "message": "HIDRS 已连接"
            })
    except requests.exceptions.RequestException:
        pass

    return jsonify({
        "connected": False,
        "endpoint": endpoint,
        "message": "HIDRS 未连接 - 开启可获得更多功能",
        "features": [
            "网络拓扑实时监控",
            "Fiedler 值异常检测",
            "全息搜索功能",
            "AI 决策反馈"
        ]
    })


@app.route('/api/hidrs/proxy/<path:path>')
def hidrs_proxy(path):
    """代理 HIDRS API 请求"""
    endpoint = config.get('hidrs', {}).get('endpoint', 'http://localhost:5000')
    try:
        resp = requests.get(
            f"{endpoint}/{path}",
            params=request.args,
            timeout=10
        )
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"HIDRS 请求失败: {e}"}), 503


# ============================================================
# 新闻 RSS API
# ============================================================

# RSS 缓存（避免每次请求都重新抓取）
_rss_cache = {
    'items': [],
    'timestamp': 0,
    'ttl': 120  # 缓存 2 分钟
}


@app.route('/api/feeds/news')
def news_feeds():
    """获取 RSS 新闻聚合（带缓存 + 并发抓取）"""
    load_config()
    max_items = request.args.get('limit', 20, type=int)
    force = request.args.get('force', '0') == '1'

    # 缓存未过期且非强制刷新，直接返回
    if not force and _rss_cache['items'] and (time.time() - _rss_cache['timestamp']) < _rss_cache['ttl']:
        return jsonify(_rss_cache['items'][:max_items])

    feeds_config = config.get('right_screen', {}).get('news', {}).get('feeds', [])
    enabled_feeds = [f for f in feeds_config if f.get('enabled', True)]

    def fetch_one(feed_cfg):
        """抓取单个 RSS 源"""
        items = []
        try:
            feed = feedparser.parse(feed_cfg['url'])
            for entry in feed.entries[:10]:
                items.append({
                    "source": feed_cfg['name'],
                    "title": entry.get('title', ''),
                    "link": entry.get('link', ''),
                    "published": entry.get('published', ''),
                    "summary": entry.get('summary', '')[:200] if entry.get('summary') else ''
                })
        except Exception as e:
            logger.warning(f"获取 RSS 失败 [{feed_cfg['name']}]: {e}")
        return items

    # 并发抓取所有 RSS 源
    all_items = []
    with ThreadPoolExecutor(max_workers=len(enabled_feeds) or 1) as executor:
        futures = {executor.submit(fetch_one, f): f['name'] for f in enabled_feeds}
        for future in as_completed(futures):
            all_items.extend(future.result())

    all_items.sort(key=lambda x: x.get('published', ''), reverse=True)

    # 更新缓存
    _rss_cache['items'] = all_items
    _rss_cache['timestamp'] = time.time()

    return jsonify(all_items[:max_items])


# ============================================================
# Twitter 代理 API（绕过 X-Frame-Options 限制）
# ============================================================

@app.route('/api/twitter/timeline/<username>')
def twitter_timeline_proxy(username):
    """代理 Twitter syndication timeline，绕过 iframe 嵌入限制"""
    try:
        # Twitter 官方 syndication endpoint（无需认证）
        url = f'https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}'
        resp = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

        if resp.status_code != 200:
            # 如果 syndication 失败，返回一个简单的 fallback 页面
            return Response(
                _twitter_fallback_html(username),
                mimetype='text/html'
            )

        # 获取原始 HTML，注入深色主题样式
        html = resp.text

        # 注入自定义 CSS 使其匹配深色主题
        dark_css = """
        <style>
          body { background: #0a0e17 !important; color: #e5e7eb !important; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
          a { color: #00f0ff !important; }
          .timeline-Widget { background: #0a0e17 !important; border: none !important; }
          .timeline-Header { background: transparent !important; border-bottom: 1px solid rgba(0,240,255,0.2) !important; }
          .timeline-Tweet { border-bottom: 1px solid rgba(0,240,255,0.1) !important; }
          .timeline-Tweet-text { color: #e5e7eb !important; }
          .timeline-Tweet-author { color: #9ca3af !important; }
          .TweetAuthor-name { color: #e5e7eb !important; }
          .TweetAuthor-screenName { color: #6b7280 !important; }
          .timeline-Footer { background: transparent !important; border-top: 1px solid rgba(0,240,255,0.2) !important; }
          /* 覆盖所有白色背景 */
          [style*="background-color: white"], [style*="background: white"],
          [style*="background-color: rgb(255, 255, 255)"] {
            background-color: #0a0e17 !important;
          }
        </style>
        """

        # 在 </head> 前注入样式
        if '</head>' in html:
            html = html.replace('</head>', dark_css + '</head>')
        else:
            html = dark_css + html

        return Response(html, mimetype='text/html')

    except requests.exceptions.RequestException as e:
        logger.warning(f"Twitter syndication 代理失败: {e}")
        return Response(
            _twitter_fallback_html(username),
            mimetype='text/html'
        )


def _twitter_fallback_html(username):
    """Twitter 代理失败时的 fallback HTML"""
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  body {{ background: #0a0e17; color: #e5e7eb; font-family: -apple-system, sans-serif;
         display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
  .container {{ text-align: center; }}
  .icon {{ font-size: 48px; margin-bottom: 16px; }}
  h3 {{ color: #00f0ff; font-weight: normal; margin-bottom: 8px; }}
  p {{ color: #6b7280; font-size: 12px; margin-bottom: 20px; max-width: 280px; line-height: 1.6; }}
  .btn {{ padding: 10px 24px; background: rgba(0,240,255,0.15); border: 1px solid #00f0ff;
          border-radius: 6px; color: #00f0ff; font-size: 13px; cursor: pointer; text-decoration: none; display: inline-block; }}
  .btn:hover {{ background: #00f0ff; color: #0a0e17; }}
</style></head><body>
<div class="container">
  <div class="icon">\U0001D54F</div>
  <h3>X / Twitter</h3>
  <p>Timeline 加载失败。可能是网络限制。</p>
  <a class="btn" href="https://x.com/{username}" target="_blank">\U0001F680 打开 @{username}</a>
</div></body></html>"""


# ============================================================
# 配置管理 API
# ============================================================

@app.route('/api/config', methods=['GET'])
def get_config():
    """获取当前配置（每次从磁盘重新加载，确保外部修改生效）"""
    load_config()
    return jsonify(config)


@app.route('/api/config', methods=['POST'])
def update_config():
    """更新配置"""
    global config
    try:
        new_config = request.get_json()
        if not new_config:
            return jsonify({"error": "无效的配置数据"}), 400

        config = new_config
        if save_config():
            add_system_log("info", "配置已更新")
            return jsonify({"success": True, "message": "配置已保存"})
        else:
            return jsonify({"error": "配置保存失败"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/config/reset', methods=['POST'])
def reset_config():
    """恢复默认配置"""
    global config
    try:
        config = get_default_config()
        if save_config():
            add_system_log("info", "配置已恢复为默认值")
            return jsonify({"success": True, "message": "已恢复默认配置"})
        else:
            return jsonify({"error": "保存失败"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/config/tabs', methods=['GET'])
def get_tabs():
    """获取左屏 Tab 配置"""
    tabs = config.get('left_screen', {}).get('tabs', [])
    return jsonify(tabs)


@app.route('/api/config/tabs', methods=['POST'])
def add_tab():
    """添加新 Tab"""
    try:
        tab_data = request.get_json()
        if not tab_data or not tab_data.get('name') or not tab_data.get('url'):
            return jsonify({"error": "缺少必要字段 (name, url)"}), 400

        # 生成 ID
        tab_id = tab_data.get('id') or tab_data['name'].lower().replace(' ', '_')

        new_tab = {
            "id": tab_id,
            "name": tab_data['name'],
            "icon": tab_data.get('icon', '🌐'),
            "url": tab_data['url'],
            "category": tab_data.get('category', 'custom'),
            "loadStrategy": tab_data.get('loadStrategy', 'lazy'),
            "builtIn": False
        }

        if 'left_screen' not in config:
            config['left_screen'] = {'tabs': []}
        if 'tabs' not in config['left_screen']:
            config['left_screen']['tabs'] = []

        config['left_screen']['tabs'].append(new_tab)
        save_config()

        add_system_log("info", f"添加新 Tab: {new_tab['name']}")
        return jsonify({"success": True, "tab": new_tab})

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/config/tabs/<tab_id>', methods=['DELETE'])
def delete_tab(tab_id):
    """删除 Tab"""
    tabs = config.get('left_screen', {}).get('tabs', [])

    for i, tab in enumerate(tabs):
        if tab['id'] == tab_id:
            if tab.get('builtIn'):
                return jsonify({"error": "无法删除内置 Tab"}), 400
            tabs.pop(i)
            save_config()
            add_system_log("info", f"删除 Tab: {tab['name']}")
            return jsonify({"success": True})

    return jsonify({"error": "Tab 不存在"}), 404


@app.route('/api/config/tabs/<tab_id>', methods=['PUT'])
def update_tab(tab_id):
    """更新 Tab 配置"""
    tabs = config.get('left_screen', {}).get('tabs', [])
    tab_data = request.get_json()

    for tab in tabs:
        if tab['id'] == tab_id:
            # 更新允许的字段
            for key in ['name', 'icon', 'url', 'loadStrategy', 'category']:
                if key in tab_data:
                    tab[key] = tab_data[key]
            save_config()
            add_system_log("info", f"更新 Tab: {tab['name']}")
            return jsonify({"success": True, "tab": tab})

    return jsonify({"error": "Tab 不存在"}), 404


# ============================================================
# 事件流 API（告警）
# ============================================================

# 事件缓存
events = []
MAX_EVENTS = 100


@app.route('/api/events', methods=['POST'])
def add_event():
    """添加事件"""
    global events
    try:
        event = request.get_json()
        event['timestamp'] = datetime.now().isoformat()
        events.append(event)
        if len(events) > MAX_EVENTS:
            events = events[-MAX_EVENTS:]
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/events/stream')
def events_stream():
    """事件流 SSE"""
    def generate():
        last_index = 0
        while True:
            if len(events) > last_index:
                for event in events[last_index:]:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                last_index = len(events)
            time.sleep(1)

    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/events/history')
def events_history():
    """获取历史事件"""
    limit = request.args.get('limit', 50, type=int)
    return jsonify(events[-limit:])


# ============================================================
# 健康检查
# ============================================================

@app.route('/health')
def health_check():
    """健康检查端点"""
    return jsonify({
        "status": "ok",
        "service": "FAIRY-DESK",
        "timestamp": datetime.now().isoformat()
    })


# ============================================================
# 启动
# ============================================================

if __name__ == '__main__':
    # 加载配置
    load_config()

    # 自动启动 ttyd（如果已安装）
    ttyd_path = shutil.which('ttyd')
    if ttyd_path:
        try:
            subprocess.Popen(
                [ttyd_path, '-p', '7681', '-W', 'bash'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            add_system_log("info", f"ttyd 已启动于端口 7681")
        except Exception as e:
            add_system_log("warning", f"ttyd 启动失败: {e}")
    else:
        add_system_log("info", "ttyd 未安装，终端使用模拟模式（安装: sudo apt install ttyd）")

    # 启动日志
    add_system_log("info", "FAIRY-DESK 启动中...")
    add_system_log("info", f"监听地址: {config['server']['host']}:{config['server']['port']}")
    add_system_log("info", f"RSS 源数量: {len(config.get('right_screen', {}).get('news', {}).get('feeds', []))}")
    add_system_log("info", f"股票标的: {', '.join(config.get('right_screen', {}).get('stocks', {}).get('symbols', []))}")
    add_system_log("info", "系统控制台就绪，等待指令...")

    # 启动 Flask
    app.run(
        host=config.get('server', {}).get('host', '0.0.0.0'),
        port=config.get('server', {}).get('port', 38080),
        debug=config.get('server', {}).get('debug', True),
        threaded=True
    )
