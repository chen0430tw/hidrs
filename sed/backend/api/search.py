"""
搜索API模块 - 提供数据查询功能
"""
import logging
from flask import Blueprint, request, jsonify, current_app

# 设置日志
logger = logging.getLogger(__name__)

# 创建蓝图
search_bp = Blueprint('search', __name__)

def register_search_routes(app):
    """注册搜索API路由"""
    app.register_blueprint(search_bp, url_prefix='/api')

@search_bp.route('/find/user/<string:user>')
def find_user(user):
    """根据用户名查询"""
    logger.info(f"处理用户查询: {user}")
    
    # 获取分页参数
    limit = request.args.get('limit', default=10, type=int)
    skip = request.args.get('skip', default=0, type=int)
    
    # 获取客户端
    client = current_app.config.get('CLIENT')
    
    # 构建查询
    query = {
        "query": {
            "wildcard": {
                "user": {
                    "value": f"*{user}*"
                }
            }
        }
    }
    
    # 执行搜索
    data, total = client.search(query, limit, skip)
    
    if data:
        return jsonify({"status": "ok", "data": data, "datacounts": total})
    else:
        return jsonify({"status": "not found", "data": [], "datacounts": 0})

@search_bp.route('/find/email/<string:email>')
def find_email(email):
    """根据邮箱查询"""
    # 获取分页参数
    limit = request.args.get('limit', default=10, type=int)
    skip = request.args.get('skip', default=0, type=int)
    
    # 获取客户端
    client = current_app.config.get('CLIENT')
    
    # 构建查询
    query = {
        "query": {
            "wildcard": {
                "email": {
                    "value": f"*{email}*"
                }
            }
        }
    }
    
    # 执行搜索
    data, total = client.search(query, limit, skip)
    
    if data:
        return jsonify({"status": "ok", "data": data, "datacounts": total})
    else:
        return jsonify({"status": "not found", "data": [], "datacounts": 0})

@search_bp.route('/find/password/<string:password>')
def find_password(password):
    """根据密码查询"""
    # 获取分页参数
    limit = request.args.get('limit', default=10, type=int)
    skip = request.args.get('skip', default=0, type=int)
    
    # 获取客户端
    client = current_app.config.get('CLIENT')
    
    # 构建查询
    query = {
        "query": {
            "wildcard": {
                "password": {
                    "value": f"*{password}*"
                }
            }
        }
    }
    
    # 执行搜索
    data, total = client.search(query, limit, skip)
    
    if data:
        return jsonify({"status": "ok", "data": data, "datacounts": total})
    else:
        return jsonify({"status": "not found", "data": [], "datacounts": 0})

@search_bp.route('/find/passwordHash/<string:passwordHash>')
def find_passwordHash(passwordHash):
    """根据密码哈希查询"""
    # 获取分页参数
    limit = request.args.get('limit', default=10, type=int)
    skip = request.args.get('skip', default=0, type=int)
    
    # 获取客户端
    client = current_app.config.get('CLIENT')
    
    # 构建查询
    query = {
        "query": {
            "wildcard": {
                "passwordHash": {
                    "value": f"*{passwordHash}*"
                }
            }
        }
    }
    
    # 执行搜索
    data, total = client.search(query, limit, skip)
    
    if data:
        return jsonify({"status": "ok", "data": data, "datacounts": total})
    else:
        return jsonify({"status": "not found", "data": [], "datacounts": 0})

@search_bp.route('/find/source/<string:source>')
def find_source(source):
    """根据来源查询"""
    # 获取分页参数
    limit = request.args.get('limit', default=10, type=int)
    skip = request.args.get('skip', default=0, type=int)
    
    # 获取客户端
    client = current_app.config.get('CLIENT')
    
    # 构建查询
    query = {
        "query": {
            "wildcard": {
                "source": {
                    "value": f"*{source}*"
                }
            }
        }
    }
    
    # 执行搜索
    data, total = client.search(query, limit, skip)
    
    if data:
        return jsonify({"status": "ok", "data": data, "datacounts": total})
    else:
        return jsonify({"status": "not found", "data": [], "datacounts": 0})

