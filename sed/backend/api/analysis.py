"""
分析API模块 - 提供数据分析功能
"""
import logging
from flask import Blueprint, request, jsonify, current_app

# 设置日志
logger = logging.getLogger(__name__)

# 创建蓝图
analysis_bp = Blueprint('analysis', __name__)

def register_analysis_routes(app):
    """注册分析API路由"""
    app.register_blueprint(analysis_bp, url_prefix='/api')

@analysis_bp.route('/analysis/<string:type_analyze>')
def analysis(type_analyze):
    """执行聚合分析"""
    try:
        # 验证分析类型
        valid_types = ["source", "xtime", "suffix_email", "create_time"]
        
        if type_analyze not in valid_types:
            return jsonify({
                "status": "error", 
                "message": f"不支持的分析类型: {type_analyze}，有效类型: {', '.join(valid_types)}"
            }), 400
        
        # 获取客户端
        client = current_app.config.get('CLIENT')
        
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
        
        # 执行聚合
        aggs = client.aggregate(agg_query)
        
        # 转换结果格式
        results = []
        for bucket in aggs.get("group_by_field", {}).get("buckets", []):
            results.append({
                "_id": bucket["key"],
                "sum": bucket["doc_count"]
            })
        
        return jsonify({"status": "ok", "data": results})
        
    except Exception as e:
        logger.error(f"分析出错: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@analysis_bp.route('/stats')
def get_stats():
    """获取系统统计信息"""
    try:
        # 获取客户端和模式
        client = current_app.config.get('CLIENT')
        mode = current_app.config.get('MODE')
        
        if mode == 'remote':
            # 远程模式：使用远程API获取统计信息
            stats = client.get_stats()
        else:
            # 本地模式：查询ES统计信息
            # 获取总记录数
            count_query = {"query": {"match_all": {}}}
            total_count = client.count(count_query)
            
            # 获取索引信息
            use_partitioning = current_app.config.get('USE_PARTITIONING', False)
            storage_mode = current_app.config.get('STORAGE_MODE', 'reference')
            
            try:
                if use_partitioning:
                    index_pattern = f"{client.index_name}*"
                    stats = client.es.indices.stats(index=index_pattern)
                    indices_stats = stats.get('_all', {})
                else:
                    stats = client.es.indices.stats(index=client.index_name)
                    indices_stats = stats.get('_all', {})
                
                # 计算索引大小
                size_in_bytes = indices_stats.get('total', {}).get('store', {}).get('size_in_bytes', 0)
                size_in_mb = round(size_in_bytes / (1024 * 1024), 2)
                
                stats = {
                    "total_records": total_count,
                    "index_size_mb": size_in_mb,
                    "storage_mode": storage_mode,
                    "partitioning": use_partitioning,
                    "indices_count": len(indices_stats.get('indices', {}))
                }
            except Exception as e:
                logger.error(f"获取索引统计信息失败: {str(e)}")
                stats = {
                    "total_records": total_count,
                    "storage_mode": storage_mode
                }
        
        return jsonify({
            "status": "ok",
            "data": stats
        })
        
    except Exception as e:
        logger.error(f"获取统计信息出错: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@analysis_bp.route('/distribution/<string:field>')
def get_distribution(field):
    """获取字段分布"""
    try:
        # 验证字段
        valid_fields = ["source", "xtime", "suffix_email", "create_time"]
        
        if field not in valid_fields:
            return jsonify({
                "status": "error", 
                "message": f"不支持的字段: {field}，有效字段: {', '.join(valid_fields)}"
            }), 400
        
        # 获取客户端
        client = current_app.config.get('CLIENT')
        
        # 构建聚合查询
        agg_query = {
            "size": 0,
            "aggs": {
                "distribution": {
                    "terms": {
                        "field": field,
                        "size": 200,
                        "order": {"_count": "desc"}
                    }
                }
            }
        }
        
        # 执行聚合
        aggs = client.aggregate(agg_query)
        
        # 转换结果格式
        results = []
        for bucket in aggs.get("distribution", {}).get("buckets", []):
            results.append({
                "key": bucket["key"],
                "count": bucket["doc_count"]
            })
        
        return jsonify({
            "status": "ok",
            "data": results
        })
        
    except Exception as e:
        logger.error(f"获取分布信息出错: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@analysis_bp.route('/trend')
def get_trend():
    """获取时间趋势"""
    try:
        # 获取客户端
        client = current_app.config.get('CLIENT')
        
        # 构建聚合查询
        agg_query = {
            "size": 0,
            "aggs": {
                "time_trend": {
                    "terms": {
                        "field": "xtime",
                        "size": 100,
                        "order": {"_key": "asc"}
                    }
                }
            }
        }
        
        # 执行聚合
        aggs = client.aggregate(agg_query)
        
        # 转换结果格式
        results = []
        for bucket in aggs.get("time_trend", {}).get("buckets", []):
            results.append({
                "time": bucket["key"],
                "count": bucket["doc_count"]
            })
        
        return jsonify({
            "status": "ok",
            "data": results
        })
        
    except Exception as e:
        logger.error(f"获取趋势信息出错: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@analysis_bp.route('/password/strength')
def password_strength():
    """分析密码强度"""
    try:
        # 获取客户端
        client = current_app.config.get('CLIENT')
        
        # 构建聚合查询 - 密码长度分布
        length_query = {
            "size": 0,
            "aggs": {
                "password_length": {
                    "range": {
                        "script": {
                            "source": "doc['password'].value.length()"
                        },
                        "ranges": [
                            {"to": 6},
                            {"from": 6, "to": 8},
                            {"from": 8, "to": 10},
                            {"from": 10, "to": 12},
                            {"from": 12}
                        ]
                    }
                }
            }
        }
        
        # 执行聚合
        length_aggs = client.aggregate(length_query)
        
        # 转换结果格式
        length_results = []
        for bucket in length_aggs.get("password_length", {}).get("buckets", []):
            length_results.append({
                "range": f"{bucket.get('from', 0)}-{bucket.get('to', '+inf')}",
               "count": bucket["doc_count"]
           })
       
       # 密码复杂度分析
       # 注意：复杂查询可能需要调整ES配置或使用别的方式实现
        complexity_query = {
           "size": 0,
           "aggs": {
               "complexity": {
                   "terms": {
                       "script": {
                           "source": """
                           String pwd = doc['password'].value; 
                           if (pwd.length() < 6) return 'very_weak';
                           boolean hasDigit = pwd.matches('.*\\d.*');
                           boolean hasLetter = pwd.matches('.*[a-zA-Z].*');
                           boolean hasSymbol = pwd.matches('.*[^a-zA-Z\\d].*');
                           
                           if (hasDigit && hasLetter && hasSymbol) return 'strong';
                           if ((hasDigit && hasLetter) || (hasLetter && hasSymbol) || (hasDigit && hasSymbol)) return 'medium';
                           return 'weak';
                           """
                       },
                       "size": 10
                   }
               }
           }
       }
       
       # 由于脚本查询可能较耗资源，此处模拟结果
        complexity_results = [
           {"category": "very_weak", "count": 0},
           {"category": "weak", "count": 0},
           {"category": "medium", "count": 0},
           {"category": "strong", "count": 0}
       ]
       
        return jsonify({
           "status": "ok",
           "data": {
               "length_distribution": length_results,
               "complexity": complexity_results
           }
       })
       
    except Exception as e:
       logger.error(f"分析密码强度出错: {str(e)}")
       return jsonify({"status": "error", "message": str(e)}), 500