"""
决策反馈系统类，提供系统状态监控和动态调整建议
"""
import json
import time
import threading
import numpy as np
from datetime import datetime, timedelta
from pymongo import MongoClient
from kafka import KafkaConsumer, KafkaProducer


class DecisionFeedbackSystem:
    """决策反馈系统类，提供系统状态监控和动态调整建议"""
    
    def __init__(self, config_path="config/decision_feedback_config.json"):
        """初始化决策反馈系统"""
        # 读取配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # 初始化MongoDB连接
        self.mongo_client = MongoClient(self.config['mongodb_uri'])
        self.db = self.mongo_client[self.config['mongodb_db']]
        self.feedback_collection = self.db[self.config['feedback_collection']]
        self.topology_collection = self.db[self.config['topology_collection']]
        self.search_logs_collection = self.db[self.config['search_logs_collection']]
        
        # 初始化Kafka消费者，接收拓扑分析和搜索事件
        self.topology_consumer = KafkaConsumer(
            self.config['kafka_topology_topic'],
            bootstrap_servers=self.config['kafka_servers'],
            auto_offset_reset='latest',
            group_id='decision_feedback_topology_group',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        
        self.search_consumer = KafkaConsumer(
            self.config['kafka_search_events_topic'],
            bootstrap_servers=self.config['kafka_servers'],
            auto_offset_reset='latest',
            group_id='decision_feedback_search_group',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        
        self.alert_consumer = KafkaConsumer(
            self.config['kafka_alert_topic'],
            bootstrap_servers=self.config['kafka_servers'],
            auto_offset_reset='latest',
            group_id='decision_feedback_alert_group',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        
        # 初始化Kafka生产者，用于发送决策反馈
        self.producer = KafkaProducer(
            bootstrap_servers=self.config['kafka_servers'],
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        # 监控线程
        self.topology_monitor_thread = None
        self.search_monitor_thread = None
        self.alert_monitor_thread = None
        self.running = False
        
        # 系统状态指标
        self.system_metrics = {
            'fiedler_value_history': [],
            'node_count_history': [],
            'search_latency_history': [],
            'alert_count': 0,
            'last_update': datetime.now()
        }
    
    def _topology_monitor_worker(self):
        """拓扑监控线程，监控网络拓扑变化"""
        while self.running:
            try:
                # 从Kafka消费拓扑分析结果
                for message in self.topology_consumer:
                    if not self.running:
                        break
                    
                    try:
                        # 获取拓扑数据
                        topology_data = message.value
                        
                        # 更新系统指标
                        if 'fiedler_value' in topology_data:
                            self.system_metrics['fiedler_value_history'].append({
                                'value': topology_data['fiedler_value'],
                                'timestamp': datetime.now()
                            })
                            # 保持历史记录不超过配置的最大长度
                            max_history = self.config['max_metric_history_length']
                            if len(self.system_metrics['fiedler_value_history']) > max_history:
                                self.system_metrics['fiedler_value_history'] = self.system_metrics['fiedler_value_history'][-max_history:]
                        
                        if 'node_count' in topology_data:
                            self.system_metrics['node_count_history'].append({
                                'value': topology_data['node_count'],
                                'timestamp': datetime.now()
                            })
                            # 保持历史记录不超过配置的最大长度
                            max_history = self.config['max_metric_history_length']
                            if len(self.system_metrics['node_count_history']) > max_history:
                                self.system_metrics['node_count_history'] = self.system_metrics['node_count_history'][-max_history:]
                        
                        # 检查是否需要生成决策建议
                        if self._should_generate_feedback():
                            self._generate_and_send_feedback()
                        
                        # 更新最后更新时间
                        self.system_metrics['last_update'] = datetime.now()
                    
                    except Exception as e:
                        print(f"Error processing topology data: {str(e)}")
            
            except Exception as e:
                print(f"Topology monitor error: {str(e)}")
                time.sleep(10)  # 出错后等待一段时间再继续
    
    def _search_monitor_worker(self):
        """搜索监控线程，监控搜索性能和用户行为"""
        while self.running:
            try:
                # 从Kafka消费搜索事件
                for message in self.search_consumer:
                    if not self.running:
                        break
                    
                    try:
                        # 获取搜索事件数据
                        search_event = message.value
                        
                        # 更新系统指标
                        if 'search_time_ms' in search_event:
                            self.system_metrics['search_latency_history'].append({
                                'value': search_event['search_time_ms'],
                                'timestamp': datetime.now()
                            })
                            # 保持历史记录不超过配置的最大长度
                            max_history = self.config['max_metric_history_length']
                            if len(self.system_metrics['search_latency_history']) > max_history:
                                self.system_metrics['search_latency_history'] = self.system_metrics['search_latency_history'][-max_history:]
                        
                        # 检查搜索性能是否需要优化
                        self._check_search_performance()
                    
                    except Exception as e:
                        print(f"Error processing search event: {str(e)}")
            
            except Exception as e:
                print(f"Search monitor error: {str(e)}")
                time.sleep(10)  # 出错后等待一段时间再继续
    
    def _alert_monitor_worker(self):
        """告警监控线程，监控系统异常和告警"""
        while self.running:
            try:
                # 从Kafka消费告警事件
                for message in self.alert_consumer:
                    if not self.running:
                        break
                    
                    try:
                        # 获取告警事件数据
                        alert_event = message.value
                        
                        # 更新告警计数
                        self.system_metrics['alert_count'] += 1
                        
                        # 根据告警类型生成应对策略
                        self._process_alert(alert_event)
                    
                    except Exception as e:
                        print(f"Error processing alert event: {str(e)}")
            
            except Exception as e:
                print(f"Alert monitor error: {str(e)}")
                time.sleep(10)  # 出错后等待一段时间再继续
    
    def _should_generate_feedback(self):
        """判断是否应该生成决策反馈"""
        # 如果距离上次反馈时间超过配置的间隔，则生成反馈
        last_feedback = self.feedback_collection.find_one(
            sort=[('timestamp', -1)]
        )
        
        if not last_feedback:
            return True
        
        last_feedback_time = last_feedback['timestamp']
        time_since_last_feedback = (datetime.now() - last_feedback_time).total_seconds()
        
        return time_since_last_feedback > self.config['feedback_interval_seconds']
    
    def _generate_and_send_feedback(self):
        """生成并发送决策反馈"""
        # 分析系统状态
        system_analysis = self._analyze_system_state()
        
        # 生成决策建议
        recommendations = self._generate_recommendations(system_analysis)
        
        # 创建反馈文档
        feedback_doc = {
            'timestamp': datetime.now(),
            'system_state': system_analysis,
            'recommendations': recommendations
        }
        
        # 保存到MongoDB
        feedback_id = self.feedback_collection.insert_one(feedback_doc).inserted_id
        
        # 发送到Kafka
        self.producer.send(
            self.config['kafka_feedback_topic'],
            {
                'feedback_id': str(feedback_id),
                'timestamp': datetime.now().isoformat(),
                'recommendations': recommendations
            }
        )
        
        print(f"Generated and sent feedback: {len(recommendations)} recommendations")
    
    def _analyze_system_state(self):
        """分析系统当前状态"""
        # 提取最近的Fiedler值
        recent_fiedler_values = [item['value'] for item in self.system_metrics['fiedler_value_history']]
        
        # 提取最近的节点数量
        recent_node_counts = [item['value'] for item in self.system_metrics['node_count_history']]
        
        # 提取最近的搜索延迟
        recent_search_latencies = [item['value'] for item in self.system_metrics['search_latency_history']]
        
        # 计算统计指标
        fiedler_avg = np.mean(recent_fiedler_values) if recent_fiedler_values else 0
        fiedler_std = np.std(recent_fiedler_values) if recent_fiedler_values else 0
        fiedler_trend = self._calculate_trend(recent_fiedler_values)
        
        node_count_avg = np.mean(recent_node_counts) if recent_node_counts else 0
        node_count_trend = self._calculate_trend(recent_node_counts)
        
        search_latency_avg = np.mean(recent_search_latencies) if recent_search_latencies else 0
        search_latency_trend = self._calculate_trend(recent_search_latencies)
        
        # 获取搜索统计
        search_stats = self._get_search_stats(hours=24)
        
        return {
            'fiedler_value': {
                'current': recent_fiedler_values[-1] if recent_fiedler_values else 0,
                'average': fiedler_avg,
                'std_dev': fiedler_std,
                'trend': fiedler_trend
            },
            'node_count': {
                'current': recent_node_counts[-1] if recent_node_counts else 0,
                'average': node_count_avg,
                'trend': node_count_trend
            },
            'search_performance': {
                'avg_latency_ms': search_latency_avg,
                'trend': search_latency_trend,
                'search_stats': search_stats
            },
            'alerts': {
                'count': self.system_metrics['alert_count']
            },
            'timestamp': datetime.now()
        }
    
    def _calculate_trend(self, values, window=5):
        """计算数据趋势（上升、下降或稳定）"""
        if not values or len(values) < 2:
            return "stable"
        
        # 使用最近的window个值计算趋势
        recent_values = values[-window:] if len(values) > window else values
        
        # 计算简单线性回归的斜率
        x = np.arange(len(recent_values))
        y = np.array(recent_values)
        
        if len(x) < 2:
            return "stable"
        
        # 计算斜率
        slope, _ = np.polyfit(x, y, 1)
        
        # 判断趋势
        threshold = 0.05  # 趋势判定阈值
        if slope > threshold:
            return "increasing"
        elif slope < -threshold:
            return "decreasing"
        else:
            return "stable"
    
    def _get_search_stats(self, hours=24):
        """获取搜索统计信息"""
        # 计算时间范围
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        # 查询时间范围内的搜索日志
        logs = self.search_logs_collection.find({
            'timestamp': {'$gte': start_time, '$lte': end_time}
        })
        
        # 统计信息
        total_searches = 0
        total_time_ms = 0
        empty_results = 0
        
        for log in logs:
            total_searches += 1
            total_time_ms += log.get('search_time_ms', 0)
            
            if log.get('results_count', 0) == 0:
                empty_results += 1
        
        # 计算平均搜索时间
        avg_time_ms = total_time_ms / total_searches if total_searches > 0 else 0
        
        return {
            'total_searches': total_searches,
            'empty_results_count': empty_results,
            'empty_results_percentage': (empty_results / total_searches * 100) if total_searches > 0 else 0,
            'avg_search_time_ms': avg_time_ms
        }
    
    def _check_search_performance(self):
        """检查搜索性能是否需要优化"""
        # 提取最近的搜索延迟
        recent_latencies = [item['value'] for item in self.system_metrics['search_latency_history']]
        
        if not recent_latencies:
            return
        
        # 计算平均延迟和趋势
        avg_latency = np.mean(recent_latencies)
        latency_trend = self._calculate_trend(recent_latencies)
        
        # 检查延迟是否超过阈值
        if avg_latency > self.config['search_latency_threshold_ms'] or latency_trend == "increasing":
            # 生成性能优化建议
            recommendation = {
                'type': 'search_performance',
                'severity': 'medium' if avg_latency > self.config['search_latency_threshold_ms'] * 1.5 else 'low',
                'message': f"Search latency ({avg_latency:.2f}ms) exceeds threshold or is increasing",
                'suggested_actions': [
                    "Optimize cache settings",
                    "Increase Elasticsearch resources",
                    "Review and optimize search queries"
                ],
                'timestamp': datetime.now().isoformat()
            }
            
            # 发送到Kafka
            self.producer.send(
                self.config['kafka_recommendation_topic'],
                recommendation
            )
            
            print(f"Generated search performance recommendation: {recommendation['message']}")
    
    def _process_alert(self, alert_event):
        """处理告警事件并生成应对策略"""
        alert_type = alert_event.get('type', '')
        
        if alert_type == 'topology_anomaly':
            # 拓扑异常告警
            fiedler_change = alert_event.get('fiedler_change', 0)
            severity = alert_event.get('severity', 'medium')
            
            # 生成应对策略
            recommendation = {
                'type': 'topology_anomaly_response',
                'severity': severity,
                'message': f"Topology anomaly detected with Fiedler change: {fiedler_change:.4f}",
                'suggested_actions': [
                    "Increase crawling frequency in affected areas",
                    "Adjust similarity threshold for network construction",
                    "Rebalance node distribution across clusters"
                ],
                'timestamp': datetime.now().isoformat()
            }
            
            # 发送到Kafka
            self.producer.send(
                self.config['kafka_recommendation_topic'],
                recommendation
            )
            
            print(f"Generated topology anomaly recommendation: {recommendation['message']}")
        
        elif alert_type == 'search_zero_results':
            # 搜索零结果告警
            query = alert_event.get('query', '')
            
            # 生成应对策略
            recommendation = {
                'type': 'search_improvement',
                'severity': 'low',
                'message': f"Search query '{query}' returned zero results",
                'suggested_actions': [
                    "Expand data collection scope",
                    "Adjust similarity thresholds for search",
                    "Implement query expansion techniques"
                ],
                'timestamp': datetime.now().isoformat()
            }
            
            # 发送到Kafka
            self.producer.send(
                self.config['kafka_recommendation_topic'],
                recommendation
            )
            
            print(f"Generated search improvement recommendation for query: {query}")
    
    def _generate_recommendations(self, system_analysis):
        """根据系统分析生成决策建议"""
        recommendations = []
        
        # 检查Fiedler值变化
        fiedler_data = system_analysis['fiedler_value']
        if fiedler_data['trend'] == 'decreasing':
            recommendations.append({
                'type': 'network_stability',
                'severity': 'medium',
                'message': "Network connectivity is weakening (decreasing Fiedler value)",
                'suggested_actions': [
                    "Increase data collection in sparse areas",
                    "Adjust similarity threshold for edge creation",
                    "Review recent topology changes"
                ]
            })
        
        # 检查节点增长
        node_data = system_analysis['node_count']
        if node_data['trend'] == 'increasing' and node_data['current'] > self.config['node_count_high_threshold']:
            recommendations.append({
                'type': 'scaling',
                'severity': 'low',
                'message': f"Node count is rapidly increasing ({node_data['current']} nodes)",
                'suggested_actions': [
                    "Scale up computational resources",
                    "Implement sharding for network topology",
                    "Optimize spectral analysis algorithms"
                ]
            })
        
        # 检查搜索性能
        search_data = system_analysis['search_performance']
        if search_data['avg_latency_ms'] > self.config['search_latency_threshold_ms']:
            recommendations.append({
                'type': 'search_optimization',
                'severity': 'medium',
                'message': f"Search latency ({search_data['avg_latency_ms']:.2f}ms) exceeds threshold",
                'suggested_actions': [
                    "Optimize caching strategy",
                    "Increase Elasticsearch resources",
                    "Review holographic index structure"
                ]
            })
        
        # 检查空结果率
        empty_results_pct = search_data['search_stats'].get('empty_results_percentage', 0)
        if empty_results_pct > self.config['empty_results_threshold_percent']:
            recommendations.append({
                'type': 'data_coverage',
                'severity': 'high',
                'message': f"High rate of empty search results ({empty_results_pct:.2f}%)",
                'suggested_actions': [
                    "Expand data collection scope",
                    "Implement query expansion techniques",
                    "Adjust similarity thresholds for search"
                ]
            })
        
        # 检查告警数量
        if system_analysis['alerts']['count'] > self.config['alert_count_threshold']:
            recommendations.append({
                'type': 'system_health',
                'severity': 'high',
                'message': f"High number of system alerts ({system_analysis['alerts']['count']})",
                'suggested_actions': [
                    "Review alert logs and address common issues",
                    "Adjust alert thresholds if necessary",
                    "Consider system-wide maintenance"
                ]
            })
        
        return recommendations
    
    def start(self):
        """启动决策反馈系统"""
        self.running = True
        
        # 启动监控线程
        self.topology_monitor_thread = threading.Thread(
            target=self._topology_monitor_worker,
            daemon=True
        )
        self.topology_monitor_thread.start()
        
        self.search_monitor_thread = threading.Thread(
            target=self._search_monitor_worker,
            daemon=True
        )
        self.search_monitor_thread.start()
        
        self.alert_monitor_thread = threading.Thread(
            target=self._alert_monitor_worker,
            daemon=True
        )
        self.alert_monitor_thread.start()
        
        print("Decision feedback system started")
    
    def stop(self):
        """停止决策反馈系统"""
        self.running = False
        
        # 等待线程结束
        if self.topology_monitor_thread:
            self.topology_monitor_thread.join(timeout=10)
        if self.search_monitor_thread:
            self.search_monitor_thread.join(timeout=10)
        if self.alert_monitor_thread:
            self.alert_monitor_thread.join(timeout=10)
        
        # 关闭资源
        self.mongo_client.close()
        self.topology_consumer.close()
        self.search_consumer.close()
        self.alert_consumer.close()
        self.producer.close()
        
        print("Decision feedback system stopped")
    
    def get_recent_feedback(self, limit=10):
        """获取最近的决策反馈"""
        recent_feedback = list(self.feedback_collection.find(
            sort=[('timestamp', -1)]
        ).limit(limit))
        
        # 将MongoDB对象ID转换为字符串
        for feedback in recent_feedback:
            feedback['_id'] = str(feedback['_id'])
        
        return recent_feedback