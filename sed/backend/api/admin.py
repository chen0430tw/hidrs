"""
管理API模块 - 提供系统配置和管理功能
"""
import os
import json
import logging
from flask import Blueprint, request, jsonify, current_app

# 配置
from config import AppConfig, StorageConfig

# 设置日志
logger = logging.getLogger(__name__)

# 创建蓝图
admin_bp = Blueprint('admin', __name__)

def register_admin_routes(app):
    """注册管理API路由"""
    app.register_blueprint(admin_bp, url_prefix='/api/admin')

@admin_bp.route('/config/system', methods=['GET'])
def get_system_config():
    """获取系统配置"""
    try:
        config = {
            "app": {
                "debug": AppConfig.DEBUG,
                "host": AppConfig.HOST,
                "port": AppConfig.PORT,
                "log_file": AppConfig.ERROR_LOG_FILE
            },
            "storage": {
                "mode": StorageConfig.STORAGE_MODE,
                "data_dir": StorageConfig.SOURCE_DATA_DIR,
                "compress_index": StorageConfig.COMPRESS_INDEX,
                "use_partitioning": StorageConfig.USE_PARTITIONING,
                "partition_strategy": StorageConfig.PARTITION_STRATEGY
            },
            "system_mode": os.getenv('MODE', 'local')
        }
        
        return jsonify({
            "status": "ok",
            "data": config
        })
    except Exception as e:
        logger.error(f"获取系统配置失败: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@admin_bp.route('/config/system', methods=['POST'])
def update_system_config():
    """更新系统配置"""
    try:
        data = request.get_json()
        
        # 更新存储配置
        if 'storage' in data:
            storage = data['storage']
            
            if 'mode' in storage:
                StorageConfig.STORAGE_MODE = storage['mode']
                
            if 'use_partitioning' in storage:
                StorageConfig.USE_PARTITIONING = storage['use_partitioning']
                
            if 'partition_strategy' in storage:
                StorageConfig.PARTITION_STRATEGY = storage['partition_strategy']
        
        # 更新应用配置
        if 'app' in data:
            app = data['app']
            
            if 'debug' in app:
                AppConfig.DEBUG = app['debug']
        
        return jsonify({
            "status": "ok",
            "message": "系统配置已更新"
        })
    except Exception as e:
        logger.error(f"更新系统配置失败: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@admin_bp.route('/config/import', methods=['GET'])
def get_import_config():
    """获取导入配置"""
    try:
        # 读取导入配置
        config_path = os.path.join('configs', 'import_settings.json')
        
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            # 返回默认配置
            config = {
                "batchSize": 1000,
                "storageMode": StorageConfig.STORAGE_MODE,
                "usePartitioning": StorageConfig.USE_PARTITIONING,
                "partitionStrategy": StorageConfig.PARTITION_STRATEGY,
                "useMSNumber": True
            }
        
        return jsonify({
            "status": "ok",
            "data": config
        })
    except Exception as e:
        logger.error(f"获取导入配置失败: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@admin_bp.route('/config/import', methods=['POST'])
def update_import_config():
    """更新导入配置"""
    try:
        data = request.get_json()
        
        # 更新存储配置
        if 'storageMode' in data:
            StorageConfig.STORAGE_MODE = data['storageMode']
            
        if 'usePartitioning' in data:
            StorageConfig.USE_PARTITIONING = data['usePartitioning']
            
        if 'partitionStrategy' in data:
            StorageConfig.PARTITION_STRATEGY = data['partitionStrategy']
        
        # 保存配置
        config_dir = 'configs'
        os.makedirs(config_dir, exist_ok=True)
        
        config_path = os.path.join(config_dir, 'import_settings.json')
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        return jsonify({
            "status": "ok",
            "message": "导入配置已更新"
        })
    except Exception as e:
        logger.error(f"更新导入配置失败: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@admin_bp.route('/config/remote', methods=['POST'])
def update_remote_config():
    """更新远程API配置"""
    try:
        data = request.get_json()
        
        # 仅在远程模式下可修改
        if os.getenv('MODE', 'local') != 'remote':
            return jsonify({
                "status": "error",
                "message": "只有在远程模式下才能修改API配置"
            }), 400
        
        client = current_app.config.get('CLIENT')
        
        # 更新客户端配置
        if hasattr(client, 'timeout') and 'timeout' in data:
            client.timeout = data['timeout']
            
        if hasattr(client, 'use_cache') and 'useCache' in data:
            client.use_cache = data['useCache']
        
        return jsonify({
            "status": "ok",
            "message": "远程API配置已更新"
        })
    except Exception as e:
        logger.error(f"更新远程API配置失败: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@admin_bp.route('/stats', methods=['GET'])
def get_stats():
    """获取系统统计信息"""
    try:
        client = current_app.config.get('CLIENT')
        
        # 确定系统模式
        mode = os.getenv('MODE', 'local')
        
        if mode == 'local':
            # 本地ES模式
            es_client = client
            
            # 获取ES统计信息
            count_query = {"query": {"match_all": {}}}
            total_count = es_client.count(count_query)
            
            index_pattern = f"{es_client.index_name}*" if StorageConfig.USE_PARTITIONING else es_client.index_name
            indices_stats = es_client.es.indices.stats(index=index_pattern).get('_all', {})
            
            # 计算大小
            size_in_bytes = indices_stats.get('total', {}).get('store', {}).get('size_in_bytes', 0)
            size_in_mb = round(size_in_bytes / (1024 * 1024), 2)
            
            stats = {
                "total_records": total_count,
                "index_size_mb": size_in_mb,
                "storage_mode": StorageConfig.STORAGE_MODE,
                "partitioning": StorageConfig.USE_PARTITIONING,
                "partition_strategy": StorageConfig.PARTITION_STRATEGY,
                "indices_count": len(indices_stats.get('indices', {}))
            }
        else:
            # 远程API模式
            stats = client.get_stats()
        
        return jsonify({
            "status": "ok",
            "data": stats
        })
    except Exception as e:
        logger.error(f"获取统计信息失败: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500