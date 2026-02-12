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

使用示例:
    from hidrs.file_analysis import FileAnalyzer, analyze_file

    # 方法1: 使用便捷函数
    result = analyze_file('/path/to/file.pdf')

    # 方法2: 使用类
    analyzer = FileAnalyzer('/path/to/file.pdf')
    result = analyzer.analyze()
    json_str = analyzer.to_json()
"""

from .file_analyzer import FileAnalyzer, analyze_file
from .doc_searcher import DocSearcher, TextDetector, FilenameTranslator

__all__ = ['FileAnalyzer', 'analyze_file', 'DocSearcher', 'TextDetector', 'FilenameTranslator']
__version__ = '1.0.0'
__author__ = 'HIDRS Team (based on Xkeystroke)'
