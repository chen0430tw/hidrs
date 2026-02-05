"""
HIDRS File Analysis Module
基于Xkeystroke项目改编的文件分析模块

主要功能:
- 文件哈希计算
- 熵值分析
- 文件签名验证
- EXIF元数据提取
- 安全模式检测
- ZIP/压缩包分析
- GPS地理定位分析（新增）

使用示例:
    from hidrs.file_analysis import FileAnalyzer, analyze_file
    from hidrs.file_analysis import GeoLocationAnalyzer  # 地理定位

    # 方法1: 文件分析
    result = analyze_file('/path/to/file.pdf')

    # 方法2: 使用类
    analyzer = FileAnalyzer('/path/to/file.pdf')
    result = analyzer.analyze()
    json_str = analyzer.to_json()

    # 方法3: GPS地理定位
    geo = GeoLocationAnalyzer()
    gps_data = geo.extract_gps_from_image('/path/to/photo.jpg')
    geo.analyze_directory('/path/to/photos')
    geo.generate_map('map.html')
"""

from .file_analyzer import FileAnalyzer, analyze_file

# 地理定位分析器（可选导入）
try:
    from .geo_analyzer import GeoLocationAnalyzer
    __all__ = ['FileAnalyzer', 'analyze_file', 'GeoLocationAnalyzer']
except ImportError:
    # PIL或folium未安装时跳过
    __all__ = ['FileAnalyzer', 'analyze_file']

__version__ = '1.1.0'
__author__ = 'HIDRS Team (based on Xkeystroke)'
