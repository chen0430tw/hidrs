"""
本地文件搜索插件 - Local File Search Plugin
提供文件索引、搜索、空间分析、重复文件检测等功能
"""
import os
import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict
from datetime import datetime
from plugin_manager import PluginBase

logger = logging.getLogger(__name__)


class FileIndexer:
    """文件索引器 - 跨平台文件系统索引"""

    def __init__(self, root_path: str, exclude_patterns: List[str] = None):
        self.root_path = Path(root_path)
        self.exclude_patterns = exclude_patterns or []
        self.index = {}  # path -> file_info
        self.index_file = Path('data/file_index.json')
        self.index_file.parent.mkdir(parents=True, exist_ok=True)

    def build_index(self, max_files: int = None) -> int:
        """构建文件索引"""
        logger.info(f"开始索引: {self.root_path}")
        start_time = time.time()
        file_count = 0

        for root, dirs, files in os.walk(self.root_path):
            # 排除特定目录
            dirs[:] = [d for d in dirs if not self._should_exclude(os.path.join(root, d))]

            for file in files:
                if max_files and file_count >= max_files:
                    break

                file_path = os.path.join(root, file)

                if self._should_exclude(file_path):
                    continue

                try:
                    stat = os.stat(file_path)
                    self.index[file_path] = {
                        'name': file,
                        'path': file_path,
                        'size': stat.st_size,
                        'created': stat.st_ctime,
                        'modified': stat.st_mtime,
                        'extension': Path(file).suffix.lower(),
                        'directory': root,
                    }
                    file_count += 1

                    if file_count % 10000 == 0:
                        logger.info(f"已索引 {file_count} 个文件...")
                except (PermissionError, FileNotFoundError, OSError):
                    continue

        elapsed = time.time() - start_time
        logger.info(f"索引完成: {file_count} 个文件，耗时 {elapsed:.1f} 秒")

        # 保存索引
        self.save_index()

        return file_count

    def _should_exclude(self, path: str) -> bool:
        """检查路径是否应该被排除"""
        for pattern in self.exclude_patterns:
            if pattern in path:
                return True
        return False

    def save_index(self):
        """保存索引到文件"""
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)
        logger.info(f"索引已保存到 {self.index_file}")

    def load_index(self) -> bool:
        """加载已有索引"""
        if not self.index_file.exists():
            return False

        try:
            with open(self.index_file, 'r', encoding='utf-8') as f:
                self.index = json.load(f)
            logger.info(f"已加载索引: {len(self.index)} 个文件")
            return True
        except Exception as e:
            logger.error(f"加载索引失败: {e}")
            return False

    def get_all_files(self) -> List[Dict]:
        """获取所有已索引文件"""
        return list(self.index.values())

    def get_file_count(self) -> int:
        """获取文件数量"""
        return len(self.index)

    def get_total_size(self) -> int:
        """获取总文件大小"""
        return sum(f['size'] for f in self.index.values())


