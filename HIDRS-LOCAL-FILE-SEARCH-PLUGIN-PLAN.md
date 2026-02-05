# HIDRS本地文件搜索插件规划

## 1. 概述

### 1.1 目标

设计一个本地文件搜索与分析插件，用于：
1. **快速文件索引与搜索** - 秒级响应，支持海量文件
2. **磁盘空间"热胀冷缩"分析** - 追踪清理后空间快速回填的原因
3. **文件关联性分析** - 结合HIDRS拉普拉斯谱分析，发现文件之间的隐藏关联
4. **重复文件检测** - 识别占用大量空间的重复内容
5. **时间线追踪** - 监控文件增长趋势，预警异常空间占用

### 1.2 应用场景

- **问题诊断**: 刚清出7GB容量，马上被回填5GB - 找出罪魁祸首
- **空间优化**: 识别可安全删除的临时文件、缓存、重复文件
- **取证分析**: 发现隐藏的大文件、可疑的快速增长文件
- **数据恢复**: 结合文件签名识别，恢复误删文件

---

## 2. 现有工具调研（2026）

### 2.1 Everything - 极速文件名搜索

**核心技术**:
- 直接读取NTFS MFT（主文件表）
- 使用USN变更日志实时监控文件变化
- 秒级索引整个系统，支持数十万文件

**功能特性**:
- ✅ 布尔运算符 (AND, OR, NOT)
- ✅ 正则表达式支持
- ✅ 实时更新（无需重新扫描）
- ✅ 极低资源占用（数据库仅数MB）
- ✅ v1.5+ 支持内容索引（可选）

**局限性**:
- ❌ 仅支持Windows NTFS
- ❌ 不支持磁盘空间可视化
- ❌ 无文件关联性分析

