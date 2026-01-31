"""
API服务类，提供RESTful API接口
"""
import os
import json
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient

from .graph_visualizer import GraphVisualizer


class ApiServer:
    """API服务类，提供RESTful API接口"""
    
    def __init__(self, config_path="config/api_server_config.json"):
        """初始化API服务器"""
        # 设置Flask日志
        import logging
        from logging.handlers import RotatingFileHandler
        
        # 创建日志目录
        os.makedirs('/app/logs', exist_ok=True)
        
        # 设置Flask日志处理器
        flask_log_handler = RotatingFileHandler(
            '/app/logs/flask.log', 
            maxBytes=10485760,  # 10MB
            backupCount=3
        )
        flask_log_handler.setLevel(logging.DEBUG)
        flask_log_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        
        # 设置Flask应用的日志级别
        flask_logger = logging.getLogger('flask')
        flask_logger.setLevel(logging.DEBUG)
        flask_logger.addHandler(flask_log_handler)
        
        # 添加额外日志处理器以记录我们的调试信息
        debug_log_handler = RotatingFileHandler(
            '/app/logs/flask_debug.log', 
            maxBytes=10485760,  # 10MB
            backupCount=3
        )
        debug_log_handler.setLevel(logging.DEBUG)
        debug_log_handler.setFormatter(logging.Formatter(
            '%(asctime)s - DEBUG - %(message)s'
        ))
        
        # 创建自定义日志器
        self.debug_logger = logging.getLogger('flask_debug')
        self.debug_logger.setLevel(logging.DEBUG)
        self.debug_logger.addHandler(debug_log_handler)
        
        # 读取配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # 使用绝对路径创建Flask应用
        self.app = Flask(__name__, 
                     static_folder="/app/static",
                     template_folder="/app/templates")
        
        # 记录到自定义日志器
        self.debug_logger.debug(f"Flask template folder: {self.app.template_folder}")
        self.debug_logger.debug(f"Template loader: {self.app.jinja_loader}")
        
        # 检查模板是否存在
        try:
            template = self.app.jinja_loader.get_source(self.app.jinja_env, 'index.html')
            self.debug_logger.debug("Template exists!")
        except Exception as e:
            self.debug_logger.error(f"Template error: {e}")
        
        # 启用CORS
        CORS(self.app)
        
        # 初始化MongoDB连接
        self.mongo_client = MongoClient(self.config['mongodb_uri'])
        self.db = self.mongo_client[self.config['mongodb_db']]
        
        # 创建图可视化器
        self.graph_visualizer = GraphVisualizer(
            config_path=self.config['graph_visualizer_config_path']
        )
        
        # 导入各层组件
        self._import_components()
        
        # 注册路由
        self._register_routes()
    
    def _import_components(self):
        """导入各层组件"""
        import sys
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # 导入网络拓扑层
        from network_topology.topology_manager import TopologyManager
        self.topology_manager = TopologyManager(
            config_path=self.config['topology_manager_config_path']
        )
        
        # 导入全息映射层
        from holographic_mapping.holographic_mapping_manager import HolographicMappingManager
        self.mapping_manager = HolographicMappingManager(
            config_path=self.config['holographic_mapping_manager_config_path']
        )
        
        # 导入实时搜索层
        from realtime_search.search_engine import RealtimeSearchEngine
        self.search_engine = RealtimeSearchEngine(
            config_path=self.config['realtime_search_config_path']
        )
        
        # 导入决策反馈系统
        from realtime_search.decision_feedback import DecisionFeedbackSystem
        self.feedback_system = DecisionFeedbackSystem(
            config_path=self.config['decision_feedback_config_path']
        )
    
    def _register_routes(self):
        """注册API路由"""
        # 静态文件和HTML模板
        @self.app.route('/')
        def index():
            return render_template('index.html')
        
        @self.app.route('/dashboard')
        def dashboard():
            return render_template('dashboard.html')
        
        @self.app.route('/search')
        def search_page():
            return render_template('search.html')
        
        @self.app.route('/network')
        def network_page():
            return render_template('network.html')
        
        @self.app.route('/feedback')
        def feedback_page():
            return render_template('feedback.html')
        
        # API路由
        @self.app.route('/api/search', methods=['GET'])
        def api_search():
            query = request.args.get('q', '')
            limit = int(request.args.get('limit', 10))
            use_cache = request.args.get('cache', 'true').lower() == 'true'
            
            results = self.search_engine.search(
                query_text=query,
                limit=limit,
                use_cache=use_cache
            )
            
            return jsonify(results)
        
        @self.app.route('/api/network/graph', methods=['GET'])
        def api_network_graph():
            # 获取网络图
            graph = self.topology_manager.get_graph()
            
            # 生成可视化图像
            color_by = request.args.get('color_by', 'cluster')
            img_base64 = self.graph_visualizer.generate_graph_image(
                graph,
                title="全息互联网拓扑图",
                node_color_by=color_by
            )
            
            return jsonify({
                'image': img_base64,
                'node_count': graph.number_of_nodes(),
                'edge_count': graph.number_of_edges()
            })
        
        @self.app.route('/api/network/metrics', methods=['GET'])
        def api_network_metrics():
            # 获取网络指标
            topology_info = self.topology_manager.get_topology_info()
            
            # 从MongoDB获取历史Fiedler值
            fiedler_history = list(self.db.topology_analysis.find(
                {},
                {'timestamp': 1, 'fiedler_value': 1, '_id': 0}
            ).sort('timestamp', -1).limit(100))
            
            # 格式化时间戳
            for item in fiedler_history:
                if 'timestamp' in item:
                    item['timestamp'] = item['timestamp'].isoformat()
            
            return jsonify({
                'current_metrics': topology_info,
                'fiedler_history': fiedler_history
            })
        
        @self.app.route('/api/network/communities', methods=['GET'])
        def api_network_communities():
            # 获取社区结构
            communities = self.topology_manager.get_community_structure()
            
            # 转换为列表格式
            communities_list = []
            for cluster_id, nodes in communities.items():
                communities_list.append({
                    'cluster_id': cluster_id,
                    'node_count': len(nodes),
                    'sample_nodes': nodes[:10]  # 仅返回前10个节点示例
                })
            
            return jsonify(communities_list)
        
        @self.app.route('/api/search/stats', methods=['GET'])
        def api_search_stats():
            # 获取搜索统计
            hours = int(request.args.get('hours', 24))
            stats = self.search_engine.get_search_stats(time_range_hours=hours)
            
            return jsonify(stats)
        
        @self.app.route('/api/feedback/recent', methods=['GET'])
        def api_recent_feedback():
            # 获取最近的决策反馈
            limit = int(request.args.get('limit', 10))
            feedback = self.feedback_system.get_recent_feedback(limit=limit)
            
            # 格式化时间戳
            for item in feedback:
                if 'timestamp' in item:
                    item['timestamp'] = item['timestamp'].isoformat()
                if 'system_state' in item and 'timestamp' in item['system_state']:
                    item['system_state']['timestamp'] = item['system_state']['timestamp'].isoformat()
            
            return jsonify(feedback)
        
        @self.app.route('/api/metrics/plot', methods=['GET'])
        def api_metrics_plot():
            # 生成指标变化图
            metric_type = request.args.get('type', 'fiedler')
            days = int(request.args.get('days', 7))
            
            # 计算时间范围
            import datetime
            end_time = datetime.datetime.now()
            start_time = end_time - datetime.timedelta(days=days)
            
            # 从MongoDB获取数据
            if metric_type == 'fiedler':
                data = list(self.db.topology_analysis.find(
                    {'timestamp': {'$gte': start_time, '$lte': end_time}},
                    {'timestamp': 1, 'fiedler_value': 1, '_id': 0}
                ).sort('timestamp', 1))
                
                if data:
                    # 绘制Fiedler值变化图
                    img_base64 = self.graph_visualizer.generate_metrics_plot(
                        data,
                        x_key='timestamp',
                        y_key='fiedler_value',
                        title=f"Fiedler值变化趋势（过去{days}天）",
                        xlabel="时间",
                        ylabel="Fiedler值"
                    )
                    
                    return jsonify({'image': img_base64})
            
            elif metric_type == 'node_count':
                data = list(self.db.topology_analysis.find(
                    {'timestamp': {'$gte': start_time, '$lte': end_time}},
                    {'timestamp': 1, 'node_count': 1, '_id': 0}
                ).sort('timestamp', 1))
                
                if data:
                    # 绘制节点数变化图
                    img_base64 = self.graph_visualizer.generate_metrics_plot(
                        data,
                        x_key='timestamp',
                        y_key='node_count',
                        title=f"节点数变化趋势（过去{days}天）",
                        xlabel="时间",
                        ylabel="节点数量"
                    )
                    
                    return jsonify({'image': img_base64})
            
            elif metric_type == 'search_latency':
                # 聚合搜索延迟数据
                pipeline = [
                    {'$match': {'timestamp': {'$gte': start_time, '$lte': end_time}}},
                    {'$group': {
                        '_id': {
                            'year': {'$year': '$timestamp'},
                            'month': {'$month': '$timestamp'},
                            'day': {'$dayOfMonth': '$timestamp'},
                            'hour': {'$hour': '$timestamp'}
                        },
                        'avg_search_time_ms': {'$avg': '$search_time_ms'},
                        'timestamp': {'$first': '$timestamp'}
                    }},
                    {'$project': {
                        '_id': 0,
                        'timestamp': '$timestamp',
                        'avg_search_time_ms': 1
                    }},
                    {'$sort': {'timestamp': 1}}
                ]
                
                data = list(self.db.search_logs.aggregate(pipeline))
                
                if data:
                    # 绘制搜索延迟变化图
                    img_base64 = self.graph_visualizer.generate_metrics_plot(
                        data,
                        x_key='timestamp',
                        y_key='avg_search_time_ms',
                        title=f"平均搜索延迟变化趋势（过去{days}天）",
                        xlabel="时间",
                        ylabel="平均延迟(毫秒)"
                    )
                    
                    return jsonify({'image': img_base64})
            
            # 没有数据或不支持的指标类型
            return jsonify({'error': 'No data available or unsupported metric type'})
    
    def start(self, host='0.0.0.0', port=5000, debug=False):
        """启动API服务器"""
        self.app.run(host=host, port=port, debug=debug)
    
    def shutdown(self):
        """关闭API服务器"""
        self.mongo_client.close()