class SpaceLeakDetector:
    """空间泄漏检测器 - 诊断磁盘空间快速回填问题"""

    def __init__(self, indexer: FileIndexer):
        self.indexer = indexer
        self.baseline = None
        self.baseline_file = Path('data/space_baseline.json')
        self.baseline_file.parent.mkdir(parents=True, exist_ok=True)

    def create_baseline_snapshot(self) -> Dict:
        """创建基线快照（清理后立即执行）"""
        logger.info("创建基线快照...")

        # 按目录统计
        dir_stats = defaultdict(lambda: {'count': 0, 'size': 0})
        for file_info in self.indexer.get_all_files():
            dir_path = file_info['directory']
            dir_stats[dir_path]['count'] += 1
            dir_stats[dir_path]['size'] += file_info['size']

        # 按文件类型统计
        type_stats = defaultdict(lambda: {'count': 0, 'size': 0})
        for file_info in self.indexer.get_all_files():
            ext = file_info['extension'] or 'no_ext'
            type_stats[ext]['count'] += 1
            type_stats[ext]['size'] += file_info['size']

        self.baseline = {
            'timestamp': time.time(),
            'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_size': self.indexer.get_total_size(),
            'file_count': self.indexer.get_file_count(),
            'dir_stats': dict(dir_stats),
            'type_stats': dict(type_stats),
        }

        # 保存基线
        with open(self.baseline_file, 'w', encoding='utf-8') as f:
            json.dump(self.baseline, f, ensure_ascii=False, indent=2)

        logger.info(f"基线快照已创建: {self.baseline['file_count']} 个文件")
        return self.baseline

    def load_baseline(self) -> bool:
        """加载已有基线"""
        if not self.baseline_file.exists():
            return False

        try:
            with open(self.baseline_file, 'r', encoding='utf-8') as f:
                self.baseline = json.load(f)
            logger.info(f"已加载基线快照: {self.baseline['datetime']}")
            return True
        except Exception as e:
            logger.error(f"加载基线失败: {e}")
            return False

    def detect_space_leak(self) -> Dict:
        """检测空间泄漏"""
        if not self.baseline:
            if not self.load_baseline():
                return {
                    'error': '未找到基线快照，请先创建基线',
                    'action': 'create_baseline'
                }

        # 当前状态
        current_dir_stats = defaultdict(lambda: {'count': 0, 'size': 0})
        for file_info in self.indexer.get_all_files():
            dir_path = file_info['directory']
            current_dir_stats[dir_path]['count'] += 1
            current_dir_stats[dir_path]['size'] += file_info['size']

        current_total_size = self.indexer.get_total_size()
        current_file_count = self.indexer.get_file_count()

        # 计算增量
        time_elapsed = (time.time() - self.baseline['timestamp']) / 60  # 分钟
        size_increase = current_total_size - self.baseline['total_size']
        file_increase = current_file_count - self.baseline['file_count']

        # 找出快速增长的目录
        fast_growing_dirs = []
        for dir_path, current_stats in current_dir_stats.items():
            baseline_stats = self.baseline['dir_stats'].get(dir_path, {'count': 0, 'size': 0})
            growth = current_stats['size'] - baseline_stats['size']

            if growth > 10 * 1024 * 1024:  # 增长超过10MB
                fast_growing_dirs.append({
                    'path': dir_path,
                    'growth_mb': growth / (1024 * 1024),
                    'baseline_mb': baseline_stats['size'] / (1024 * 1024),
                    'current_mb': current_stats['size'] / (1024 * 1024),
                    'growth_rate': (growth / baseline_stats['size'] * 100) if baseline_stats['size'] > 0 else float('inf'),
                })

        # 排序
        fast_growing_dirs.sort(key=lambda x: x['growth_mb'], reverse=True)

        # 识别常见罪魁祸首
        culprits = self._identify_culprits(fast_growing_dirs)

        return {
            'summary': {
                'time_elapsed_minutes': time_elapsed,
                'size_increase_mb': size_increase / (1024 * 1024),
                'file_increase': file_increase,
                'growth_rate_mb_per_hour': (size_increase / (1024 * 1024)) / (time_elapsed / 60) if time_elapsed > 0 else 0,
            },
            'fast_growing_dirs': fast_growing_dirs[:20],
            'culprits': culprits,
            'recommendations': self._generate_recommendations(culprits),
        }

    def _identify_culprits(self, growing_dirs: List[Dict]) -> List[Dict]:
        """识别常见的空间占用"罪魁祸首""""
        culprits = []

        # 已知的空间消耗路径模式
        patterns = {
            'temp': {
                'keywords': ['temp', 'tmp', 'cache'],
                'name': '临时文件/缓存',
                'description': '应用程序运行时产生的临时文件',
                'solution': '定期清理临时目录',
            },
            'logs': {
                'keywords': ['logs', 'log'],
                'name': '日志文件',
                'description': '系统和应用程序日志',
                'solution': '配置日志轮转，定期归档旧日志',
            },
            'downloads': {
                'keywords': ['downloads', 'download'],
                'name': '下载文件',
                'description': '浏览器或下载工具下载的文件',
                'solution': '整理下载目录，删除不需要的文件',
            },
            'node_modules': {
                'keywords': ['node_modules'],
                'name': 'Node.js依赖',
                'description': 'JavaScript项目的依赖包',
                'solution': '删除旧项目的node_modules，按需重新安装',
            },
        }

        for dir_info in growing_dirs:
            dir_path_lower = dir_info['path'].lower()

            for culprit_type, pattern_info in patterns.items():
                if any(keyword in dir_path_lower for keyword in pattern_info['keywords']):
                    culprits.append({
                        'type': culprit_type,
                        'name': pattern_info['name'],
                        'path': dir_info['path'],
                        'growth_mb': dir_info['growth_mb'],
                        'description': pattern_info['description'],
                        'solution': pattern_info['solution'],
                    })
                    break

        return culprits

    def _generate_recommendations(self, culprits: List[Dict]) -> List[str]:
        """生成清理建议"""
        recommendations = []

        for culprit in culprits:
            recommendations.append(
                f"⚠️ {culprit['name']} (+{culprit['growth_mb']:.1f} MB): {culprit['solution']}"
            )

        if not recommendations:
            recommendations.append("✅ 未检测到明显的空间泄漏模式")

        return recommendations