@search_bp.route('/find/xtime/<string:xtime>')
def find_time(xtime):
    """根据时间查询"""
    # 获取分页参数
    limit = request.args.get('limit', default=10, type=int)
    skip = request.args.get('skip', default=0, type=int)
    
    # 获取客户端
    client = current_app.config.get('CLIENT')
    
    # 构建查询
    query = {
        "query": {
            "wildcard": {
                "xtime": {
                    "value": f"*{xtime}*"
                }
            }
        }
    }
    
    # 执行搜索
    data, total = client.search(query, limit, skip)
    
    if data:
        return jsonify({"status": "ok", "data": data, "datacounts": total})
    else:
        return jsonify({"status": "not found", "data": [], "datacounts": 0})

@search_bp.route('/find')
def find_all():
    """查询所有数据(带限制)"""
    try:
        # 获取客户端
        client = current_app.config.get('CLIENT')
        
        # 构建查询
        query = {
            "query": {
                "match_all": {}
            }
        }
        
        # 执行搜索
        data, total = client.search(query, 10, 0)
        
        if data:
            return jsonify({"status": "ok", "data": data, "datacounts": min(total, 10)})
        else:
            return jsonify({"status": "not found", "data": [], "datacounts": 0})
            
    except Exception as e:
        logger.error(f"查询所有数据出错: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

@search_bp.route('/detail')
def get_record_detail():
    """获取完整记录"""
    try:
        # 获取参数
        file = request.args.get('file')
        line = request.args.get('line', type=int)
        
        if not file or not line:
            return jsonify({"status": "error", "message": "Missing file or line parameters"})
        
        # 获取客户端和模式
        client = current_app.config.get('CLIENT')
        mode = current_app.config.get('MODE')
        
        if mode == 'remote':
            # 远程模式
            record = client.get_file_content(file, line)
        else:
            # 本地模式
            from utils.data_processor import parse_record
            import os
            
            # 获取数据目录
            data_dir = os.getenv('DATA_DIR', 'data')
            file_path = os.path.join(data_dir, file)
            
            # 读取指定行
            record = None
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for i, line_content in enumerate(f, 1):
                        if i == line:
                            # 从配置目录加载解析配置
                            import json
                            config_path = os.path.join('configs', 'default.json')
                            config = {}
                            
                            if os.path.exists(config_path):
                                with open(config_path, 'r', encoding='utf-8') as cf:
                                    config = json.load(cf)
                            
                            # 解析记录
                            record = parse_record(
                                line=line_content,
                                split_sign=config.get('split', '----'),
                                fields=config.get('fields', ['email', 'password']),
                                regex_patterns=config.get('regex', {}),
                                custom_fields=config.get('custom_field', {})
                            )
                            break
            except Exception as e:
                logger.error(f"读取文件失败: {str(e)}")
        
        if record:
            return jsonify({"status": "ok", "data": record})
        else:
            return jsonify({"status": "not found", "message": "Record not found"})
            
    except Exception as e:
        logger.error(f"获取记录详情出错: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

@search_bp.route('/remote', methods=['POST'])
def remote_search():
    """接受远程搜索请求"""
    try:
        # 仅在本地模式下可用
        if current_app.config.get('MODE') != 'local':
            return jsonify({"status": "error", "message": "Remote search only available in local mode"}), 400
        
        # 获取请求数据
        data = request.get_json()
        query = data.get('query')
        limit = data.get('limit', 10)
        skip = data.get('skip', 0)
        
        if not query:
            return jsonify({"status": "error", "message": "Missing query parameter"}), 400
        
        # 获取客户端
        client = current_app.config.get('CLIENT')
        
        # 执行搜索
        results, total = client.search(query, limit, skip)
        
        return jsonify({
            "status": "ok",
            "data": results,
            "total": total
        })
    except Exception as e:
        logger.error(f"远程搜索出错: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500