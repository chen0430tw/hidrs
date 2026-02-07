"""
人员躲避系统插件 - Person Avoidance System
基于活动模式分析和路线规划，提供安全路线建议

⚠️ 严格合规声明 ⚠️

本插件仅用于合法授权场景：
1. 家长监护未成年子女（需子女知情）
2. 企业管理公司资产（需员工同意）
3. 紧急救援定位（生命安全需要）
4. 执法机关依法使用（需法律授权）
5. 学术研究和技术演示（虚拟数据）

未经授权追踪他人是严重违法行为！
违反者承担一切法律后果！
"""
import logging
import time
import math
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from plugin_manager import PluginBase

logger = logging.getLogger(__name__)


class ActivityPatternAnalyzer:
    """活动模式分析器"""

    def __init__(self):
        self.location_history = []

    def add_location(self, lat: float, lon: float, timestamp: float):
        """添加位置记录"""
        dt = datetime.fromtimestamp(timestamp)
        self.location_history.append({
            'lat': lat,
            'lon': lon,
            'timestamp': timestamp,
            'hour': dt.hour,
            'weekday': dt.weekday()
        })

    def analyze_hotspots(self, eps: float = 0.01, min_samples: int = 5) -> List[Dict]:
        """识别常去地点（DBSCAN聚类）"""
        if len(self.location_history) < min_samples:
            logger.warning(f"历史数据不足: {len(self.location_history)} < {min_samples}")
            return []

        try:
            import numpy as np
            from sklearn.cluster import DBSCAN

            # 提取坐标矩阵
            coords = np.array([[loc['lat'], loc['lon']]
                              for loc in self.location_history])

            # DBSCAN聚类
            clustering = DBSCAN(eps=eps, min_samples=min_samples, metric='euclidean').fit(coords)

            # 统计每个聚类
            hotspots = []
            unique_labels = set(clustering.labels_)

            for label in unique_labels:
                if label == -1:  # 噪音点
                    continue

                # 提取该聚类的所有点
                cluster_mask = clustering.labels_ == label
                cluster_points = coords[cluster_mask]
                center = cluster_points.mean(axis=0)  # 中心点

                # 统计访问信息
                visits = [loc for i, loc in enumerate(self.location_history)
                         if clustering.labels_[i] == label]

                # 计算半径（95%包含）
                distances = [self._haversine_distance(
                    center[0], center[1], point[0], point[1]
                ) for point in cluster_points]
                radius = np.percentile(distances, 95) if len(distances) > 0 else 0.5

                hotspots.append({
                    'center': {'lat': float(center[0]), 'lon': float(center[1])},
                    'visit_count': len(visits),
                    'radius': float(radius),  # 公里
                    'time_distribution': self._analyze_time_pattern(visits),
                    'danger_level': min(10, len(visits) / 10)  # 1-10级
                })

            # 按访问频率排序
            hotspots.sort(key=lambda x: x['visit_count'], reverse=True)
            logger.info(f"识别到 {len(hotspots)} 个常去地点")
            return hotspots

        except ImportError:
            logger.error("scikit-learn 未安装，无法进行聚类分析")
            return []
        except Exception as e:
            logger.error(f"聚类分析失败: {e}")
            return []

    def _analyze_time_pattern(self, visits: List[Dict]) -> Dict:
        """分析时间模式"""
        hour_counts = defaultdict(int)
        weekday_counts = defaultdict(int)

        for visit in visits:
            hour_counts[visit['hour']] += 1
            weekday_counts[visit['weekday']] += 1

        return {
            'peak_hours': sorted(hour_counts.items(),
                               key=lambda x: x[1], reverse=True)[:3],
            'peak_weekdays': sorted(weekday_counts.items(),
                                   key=lambda x: x[1], reverse=True)[:2]
        }

    def predict_location(self, target_timestamp: float) -> Optional[Dict]:
        """预测指定时间的可能位置"""
        if not self.location_history:
            return None

        target_dt = datetime.fromtimestamp(target_timestamp)
        target_hour = target_dt.hour
        target_weekday = target_dt.weekday()

        # 找出相似时间段的历史记录
        similar_records = [
            loc for loc in self.location_history
            if loc['hour'] == target_hour and loc['weekday'] == target_weekday
        ]

        if not similar_records:
            # 放宽条件（只匹配小时）
            similar_records = [
                loc for loc in self.location_history
                if abs(loc['hour'] - target_hour) <= 1
            ]

        if not similar_records:
            return None

        # 找出最常出现的位置
        locations = [(loc['lat'], loc['lon']) for loc in similar_records]
        most_common = Counter(locations).most_common(1)[0]

        return {
            'lat': most_common[0][0],
            'lon': most_common[0][1],
            'confidence': most_common[1] / len(similar_records),
            'sample_size': len(similar_records)
        }

    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """计算地球表面距离（公里）"""
        R = 6371  # 地球半径（公里）

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = (math.sin(delta_lat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(delta_lon / 2) ** 2)
        c = 2 * math.asin(math.sqrt(a))

        return R * c


class AvoidanceRoutePlanner:
    """躲避路线规划器"""

    def __init__(self, hotspots: List[Dict]):
        self.hotspots = hotspots
        self.danger_zones = self._create_danger_zones()

    def _create_danger_zones(self) -> List[Dict]:
        """创建危险区域"""
        zones = []
        for i, hotspot in enumerate(self.hotspots):
            zones.append({
                'id': f'zone_{i}',
                'center': hotspot['center'],
                'radius': hotspot['radius'] + 0.5,  # +500米缓冲
                'danger_level': hotspot['danger_level'],
                'visit_count': hotspot['visit_count']
            })
        return zones

    def calculate_route_cost(self, point: Dict, avoid_hotspots: bool = True) -> float:
        """计算点的危险代价"""
        if not avoid_hotspots or not self.danger_zones:
            return 0

        danger_penalty = 0
        for zone in self.danger_zones:
            dist_to_zone = self._haversine_distance(
                point['lat'], point['lon'],
                zone['center']['lat'], zone['center']['lon']
            )

            if dist_to_zone < zone['radius']:
                # 在危险区域内，增加惩罚
                danger_penalty += zone['danger_level'] * 10

        return danger_penalty

    def plan_safe_route(self, start: Dict, destination: Dict) -> Dict:
        """规划躲避路线"""
        routes = []

        # 1. 直线路线
        direct_distance = self._haversine_distance(
            start['lat'], start['lon'],
            destination['lat'], destination['lon']
        )
        direct_penalty = (
            self.calculate_route_cost(start) +
            self.calculate_route_cost(destination)
        )
        routes.append({
            'name': '直线路线',
            'waypoints': [start, destination],
            'distance': direct_distance,
            'cost': direct_distance + direct_penalty,
            'danger_penalty': direct_penalty
        })

        # 2. 绕行路线（8个方向）
        for angle in range(0, 360, 45):
            waypoint = self._generate_waypoint(start, destination, angle, ratio=0.5)
            detour_distance = (
                self._haversine_distance(start['lat'], start['lon'],
                                        waypoint['lat'], waypoint['lon']) +
                self._haversine_distance(waypoint['lat'], waypoint['lon'],
                                        destination['lat'], destination['lon'])
            )
            detour_penalty = (
                self.calculate_route_cost(start) +
                self.calculate_route_cost(waypoint) +
                self.calculate_route_cost(destination)
            )
            routes.append({
                'name': f'绕行路线{angle}°',
                'waypoints': [start, waypoint, destination],
                'distance': detour_distance,
                'cost': detour_distance + detour_penalty,
                'danger_penalty': detour_penalty
            })

        # 3. 选择代价最小的路线
        best_route = min(routes, key=lambda x: x['cost'])
        crossed_zones = self._get_crossed_zones(best_route['waypoints'])

        return {
            'route_name': best_route['name'],
            'waypoints': best_route['waypoints'],
            'distance_km': round(best_route['distance'], 2),
            'danger_penalty': round(best_route['danger_penalty'], 2),
            'danger_zones_crossed': crossed_zones,
            'safety_score': self._calculate_safety_score(best_route)
        }

    def _generate_waypoint(self, start: Dict, end: Dict, angle: float, ratio: float = 0.5) -> Dict:
        """生成中间点（在直线外侧）"""
        # 中点
        mid_lat = start['lat'] + (end['lat'] - start['lat']) * ratio
        mid_lon = start['lon'] + (end['lon'] - start['lon']) * ratio

        # 垂直偏移
        offset = 0.05  # 约5公里
        angle_rad = math.radians(angle)

        waypoint_lat = mid_lat + offset * math.cos(angle_rad)
        waypoint_lon = mid_lon + offset * math.sin(angle_rad)

        return {'lat': waypoint_lat, 'lon': waypoint_lon}

    def _get_crossed_zones(self, waypoints: List[Dict]) -> List[str]:
        """获取经过的危险区域"""
        crossed = []
        for i, zone in enumerate(self.danger_zones):
            for waypoint in waypoints:
                dist = self._haversine_distance(
                    waypoint['lat'], waypoint['lon'],
                    zone['center']['lat'], zone['center']['lon']
                )
                if dist < zone['radius']:
                    crossed.append(f"区域{i+1}(危险等级{zone['danger_level']:.1f})")
                    break
        return crossed

    def _calculate_safety_score(self, route: Dict) -> int:
        """计算安全评分（0-100）"""
        max_penalty = 100  # 最大惩罚
        penalty_ratio = min(1.0, route['danger_penalty'] / max_penalty)
        score = int(100 * (1 - penalty_ratio))
        return max(0, min(100, score))

    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """计算距离（公里）"""
        R = 6371
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = (math.sin(delta_lat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(delta_lon / 2) ** 2)
        c = 2 * math.asin(math.sqrt(a))
        return R * c


class PersonAvoidancePlugin(PluginBase):
    """人员躲避系统插件"""

    # 合规性警告
    COMPLIANCE_WARNING = """
    ⚠️⚠️⚠️ 人员躲避系统严格合规声明 ⚠️⚠️⚠️

    本插件仅用于合法授权场景：
    1. 家长监护未成年子女（需子女知情）
    2. 企业管理公司资产（需员工同意）
    3. 紧急救援定位（生命安全需要）
    4. 执法机关依法使用（需法律授权）
    5. 学术研究和技术演示（虚拟数据）

    未经授权追踪他人是严重违法行为！
    违反者承担一切法律后果！
    """

    def __init__(self):
        super().__init__()
        self.name = "PersonAvoidance"
        self.version = "1.0.0"
        self.author = "HIDRS Team"
        self.description = "人员躲避系统：活动模式分析 + 安全路线规划"

        # 核心组件
        self.analyzer = ActivityPatternAnalyzer()
        self.planner = None

        # 模拟数据
        self.mock_targets = {}

    def on_load(self):
        """插件加载时调用"""
        logger.info(f"[{self.name}] 正在加载...")

        # 显示合规性警告
        logger.warning(self.COMPLIANCE_WARNING)

        # 读取配置
        config = self.get_config()

        # 强制要求用户明确同意
        if not config.get('user_consent', False):
            raise ValueError(
                f"[{self.name}] 需要用户明确同意合规条款。\n"
                f"请阅读合规声明后，在配置中设置 'user_consent: true'"
            )

        # 如果没有真实数据，使用演示数据
        if not self.analyzer.location_history:
            self._generate_mock_data()
            logger.warning(
                f"[{self.name}] 使用演示数据 "
                f"（调用 analyzer.add_location_record() 导入真实位置数据）"
            )

        logger.info(f"[{self.name}] 加载完成")

    def on_unload(self):
        """插件卸载时调用"""
        logger.info(f"[{self.name}] 正在卸载...")

    def _generate_mock_data(self):
        """生成模拟追踪数据（用于演示）"""
        # 模拟目标：某人30天的位置记录
        target_id = 'TARGET_001'
        base_time = time.time() - 30 * 24 * 3600  # 30天前

        # 模拟3个常去地点
        locations = [
            {'lat': 39.9042, 'lon': 116.4074, 'weight': 0.5},  # 工作地点（50%）
            {'lat': 39.9163, 'lon': 116.3972, 'weight': 0.3},  # 家（30%）
            {'lat': 39.9289, 'lon': 116.3883, 'weight': 0.2},  # 其他（20%）
        ]

        # 生成720个位置点（30天 × 24小时）
        import random
        for day in range(30):
            for hour in range(24):
                timestamp = base_time + day * 24 * 3600 + hour * 3600

                # 根据时间选择位置
                if 9 <= hour <= 18:  # 工作时间
                    loc = locations[0]
                elif 19 <= hour <= 23 or 0 <= hour <= 7:  # 晚上和早上
                    loc = locations[1]
                else:
                    loc = random.choice(locations)

                # 添加随机偏移
                lat = loc['lat'] + random.uniform(-0.01, 0.01)
                lon = loc['lon'] + random.uniform(-0.01, 0.01)

                self.analyzer.add_location(lat, lon, timestamp)

        logger.info(f"生成了 {len(self.analyzer.location_history)} 条模拟位置记录")

    def analyze_activity_pattern(self, eps: float = 0.01, min_samples: int = 5) -> Dict:
        """分析活动模式"""
        try:
            hotspots = self.analyzer.analyze_hotspots(eps=eps, min_samples=min_samples)

            # 更新路线规划器
            if hotspots:
                self.planner = AvoidanceRoutePlanner(hotspots)

            return {
                'success': True,
                'hotspots': hotspots,
                'total_records': len(self.analyzer.location_history)
            }
        except Exception as e:
            logger.error(f"活动模式分析失败: {e}")
            return {'error': str(e)}

    def predict_future_location(self, hours_ahead: int = 1) -> Dict:
        """预测未来位置"""
        try:
            target_timestamp = time.time() + hours_ahead * 3600
            prediction = self.analyzer.predict_location(target_timestamp)

            if prediction:
                return {
                    'success': True,
                    'prediction': prediction,
                    'target_time': datetime.fromtimestamp(target_timestamp).isoformat()
                }
            else:
                return {
                    'success': False,
                    'message': '历史数据不足，无法预测'
                }
        except Exception as e:
            logger.error(f"位置预测失败: {e}")
            return {'error': str(e)}

    def plan_safe_route(self, start_lat: float, start_lon: float,
                       end_lat: float, end_lon: float) -> Dict:
        """规划安全路线"""
        try:
            if not self.planner:
                # 如果没有分析过，先分析
                self.analyze_activity_pattern()

            if not self.planner:
                return {'error': '无法创建路线规划器，请先分析活动模式'}

            start = {'lat': start_lat, 'lon': start_lon}
            end = {'lat': end_lat, 'lon': end_lon}

            result = self.planner.plan_safe_route(start, end)

            return {
                'success': True,
                'route': result
            }
        except Exception as e:
            logger.error(f"路线规划失败: {e}")
            return {'error': str(e)}

    def get_danger_zones(self) -> Dict:
        """获取危险区域列表"""
        if not self.planner:
            return {'error': '未进行活动模式分析'}

        return {
            'success': True,
            'zones': self.planner.danger_zones,
            'count': len(self.planner.danger_zones)
        }

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'total_records': len(self.analyzer.location_history),
            'analyzer_available': self.analyzer is not None,
            'planner_available': self.planner is not None,
            'danger_zones': len(self.planner.danger_zones) if self.planner else 0
        }
