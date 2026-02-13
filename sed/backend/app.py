"""
社工库API主入口 - 支持本地和远程模式
"""
import os
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS

# 导入本地模式工具
from utils.es_client import ESClient
from api.search import register_search_routes
from api.analysis import register_analysis_routes
from api.admin import register_admin_routes

# 导入远程模式工具
from utils.remote_api import RemoteAPIClient

# 配置
from config import AppConfig

# 确保日志目录存在
os.makedirs(os.path.dirname(AppConfig.ERROR_LOG_FILE), exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(AppConfig.ERROR_LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 初始化Flask应用
app = Flask(__name__)
CORS(app)

# 系统模式：本地或远程
MODE = os.getenv('MODE', 'local')
logger.info(f"系统运行模式: {MODE}")

# 初始化客户端
if MODE == 'local':
    # 本地模式：使用Elasticsearch
    es_client = ESClient()
    client = es_client
    logger.info("使用本地Elasticsearch模式")
else:
    # 远程模式：使用远程API
    remote_api = os.getenv('REMOTE_API', '')
    if not remote_api:
        logger.error("远程模式下必须设置REMOTE_API环境变量")
        raise ValueError("未设置远程API地址")
    
    client = RemoteAPIClient(remote_api)
    logger.info(f"使用远程API模式: {remote_api}")

# 添加全局变量到Flask应用
app.config['CLIENT'] = client
app.config['MODE'] = MODE

# 注册路由
register_search_routes(app)
register_analysis_routes(app)
register_admin_routes(app)

# 注册工具路由
from api.tools import register_tools_routes
register_tools_routes(app)

# 注册LLM路由
from api.llm import register_llm_routes
register_llm_routes(app)

# 注册插件管理路由
from plugins.core.loader import plugin_loader
plugin_loader.discover()
plugin_loader.install_all(app)

# 插件管理API
@app.route('/api/admin/plugins')
def list_plugins():
    return jsonify({'status': 'ok', 'data': plugin_loader.get_all()})

@app.route('/api/admin/plugins/<plugin_id>/toggle', methods=['POST'])
def toggle_plugin(plugin_id):
    result = plugin_loader.toggle(plugin_id)
    if result is not None:
        return jsonify({'status': 'ok', 'enabled': result})
    return jsonify({'status': 'error', 'message': '插件不存在'}), 404

# 添加测试端点
@app.route('/api/test')
def test_api():
    """测试API是否正常工作"""
    mode_str = "远程API模式" if MODE == 'remote' else "本地Elasticsearch模式"
    return jsonify({
        "status": "ok", 
        "message": "API服务正常", 
        "mode": mode_str,
        "version": "2.0.0"
    })

# 主应用入口
if __name__ == '__main__':
    logger.info(f"启动Flask应用，模式: {MODE}")
    app.run(host=AppConfig.HOST, port=AppConfig.PORT, debug=AppConfig.DEBUG)