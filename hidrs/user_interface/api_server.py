"""
API服务类，提供RESTful API接口
"""
import os
import json
import logging
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient

from .graph_visualizer import GraphVisualizer

logger = logging.getLogger(__name__)


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

        # 导入插件管理器
        from plugin_manager import get_plugin_manager
        self.plugin_manager = get_plugin_manager()
    
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

        @self.app.route('/plugins')
        def plugins_page():
            return render_template('plugins.html')

        @self.app.route('/local-files')
        def local_files_page():
            return render_template('local_files.html')

        @self.app.route('/advanced-scan')
        def advanced_scan_page():
            return render_template('advanced_scan.html')

        @self.app.route('/sed-geo')
        def sed_geo_page():
            return render_template('sed_geo.html')

        @self.app.route('/realtime-tracker')
        def realtime_tracker_page():
            return render_template('realtime_tracker.html')

        @self.app.route('/person-avoidance')
        def person_avoidance_page():
            return render_template('person_avoidance.html')

        @self.app.route('/global-broadcast')
        def global_broadcast_page():
            return render_template('global_broadcast.html')

        @self.app.route('/broadcast-player')
        def broadcast_player_page():
            return render_template('broadcast_player.html')

        @self.app.route('/commoncrawl')
        def commoncrawl_page():
            return render_template('commoncrawl_search.html')

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

        # 插件管理API
        @self.app.route('/api/plugins/list', methods=['GET'])
        def api_plugins_list():
            """获取所有插件列表"""
            try:
                plugins = self.plugin_manager.list_plugins()
                return jsonify(plugins)
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/plugins/load/<plugin_name>', methods=['POST'])
        def api_plugins_load(plugin_name):
            """加载插件"""
            try:
                success = self.plugin_manager.load_plugin(plugin_name)
                if success:
                    return jsonify({'success': True, 'message': f'Plugin {plugin_name} loaded successfully'})
                else:
                    return jsonify({'success': False, 'error': f'Failed to load plugin {plugin_name}'}), 400
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.app.route('/api/plugins/unload/<plugin_name>', methods=['POST'])
        def api_plugins_unload(plugin_name):
            """卸载插件"""
            try:
                success = self.plugin_manager.unload_plugin(plugin_name)
                if success:
                    return jsonify({'success': True, 'message': f'Plugin {plugin_name} unloaded successfully'})
                else:
                    return jsonify({'success': False, 'error': f'Failed to unload plugin {plugin_name}'}), 400
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.app.route('/api/plugins/enable/<plugin_name>', methods=['POST'])
        def api_plugins_enable(plugin_name):
            """启用插件"""
            try:
                success = self.plugin_manager.enable_plugin(plugin_name)
                if success:
                    return jsonify({'success': True, 'message': f'Plugin {plugin_name} enabled successfully'})
                else:
                    return jsonify({'success': False, 'error': f'Failed to enable plugin {plugin_name}'}), 400
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.app.route('/api/plugins/disable/<plugin_name>', methods=['POST'])
        def api_plugins_disable(plugin_name):
            """停用插件"""
            try:
                success = self.plugin_manager.disable_plugin(plugin_name)
                if success:
                    return jsonify({'success': True, 'message': f'Plugin {plugin_name} disabled successfully'})
                else:
                    return jsonify({'success': False, 'error': f'Failed to disable plugin {plugin_name}'}), 400
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.app.route('/api/plugins/config/<plugin_name>', methods=['POST'])
        def api_plugins_config(plugin_name):
            """保存插件配置"""
            try:
                config = request.json.get('config', {})
                plugin = self.plugin_manager.get_plugin(plugin_name)

                if not plugin:
                    return jsonify({'success': False, 'error': f'Plugin {plugin_name} not found'}), 404

                plugin.set_config(config)

                # 更新配置文件
                if plugin_name not in self.plugin_manager.config.get('plugins', {}):
                    if 'plugins' not in self.plugin_manager.config:
                        self.plugin_manager.config['plugins'] = {}
                    self.plugin_manager.config['plugins'][plugin_name] = {}

                self.plugin_manager.config['plugins'][plugin_name] = config
                self.plugin_manager._save_config()

                return jsonify({'success': True, 'message': f'Plugin {plugin_name} config saved successfully'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500

        # 本地文件搜索API
        @self.app.route('/api/local-file/search', methods=['POST'])
        def api_local_file_search():
            """本地文件搜索"""
            try:
                data = request.json
                pattern = data.get('pattern', '')
                limit = data.get('limit', 100)

                plugin = self.plugin_manager.get_plugin('LocalFileSearch')
                if not plugin:
                    return jsonify({'error': 'Local file search plugin not loaded'}), 400

                results = plugin.search_files(pattern, limit)
                return jsonify({'success': True, 'results': results})
            except Exception as e:
                logger.error(f"File search error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/local-file/rebuild-index', methods=['POST'])
        def api_rebuild_index():
            """重建文件索引"""
            try:
                data = request.json
                max_files = data.get('max_files')

                plugin = self.plugin_manager.get_plugin('LocalFileSearch')
                if not plugin:
                    return jsonify({'error': 'Local file search plugin not loaded'}), 400

                result = plugin.rebuild_index(max_files)
                return jsonify(result)
            except Exception as e:
                logger.error(f"Rebuild index error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/local-file/create-baseline', methods=['POST'])
        def api_create_baseline():
            """创建基线快照"""
            try:
                plugin = self.plugin_manager.get_plugin('LocalFileSearch')
                if not plugin:
                    return jsonify({'error': 'Local file search plugin not loaded'}), 400

                result = plugin.create_baseline()
                return jsonify(result)
            except Exception as e:
                logger.error(f"Create baseline error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/local-file/diagnose-space-leak', methods=['POST'])
        def api_diagnose_space_leak():
            """诊断空间泄漏"""
            try:
                plugin = self.plugin_manager.get_plugin('LocalFileSearch')
                if not plugin:
                    return jsonify({'error': 'Local file search plugin not loaded'}), 400

                result = plugin.diagnose_space_leak()
                return jsonify(result)
            except Exception as e:
                logger.error(f"Diagnose space leak error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/local-file/find-duplicates', methods=['POST'])
        def api_find_duplicates():
            """查找重复文件"""
            try:
                data = request.json
                min_size_mb = data.get('min_size_mb', 1)

                plugin = self.plugin_manager.get_plugin('LocalFileSearch')
                if not plugin:
                    return jsonify({'error': 'Local file search plugin not loaded'}), 400

                result = plugin.find_duplicates(min_size_mb)
                return jsonify(result)
            except Exception as e:
                logger.error(f"Find duplicates error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/local-file/stats', methods=['GET'])
        def api_local_file_stats():
            """获取磁盘统计信息"""
            try:
                plugin = self.plugin_manager.get_plugin('LocalFileSearch')
                if not plugin:
                    return jsonify({'error': 'Local file search plugin not loaded'}), 400

                result = plugin.get_disk_stats()
                return jsonify(result)
            except Exception as e:
                logger.error(f"Get stats error: {e}")
                return jsonify({'error': str(e)}), 500

        # 设备扫描API
        @self.app.route('/api/device-scanner/search', methods=['POST'])
        def api_device_scanner_search():
            """设备扫描搜索"""
            try:
                data = request.json
                query = data.get('query', '')
                source = data.get('source', 'shodan')
                limit = data.get('limit', 100)

                plugin = self.plugin_manager.get_plugin('DeviceScanner')
                if not plugin:
                    return jsonify({'error': 'Device scanner plugin not loaded'}), 400

                result = plugin.search(query, source, limit)
                return jsonify(result)
            except Exception as e:
                logger.error(f"Device scanner search error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/device-scanner/host/<ip>', methods=['GET'])
        def api_device_scanner_host(ip):
            """查询主机详细信息"""
            try:
                source = request.args.get('source', 'shodan')

                plugin = self.plugin_manager.get_plugin('DeviceScanner')
                if not plugin:
                    return jsonify({'error': 'Device scanner plugin not loaded'}), 400

                result = plugin.host_lookup(ip, source)
                return jsonify(result)
            except Exception as e:
                logger.error(f"Device scanner host lookup error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/device-scanner/sources', methods=['GET'])
        def api_device_scanner_sources():
            """获取可用的数据源"""
            try:
                plugin = self.plugin_manager.get_plugin('DeviceScanner')
                if not plugin:
                    return jsonify({'error': 'Device scanner plugin not loaded'}), 400

                sources = plugin.get_available_sources()
                return jsonify({'sources': sources})
            except Exception as e:
                logger.error(f"Get sources error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/device-scanner/stats', methods=['GET'])
        def api_device_scanner_stats():
            """获取设备扫描统计信息"""
            try:
                plugin = self.plugin_manager.get_plugin('DeviceScanner')
                if not plugin:
                    return jsonify({'error': 'Device scanner plugin not loaded'}), 400

                stats = plugin.get_stats()
                return jsonify(stats)
            except Exception as e:
                logger.error(f"Get stats error: {e}")
                return jsonify({'error': str(e)}), 500

        # 暗网爬虫API
        @self.app.route('/api/darkweb/crawl', methods=['POST'])
        def api_darkweb_crawl():
            """暗网爬取"""
            try:
                data = request.json
                url = data.get('url', '')
                renew_identity = data.get('renew_identity', True)

                plugin = self.plugin_manager.get_plugin('DarkWebCrawler')
                if not plugin:
                    return jsonify({'error': 'DarkWeb crawler plugin not loaded'}), 400

                result = plugin.crawl(url, renew_identity)
                return jsonify(result)
            except Exception as e:
                logger.error(f"DarkWeb crawl error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/darkweb/renew-identity', methods=['POST'])
        def api_darkweb_renew_identity():
            """更换 Tor 身份"""
            try:
                plugin = self.plugin_manager.get_plugin('DarkWebCrawler')
                if not plugin:
                    return jsonify({'error': 'DarkWeb crawler plugin not loaded'}), 400

                result = plugin.renew_tor_identity()
                return jsonify(result)
            except Exception as e:
                logger.error(f"Renew identity error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/darkweb/current-ip', methods=['GET'])
        def api_darkweb_current_ip():
            """获取当前 Tor IP"""
            try:
                plugin = self.plugin_manager.get_plugin('DarkWebCrawler')
                if not plugin:
                    return jsonify({'error': 'DarkWeb crawler plugin not loaded'}), 400

                result = plugin.get_current_tor_ip()
                return jsonify(result)
            except Exception as e:
                logger.error(f"Get current IP error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/darkweb/stats', methods=['GET'])
        def api_darkweb_stats():
            """获取暗网爬虫统计信息"""
            try:
                plugin = self.plugin_manager.get_plugin('DarkWebCrawler')
                if not plugin:
                    return jsonify({'error': 'DarkWeb crawler plugin not loaded'}), 400

                stats = plugin.get_stats()
                return jsonify(stats)
            except Exception as e:
                logger.error(f"Get stats error: {e}")
                return jsonify({'error': str(e)}), 500

        # SED地理可视化API
        @self.app.route('/api/sed-geo/sources', methods=['GET'])
        def api_sed_geo_sources():
            """获取数据源地理分布"""
            try:
                plugin = self.plugin_manager.get_plugin('SEDGeoVisualization')
                if not plugin:
                    return jsonify({'error': 'SED Geo Visualization plugin not loaded'}), 400

                result = plugin.get_source_distribution()
                return jsonify(result)
            except Exception as e:
                logger.error(f"Get source distribution error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/sed-geo/heatmap', methods=['GET'])
        def api_sed_geo_heatmap():
            """获取热力图数据"""
            try:
                plugin = self.plugin_manager.get_plugin('SEDGeoVisualization')
                if not plugin:
                    return jsonify({'error': 'SED Geo Visualization plugin not loaded'}), 400

                result = plugin.get_heatmap_data()
                return jsonify(result)
            except Exception as e:
                logger.error(f"Get heatmap data error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/sed-geo/timeline', methods=['GET'])
        def api_sed_geo_timeline():
            """获取时间轴数据"""
            try:
                plugin = self.plugin_manager.get_plugin('SEDGeoVisualization')
                if not plugin:
                    return jsonify({'error': 'SED Geo Visualization plugin not loaded'}), 400

                result = plugin.get_timeline_data()
                return jsonify(result)
            except Exception as e:
                logger.error(f"Get timeline data error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/sed-geo/region/<region_name>', methods=['GET'])
        def api_sed_geo_region(region_name):
            """查询指定地区的数据"""
            try:
                plugin = self.plugin_manager.get_plugin('SEDGeoVisualization')
                if not plugin:
                    return jsonify({'error': 'SED Geo Visualization plugin not loaded'}), 400

                result = plugin.get_region_data(region_name)
                return jsonify(result)
            except Exception as e:
                logger.error(f"Get region data error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/sed-geo/stats', methods=['GET'])
        def api_sed_geo_stats():
            """获取统计信息"""
            try:
                plugin = self.plugin_manager.get_plugin('SEDGeoVisualization')
                if not plugin:
                    return jsonify({'error': 'SED Geo Visualization plugin not loaded'}), 400

                stats = plugin.get_stats()
                return jsonify(stats)
            except Exception as e:
                logger.error(f"Get stats error: {e}")
                return jsonify({'error': str(e)}), 500

        # ===== 人员躲避系统 API =====
        @self.app.route('/api/avoidance/analyze', methods=['POST'])
        def api_avoidance_analyze():
            """分析活动模式"""
            try:
                plugin = self.plugin_manager.get_plugin('PersonAvoidance')
                if not plugin:
                    return jsonify({'error': 'Person Avoidance plugin not loaded'}), 400

                data = request.get_json() or {}
                eps = data.get('eps', 0.01)
                min_samples = data.get('min_samples', 5)

                result = plugin.analyze_activity_pattern(eps=eps, min_samples=min_samples)
                return jsonify(result)
            except Exception as e:
                logger.error(f"Analyze activity pattern error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/avoidance/predict', methods=['GET'])
        def api_avoidance_predict():
            """预测未来位置"""
            try:
                plugin = self.plugin_manager.get_plugin('PersonAvoidance')
                if not plugin:
                    return jsonify({'error': 'Person Avoidance plugin not loaded'}), 400

                hours_ahead = int(request.args.get('hours', 1))
                result = plugin.predict_future_location(hours_ahead=hours_ahead)
                return jsonify(result)
            except Exception as e:
                logger.error(f"Predict location error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/avoidance/plan-route', methods=['POST'])
        def api_avoidance_plan_route():
            """规划安全路线"""
            try:
                plugin = self.plugin_manager.get_plugin('PersonAvoidance')
                if not plugin:
                    return jsonify({'error': 'Person Avoidance plugin not loaded'}), 400

                data = request.get_json()
                start_lat = float(data['start_lat'])
                start_lon = float(data['start_lon'])
                end_lat = float(data['end_lat'])
                end_lon = float(data['end_lon'])

                result = plugin.plan_safe_route(start_lat, start_lon, end_lat, end_lon)
                return jsonify(result)
            except Exception as e:
                logger.error(f"Plan route error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/avoidance/danger-zones', methods=['GET'])
        def api_avoidance_danger_zones():
            """获取危险区域"""
            try:
                plugin = self.plugin_manager.get_plugin('PersonAvoidance')
                if not plugin:
                    return jsonify({'error': 'Person Avoidance plugin not loaded'}), 400

                result = plugin.get_danger_zones()
                return jsonify(result)
            except Exception as e:
                logger.error(f"Get danger zones error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/avoidance/stats', methods=['GET'])
        def api_avoidance_stats():
            """获取统计信息"""
            try:
                plugin = self.plugin_manager.get_plugin('PersonAvoidance')
                if not plugin:
                    return jsonify({'error': 'Person Avoidance plugin not loaded'}), 400

                stats = plugin.get_stats()
                return jsonify(stats)
            except Exception as e:
                logger.error(f"Get stats error: {e}")
                return jsonify({'error': str(e)}), 500

        # ===== 全球广播系统 API =====
        @self.app.route('/api/broadcast/start', methods=['POST'])
        def api_broadcast_start():
            """启动广播"""
            try:
                plugin = self.plugin_manager.get_plugin('GlobalBroadcast')
                if not plugin:
                    return jsonify({'error': 'Global Broadcast plugin not loaded'}), 400

                data = request.get_json()
                result = plugin.start_broadcast(
                    title=data.get('title', '系统广播'),
                    level=int(data.get('level', 0)),
                    content_type=data.get('content_type', 'message'),
                    content=data.get('content', ''),
                    duration=int(data.get('duration', 0))
                )
                return jsonify(result)
            except Exception as e:
                logger.error(f"Start broadcast error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/broadcast/stop', methods=['POST'])
        def api_broadcast_stop():
            """停止广播"""
            try:
                plugin = self.plugin_manager.get_plugin('GlobalBroadcast')
                if not plugin:
                    return jsonify({'error': 'Global Broadcast plugin not loaded'}), 400

                data = request.get_json()
                broadcast_id = data.get('broadcast_id')
                result = plugin.stop_broadcast(broadcast_id)
                return jsonify(result)
            except Exception as e:
                logger.error(f"Stop broadcast error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/broadcast/active', methods=['GET'])
        def api_broadcast_active():
            """获取活跃广播列表"""
            try:
                plugin = self.plugin_manager.get_plugin('GlobalBroadcast')
                if not plugin:
                    return jsonify({'error': 'Global Broadcast plugin not loaded'}), 400

                result = plugin.get_active_broadcasts()
                return jsonify(result)
            except Exception as e:
                logger.error(f"Get active broadcasts error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/broadcast/status/<broadcast_id>', methods=['GET'])
        def api_broadcast_status(broadcast_id):
            """获取广播状态"""
            try:
                plugin = self.plugin_manager.get_plugin('GlobalBroadcast')
                if not plugin:
                    return jsonify({'error': 'Global Broadcast plugin not loaded'}), 400

                result = plugin.get_broadcast_status(broadcast_id)
                return jsonify(result)
            except Exception as e:
                logger.error(f"Get broadcast status error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/broadcast/clients', methods=['GET'])
        def api_broadcast_clients():
            """获取已连接客户端列表"""
            try:
                plugin = self.plugin_manager.get_plugin('GlobalBroadcast')
                if not plugin:
                    return jsonify({'error': 'Global Broadcast plugin not loaded'}), 400

                result = plugin.get_connected_clients()
                return jsonify(result)
            except Exception as e:
                logger.error(f"Get clients error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/broadcast/simulation-log', methods=['GET'])
        def api_broadcast_simulation_log():
            """获取模拟日志"""
            try:
                plugin = self.plugin_manager.get_plugin('GlobalBroadcast')
                if not plugin:
                    return jsonify({'error': 'Global Broadcast plugin not loaded'}), 400

                limit = int(request.args.get('limit', 100))
                result = plugin.get_simulation_log(limit)
                return jsonify(result)
            except Exception as e:
                logger.error(f"Get simulation log error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/broadcast/stats', methods=['GET'])
        def api_broadcast_stats():
            """获取统计信息"""
            try:
                plugin = self.plugin_manager.get_plugin('GlobalBroadcast')
                if not plugin:
                    return jsonify({'error': 'Global Broadcast plugin not loaded'}), 400

                stats = plugin.get_stats()
                return jsonify(stats)
            except Exception as e:
                logger.error(f"Get stats error: {e}")
                return jsonify({'error': str(e)}), 500

        # ===== RTMP推流管理 API =====
        @self.app.route('/api/broadcast/rtmp/auth', methods=['POST'])
        def api_rtmp_auth():
            """RTMP推流认证（nginx-rtmp回调）"""
            try:
                plugin = self.plugin_manager.get_plugin('GlobalBroadcast')
                if not plugin:
                    return '', 403

                # nginx-rtmp会通过POST发送认证请求
                stream_name = request.form.get('name', '')
                stream_key = request.args.get('key', '')
                remote_addr = request.remote_addr

                if plugin.rtmp_auth(stream_name, stream_key, remote_addr):
                    return '', 200  # 认证成功
                else:
                    return '', 403  # 认证失败
            except Exception as e:
                logger.error(f"RTMP auth error: {e}")
                return '', 500

        @self.app.route('/api/broadcast/rtmp/start', methods=['POST'])
        def api_rtmp_publish_start():
            """RTMP推流开始回调（nginx-rtmp回调）"""
            try:
                plugin = self.plugin_manager.get_plugin('GlobalBroadcast')
                if not plugin:
                    return '', 200

                stream_name = request.form.get('name', '')
                remote_addr = request.remote_addr

                plugin.rtmp_publish_start(stream_name, remote_addr)
                return '', 200
            except Exception as e:
                logger.error(f"RTMP publish start error: {e}")
                return '', 500

        @self.app.route('/api/broadcast/rtmp/stop', methods=['POST'])
        def api_rtmp_publish_done():
            """RTMP推流结束回调（nginx-rtmp回调）"""
            try:
                plugin = self.plugin_manager.get_plugin('GlobalBroadcast')
                if not plugin:
                    return '', 200

                stream_name = request.form.get('name', '')
                remote_addr = request.remote_addr

                plugin.rtmp_publish_done(stream_name, remote_addr)
                return '', 200
            except Exception as e:
                logger.error(f"RTMP publish done error: {e}")
                return '', 500

        @self.app.route('/api/broadcast/hls/urls', methods=['GET'])
        def api_get_hls_urls():
            """获取HLS播放地址"""
            try:
                plugin = self.plugin_manager.get_plugin('GlobalBroadcast')
                if not plugin:
                    return jsonify({'error': 'Global Broadcast plugin not loaded'}), 400

                broadcast_id = request.args.get('broadcast_id')
                result = plugin.get_hls_urls(broadcast_id)
                return jsonify(result)
            except Exception as e:
                logger.error(f"Get HLS URLs error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/broadcast/stream-key/generate', methods=['POST'])
        def api_generate_stream_key():
            """生成新的推流密钥"""
            try:
                plugin = self.plugin_manager.get_plugin('GlobalBroadcast')
                if not plugin:
                    return jsonify({'error': 'Global Broadcast plugin not loaded'}), 400

                stream_key = plugin.generate_stream_key()
                return jsonify({
                    'success': True,
                    'stream_key': stream_key,
                    'rtmp_url': f'rtmp://localhost:1935/live/emergency?key={stream_key}'
                })
            except Exception as e:
                logger.error(f"Generate stream key error: {e}")
                return jsonify({'error': str(e)}), 500

        # ===== 一图流广播 API =====
        @self.app.route('/api/broadcast/oneimage/set', methods=['POST'])
        def api_set_oneimage_broadcast():
            """设置一图流广播"""
            try:
                plugin = self.plugin_manager.get_plugin('GlobalBroadcast')
                if not plugin:
                    return jsonify({'error': 'Global Broadcast plugin not loaded'}), 400

                data = request.get_json()
                result = plugin.set_oneimage_broadcast(
                    image_url=data.get('image_url', ''),
                    title=data.get('title', '一图流广播'),
                    duration=int(data.get('duration', 0))
                )
                return jsonify(result)
            except Exception as e:
                logger.error(f"Set oneimage broadcast error: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/broadcast/hijack/activate', methods=['POST'])
        def api_activate_hijack_mode():
            """激活设备劫持模式"""
            try:
                plugin = self.plugin_manager.get_plugin('GlobalBroadcast')
                if not plugin:
                    return jsonify({'error': 'Global Broadcast plugin not loaded'}), 400

                data = request.get_json()
                result = plugin.activate_hijack_mode(
                    target_clients=data.get('target_clients'),
                    hijack_type=data.get('hijack_type', 'oneimage')
                )
                return jsonify(result)
            except Exception as e:
                logger.error(f"Activate hijack mode error: {e}")
                return jsonify({'error': str(e)}), 500

        # ===== Common Crawl API =====
        @self.app.route('/api/commoncrawl/search', methods=['GET'])
        def api_commoncrawl_search():
            """Common Crawl搜索"""
            try:
                from hidrs.commoncrawl import CommonCrawlQueryEngine

                # 获取查询参数
                keywords_str = request.args.get('keywords', '')
                keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
                domain = request.args.get('domain', '')
                from_date = request.args.get('from_date', '')
                to_date = request.args.get('to_date', '')
                language = request.args.get('language', '')
                limit = int(request.args.get('limit', 20))

                if not keywords:
                    return jsonify({'error': 'Keywords required'}), 400

                # 初始化查询引擎
                query_engine = CommonCrawlQueryEngine(
                    mongodb_uri=self.config['mongodb_uri'],
                    db_name=self.config['mongodb_db']
                )

                # 执行搜索
                results = query_engine.advanced_search(
                    keywords=keywords,
                    domain=domain,
                    from_date=from_date,
                    to_date=to_date,
                    language=language,
                    limit=limit
                )

                return jsonify({
                    'success': True,
                    'results': results,
                    'total': len(results)
                })

            except Exception as e:
                import traceback
                traceback.print_exc()
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/commoncrawl/cluster', methods=['POST'])
        def api_commoncrawl_cluster():
            """Common Crawl结果聚类"""
            try:
                from hidrs.commoncrawl import CommonCrawlQueryEngine

                data = request.get_json()
                results = data.get('results', [])
                n_clusters = int(data.get('n_clusters', 5))

                if not results:
                    return jsonify({'error': 'No results provided'}), 400

                # 初始化查询引擎
                query_engine = CommonCrawlQueryEngine(
                    mongodb_uri=self.config['mongodb_uri'],
                    db_name=self.config['mongodb_db']
                )

                # 执行聚类
                cluster_result = query_engine.cluster_results(
                    results=results,
                    n_clusters=n_clusters
                )

                return jsonify({
                    'success': True,
                    'clusters': cluster_result.get('clusters', {}),
                    'method': cluster_result.get('method', 'unknown')
                })

            except Exception as e:
                import traceback
                traceback.print_exc()
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/commoncrawl/stats', methods=['GET'])
        def api_commoncrawl_stats():
            """Common Crawl统计信息"""
            try:
                # 从MongoDB获取统计信息
                collection = self.db.commoncrawl

                total_docs = collection.count_documents({})

                # 域名统计（Top 10）
                domain_stats = list(collection.aggregate([
                    {'$group': {'_id': '$domain', 'count': {'$sum': 1}}},
                    {'$sort': {'count': -1}},
                    {'$limit': 10}
                ]))

                # 时间线统计
                timeline_stats = list(collection.aggregate([
                    {'$group': {'_id': {'$substr': ['$timestamp', 0, 7]}, 'count': {'$sum': 1}}},
                    {'$sort': {'_id': 1}}
                ]))

                return jsonify({
                    'success': True,
                    'total_documents': total_docs,
                    'top_domains': [{'domain': item['_id'], 'count': item['count']} for item in domain_stats],
                    'timeline': [{'month': item['_id'], 'count': item['count']} for item in timeline_stats]
                })

            except Exception as e:
                import traceback
                traceback.print_exc()
                return jsonify({'error': str(e)}), 500

    def start(self, host='0.0.0.0', port=5000, debug=False):
        """启动API服务器"""
        self.app.run(host=host, port=port, debug=debug)
    
    def shutdown(self):
        """关闭API服务器"""
        self.mongo_client.close()