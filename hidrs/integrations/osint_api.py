"""
HIDRS OSINT API服务器
为第三方OSINT工具提供标准化的REST API接口

符合OSINT行业标准：
- RESTful API设计
- JSON响应格式
- API密钥认证
- 速率限制
- CORS支持

API端点：
- GET  /api/v1/search - 搜索
- GET  /api/v1/domain/{domain} - 域名情报
- GET  /api/v1/ip/{ip} - IP情报
- GET  /api/v1/email/{email} - 邮箱情报
- GET  /api/v1/topology - 网络拓扑
- GET  /api/v1/export/stix - STIX导出
- GET  /api/v1/health - 健康检查

使用示例：
```bash
# 搜索
curl -H "X-API-Key: your-key" "http://localhost:8080/api/v1/search?q=example"

# 域名情报
curl -H "X-API-Key: your-key" "http://localhost:8080/api/v1/domain/example.com"

# STIX导出
curl -H "X-API-Key: your-key" "http://localhost:8080/api/v1/export/stix?q=example"
```
"""

import os
import time
import hashlib
import secrets
import logging
from functools import wraps
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict

from flask import Flask, request, jsonify, Response
from flask_cors import CORS

logger = logging.getLogger(__name__)


class RateLimiter:
    """API速率限制器"""

    def __init__(self, requests_per_minute: int = 60):
        """
        初始化速率限制器

        参数:
        - requests_per_minute: 每分钟最大请求数
        """
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(list)

    def is_allowed(self, api_key: str) -> bool:
        """检查是否允许请求"""
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=1)

        # 清理过期记录
        self.requests[api_key] = [
            ts for ts in self.requests[api_key]
            if ts > cutoff
        ]

        # 检查是否超过限制
        if len(self.requests[api_key]) >= self.requests_per_minute:
            return False

        # 记录本次请求
        self.requests[api_key].append(now)
        return True

    def get_remaining(self, api_key: str) -> int:
        """获取剩余请求数"""
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=1)

        # 清理过期记录
        self.requests[api_key] = [
            ts for ts in self.requests[api_key]
            if ts > cutoff
        ]

        return max(0, self.requests_per_minute - len(self.requests[api_key]))


class APIKeyManager:
    """API密钥管理器"""

    def __init__(self, keys_file: str = 'api_keys.json'):
        """
        初始化API密钥管理器

        参数:
        - keys_file: 密钥存储文件
        """
        self.keys_file = keys_file
        self.keys = self._load_keys()

    def _load_keys(self) -> Dict:
        """加载API密钥"""
        import json

        if os.path.exists(self.keys_file):
            try:
                with open(self.keys_file, 'r') as f:
                    return json.load(f)
            except:
                logger.warning(f"无法加载密钥文件: {self.keys_file}")
                return {}
        return {}

    def _save_keys(self):
        """保存API密钥"""
        import json

        try:
            with open(self.keys_file, 'w') as f:
                json.dump(self.keys, f, indent=2)
        except Exception as e:
            logger.error(f"保存密钥文件失败: {e}")

    def generate_key(self, name: str, rate_limit: int = 60) -> str:
        """
        生成新的API密钥

        参数:
        - name: 密钥名称
        - rate_limit: 每分钟请求限制

        返回:
        - API密钥字符串
        """
        # 生成随机密钥
        key = f"hidrs_{secrets.token_urlsafe(32)}"

        # 存储密钥信息
        self.keys[key] = {
            'name': name,
            'created_at': datetime.utcnow().isoformat(),
            'rate_limit': rate_limit,
            'enabled': True
        }

        self._save_keys()
        logger.info(f"生成新API密钥: {name}")

        return key

    def validate_key(self, key: str) -> bool:
        """验证API密钥"""
        if key not in self.keys:
            return False

        key_info = self.keys[key]
        return key_info.get('enabled', False)

    def get_rate_limit(self, key: str) -> int:
        """获取密钥的速率限制"""
        if key not in self.keys:
            return 60  # 默认值

        return self.keys[key].get('rate_limit', 60)

    def revoke_key(self, key: str):
        """吊销API密钥"""
        if key in self.keys:
            self.keys[key]['enabled'] = False
            self._save_keys()
            logger.info(f"API密钥已吊销: {key}")


