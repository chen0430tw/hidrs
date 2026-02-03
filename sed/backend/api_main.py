'''
重构后的API接口，使用Elasticsearch代替MongoDB
支持引用模式和多格式数据
'''

import os
import time
import logging
import json
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from flask_restful import Api, Resource

# 导入工具类
from es_utils import ESClient
from record_parser import get_record_from_file
from conf.config import AppConfig, StorageConfig, ElasticConfig

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

# 创建ES客户端
es_client = ESClient()

# 定义查询函数
def execute_search(field, value, limit=10, skip=0):
    """执行搜索查询"""
    try:
        # 构建查询
        query = {
            "query": {
                "wildcard": {
                    field: {
                        "value": f"*{value}*"
                    }
                }
            }
        }
        
        # 执行搜索
        data, total = es_client.search(query, limit, skip)
        
        if data:
            return {"status": "ok", "data": data, "datacounts": total}
        else:
            return {"status": "not found", "data": [], "datacounts": 0}
            
    except Exception as e:
        logger.error(f"查询失败 - {field}:{value}: {str(e)}")
        return {"status": "error", "message": str(e)}

# 定义API路由
@app.route('/api/find/user/<string:user>')
def find_user(user):
    """根据用户名查询"""
    logger.info(f"处理用户查询: {user}")
    
    # 获取分页参数
    limit = request.args.get('limit', default=10, type=int)
    skip = request.args.get('skip', default=0, type=int)
    
    return jsonify(execute_search("user", user, limit, skip))

@app.route('/api/find/email/<string:email>')
def find_email(email):
    """根据邮箱查询"""
    # 获取分页参数
    limit = request.args.get('limit', default=10, type=int)
    skip = request.args.get('skip', default=0, type=int)
    
    return jsonify(execute_search("email", email, limit, skip))

@app.route('/api/find/password/<string:password>')
def find_password(password):
    """根据密码查询"""
    # 获取分页参数
    limit = request.args.get('limit', default=10, type=int)
    skip = request.args.get('skip', default=0, type=int)
    
    return jsonify(execute_search("password", password, limit, skip))

@app.route('/api/find/passwordHash/<string:passwordHash>')
def find_passwordHash(passwordHash):
    """根据密码哈希查询"""
    # 获取分页参数
    limit = request.args.get('limit', default=10, type=int)
    skip = request.args.get('skip', default=0, type=int)
    
    return jsonify(execute_search("passwordHash", passwordHash, limit, skip))

@app.route('/api/find/source/<string:source>')
def find_source(source):
    """根据来源查询"""
    # 获取分页参数
    limit = request.args.get('limit', default=10, type=int)
    skip = request.args.get('skip', default=0, type=int)
    
    return jsonify(execute_search("source", source, limit, skip))

@app.route('/api/find/time/<string:xtime>')
def find_time(xtime):
    """根据时间查询"""
    # 获取分页参数
    limit = request.args.get('limit', default=10, type=int)
    skip = request.args.get('skip', default=0, type=int)
    
    return jsonify(execute_search("xtime", xtime, limit, skip))