class DuplicateFinder:
    """重复文件检测器"""

    def __init__(self, indexer: FileIndexer):
        self.indexer = indexer

    def find_duplicates(self, min_size_mb: float = 1) -> Dict:
        """查找重复文件（基于内容哈希）"""
        logger.info(f"开始查找重复文件（最小 {min_size_mb} MB）...")

        min_size = int(min_size_mb * 1024 * 1024)

        # 第一遍：按大小分组
        size_groups = defaultdict(list)
        for file_info in self.indexer.get_all_files():
            if file_info['size'] >= min_size:
                size_groups[file_info['size']].append(file_info['path'])

        # 第二遍：对相同大小的文件计算哈希
        hash_groups = defaultdict(list)
        processed = 0

        for size, file_paths in size_groups.items():
            if len(file_paths) < 2:
                continue

            for file_path in file_paths:
                try:
                    file_hash = self._compute_file_hash(file_path)
                    hash_groups[file_hash].append(file_path)
                    processed += 1

                    if processed % 100 == 0:
                        logger.info(f"已处理 {processed} 个文件...")
                except Exception as e:
                    logger.warning(f"计算哈希失败 {file_path}: {e}")
                    continue

        # 返回重复文件组
        duplicates = [
            {'files': files, 'size': os.path.getsize(files[0])}
            for files in hash_groups.values()
            if len(files) > 1
        ]

        # 计算浪费的空间
        wasted_space = sum(
            dup['size'] * (len(dup['files']) - 1)
            for dup in duplicates
        )

        logger.info(f"找到 {len(duplicates)} 组重复文件，浪费空间 {wasted_space / (1024 * 1024):.1f} MB")

        return {
            'duplicate_groups': duplicates,
            'total_groups': len(duplicates),
            'total_duplicates': sum(len(dup['files']) - 1 for dup in duplicates),
            'wasted_space_mb': wasted_space / (1024 * 1024),
        }

    def _compute_file_hash(self, file_path: str, algorithm='md5') -> str:
        """计算文件哈希（支持大文件）"""
        hash_func = hashlib.new(algorithm)

        with open(file_path, 'rb') as f:
            # 分块读取，避免内存溢出
            while chunk := f.read(8192):
                hash_func.update(chunk)

        return hash_func.hexdigest()