class OSINTAPIServer:
    """HIDRS OSINT API服务器"""

    def __init__(
        self,
        host: str = '0.0.0.0',
        port: int = 8080,
        require_auth: bool = True,
        enable_cors: bool = True
    ):
        """
        初始化API服务器

        参数:
        - host: 监听地址
        - port: 监听端口
        - require_auth: 是否需要API密钥认证
        - enable_cors: 是否启用CORS
        """
        self.host = host
        self.port = port
        self.require_auth = require_auth

        # 创建Flask应用
        self.app = Flask(__name__)

        # 启用CORS
        if enable_cors:
            CORS(self.app)

        # 初始化组件
        self.api_key_manager = APIKeyManager()
        self.rate_limiter = RateLimiter()

        # 注册路由
        self._register_routes()

    def _require_api_key(self, f):
        """API密钥验证装饰器"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not self.require_auth:
                return f(*args, **kwargs)

            # 获取API密钥
            api_key = request.headers.get('X-API-Key') or request.args.get('api_key')

            if not api_key:
                return jsonify({'error': 'API key required'}), 401

            # 验证密钥
            if not self.api_key_manager.validate_key(api_key):
                return jsonify({'error': 'Invalid API key'}), 403

            # 速率限制
            rate_limit = self.api_key_manager.get_rate_limit(api_key)
            self.rate_limiter.requests_per_minute = rate_limit

            if not self.rate_limiter.is_allowed(api_key):
                return jsonify({
                    'error': 'Rate limit exceeded',
                    'retry_after': 60
                }), 429

            # 添加速率限制响应头
            response = f(*args, **kwargs)
            if isinstance(response, tuple):
                response_obj, status_code = response[0], response[1]
            else:
                response_obj = response
                status_code = 200

            if hasattr(response_obj, 'headers'):
                response_obj.headers['X-RateLimit-Limit'] = str(rate_limit)
                response_obj.headers['X-RateLimit-Remaining'] = str(
                    self.rate_limiter.get_remaining(api_key)
                )

            return response_obj, status_code

        return decorated_function

    def _register_routes(self):
        """注册API路由"""

        @self.app.route('/api/v1/health', methods=['GET'])
        def health_check():
            """健康检查"""
            return jsonify({
                'status': 'healthy',
                'service': 'HIDRS OSINT API',
                'version': '1.0.0',
                'timestamp': datetime.utcnow().isoformat()
            })

        @self.app.route('/api/v1/search', methods=['GET'])
        @self._require_api_key
        def search():
            """搜索接口"""
            query = request.args.get('q', '')
            limit = int(request.args.get('limit', 20))
            source = request.args.get('source', 'all')  # all/hidrs/commoncrawl

            if not query:
                return jsonify({'error': 'Query required'}), 400

            try:
                results = []

                # HIDRS实时搜索
                if source in ['all', 'hidrs']:
                    from hidrs.realtime_search.search_engine import RealtimeSearchEngine

                    engine = RealtimeSearchEngine(
                        elasticsearch_host='localhost:9200',
                        enable_hlig=True
                    )

                    hidrs_results = engine.search(query_text=query, limit=limit)
                    if hidrs_results and 'results' in hidrs_results:
                        for r in hidrs_results['results']:
                            r['source'] = 'hidrs'
                        results.extend(hidrs_results['results'])

                # Common Crawl搜索
                if source in ['all', 'commoncrawl']:
                    from hidrs.commoncrawl import CommonCrawlQueryEngine

                    cc_engine = CommonCrawlQueryEngine(
                        mongodb_uri='mongodb://localhost:27017',
                        db_name='hidrs'
                    )

                    cc_results = cc_engine.advanced_search(
                        keywords=[query],
                        limit=limit
                    )

                    for r in cc_results:
                        r['source'] = 'commoncrawl'
                    results.extend(cc_results)

                return jsonify({
                    'success': True,
                    'query': query,
                    'total': len(results),
                    'results': results[:limit]
                })

            except Exception as e:
                logger.error(f"搜索失败: {e}", exc_info=True)
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/v1/domain/<domain>', methods=['GET'])
        @self._require_api_key
        def domain_intel(domain):
            """域名情报"""
            try:
                # 搜索包含该域名的结果
                from hidrs.realtime_search.search_engine import RealtimeSearchEngine

                engine = RealtimeSearchEngine(
                    elasticsearch_host='localhost:9200',
                    enable_hlig=True
                )

                results = engine.search(query_text=f'domain:{domain}', limit=50)

                # 分析域名
                intel = {
                    'domain': domain,
                    'timestamp': datetime.utcnow().isoformat(),
                    'total_results': len(results.get('results', [])),
                    'urls': [r.get('url') for r in results.get('results', []) if r.get('url')],
                    'titles': [r.get('title') for r in results.get('results', []) if r.get('title')],
                    'avg_fiedler_score': sum(
                        r.get('metadata', {}).get('fiedler_score', 0)
                        for r in results.get('results', [])
                    ) / max(len(results.get('results', [])), 1)
                }

                return jsonify(intel)

            except Exception as e:
                logger.error(f"域名情报查询失败: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/v1/ip/<ip>', methods=['GET'])
        @self._require_api_key
        def ip_intel(ip):
            """IP情报"""
            try:
                from hidrs.realtime_search.search_engine import RealtimeSearchEngine

                engine = RealtimeSearchEngine(
                    elasticsearch_host='localhost:9200',
                    enable_hlig=True
                )

                results = engine.search(query_text=f'ip:{ip}', limit=50)

                intel = {
                    'ip': ip,
                    'timestamp': datetime.utcnow().isoformat(),
                    'total_results': len(results.get('results', [])),
                    'associated_urls': [r.get('url') for r in results.get('results', []) if r.get('url')]
                }

                return jsonify(intel)

            except Exception as e:
                logger.error(f"IP情报查询失败: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/v1/topology', methods=['GET'])
        @self._require_api_key
        def topology():
            """网络拓扑"""
            try:
                from hidrs.network_topology.topology_manager import TopologyManager

                mgr = TopologyManager()
                topology_info = mgr.get_topology_info()

                return jsonify(topology_info)

            except Exception as e:
                logger.error(f"拓扑查询失败: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/v1/export/stix', methods=['GET'])
        @self._require_api_key
        def export_stix():
            """导出STIX格式"""
            query = request.args.get('q', '')
            tlp_level = request.args.get('tlp', 'white')

            if not query:
                return jsonify({'error': 'Query required'}), 400

            try:
                from hidrs.integrations.stix_exporter import STIXExporter
                from hidrs.realtime_search.search_engine import RealtimeSearchEngine

                # 搜索
                engine = RealtimeSearchEngine(
                    elasticsearch_host='localhost:9200',
                    enable_hlig=True
                )

                results = engine.search(query_text=query, limit=100)

                # 导出STIX
                exporter = STIXExporter()
                bundle = exporter.export_search_results(
                    results.get('results', []),
                    tlp_level=tlp_level
                )

                # 返回JSON
                return Response(
                    bundle.serialize(pretty=True),
                    mimetype='application/json',
                    headers={
                        'Content-Disposition': f'attachment; filename=hidrs_stix_{int(time.time())}.json'
                    }
                )

            except Exception as e:
                logger.error(f"STIX导出失败: {e}")
                return jsonify({'error': str(e)}), 500

    def run(self, debug: bool = False):
        """启动API服务器"""
        logger.info(f"启动HIDRS OSINT API服务器: {self.host}:{self.port}")
        self.app.run(host=self.host, port=self.port, debug=debug)


# CLI工具
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='HIDRS OSINT API服务器')
    parser.add_argument('command', choices=['run', 'genkey'], help='命令')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址')
    parser.add_argument('--port', type=int, default=8080, help='监听端口')
    parser.add_argument('--no-auth', action='store_true', help='禁用认证')
    parser.add_argument('--name', help='API密钥名称（用于genkey）')

    args = parser.parse_args()

    if args.command == 'run':
        # 启动服务器
        server = OSINTAPIServer(
            host=args.host,
            port=args.port,
            require_auth=not args.no_auth
        )
        server.run(debug=True)

    elif args.command == 'genkey':
        # 生成API密钥
        name = args.name or f"key_{int(time.time())}"
        manager = APIKeyManager()
        key = manager.generate_key(name)
        print(f"\n新API密钥已生成:")
        print(f"名称: {name}")
        print(f"密钥: {key}")
        print(f"\n使用示例:")
        print(f'curl -H "X-API-Key: {key}" "http://localhost:8080/api/v1/search?q=example"')