**参考**: [Everything - voidtools](https://www.voidtools.com/)

### 2.2 R-Studio - 专业数据恢复

**核心技术**:
- 文件签名识别（支持自定义签名）
- 十六进制模式搜索
- 深度扫描损坏的文件系统

**功能特性**:
- ✅ 原始文件搜索（按文件类型）
- ✅ 正则表达式 + 十六进制模式
- ✅ 自定义文件类型定义
- ✅ 损坏文件系统恢复

**局限性**:
- ❌ 专注数据恢复，非日常搜索工具
- ❌ 商业软件（$49.99 - $999）
- ❌ 无空间分析功能

**参考**: [R-Studio Data Recovery Software](https://www.r-studio.com/)

### 2.3 磁盘空间分析工具

#### WizTree - 最快的空间分析器

**核心技术**:
- 直接读取MFT（与Everything同原理）
- 数秒内扫描TB级硬盘

**功能特性**:
- ✅ 树形图（Treemap）可视化
- ✅ 按文件类型分组
- ✅ 导出CSV报告
- ✅ 免费个人使用

**参考**: [WizTree - The Fastest Disk Space Analyzer](https://diskanalyzer.com/)

#### TreeSize - 功能丰富的企业级工具

**功能特性**:
- ✅ 多种可视化方式（树状、图表、Treemap）
- ✅ 自定义文件搜索
- ✅ 详细报告导出
- ✅ 文件年龄分析（File Age View）
- ✅ 重复文件查找

**版本**: Free / Personal / Professional

**参考**: [TreeSize – Official Free Download](https://www.jam-software.com/treesize)

#### WinDirStat - 开源经典

**功能特性**:
- ✅ 经典的Treemap可视化
- ✅ 完全开源免费
- ✅ 扩展名统计
- ✅ 文件类型清理列表

**局限性**:
- ❌ 扫描速度较慢（不使用MFT直接读取）

**参考**: [WinDirStat - Windows Directory Statistics](https://windirstat.net/)

---

## 3. HIDRS本地文件搜索插件设计

### 3.1 架构设计

```
LocalFileSearchPlugin
├── 索引引擎 (IndexEngine)
│   ├── MFTReader (Windows NTFS直接读取)
│   ├── FileSystemWatcher (Linux/Mac/其他FS)
│   └── IncrementalIndexer (增量更新)
│
├── 搜索引擎 (SearchEngine)
│   ├── NameSearch (文件名正则搜索)
│   ├── ContentSearch (内容全文索引)
│   └── SignatureSearch (文件签名识别)
│
├── 空间分析器 (SpaceAnalyzer)
│   ├── TreemapGenerator (树形图生成)
│   ├── FileTypeStatistics (文件类型统计)
│   └── TimelineTracker (时间线追踪)
│
├── 关联分析器 (RelationAnalyzer)
│   ├── LaplacianMapper (文件拉普拉斯向量)
│   ├── DuplicateFinder (重复文件检测)
│   └── ClusterAnalyzer (文件聚类分析)
│
└── 诊断引擎 (DiagnosticEngine)
    ├── SpaceLeakDetector (空间泄漏检测)
    ├── GrowthMonitor (增长监控)
    └── AnomalyDetector (异常检测)
```

### 3.2 核心功能模块

#### 3.2.1 索引引擎 (IndexEngine)

**MFT Reader (Windows)**:
```python
import win32file
import struct

class MFTReader:
    """直接读取NTFS MFT，类似Everything的实现"""

    def __init__(self, drive_letter: str = 'C'):
        self.drive = f"\\\\.\\{drive_letter}:"
        self.mft_records = []

    def read_mft(self) -> List[Dict[str, Any]]:
        """读取MFT所有文件记录"""
        handle = win32file.CreateFile(
            self.drive,
            win32file.GENERIC_READ,
            win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
            None,
            win32file.OPEN_EXISTING,
            0,
            None
        )

        # 读取MFT起始位置
        mft_start = self._get_mft_start(handle)

        # 按1024字节块读取MFT记录
        records = []
        offset = mft_start
        while True:
            try:
                win32file.SetFilePointer(handle, offset, win32file.FILE_BEGIN)
                data = win32file.ReadFile(handle, 1024)[1]

                if data[:4] == b'FILE':  # MFT记录签名
                    record = self._parse_mft_record(data)
                    if record:
                        records.append(record)

                offset += 1024
            except:
                break

        win32file.CloseHandle(handle)
        return records

    def _parse_mft_record(self, data: bytes) -> Optional[Dict]:
        """解析单个MFT记录"""
        # FILE记录格式（简化版）
        # 0x00-0x03: "FILE" 签名
        # 0x16-0x17: 属性偏移
        # 0x20-0x27: 文件引用号

        try:
            file_reference = struct.unpack('<Q', data[0x20:0x28])[0]
            attr_offset = struct.unpack('<H', data[0x14:0x16])[0]

            # 解析属性（$FILE_NAME, $DATA等）
            attributes = self._parse_attributes(data[attr_offset:])

            return {
                'file_reference': file_reference,
                'name': attributes.get('filename'),
                'size': attributes.get('data_size', 0),
                'created': attributes.get('created'),
                'modified': attributes.get('modified'),
                'path': attributes.get('path'),
            }
        except:
            return None

    def monitor_changes(self, callback):
        """监控USN变更日志（实时更新）"""
        # 使用DeviceIoControl读取USN日志
        pass
```

**跨平台文件监控**:
```python
import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class FileChangeHandler(FileSystemEventHandler):
    """跨平台文件系统监控（Linux/Mac/Windows非NTFS）"""

    def __init__(self, index_manager):
        self.index = index_manager

    def on_created(self, event):
        if not event.is_directory:
            self.index.add_file(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self.index.remove_file(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self.index.update_file(event.src_path)

    def on_moved(self, event):
        self.index.move_file(event.src_path, event.dest_path)
```

#### 3.2.2 空间分析器 (SpaceAnalyzer)

**磁盘空间"热胀冷缩"诊断**:
```python
class SpaceLeakDetector:
    """空间泄漏检测器 - 找出"清理7GB，回填5GB"的原因"""

    def __init__(self, index_manager):
        self.index = index_manager
        self.baseline = None  # 清理后的基线快照

    def create_baseline_snapshot(self):
        """创建基线快照（清理后立即执行）"""
        self.baseline = {
            'timestamp': time.time(),
            'total_size': self._get_total_size(),
            'file_count': self.index.get_file_count(),
            'top_dirs': self._get_top_directories(100),
            'files_by_type': self._group_by_type(),
        }

    def detect_space_leak(self, interval_minutes: int = 60) -> Dict:
        """检测空间泄漏（清理后N分钟对比）"""
        if not self.baseline:
            raise ValueError("请先创建基线快照")

        current = {
            'timestamp': time.time(),
            'total_size': self._get_total_size(),
            'file_count': self.index.get_file_count(),
            'top_dirs': self._get_top_directories(100),
            'files_by_type': self._group_by_type(),
        }

        # 计算增量
        delta = {
            'size_increase': current['total_size'] - self.baseline['total_size'],
            'file_increase': current['file_count'] - self.baseline['file_count'],
            'time_elapsed': (current['timestamp'] - self.baseline['timestamp']) / 60,
            'growth_rate_mb_per_hour': 0,
        }

        delta['growth_rate_mb_per_hour'] = (
            delta['size_increase'] / (1024 * 1024) / (delta['time_elapsed'] / 60)
        )

        # 找出快速增长的目录
        fast_growing_dirs = []
        for dir_path in current['top_dirs']:
            baseline_size = self.baseline['top_dirs'].get(dir_path, 0)
            current_size = current['top_dirs'][dir_path]
            growth = current_size - baseline_size

            if growth > 100 * 1024 * 1024:  # 增长超过100MB
                fast_growing_dirs.append({
                    'path': dir_path,
                    'growth_mb': growth / (1024 * 1024),
                    'baseline_mb': baseline_size / (1024 * 1024),
                    'current_mb': current_size / (1024 * 1024),
                    'growth_rate': (growth / baseline_size * 100) if baseline_size > 0 else float('inf'),
                })

        # 按增长量排序
        fast_growing_dirs.sort(key=lambda x: x['growth_mb'], reverse=True)

        # 识别常见"罪魁祸首"
        culprits = self._identify_culprits(fast_growing_dirs)

        return {
            'summary': delta,
            'fast_growing_dirs': fast_growing_dirs[:20],  # Top 20
            'culprits': culprits,
            'recommendations': self._generate_recommendations(culprits),
        }

    def _identify_culprits(self, growing_dirs: List[Dict]) -> List[Dict]:
        """识别常见的空间占用"罪魁祸首""""
        culprits = []

        # 已知的空间消耗路径模式
        patterns = {
            'windows_update': {
                'paths': [
                    r'C:\\Windows\\SoftwareDistribution',
                    r'C:\\Windows\\WinSxS',
                ],
                'name': 'Windows更新缓存',
                'description': 'Windows Update下载的更新包',
                'solution': '运行"磁盘清理" > "清理系统文件" > 勾选"Windows更新清理"',
            },
            'system_restore': {
                'paths': [
                    r'C:\\System Volume Information',
                ],
                'name': '系统还原点/卷影副本',
                'description': 'Windows自动创建的还原点',
                'solution': '控制面板 > 系统 > 系统保护 > 配置 > 减少磁盘使用量',
            },
            'temp_files': {
                'paths': [
                    r'C:\\Windows\\Temp',
                    r'C:\\Users\\.*\\AppData\\Local\\Temp',
                ],
                'name': '临时文件',
                'description': '程序运行时产生的临时文件',
                'solution': '运行"磁盘清理" > 勾选"临时文件"',
            },
            'browser_cache': {
                'paths': [
                    r'C:\\Users\\.*\\AppData\\Local\\Google\\Chrome\\User Data',
                    r'C:\\Users\\.*\\AppData\\Local\\Microsoft\\Edge',
                    r'C:\\Users\\.*\\AppData\\Roaming\\Mozilla\\Firefox',
                ],
                'name': '浏览器缓存',
                'description': '网页缓存、下载文件、扩展数据',
                'solution': '浏览器设置 > 清除浏览数据 > 缓存图像和文件',
            },
            'pagefile': {
                'paths': [
                    r'C:\\pagefile.sys',
                    r'C:\\swapfile.sys',
                    r'C:\\hiberfil.sys',
                ],
                'name': '虚拟内存/休眠文件',
                'description': '系统管理的虚拟内存和休眠文件',
                'solution': '高级系统设置 > 性能 > 虚拟内存 > 自定义大小或禁用休眠',
            },
            'recycle_bin': {
                'paths': [
                    r'C:\\$Recycle.Bin',
                ],
                'name': '回收站',
                'description': '已删除但未清空的文件',
                'solution': '右键回收站 > 清空回收站',
            },
            'logs': {
                'paths': [
                    r'C:\\Windows\\Logs',
                    r'C:\\ProgramData\\.*\\logs',
                ],
                'name': '日志文件',
                'description': '系统和应用程序日志',
                'solution': '事件查看器 > 右键日志 > 清除日志',
            },
        }

        import re
        for dir_info in growing_dirs:
            for culprit_type, pattern_info in patterns.items():
                for path_pattern in pattern_info['paths']:
                    if re.match(path_pattern, dir_info['path'], re.IGNORECASE):
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

        return recommendations
```

**Treemap可视化（类似WizTree）**:
```python
import squarify  # pip install squarify
import matplotlib.pyplot as plt

class TreemapGenerator:
    """树形图生成器 - 可视化磁盘空间占用"""

    def generate_treemap(self, file_tree: Dict, max_depth: int = 3):
        """
        生成Treemap

        file_tree 格式:
        {
            'C:\\': {
                'size': 500GB,
                'children': {
                    'Windows': {'size': 50GB, 'children': {...}},
                    'Users': {'size': 200GB, 'children': {...}},
                    ...
                }
            }
        }
        """
        # 扁平化文件树（限制深度）
        flat_data = self._flatten_tree(file_tree, max_depth)

        # 准备数据
        sizes = [item['size'] for item in flat_data]
        labels = [
            f"{item['name']}\n{self._format_size(item['size'])}"
            for item in flat_data
        ]
        colors = self._generate_colors(len(flat_data))

        # 绘制Treemap
        fig, ax = plt.subplots(figsize=(16, 9))
        squarify.plot(
            sizes=sizes,
            label=labels,
            color=colors,
            alpha=0.8,
            text_kwargs={'fontsize': 10, 'weight': 'bold'},
            ax=ax
        )
        ax.axis('off')
        plt.title('磁盘空间占用树形图', fontsize=20, weight='bold')

        return fig

    def _format_size(self, bytes_size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} PB"
```

#### 3.2.3 关联分析器 (RelationAnalyzer)

**文件拉普拉斯向量映射（与HIDRS核心技术结合）**:
```python
from hidrs.laplacian_analyzer import LaplacianAnalyzer
from hidrs.holographic_mapping import HolisticMapping

class FileRelationAnalyzer:
    """文件关联性分析 - 结合HIDRS拉普拉斯谱分析"""

    def __init__(self):
        self.laplacian = LaplacianAnalyzer()
        self.holographic = HolisticMapping()

    def analyze_file_relations(self, file_list: List[str]) -> Dict:
        """分析文件之间的隐藏关联"""

        # 为每个文件计算特征向量
        file_vectors = {}
        for file_path in file_list:
            # 提取文件元数据特征
            features = self._extract_file_features(file_path)

            # 计算拉普拉斯向量（基于文件属性的图结构）
            laplacian_vector = self.laplacian.compute_file_vector(features)

            # 全息映射
            holographic_vector = self.holographic.embed(features)

            file_vectors[file_path] = {
                'laplacian': laplacian_vector,
                'holographic': holographic_vector,
            }

        # 计算文件之间的相似度矩阵
        similarity_matrix = self._compute_similarity_matrix(file_vectors)

        # 聚类分析 - 发现相关文件组
        clusters = self._cluster_files(similarity_matrix)

        return {
            'clusters': clusters,
            'similarity_matrix': similarity_matrix,
            'related_files': self._find_related_files(similarity_matrix, threshold=0.8),
        }

    def _extract_file_features(self, file_path: str) -> Dict:
        """提取文件特征"""
        import os
        import hashlib

        stat = os.stat(file_path)

        # 文件头部哈希（用于内容相似度）
        with open(file_path, 'rb') as f:
            header = f.read(4096)
            header_hash = hashlib.md5(header).hexdigest()

        return {
            'size': stat.st_size,
            'created': stat.st_ctime,
            'modified': stat.st_mtime,
            'extension': os.path.splitext(file_path)[1].lower(),
            'header_hash': header_hash,
            'directory': os.path.dirname(file_path),
            'depth': file_path.count(os.sep),
        }
```

**重复文件检测**:
```python
import hashlib
from collections import defaultdict

class DuplicateFinder:
    """重复文件检测 - 识别浪费的磁盘空间"""

    def find_duplicates(self, file_list: List[str]) -> List[List[str]]:
        """查找重复文件（基于内容哈希）"""

        # 第一遍：按大小分组（快速过滤）
        size_groups = defaultdict(list)
        for file_path in file_list:
            try:
                size = os.path.getsize(file_path)
                size_groups[size].append(file_path)
            except:
                continue

        # 第二遍：对相同大小的文件计算哈希
        hash_groups = defaultdict(list)
        for size, files in size_groups.items():
            if len(files) < 2:  # 只有一个文件，跳过
                continue

            for file_path in files:
                try:
                    file_hash = self._compute_file_hash(file_path)
                    hash_groups[file_hash].append(file_path)
                except:
                    continue

        # 返回重复文件组
        duplicates = [
            files for files in hash_groups.values() if len(files) > 1
        ]

        # 计算浪费的空间
        wasted_space = 0
        for dup_group in duplicates:
            file_size = os.path.getsize(dup_group[0])
            wasted_space += file_size * (len(dup_group) - 1)

        return {
            'duplicate_groups': duplicates,
            'total_groups': len(duplicates),
            'total_duplicates': sum(len(g) - 1 for g in duplicates),
            'wasted_space_mb': wasted_space / (1024 * 1024),
        }

    def _compute_file_hash(self, file_path: str, algorithm='md5') -> str:
        """计算文件哈希（支持大文件）"""
        hash_func = hashlib.new(algorithm)

        with open(file_path, 'rb') as f:
            # 分块读取，避免内存溢出
            for chunk in iter(lambda: f.read(8192), b''):
                hash_func.update(chunk)

        return hash_func.hexdigest()
```

#### 3.2.4 时间线追踪 (TimelineTracker)

**文件增长趋势分析**:
```python
import json
import time
from collections import defaultdict

class TimelineTracker:
    """时间线追踪器 - 监控文件增长趋势"""

    def __init__(self, snapshot_dir: str = './snapshots'):
        self.snapshot_dir = snapshot_dir
        os.makedirs(snapshot_dir, exist_ok=True)

    def create_snapshot(self, name: str = None):
        """创建磁盘状态快照"""
        if name is None:
            name = f"snapshot_{int(time.time())}"

        snapshot = {
            'name': name,
            'timestamp': time.time(),
            'datetime': time.strftime('%Y-%m-%d %H:%M:%S'),
            'file_count': 0,
            'total_size': 0,
            'files_by_dir': defaultdict(lambda: {'count': 0, 'size': 0}),
            'files_by_ext': defaultdict(lambda: {'count': 0, 'size': 0}),
            'top_files': [],  # 前100个最大文件
        }

        # 遍历所有文件
        all_files = []
        for root, dirs, files in os.walk('C:\\'):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    size = os.path.getsize(file_path)
                    ext = os.path.splitext(file)[1].lower()

                    snapshot['file_count'] += 1
                    snapshot['total_size'] += size

                    snapshot['files_by_dir'][root]['count'] += 1
                    snapshot['files_by_dir'][root]['size'] += size

                    snapshot['files_by_ext'][ext]['count'] += 1
                    snapshot['files_by_ext'][ext]['size'] += size

                    all_files.append({'path': file_path, 'size': size})
                except:
                    continue

        # 保存前100个最大文件
        all_files.sort(key=lambda x: x['size'], reverse=True)
        snapshot['top_files'] = all_files[:100]

        # 保存快照
        snapshot_path = os.path.join(self.snapshot_dir, f"{name}.json")
        with open(snapshot_path, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)

        return snapshot

    def compare_snapshots(self, snapshot1_name: str, snapshot2_name: str) -> Dict:
        """对比两个快照，找出差异"""

        snap1 = self._load_snapshot(snapshot1_name)
        snap2 = self._load_snapshot(snapshot2_name)

        delta = {
            'time_elapsed_hours': (snap2['timestamp'] - snap1['timestamp']) / 3600,
            'file_count_change': snap2['file_count'] - snap1['file_count'],
            'size_change_mb': (snap2['total_size'] - snap1['total_size']) / (1024 * 1024),
            'growth_rate_mb_per_hour': 0,
        }

        delta['growth_rate_mb_per_hour'] = (
            delta['size_change_mb'] / delta['time_elapsed_hours']
        )

        # 找出增长最快的目录
        dir_changes = []
        for dir_path in snap2['files_by_dir']:
            size1 = snap1['files_by_dir'].get(dir_path, {}).get('size', 0)
            size2 = snap2['files_by_dir'][dir_path]['size']
            growth = size2 - size1

            if growth > 10 * 1024 * 1024:  # 增长超过10MB
                dir_changes.append({
                    'path': dir_path,
                    'growth_mb': growth / (1024 * 1024),
                    'size_before_mb': size1 / (1024 * 1024),
                    'size_after_mb': size2 / (1024 * 1024),
                })

        dir_changes.sort(key=lambda x: x['growth_mb'], reverse=True)

        # 找出新增的大文件
        snap1_top_paths = {f['path'] for f in snap1['top_files']}
        new_large_files = [
            f for f in snap2['top_files'] if f['path'] not in snap1_top_paths
        ]

        return {
            'summary': delta,
            'dir_changes': dir_changes[:20],
            'new_large_files': new_large_files[:20],
        }

    def _load_snapshot(self, name: str) -> Dict:
        """加载快照"""
        snapshot_path = os.path.join(self.snapshot_dir, f"{name}.json")
        with open(snapshot_path, 'r', encoding='utf-8') as f:
            return json.load(f)
```

---

## 4. 插件实现

### 4.1 插件主类

```python
from plugins.base import HIDRSPlugin
from typing import Dict, List, Any

class LocalFileSearchPlugin(HIDRSPlugin):
    """HIDRS本地文件搜索插件"""

    PLUGIN_NAME = "local_file_search"
    PLUGIN_VERSION = "1.0.0"
    REQUIRED_PERMISSIONS = ['filesystem.read', 'filesystem.index', 'system.process']

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        # 索引引擎
        if os.name == 'nt':  # Windows
            from .mft_reader import MFTReader
            self.indexer = MFTReader(config.get('drive', 'C'))
        else:  # Linux/Mac
            from .file_watcher import FileSystemWatcher
            self.indexer = FileSystemWatcher(config.get('root', '/'))

        # 空间分析器
        self.space_analyzer = SpaceAnalyzer(self.indexer)
        self.leak_detector = SpaceLeakDetector(self.indexer)

        # 关联分析器
        self.relation_analyzer = FileRelationAnalyzer()
        self.duplicate_finder = DuplicateFinder()

        # 时间线追踪
        self.timeline = TimelineTracker(config.get('snapshot_dir', './snapshots'))

    def initialize(self) -> bool:
        """插件初始化"""
        try:
            logger.info(f"[{self.PLUGIN_NAME}] 开始建立文件索引...")

            # 建立初始索引
            self.indexer.build_index()

            # 启动实时监控
            self.indexer.start_monitoring()

            logger.info(f"[{self.PLUGIN_NAME}] 索引完成，共 {self.indexer.get_file_count()} 个文件")
            return True
        except Exception as e:
            logger.error(f"[{self.PLUGIN_NAME}] 初始化失败: {e}")
            return False

    def execute(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """执行查询"""
        search_type = kwargs.get('type', 'name')  # name, content, signature, space

        if search_type == 'name':
            return self._search_by_name(query, **kwargs)
        elif search_type == 'content':
            return self._search_by_content(query, **kwargs)
        elif search_type == 'space_leak':
            return self._diagnose_space_leak(**kwargs)
        elif search_type == 'duplicates':
            return self._find_duplicates(**kwargs)
        elif search_type == 'timeline':
            return self._timeline_analysis(**kwargs)
        else:
            raise ValueError(f"未知的搜索类型: {search_type}")

    def _search_by_name(self, pattern: str, **kwargs) -> List[Dict]:
        """按文件名搜索（支持正则）"""
        import re
        regex = re.compile(pattern, re.IGNORECASE)

        results = []
        for file_info in self.indexer.get_all_files():
            if regex.search(file_info['name']):
                results.append(file_info)

        # 按修改时间排序
        results.sort(key=lambda x: x.get('modified', 0), reverse=True)

        return results[:kwargs.get('limit', 1000)]

    def _diagnose_space_leak(self, **kwargs) -> Dict:
        """诊断磁盘空间"热胀冷缩"问题"""

        # 如果没有基线，先创建
        if not self.leak_detector.baseline:
            logger.warning("未找到基线快照，正在创建...")
            self.leak_detector.create_baseline_snapshot()
            return {
                'status': 'baseline_created',
                'message': '基线快照已创建，请在清理磁盘后再次运行诊断',
            }

        # 执行泄漏检测
        interval = kwargs.get('interval_minutes', 60)
        report = self.leak_detector.detect_space_leak(interval)

        return report

    def _find_duplicates(self, **kwargs) -> Dict:
        """查找重复文件"""
        scan_path = kwargs.get('path', 'C:\\')
        min_size = kwargs.get('min_size_mb', 1) * 1024 * 1024

        # 获取所有文件（过滤小文件）
        all_files = [
            f['path'] for f in self.indexer.get_all_files()
            if f['size'] >= min_size and f['path'].startswith(scan_path)
        ]

        logger.info(f"正在扫描 {len(all_files)} 个文件...")

        # 查找重复
        duplicates = self.duplicate_finder.find_duplicates(all_files)

        return duplicates

    def _timeline_analysis(self, **kwargs) -> Dict:
        """时间线分析"""
        action = kwargs.get('action', 'snapshot')

        if action == 'snapshot':
            # 创建快照
            name = kwargs.get('name')
            snapshot = self.timeline.create_snapshot(name)
            return {
                'status': 'snapshot_created',
                'snapshot': snapshot,
            }

        elif action == 'compare':
            # 对比快照
            snap1 = kwargs.get('snapshot1')
            snap2 = kwargs.get('snapshot2')
            comparison = self.timeline.compare_snapshots(snap1, snap2)
            return {
                'status': 'comparison_completed',
                'comparison': comparison,
            }

        else:
            raise ValueError(f"未知的时间线操作: {action}")

    def validate_config(self) -> bool:
        """验证配置"""
        required_keys = ['drive' if os.name == 'nt' else 'root']

        for key in required_keys:
            if key not in self.config:
                logger.error(f"缺少必需配置项: {key}")
                return False

        return True
```

### 4.2 配置文件

```yaml
# plugins/local_file_search/config.yaml

name: LocalFileSearchPlugin
enabled: true
version: 1.0.0

# Windows配置
drive: C  # 扫描的驱动器

# Linux/Mac配置
root: /home  # 扫描的根目录

# 索引配置
index:
  auto_update: true  # 自动增量更新
  exclude_patterns:  # 排除的路径模式
    - "*/node_modules/*"
    - "*/.git/*"
    - "*/venv/*"
    - "*/temp/*"
  max_file_size_mb: 1024  # 最大索引文件大小（超过则跳过内容索引）

# 空间分析配置
space_analysis:
  baseline_auto_create: false  # 首次运行自动创建基线
  monitoring_interval_minutes: 60  # 监控间隔
  growth_threshold_mb: 100  # 增长阈值（超过则告警）

# 重复文件检测配置
duplicate_detection:
  min_file_size_mb: 1  # 最小文件大小（小于则忽略）
  hash_algorithm: md5  # 哈希算法 (md5, sha1, sha256)

# 快照配置
snapshot:
  dir: ./snapshots  # 快照保存目录
  retention_days: 30  # 快照保留天数

# 权限
permissions:
  - filesystem.read
  - filesystem.index
  - system.process
```

---

## 5. 前端集成

### 5.1 本地文件搜索界面

```html
<!-- plugins/local_file_search/templates/search.html -->

<div class="local-file-search-panel">
    <h3>🗂️ 本地文件搜索</h3>

    <!-- 搜索类型选择 -->
    <ul class="nav nav-tabs" id="searchTypeTabs">
        <li class="nav-item">
            <a class="nav-link active" data-tab="name-search">文件名搜索</a>
        </li>
        <li class="nav-item">
            <a class="nav-link" data-tab="space-leak">空间泄漏诊断</a>
        </li>
        <li class="nav-item">
            <a class="nav-link" data-tab="duplicates">重复文件检测</a>
        </li>
        <li class="nav-item">
            <a class="nav-link" data-tab="timeline">时间线分析</a>
        </li>
    </ul>

    <!-- 文件名搜索 -->
    <div id="name-search" class="search-tab-content active">
        <div class="input-group mb-3">
            <input type="text" class="form-control" id="file-name-input"
                   placeholder="输入文件名或正则表达式（如：.*\.log$）">
            <button class="btn btn-primary" id="search-file-name-btn">搜索</button>
        </div>

        <div id="file-search-results"></div>
    </div>

    <!-- 空间泄漏诊断 -->
    <div id="space-leak" class="search-tab-content">
        <div class="alert alert-info">
            <strong>使用说明:</strong>
            <ol>
                <li>清理磁盘前，点击"创建基线快照"</li>
                <li>清理磁盘后，等待一段时间（建议1-2小时）</li>
                <li>点击"执行诊断"查看空间回填原因</li>
            </ol>
        </div>

        <div class="btn-group mb-3">
            <button class="btn btn-success" id="create-baseline-btn">创建基线快照</button>
            <button class="btn btn-danger" id="diagnose-leak-btn">执行诊断</button>
        </div>

        <div id="space-leak-report"></div>
    </div>

    <!-- 重复文件检测 -->
    <div id="duplicates" class="search-tab-content">
        <div class="input-group mb-3">
            <input type="text" class="form-control" id="duplicate-scan-path"
                   placeholder="扫描路径（如：C:\Users）" value="C:\">
            <input type="number" class="form-control" id="duplicate-min-size"
                   placeholder="最小文件大小(MB)" value="1">
            <button class="btn btn-primary" id="find-duplicates-btn">查找重复文件</button>
        </div>

        <div id="duplicate-results"></div>
    </div>

    <!-- 时间线分析 -->
    <div id="timeline" class="search-tab-content">
        <div class="btn-group mb-3">
            <button class="btn btn-success" id="create-snapshot-btn">创建快照</button>
            <button class="btn btn-primary" id="compare-snapshots-btn">对比快照</button>
        </div>

        <div id="snapshot-list"></div>
        <div id="timeline-comparison"></div>
    </div>
</div>
```

### 5.2 空间泄漏诊断报告模板

```javascript
// frontend/js/local_file_search_ui.js

function renderSpaceLeakReport(report) {
    const container = document.getElementById('space-leak-report');

    const html = `
        <div class="space-leak-report">
            <h4>📊 诊断报告</h4>

            <!-- 概要 -->
            <div class="alert alert-warning">
                <h5>概要</h5>
                <ul>
                    <li>时间间隔: ${report.summary.time_elapsed.toFixed(1)} 分钟</li>
                    <li>空间增长: ${report.summary.size_increase_mb.toFixed(1)} MB</li>
                    <li>文件增加: ${report.summary.file_increase} 个</li>
                    <li>增长速度: ${report.summary.growth_rate_mb_per_hour.toFixed(2)} MB/小时</li>
                </ul>
            </div>

            <!-- 快速增长的目录 -->
            <h5>🚀 快速增长的目录（Top 10）</h5>
            <table class="table table-striped">
                <thead>
                    <tr>
                        <th>路径</th>
                        <th>增长(MB)</th>
                        <th>增长率</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    ${report.fast_growing_dirs.slice(0, 10).map(dir => `
                        <tr>
                            <td><code>${dir.path}</code></td>
                            <td>${dir.growth_mb.toFixed(1)}</td>
                            <td>${dir.growth_rate.toFixed(1)}%</td>
                            <td>
                                <button class="btn btn-sm btn-primary"
                                        onclick="openFolder('${dir.path}')">
                                    打开
                                </button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>

            <!-- 识别的"罪魁祸首" -->
            <h5>⚠️ 识别的"罪魁祸首"</h5>
            ${report.culprits.map(culprit => `
                <div class="alert alert-danger">
                    <h6>${culprit.name} (+${culprit.growth_mb.toFixed(1)} MB)</h6>
                    <p>${culprit.description}</p>
                    <p><strong>路径:</strong> <code>${culprit.path}</code></p>
                    <p><strong>解决方案:</strong> ${culprit.solution}</p>
                </div>
            `).join('')}

            <!-- 清理建议 -->
            <h5>💡 清理建议</h5>
            <ul>
                ${report.recommendations.map(rec => `<li>${rec}</li>`).join('')}
            </ul>
        </div>
    `;

    container.innerHTML = html;
}
```

### 5.3 Treemap可视化（ECharts）

```javascript
// frontend/js/treemap_visualizer.js

function renderTreemap(fileTree) {
    const chartDom = document.getElementById('treemap-chart');
    const myChart = echarts.init(chartDom);

    // 转换数据格式
    const data = convertToEChartsFormat(fileTree);

    const option = {
        title: {
            text: '磁盘空间占用树形图',
            left: 'center',
        },
        tooltip: {
            formatter: function (info) {
                return [
                    `<div class="tooltip-title">${info.name}</div>`,
                    `大小: ${formatSize(info.value)}`,
                    `占比: ${info.percent}%`,
                ].join('');
            }
        },
        series: [
            {
                type: 'treemap',
                data: data,
                label: {
                    show: true,
                    formatter: '{b}\n{c}',
                },
                itemStyle: {
                    borderColor: '#fff',
                    borderWidth: 2,
                },
                levels: [
                    {
                        itemStyle: {
                            borderColor: '#777',
                            borderWidth: 3,
                            gapWidth: 3,
                        }
                    },
                    {
                        colorSaturation: [0.35, 0.5],
                        itemStyle: {
                            gapWidth: 1,
                            borderColorSaturation: 0.6,
                        }
                    }
                ],
            }
        ]
    };

    myChart.setOption(option);
}

function convertToEChartsFormat(fileTree) {
    const result = [];

    for (const [name, node] of Object.entries(fileTree.children)) {
        const item = {
            name: name,
            value: node.size,
        };

        if (node.children && Object.keys(node.children).length > 0) {
            item.children = convertToEChartsFormat(node);
        }

        result.push(item);
    }

    return result;
}
```

---

## 6. API端点

### 6.1 后端路由（Flask）

```python
# backend/crawler_server.py

@app.route('/api/local-file/search', methods=['POST'])
def local_file_search():
    """本地文件搜索"""
    data = request.json
    query = data.get('query', '')
    search_type = data.get('type', 'name')

    plugin = plugin_manager.get_plugin('local_file_search')
    if not plugin:
        return jsonify({'error': '本地文件搜索插件未启用'}), 400

    try:
        results = plugin.execute(query, type=search_type, **data)
        return jsonify({'success': True, 'data': results})
    except Exception as e:
        logger.error(f"本地文件搜索失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/local-file/diagnose-space-leak', methods=['POST'])
def diagnose_space_leak():
    """诊断磁盘空间泄漏"""
    data = request.json

    plugin = plugin_manager.get_plugin('local_file_search')
    if not plugin:
        return jsonify({'error': '本地文件搜索插件未启用'}), 400

    try:
        report = plugin.execute('', type='space_leak', **data)
        return jsonify({'success': True, 'data': report})
    except Exception as e:
        logger.error(f"空间泄漏诊断失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/local-file/create-baseline', methods=['POST'])
def create_baseline():
    """创建基线快照"""
    plugin = plugin_manager.get_plugin('local_file_search')
    if not plugin:
        return jsonify({'error': '本地文件搜索插件未启用'}), 400

    try:
        plugin.leak_detector.create_baseline_snapshot()
        return jsonify({'success': True, 'message': '基线快照已创建'})
    except Exception as e:
        logger.error(f"创建基线快照失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/local-file/find-duplicates', methods=['POST'])
def find_duplicates():
    """查找重复文件"""
    data = request.json

    plugin = plugin_manager.get_plugin('local_file_search')
    if not plugin:
        return jsonify({'error': '本地文件搜索插件未启用'}), 400

    try:
        duplicates = plugin.execute('', type='duplicates', **data)
        return jsonify({'success': True, 'data': duplicates})
    except Exception as e:
        logger.error(f"重复文件检测失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/local-file/timeline', methods=['POST'])
def timeline_operation():
    """时间线操作（快照、对比）"""
    data = request.json

    plugin = plugin_manager.get_plugin('local_file_search')
    if not plugin:
        return jsonify({'error': '本地文件搜索插件未启用'}), 400

    try:
        result = plugin.execute('', type='timeline', **data)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"时间线操作失败: {e}")
        return jsonify({'error': str(e)}), 500
```

---

## 7. 实现路线图

### Phase 1: 核心索引引擎（2-3周）

**Week 1-2: 索引引擎开发**
- [ ] Windows MFT Reader实现
- [ ] Linux/Mac文件系统监控（watchdog）
- [ ] 增量索引更新机制
- [ ] 索引数据库设计（SQLite）

**Week 3: 基础搜索功能**
- [ ] 文件名正则搜索
- [ ] 基础筛选（大小、日期、类型）
- [ ] API端点实现

### Phase 2: 空间分析与诊断（2-3周）

**Week 4: 空间分析器**
- [ ] 磁盘空间统计
- [ ] 文件类型分组
- [ ] 目录树大小计算

**Week 5: 空间泄漏检测**
- [ ] 基线快照系统
- [ ] 增量对比算法
- [ ] "罪魁祸首"识别规则库

**Week 6: Treemap可视化**
- [ ] 后端数据格式化
- [ ] ECharts Treemap集成
- [ ] 交互式钻取功能

### Phase 3: 高级分析功能（2-3周）

**Week 7: 重复文件检测**
- [ ] 哈希计算优化（分块读取）
- [ ] 相似度分析（fuzzy hash）
- [ ] 批量删除接口

**Week 8: 文件关联分析**
- [ ] 文件特征提取
- [ ] 拉普拉斯向量集成
- [ ] 关联图可视化

**Week 9: 时间线追踪**
- [ ] 快照系统实现
- [ ] 快照对比算法
- [ ] 趋势图表（Chart.js）

### Phase 4: 前端UI与优化（1-2周）

**Week 10: 前端开发**
- [ ] 搜索界面实现
- [ ] 诊断报告界面
- [ ] 可视化图表集成

**Week 11: 测试与优化**
- [ ] 性能优化（大文件处理）
- [ ] 错误处理完善
- [ ] 用户文档编写

---

## 8. 技术难点与解决方案

### 8.1 MFT读取权限问题

**问题**: 直接读取MFT需要管理员权限

**解决方案**:
1. 提示用户以管理员身份运行
2. 降级到常规文件遍历（速度较慢）
3. 使用Windows Search API作为备选

### 8.2 大文件哈希计算性能

**问题**: 计算TB级硬盘的文件哈希耗时过长

**解决方案**:
1. 分块读取（8KB chunks）
2. 多进程并行计算（ProcessPoolExecutor）
3. 智能采样（仅哈希文件头+尾，快速初筛）
4. 增量更新（仅计算新文件/修改文件）

### 8.3 跨平台兼容性

**问题**: Windows MFT读取无法用于Linux/Mac

**解决方案**:
- Windows: MFT直接读取（最快）
- Linux: 使用inotify + 初始全盘扫描
- Mac: 使用FSEvents + 初始全盘扫描

---

## 9. 与现有工具的差异化优势

| 功能 | Everything | WizTree | TreeSize | **HIDRS本地搜索插件** |
|------|-----------|---------|----------|----------------------|
| 文件名搜索 | ✅ 极快 | ✅ 快 | ✅ 中等 | ✅ 快（MFT） |
| 内容搜索 | ⚠️ v1.5+ | ❌ | ❌ | ✅ 全文索引 |
| 空间可视化 | ❌ | ✅ Treemap | ✅ 多种视图 | ✅ Treemap + 统计 |
| 重复文件检测 | ❌ | ❌ | ✅ | ✅ 哈希+相似度 |
| **空间泄漏诊断** | ❌ | ❌ | ❌ | ✅ **独有** |
| **文件关联分析** | ❌ | ❌ | ❌ | ✅ **独有（拉普拉斯）** |
| **时间线追踪** | ❌ | ❌ | ⚠️ 年龄视图 | ✅ **完整快照系统** |
| 跨平台 | ❌ Windows | ❌ Windows | ❌ Windows | ✅ Win/Linux/Mac |

### 独特价值

1. **智能诊断**: 不仅显示磁盘占用，还能诊断"清理后立刻回填"的根本原因
2. **HIDRS生态集成**: 与拉普拉斯分析、全息映射、都市传说检测等功能深度结合
3. **研究导向**: 发现文件之间的隐藏关联（如：哪些临时文件属于同一应用）
4. **开源免费**: 所有功能完全开源，无商业限制

---

## 10. 安全与隐私

### 10.1 权限控制

- **只读访问**: 插件仅读取文件元数据，不修改任何文件
- **用户确认**: 删除操作（如重复文件）需用户明确确认
- **本地处理**: 所有数据处理均在本地，不上传到服务器

### 10.2 敏感数据保护

- **排除模式**: 默认排除系统文件、密钥文件（如`.ssh/`, `.gnupg/`）
- **哈希不可逆**: 文件哈希使用单向算法，无法还原内容
- **快照加密**: 快照文件可选AES加密存储

---

## 11. 参考资料

**现有工具**:
- [Everything - voidtools](https://www.voidtools.com/)
- [R-Studio Data Recovery Software](https://www.r-studio.com/)
- [WizTree - The Fastest Disk Space Analyzer](https://diskanalyzer.com/)
- [TreeSize – Official Free Download](https://www.jam-software.com/treesize)
- [WinDirStat - Windows Directory Statistics](https://windirstat.net/)

**技术文档**:
- [NTFS MFT Structure](https://docs.microsoft.com/en-us/windows/win32/fileio/master-file-table)
- [USN Change Journal](https://docs.microsoft.com/en-us/windows/win32/fileio/change-journals)
- [Python watchdog](https://github.com/gorakhargosh/watchdog)

**数据可视化**:
- [ECharts Treemap](https://echarts.apache.org/examples/en/editor.html?c=treemap-disk)
- [squarify - Pure Python Treemap Layout](https://github.com/laserson/squarify)

---

## 12. 下一步行动

1. **用户反馈**: 确认功能需求优先级
2. **技术预研**: 验证MFT读取在目标环境可行性
3. **原型开发**: 先实现核心索引引擎和空间泄漏诊断
4. **迭代优化**: 根据实际使用反馈调整功能

---

**版本**: v1.0.0
**创建日期**: 2026-02-05
**作者**: Claude (HIDRS Plugin System)