@app.route('/api/find')
def find_all():
    """查询所有数据(带限制)"""
    try:
        # 构建查询所有文档的请求
        query = {
            "query": {
                "match_all": {}
            }
        }
        
        # 执行查询，限制返回10条
        data, total = es_client.search(query, 10, 0)
        
        if data:
            return jsonify({"status": "ok", "data": data, "datacounts": min(total, 10)})
        else:
            return jsonify({"status": "not found", "data": [], "datacounts": 0})
            
    except Exception as e:
        logger.error(f"查询所有数据出错: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/detail')
def get_record_detail():
    """获取完整记录（引用模式）"""
    try:
        # 获取参数
        file = request.args.get('file')
        line = request.args.get('line', type=int)
        config_file = request.args.get('config', 'default_config.json')
        
        if not file or not line:
            return jsonify({"status": "error", "message": "Missing file or line parameters"})
        
        # 构建完整文件路径
        file_path = os.path.join(StorageConfig.SOURCE_DATA_DIR, file)
        
        # 加载配置
        config = {}
        config_path = os.path.join('configs', config_file)
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        
        # 获取完整记录
        record = get_record_from_file(file_path, line, config)
        
        if record:
            return jsonify({"status": "ok", "data": record})
        else:
            return jsonify({"status": "not found", "message": "Record not found"})
    
    except Exception as e:
        logger.error(f"获取记录详情出错: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/analysis/<string:type_analyze>')
def analysis(type_analyze):
    """执行聚合分析"""
    try:
        if type_analyze in ["source", "xtime", "suffix_email", "create_time"]:
            # 构建聚合查询
            agg_query = {
                "size": 0,
                "aggs": {
                    "group_by_field": {
                        "terms": {
                            "field": type_analyze,
                            "size": 100
                        }
                    }
                }
            }
            
            # 执行聚合查询
            aggs = es_client.aggregate(agg_query)
            
            # 转换结果为与原API兼容的格式
            results = []
            for bucket in aggs.get("group_by_field", {}).get("buckets", []):
                results.append({
                    "_id": bucket["key"],
                    "sum": bucket["doc_count"]
                })
            
            return jsonify({"status": "ok", "data": results})
        else:
            return jsonify({
                "status": "error", 
                "message": "use /api/analysis/[source, xtime, suffix_email, create_time] to get analysis data."
            })
    except Exception as e:
        logger.error(f"分析出错: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/stats')
def get_stats():
    """获取系统统计信息"""
    try:
        # 获取总记录数
        count_query = {"query": {"match_all": {}}}
        total_count = es_client.count(count_query)
        
        # 获取索引大小和其他统计信息
        indices_stats = {}
        try:
            if StorageConfig.USE_PARTITIONING:
                pattern = f"{ElasticConfig.ES_INDEX}*"
                stats = es_client.es.indices.stats(index=pattern)
                indices_stats = stats.get('_all', {})
            else:
                stats = es_client.es.indices.stats(index=ElasticConfig.ES_INDEX)
                indices_stats = stats.get('_all', {})
        except:
            pass
        
        # 计算磁盘使用
        size_in_bytes = indices_stats.get('total', {}).get('store', {}).get('size_in_bytes', 0)
        size_in_mb = round(size_in_bytes / (1024 * 1024), 2)
        
        # 返回统计信息
        return jsonify({
            "status": "ok",
            "data": {
                "total_records": total_count,
                "index_size_mb": size_in_mb,
                "storage_mode": StorageConfig.STORAGE_MODE,
                "partitioning": StorageConfig.USE_PARTITIONING,
                "indices_count": len(indices_stats.get('indices', {}))
            }
        })
    
    except Exception as e:
        logger.error(f"获取统计信息出错: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

# 使用Flask-RESTful处理POST请求
api = Api(app)

class PersonPost(Resource):
    def post(self):
        """处理数据提交"""
        logger.info(f"处理POST请求: {request.path}, Headers: {dict(request.headers)}")
        
        try:
            # 解析请求数据
            data = request.get_json(force=True)
            
            if not data:
                return {"status": "error", "message": "ERROR DATA"}, 400
            
            user = data.get('user')
            email = data.get('email')
            
            if user and email:
                # 使用ES客户端插入文档
                success, message = es_client.insert_doc(data)
                
                if success:
                    return {"status": "ok", "message": "Created successfully"}, 201
                else:
                    return {"status": "error", "message": message}, 409
            else:
                return {"status": "error", "message": "Missing user or email"}, 400
                
        except Exception as e:
            logger.error(f"POST错误: {str(e)}")
            return {"status": "error", "message": str(e)}, 500

# 添加RESTful路由
api.add_resource(PersonPost, "/api/find")

# 添加测试端点
@app.route('/api/test')
def test_api():
    """测试API是否正常工作"""
    storage_mode = "引用模式" if StorageConfig.STORAGE_MODE == "reference" else "复制模式"
    return jsonify({
        "status": "ok", 
        "message": "API is working", 
        "engine": "Elasticsearch",
        "storage_mode": storage_mode
    })

if __name__ == '__main__':
    logger.info(f"启动Flask应用，使用Elasticsearch作为后端存储，存储模式: {StorageConfig.STORAGE_MODE}")
    app.run(host=AppConfig.HOST, port=AppConfig.PORT, debug=AppConfig.DEBUG)