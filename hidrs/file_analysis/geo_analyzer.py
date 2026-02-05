#!/usr/bin/env python3
"""
HIDRS地理定位增强模块
基于EXIF GPS数据的地图可视化功能

功能:
- 从图片提取GPS坐标
- OpenStreetMap地图标注
- 批量图片地理聚类
- 时间线轨迹分析
- 地理热力图生成

作者: HIDRS Team
日期: 2026-02-04
"""

import os
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from collections import defaultdict

try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import folium
    from folium.plugins import HeatMap, MarkerCluster
    HAS_FOLIUM = True
except ImportError:
    HAS_FOLIUM = False


class GeoLocationAnalyzer:
    """
    地理定位分析器 - 从图片EXIF提取GPS并可视化
    """

    def __init__(self):
        """初始化地理定位分析器"""
        if not HAS_PIL:
            raise ImportError("需要安装 Pillow: pip install Pillow")

        self.locations = []  # [(lat, lon, metadata), ...]

    def extract_gps_from_image(self, image_path: str) -> Optional[Dict[str, Any]]:
        """
        从图片提取GPS坐标

        Args:
            image_path: 图片路径

        Returns:
            GPS信息字典或None
        """
        try:
            image = Image.open(image_path)
            exif = image.getexif()

            if not exif:
                return None

            # 查找GPS信息
            gps_info = {}
            for tag_id, value in exif.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag == 'GPSInfo':
                    for gps_tag_id in value:
                        gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                        gps_info[gps_tag] = value[gps_tag_id]

            if not gps_info:
                return None

            # 解析GPS坐标
            lat = self._convert_to_degrees(gps_info.get('GPSLatitude'))
            lon = self._convert_to_degrees(gps_info.get('GPSLongitude'))

            if lat is None or lon is None:
                return None

            # 纬度/经度参考（N/S, E/W）
            lat_ref = gps_info.get('GPSLatitudeRef', 'N')
            lon_ref = gps_info.get('GPSLongitudeRef', 'E')

            if lat_ref == 'S':
                lat = -lat
            if lon_ref == 'W':
                lon = -lon

            # 提取其他信息
            result = {
                'latitude': lat,
                'longitude': lon,
                'altitude': gps_info.get('GPSAltitude'),
                'timestamp': gps_info.get('GPSTimeStamp'),
                'date_stamp': gps_info.get('GPSDateStamp'),
                'image_path': image_path,
                'image_name': os.path.basename(image_path)
            }

            # 提取相机信息
            for tag_id, value in exif.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag in ['Make', 'Model', 'DateTime', 'DateTimeOriginal']:
                    result[tag.lower()] = str(value)

            return result

        except Exception as e:
            print(f"提取GPS失败: {image_path} - {str(e)}")
            return None

    def _convert_to_degrees(self, value) -> Optional[float]:
        """
        将GPS坐标从度分秒转换为十进制度数

        Args:
            value: GPS坐标元组 (degrees, minutes, seconds)

        Returns:
            十进制度数
        """
        if value is None:
            return None

        try:
            d, m, s = value
            return float(d) + float(m) / 60.0 + float(s) / 3600.0
        except:
            return None

    def analyze_directory(self, directory: str, recursive: bool = True) -> List[Dict[str, Any]]:
        """
        分析目录下所有图片的GPS信息

        Args:
            directory: 目录路径
            recursive: 是否递归扫描子目录

        Returns:
            GPS信息列表
        """
        results = []

        if recursive:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if file.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff', '.heic')):
                        image_path = os.path.join(root, file)
                        gps_data = self.extract_gps_from_image(image_path)
                        if gps_data:
                            results.append(gps_data)
                            self.locations.append((
                                gps_data['latitude'],
                                gps_data['longitude'],
                                gps_data
                            ))
        else:
            for file in os.listdir(directory):
                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff', '.heic')):
                    image_path = os.path.join(directory, file)
                    gps_data = self.extract_gps_from_image(image_path)
                    if gps_data:
                        results.append(gps_data)
                        self.locations.append((
                            gps_data['latitude'],
                            gps_data['longitude'],
                            gps_data
                        ))

        return results

    def generate_map(self, output_path: str = 'gps_map.html',
                     cluster: bool = True,
                     heatmap: bool = False) -> str:
        """
        生成交互式地图

        Args:
            output_path: 输出HTML文件路径
            cluster: 是否使用标记聚类
            heatmap: 是否显示热力图

        Returns:
            输出文件路径
        """
        if not HAS_FOLIUM:
            raise ImportError("需要安装 folium: pip install folium")

        if not self.locations:
            print("没有GPS数据可显示")
            return None

        # 计算地图中心点
        center_lat = sum(loc[0] for loc in self.locations) / len(self.locations)
        center_lon = sum(loc[1] for loc in self.locations) / len(self.locations)

        # 创建地图
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=12,
            tiles='OpenStreetMap'
        )

        # 添加标记
        if cluster:
            marker_cluster = MarkerCluster().add_to(m)
            for lat, lon, metadata in self.locations:
                popup_text = f"""
                <b>{metadata['image_name']}</b><br>
                坐标: {lat:.6f}, {lon:.6f}<br>
                相机: {metadata.get('make', 'N/A')} {metadata.get('model', 'N/A')}<br>
                时间: {metadata.get('datetime', 'N/A')}
                """
                folium.Marker(
                    location=[lat, lon],
                    popup=folium.Popup(popup_text, max_width=300),
                    icon=folium.Icon(color='red', icon='camera', prefix='fa')
                ).add_to(marker_cluster)
        else:
            for lat, lon, metadata in self.locations:
                popup_text = f"""
                <b>{metadata['image_name']}</b><br>
                坐标: {lat:.6f}, {lon:.6f}<br>
                相机: {metadata.get('make', 'N/A')} {metadata.get('model', 'N/A')}<br>
                时间: {metadata.get('datetime', 'N/A')}
                """
                folium.Marker(
                    location=[lat, lon],
                    popup=folium.Popup(popup_text, max_width=300),
                    icon=folium.Icon(color='red', icon='camera', prefix='fa')
                ).add_to(m)

        # 添加热力图
        if heatmap and len(self.locations) > 2:
            heat_data = [[loc[0], loc[1]] for loc in self.locations]
            HeatMap(heat_data, radius=15, blur=25, max_zoom=13).add_to(m)

        # 保存地图
        m.save(output_path)
        print(f"✅ 地图已保存: {output_path}")
        print(f"   包含 {len(self.locations)} 个GPS位置")

        return output_path

    def cluster_by_location(self, radius_km: float = 1.0) -> Dict[str, List[Dict[str, Any]]]:
        """
        按地理位置聚类

        Args:
            radius_km: 聚类半径（公里）

        Returns:
            聚类结果字典
        """
        from math import radians, cos, sin, asin, sqrt

        def haversine(lon1, lat1, lon2, lat2):
            """计算两点间距离（公里）"""
            lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * asin(sqrt(a))
            return 6371 * c  # 地球半径

        clusters = defaultdict(list)
        processed = set()

        for i, (lat1, lon1, metadata1) in enumerate(self.locations):
            if i in processed:
                continue

            cluster_key = f"cluster_{len(clusters)}"
            clusters[cluster_key].append(metadata1)
            processed.add(i)

            for j, (lat2, lon2, metadata2) in enumerate(self.locations):
                if j in processed or i == j:
                    continue

                distance = haversine(lon1, lat1, lon2, lat2)
                if distance <= radius_km:
                    clusters[cluster_key].append(metadata2)
                    processed.add(j)

        return dict(clusters)

    def generate_timeline(self) -> List[Dict[str, Any]]:
        """
        生成时间线（按拍摄时间排序）

        Returns:
            按时间排序的GPS数据
        """
        timeline = []

        for lat, lon, metadata in self.locations:
            datetime_str = metadata.get('datetimeoriginal') or metadata.get('datetime')
            if datetime_str:
                try:
                    dt = datetime.strptime(datetime_str, '%Y:%m:%d %H:%M:%S')
                    metadata['datetime_obj'] = dt
                    timeline.append(metadata)
                except:
                    pass

        timeline.sort(key=lambda x: x.get('datetime_obj', datetime.min))
        return timeline

    def export_json(self, output_path: str = 'gps_data.json'):
        """
        导出GPS数据为JSON

        Args:
            output_path: 输出文件路径
        """
        data = {
            'total_locations': len(self.locations),
            'generated_at': datetime.now().isoformat(),
            'locations': [
                {
                    'latitude': loc[0],
                    'longitude': loc[1],
                    'metadata': loc[2]
                }
                for loc in self.locations
            ]
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        print(f"✅ JSON已导出: {output_path}")

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        if not self.locations:
            return {'total': 0}

        lats = [loc[0] for loc in self.locations]
        lons = [loc[1] for loc in self.locations]

        # 相机统计
        cameras = defaultdict(int)
        for _, _, metadata in self.locations:
            camera = f"{metadata.get('make', 'Unknown')} {metadata.get('model', '')}"
            cameras[camera] += 1

        return {
            'total_locations': len(self.locations),
            'latitude_range': [min(lats), max(lats)],
            'longitude_range': [min(lons), max(lons)],
            'center': [sum(lats)/len(lats), sum(lons)/len(lons)],
            'camera_distribution': dict(cameras),
            'unique_cameras': len(cameras)
        }


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("用法: python geo_analyzer.py <图片目录>")
        sys.exit(1)

    directory = sys.argv[1]

    if not os.path.exists(directory):
        print(f"错误: 目录不存在: {directory}")
        sys.exit(1)

    print(f"正在分析目录: {directory}\n")

    analyzer = GeoLocationAnalyzer()
    results = analyzer.analyze_directory(directory, recursive=True)

    if not results:
        print("❌ 未找到包含GPS信息的图片")
        sys.exit(0)

    print(f"✅ 找到 {len(results)} 张包含GPS信息的图片\n")

    # 统计信息
    stats = analyzer.get_statistics()
    print("=" * 80)
    print("统计信息:")
    print(f"  • 总位置数: {stats['total_locations']}")
    print(f"  • 纬度范围: {stats['latitude_range'][0]:.6f} ~ {stats['latitude_range'][1]:.6f}")
    print(f"  • 经度范围: {stats['longitude_range'][0]:.6f} ~ {stats['longitude_range'][1]:.6f}")
    print(f"  • 中心点: {stats['center'][0]:.6f}, {stats['center'][1]:.6f}")
    print(f"  • 不同相机数: {stats['unique_cameras']}")
    print("\n相机分布:")
    for camera, count in stats['camera_distribution'].items():
        print(f"    - {camera}: {count}张")

    # 地理聚类
    print("\n正在进行地理聚类（半径1km）...")
    clusters = analyzer.cluster_by_location(radius_km=1.0)
    print(f"✅ 发现 {len(clusters)} 个地理聚类:")
    for cluster_name, items in clusters.items():
        print(f"  • {cluster_name}: {len(items)}张图片")

    # 时间线
    print("\n正在生成时间线...")
    timeline = analyzer.generate_timeline()
    if timeline:
        print(f"✅ 时间线包含 {len(timeline)} 个时间点")
        print("  最早: ", timeline[0].get('datetime'))
        print("  最晚: ", timeline[-1].get('datetime'))

    # 生成地图
    print("\n正在生成交互式地图...")
    map_file = analyzer.generate_map(
        output_path='gps_map.html',
        cluster=True,
        heatmap=True
    )

    # 导出JSON
    print("\n正在导出JSON数据...")
    analyzer.export_json('gps_data.json')

    print("\n" + "=" * 80)
    print("✅ 分析完成！")
    print(f"   地图文件: {map_file}")
    print(f"   JSON文件: gps_data.json")
    print(f"\n   在浏览器中打开 {map_file} 查看地图")