class LocalFileSearchPlugin(PluginBase):
    """本地文件搜索插件"""

    def __init__(self):
        super().__init__()
        self.name = "LocalFileSearch"
        self.version = "1.0.0"
        self.author = "HIDRS Team"
        self.description = "本地文件索引、搜索、空间分析插件"

        # 核心组件
        self.indexer = None
        self.leak_detector = None
        self.duplicate_finder = None

    def on_load(self):
        """插件加载时调用"""
        logger.info(f"[{self.name}] 正在加载...")

        # 读取配置
        config = self.get_config()
        root_path = config.get('root_path', '/home')
        exclude_patterns = config.get('exclude_patterns', ['node_modules', '.git', '__pycache__'])

        # 初始化组件
        self.indexer = FileIndexer(root_path, exclude_patterns)
        self.leak_detector = SpaceLeakDetector(self.indexer)
        self.duplicate_finder = DuplicateFinder(self.indexer)

        # 尝试加载已有索引
        if not self.indexer.load_index():
            logger.info(f"[{self.name}] 首次运行，需要构建索引")

        logger.info(f"[{self.name}] 加载完成")

    def on_unload(self):
        """插件卸载时调用"""
        logger.info(f"[{self.name}] 正在卸载...")

        # 保存索引
        if self.indexer:
            self.indexer.save_index()

        logger.info(f"[{self.name}] 卸载完成")

    def search_files(self, pattern: str, limit: int = 100) -> List[Dict]:
        """搜索文件（支持正则表达式）"""
        import re

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            return {'error': f'无效的正则表达式: {pattern}'}

        results = []
        for file_info in self.indexer.get_all_files():
            if regex.search(file_info['name']) or regex.search(file_info['path']):
                results.append(file_info)

        # 按修改时间排序
        results.sort(key=lambda x: x.get('modified', 0), reverse=True)

        return results[:limit]

    def rebuild_index(self, max_files: int = None) -> Dict:
        """重建文件索引"""
        try:
            file_count = self.indexer.build_index(max_files)
            return {
                'success': True,
                'file_count': file_count,
                'total_size_mb': self.indexer.get_total_size() / (1024 * 1024),
            }
        except Exception as e:
            logger.error(f"重建索引失败: {e}")
            return {'error': str(e)}

    def create_baseline(self) -> Dict:
        """创建基线快照"""
        try:
            baseline = self.leak_detector.create_baseline_snapshot()
            return {
                'success': True,
                'baseline': baseline,
            }
        except Exception as e:
            logger.error(f"创建基线失败: {e}")
            return {'error': str(e)}

    def diagnose_space_leak(self) -> Dict:
        """诊断空间泄漏"""
        try:
            report = self.leak_detector.detect_space_leak()
            return report
        except Exception as e:
            logger.error(f"诊断失败: {e}")
            return {'error': str(e)}

    def find_duplicates(self, min_size_mb: float = 1) -> Dict:
        """查找重复文件"""
        try:
            result = self.duplicate_finder.find_duplicates(min_size_mb)
            return result
        except Exception as e:
            logger.error(f"查找重复文件失败: {e}")
            return {'error': str(e)}

    def get_disk_stats(self) -> Dict:
        """获取磁盘统计信息"""
        try:
            # 按扩展名统计
            ext_stats = defaultdict(lambda: {'count': 0, 'size': 0})
            for file_info in self.indexer.get_all_files():
                ext = file_info['extension'] or 'no_ext'
                ext_stats[ext]['count'] += 1
                ext_stats[ext]['size'] += file_info['size']

            # 转换为列表并排序
            ext_list = [
                {
                    'extension': ext,
                    'count': stats['count'],
                    'size_mb': stats['size'] / (1024 * 1024),
                }
                for ext, stats in ext_stats.items()
            ]
            ext_list.sort(key=lambda x: x['size_mb'], reverse=True)

            return {
                'total_files': self.indexer.get_file_count(),
                'total_size_mb': self.indexer.get_total_size() / (1024 * 1024),
                'by_extension': ext_list[:20],  # Top 20
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {'error': str(e)}
