#!/usr/bin/env python3
"""
文档内容搜索器 (Document Content Searcher) - HIDRS
类取证工具级别的全盘/目录文本文件关键词搜索

功能:
- 遍历指定目录或盘符，递归搜索所有文本文件
- 自动检测文件是否为文本（不依赖扩展名，通过内容判定）
- 自动识别文件编码（支持 UTF-8/GBK/GB2312/Big5/Shift_JIS/EUC-KR/Latin-1 等）
- 精准关键词搜索 + 正则表达式搜索
- 反查模式：找出不包含指定关键词的文件
- 多维筛选：日期范围、文件大小、名称模式、排除模式
- 多维排序：按名称、大小、修改日期、匹配数排序
- 中英文文件名自动翻译
- 双输出模式：人类可读文本 / Agent可解析JSON

作者: HIDRS Team
日期: 2026-02-12
"""

import os
import re
import sys
import json
import time
import fnmatch
import argparse
import logging
from datetime import datetime
from typing import (
    Dict, Any, List, Optional, Tuple, Set, Generator, Pattern, Union
)
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# 编码检测
try:
    import chardet
    HAS_CHARDET = True
except ImportError:
    HAS_CHARDET = False

# 中英文翻译
try:
    from deep_translator import GoogleTranslator
    HAS_TRANSLATOR = True
except ImportError:
    HAS_TRANSLATOR = False

logger = logging.getLogger(__name__)

# ============================================================
# 常量定义
# ============================================================

# 采样大小：读取文件头部多少字节来判定是否为文本
TEXT_DETECT_SAMPLE_SIZE = 8192

# 搜索时单文件最大读取量（防止超大文件撑爆内存）
MAX_FILE_READ_BYTES = 100 * 1024 * 1024  # 100MB

# 已知二进制扩展名（跳过这些文件加速搜索）
KNOWN_BINARY_EXTENSIONS: Set[str] = {
    '.exe', '.dll', '.so', '.dylib', '.o', '.a', '.lib',
    '.zip', '.gz', '.bz2', '.xz', '.7z', '.rar', '.tar',
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.tiff', '.svg',
    '.mp3', '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.wav', '.flac',
    '.ogg', '.aac', '.wma',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.iso', '.img', '.dmg', '.bin', '.dat',
    '.pyc', '.pyo', '.class', '.wasm',
    '.ttf', '.otf', '.woff', '.woff2', '.eot',
    '.sqlite', '.db', '.mdb',
    '.pkl', '.joblib', '.npy', '.npz', '.h5', '.hdf5',
}

# 已知文本扩展名（优先当作文本处理）
KNOWN_TEXT_EXTENSIONS: Set[str] = {
    '.txt', '.md', '.rst', '.csv', '.tsv', '.log', '.ini', '.cfg', '.conf',
    '.json', '.jsonl', '.xml', '.yaml', '.yml', '.toml',
    '.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.htm', '.css', '.scss',
    '.java', '.c', '.cpp', '.h', '.hpp', '.cs', '.go', '.rs', '.rb',
    '.php', '.pl', '.pm', '.lua', '.r', '.R', '.m', '.swift', '.kt',
    '.sh', '.bash', '.zsh', '.fish', '.bat', '.cmd', '.ps1',
    '.sql', '.graphql', '.proto',
    '.tex', '.bib', '.srt', '.ass', '.vtt',
    '.env', '.gitignore', '.dockerignore', '.editorconfig',
    '.makefile', '.cmake',
}

# 尝试的编码列表（chardet 不可用时的回退）
FALLBACK_ENCODINGS = [
    'utf-8', 'gbk', 'gb2312', 'gb18030', 'big5',
    'shift_jis', 'euc-jp', 'euc-kr',
    'utf-16', 'utf-16-le', 'utf-16-be',
    'latin-1', 'iso-8859-1', 'ascii',
    'cp1252', 'cp1251', 'cp936',
]


# ============================================================
# 文本检测与编码识别
# ============================================================

class TextDetector:
    """文件文本检测器：判定文件是否为文本，并识别编码"""

    # 文本文件中允许的控制字符
    ALLOWED_CONTROL_CHARS = {0x09, 0x0A, 0x0D}  # tab, LF, CR

    @staticmethod
    def is_text_file(file_path: str, sample_size: int = TEXT_DETECT_SAMPLE_SIZE) -> Tuple[bool, Optional[str]]:
        """
        判定文件是否为文本文件，并返回检测到的编码

        不依赖扩展名，通过读取文件头部字节内容来判定：
        1. 已知二进制扩展名 → 直接跳过（加速）
        2. 已知文本扩展名 → 优先尝试文本解码
        3. 无扩展名或未知扩展名 → 通过内容检测

        Returns:
            (is_text, encoding) - 是否为文本，检测到的编码名称
        """
        try:
            ext = os.path.splitext(file_path)[1].lower()

            # 已知二进制 → 快速跳过
            if ext in KNOWN_BINARY_EXTENSIONS:
                return False, None

            # 读取样本
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                return True, 'utf-8'  # 空文件视为文本

            with open(file_path, 'rb') as f:
                sample = f.read(min(sample_size, file_size))

            # 检查 BOM 标记
            encoding = TextDetector._detect_bom(sample)
            if encoding:
                return True, encoding

            # 空字节检测：文本文件中不应包含 \x00
            # 但 UTF-16 文件会有大量 \x00，所以需要排除 BOM 情况
            null_ratio = sample.count(b'\x00') / len(sample) if sample else 0
            if null_ratio > 0.1:
                # 可能是 UTF-16 无 BOM
                encoding = TextDetector._try_utf16_no_bom(sample)
                if encoding:
                    return True, encoding
                return False, None

            # 控制字符检测
            non_text_chars = 0
            for byte in sample:
                if byte < 0x20 and byte not in TextDetector.ALLOWED_CONTROL_CHARS:
                    non_text_chars += 1
            if len(sample) > 0 and non_text_chars / len(sample) > 0.05:
                return False, None

            # chardet 检测编码
            if HAS_CHARDET:
                detection = chardet.detect(sample)
                if detection and detection['encoding']:
                    confidence = detection.get('confidence', 0)
                    detected_enc = detection['encoding'].lower()
                    if confidence >= 0.5:
                        # 验证能否解码
                        try:
                            sample.decode(detected_enc)
                            return True, detected_enc
                        except (UnicodeDecodeError, LookupError):
                            pass

            # 回退：逐一尝试编码
            for enc in FALLBACK_ENCODINGS:
                try:
                    sample.decode(enc)
                    return True, enc
                except (UnicodeDecodeError, LookupError):
                    continue

            return False, None

        except (OSError, PermissionError):
            return False, None

    @staticmethod
    def _detect_bom(data: bytes) -> Optional[str]:
        """检查 BOM (Byte Order Mark)"""
        if data[:3] == b'\xef\xbb\xbf':
            return 'utf-8-sig'
        if data[:2] == b'\xff\xfe':
            return 'utf-16-le'
        if data[:2] == b'\xfe\xff':
            return 'utf-16-be'
        if data[:4] == b'\xff\xfe\x00\x00':
            return 'utf-32-le'
        if data[:4] == b'\x00\x00\xfe\xff':
            return 'utf-32-be'
        return None

    @staticmethod
    def _try_utf16_no_bom(data: bytes) -> Optional[str]:
        """尝试无 BOM 的 UTF-16 解码"""
        for enc in ('utf-16-le', 'utf-16-be'):
            try:
                text = data.decode(enc)
                # 验证：解码后应该大部分是可打印字符
                printable = sum(1 for c in text if c.isprintable() or c in '\n\r\t')
                if len(text) > 0 and printable / len(text) > 0.8:
                    return enc
            except (UnicodeDecodeError, LookupError):
                continue
        return None

    @staticmethod
    def read_text_file(file_path: str, encoding: str,
                       max_bytes: int = MAX_FILE_READ_BYTES) -> Optional[str]:
        """
        以检测到的编码读取文本文件内容

        Returns:
            文件文本内容，读取失败返回 None
        """
        try:
            file_size = os.path.getsize(file_path)
            read_size = min(file_size, max_bytes)

            with open(file_path, 'rb') as f:
                raw = f.read(read_size)

            # 首选检测到的编码
            try:
                return raw.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                pass

            # 回退尝试
            for enc in FALLBACK_ENCODINGS:
                try:
                    return raw.decode(enc)
                except (UnicodeDecodeError, LookupError):
                    continue

            # 最后用 errors='replace' 强制解码
            return raw.decode('utf-8', errors='replace')

        except (OSError, PermissionError):
            return None


# ============================================================
# 文件名翻译器
# ============================================================

class FilenameTranslator:
    """中英文文件名自动翻译"""

    # 中文字符范围正则
    _CJK_PATTERN = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]')

    def __init__(self, cache_size: int = 1000):
        self._cache: Dict[str, str] = {}
        self._cache_size = cache_size
        self._translator_zh_en = None
        self._translator_en_zh = None
        self._available = HAS_TRANSLATOR
        if self._available:
            try:
                self._translator_zh_en = GoogleTranslator(source='zh-CN', target='en')
                self._translator_en_zh = GoogleTranslator(source='en', target='zh-CN')
            except Exception:
                self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def contains_chinese(self, text: str) -> bool:
        """检测文本是否包含中文字符"""
        return bool(self._CJK_PATTERN.search(text))

    def translate(self, filename: str) -> Optional[str]:
        """
        自动翻译文件名（保留扩展名）

        中文文件名 → 英文翻译
        英文文件名 → 中文翻译
        """
        if not self._available:
            return None

        # 缓存查询
        if filename in self._cache:
            return self._cache[filename]

        stem = Path(filename).stem
        ext = Path(filename).suffix

        try:
            if self.contains_chinese(stem):
                translated = self._translator_zh_en.translate(stem)
            else:
                translated = self._translator_en_zh.translate(stem)

            if translated:
                # 清理翻译结果用于文件名
                translated = re.sub(r'[<>:"/\\|?*]', '_', translated.strip())
                result = translated + ext
                # 写入缓存
                if len(self._cache) < self._cache_size:
                    self._cache[filename] = result
                return result
        except Exception as e:
            logger.debug(f"翻译失败 '{filename}': {e}")

        return None

    def batch_translate(self, filenames: List[str]) -> Dict[str, Optional[str]]:
        """批量翻译文件名"""
        results = {}
        for name in filenames:
            results[name] = self.translate(name)
        return results


# ============================================================
# 搜索匹配引擎
# ============================================================

class SearchMatch:
    """单条搜索匹配结果"""
    __slots__ = ('line_number', 'line_content', 'match_start', 'match_end',
                 'context_before', 'context_after')

    def __init__(self, line_number: int, line_content: str,
                 match_start: int, match_end: int,
                 context_before: List[str], context_after: List[str]):
        self.line_number = line_number
        self.line_content = line_content
        self.match_start = match_start
        self.match_end = match_end
        self.context_before = context_before
        self.context_after = context_after

    def to_dict(self) -> Dict[str, Any]:
        return {
            'line': self.line_number,
            'content': self.line_content.rstrip('\n\r'),
            'match_span': [self.match_start, self.match_end],
            'context_before': [l.rstrip('\n\r') for l in self.context_before],
            'context_after': [l.rstrip('\n\r') for l in self.context_after],
        }


class FileResult:
    """单个文件的搜索结果"""
    __slots__ = ('path', 'encoding', 'size', 'modified', 'created',
                 'matches', 'match_count', 'translated_name')

    def __init__(self, path: str, encoding: str, size: int,
                 modified: float, created: float):
        self.path = path
        self.encoding = encoding
        self.size = size
        self.modified = modified
        self.created = created
        self.matches: List[SearchMatch] = []
        self.match_count = 0
        self.translated_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            'path': self.path,
            'filename': os.path.basename(self.path),
            'encoding': self.encoding,
            'size': self.size,
            'size_display': format_size(self.size),
            'modified': datetime.fromtimestamp(self.modified).isoformat(),
            'created': datetime.fromtimestamp(self.created).isoformat(),
            'match_count': self.match_count,
        }
        if self.translated_name:
            d['translated_name'] = self.translated_name
        if self.matches:
            d['matches'] = [m.to_dict() for m in self.matches]
        return d


# ============================================================
# 主搜索器
# ============================================================

class DocSearcher:
    """
    文档内容搜索器

    支持:
    - 普通关键词搜索（精确匹配）
    - 正则表达式搜索
    - 反查模式（查找不包含关键词的文件）
    - 多条件筛选与排序
    - 中英文文件名翻译
    """

    def __init__(self,
                 target_path: str,
                 keyword: Optional[str] = None,
                 regex_pattern: Optional[str] = None,
                 case_sensitive: bool = False,
                 invert: bool = False,
                 context_lines: int = 0,
                 max_matches_per_file: int = 0,
                 recursive: bool = True,
                 # 筛选
                 min_size: Optional[int] = None,
                 max_size: Optional[int] = None,
                 after: Optional[datetime] = None,
                 before: Optional[datetime] = None,
                 include_patterns: Optional[List[str]] = None,
                 exclude_patterns: Optional[List[str]] = None,
                 exclude_dirs: Optional[List[str]] = None,
                 # 排序
                 sort_by: str = 'path',
                 sort_reverse: bool = False,
                 # 功能开关
                 translate: bool = False,
                 max_results: int = 0,
                 workers: int = 4):
        """
        Args:
            target_path:   搜索的根目录或盘符
            keyword:       搜索关键词（精确匹配）
            regex_pattern: 正则表达式搜索模式（与 keyword 二选一，regex 优先）
            case_sensitive: 是否区分大小写
            invert:        反查模式 - True 时返回不包含关键词的文件
            context_lines: 匹配行的上下文行数
            max_matches_per_file: 每个文件最多记录匹配数（0=不限）
            recursive:     是否递归搜索子目录
            min_size:      最小文件大小(字节)
            max_size:      最大文件大小(字节)
            after:         只搜索此日期之后修改的文件
            before:        只搜索此日期之前修改的文件
            include_patterns: 文件名包含模式（glob），如 ["*.py", "*.txt"]
            exclude_patterns: 文件名排除模式（glob），如 ["*.log"]
            exclude_dirs:  排除的目录名，如 [".git", "node_modules", "__pycache__"]
            sort_by:       排序字段: path | name | size | date | matches
            sort_reverse:  是否降序排列
            translate:     是否启用文件名翻译
            max_results:   最大返回文件数（0=不限）
            workers:       并行搜索线程数
        """
        self.target_path = os.path.abspath(target_path)
        self.keyword = keyword
        self.regex_pattern = regex_pattern
        self.case_sensitive = case_sensitive
        self.invert = invert
        self.context_lines = context_lines
        self.max_matches_per_file = max_matches_per_file
        self.recursive = recursive
        self.min_size = min_size
        self.max_size = max_size
        self.after = after
        self.before = before
        self.include_patterns = include_patterns or []
        self.exclude_patterns = exclude_patterns or []
        self.exclude_dirs = set(exclude_dirs or [
            '.git', '__pycache__', 'node_modules', '.svn', '.hg',
            '.tox', '.mypy_cache', '.pytest_cache', '.eggs',
        ])
        self.sort_by = sort_by
        self.sort_reverse = sort_reverse
        self.translate = translate
        self.max_results = max_results
        self.workers = workers

        # 编译搜索模式
        self._compiled_pattern: Optional[Pattern] = None
        self._compile_pattern()

        # 翻译器
        self._translator: Optional[FilenameTranslator] = None
        if self.translate:
            self._translator = FilenameTranslator()
            if not self._translator.available:
                logger.warning("翻译库不可用，请安装: pip install deep-translator")

        # 统计
        self.stats = {
            'files_scanned': 0,
            'files_matched': 0,
            'files_skipped_binary': 0,
            'files_skipped_filter': 0,
            'files_skipped_error': 0,
            'total_matches': 0,
            'scan_time_seconds': 0.0,
        }

    def _compile_pattern(self):
        """编译搜索模式"""
        flags = 0 if self.case_sensitive else re.IGNORECASE

        if self.regex_pattern:
            self._compiled_pattern = re.compile(self.regex_pattern, flags)
        elif self.keyword:
            # 关键词转为正则（转义特殊字符实现精确匹配）
            self._compiled_pattern = re.compile(re.escape(self.keyword), flags)

    def search(self) -> List[FileResult]:
        """
        执行搜索，返回匹配结果列表

        Returns:
            FileResult 列表，已按指定方式排序
        """
        start_time = time.time()
        results: List[FileResult] = []

        if not os.path.exists(self.target_path):
            logger.error(f"路径不存在: {self.target_path}")
            return results

        # 收集候选文件
        candidate_files = list(self._enumerate_files())

        # 并行搜索
        if self.workers > 1 and len(candidate_files) > 10:
            results = self._search_parallel(candidate_files)
        else:
            results = self._search_sequential(candidate_files)

        # 排序
        results = self._sort_results(results)

        # 限制结果数
        if self.max_results > 0:
            results = results[:self.max_results]

        # 文件名翻译
        if self._translator and self._translator.available:
            for r in results:
                filename = os.path.basename(r.path)
                r.translated_name = self._translator.translate(filename)

        self.stats['scan_time_seconds'] = round(time.time() - start_time, 3)
        self.stats['files_matched'] = len(results)
        return results

    def scan_text_files(self) -> List[FileResult]:
        """
        仅扫描文本文件（不搜索内容），用于列出目录下所有文本文件

        Returns:
            FileResult 列表
        """
        start_time = time.time()
        results: List[FileResult] = []

        for file_path in self._enumerate_files():
            is_text, encoding = TextDetector.is_text_file(file_path)
            self.stats['files_scanned'] += 1

            if not is_text:
                self.stats['files_skipped_binary'] += 1
                continue

            try:
                stat = os.stat(file_path)
                result = FileResult(
                    path=file_path,
                    encoding=encoding or 'unknown',
                    size=stat.st_size,
                    modified=stat.st_mtime,
                    created=stat.st_ctime,
                )
                results.append(result)
            except OSError:
                self.stats['files_skipped_error'] += 1

        results = self._sort_results(results)

        if self.max_results > 0:
            results = results[:self.max_results]

        if self._translator and self._translator.available:
            for r in results:
                filename = os.path.basename(r.path)
                r.translated_name = self._translator.translate(filename)

        self.stats['scan_time_seconds'] = round(time.time() - start_time, 3)
        self.stats['files_matched'] = len(results)
        return results

    def _enumerate_files(self) -> Generator[str, None, None]:
        """遍历目录，应用文件级筛选条件，生成候选文件路径"""
        target = self.target_path

        # 如果目标是单个文件
        if os.path.isfile(target):
            if self._file_passes_filter(target):
                yield target
            return

        if self.recursive:
            for root, dirs, files in os.walk(target, topdown=True):
                # 排除目录
                dirs[:] = [
                    d for d in dirs
                    if d not in self.exclude_dirs
                    and not d.startswith('.')  # 默认跳过隐藏目录
                    or d in ('.config', '.local')  # 但允许部分常见配置目录
                ]

                for filename in files:
                    file_path = os.path.join(root, filename)
                    if self._file_passes_filter(file_path):
                        yield file_path
        else:
            try:
                for entry in os.scandir(target):
                    if entry.is_file() and self._file_passes_filter(entry.path):
                        yield entry.path
            except PermissionError:
                logger.warning(f"权限不足: {target}")

    def _file_passes_filter(self, file_path: str) -> bool:
        """检查文件是否通过筛选条件"""
        filename = os.path.basename(file_path)

        try:
            stat = os.stat(file_path)
        except OSError:
            return False

        # 大小筛选
        if self.min_size is not None and stat.st_size < self.min_size:
            self.stats['files_skipped_filter'] += 1
            return False
        if self.max_size is not None and stat.st_size > self.max_size:
            self.stats['files_skipped_filter'] += 1
            return False

        # 日期筛选（基于修改时间）
        if self.after is not None:
            mtime = datetime.fromtimestamp(stat.st_mtime)
            if mtime < self.after:
                self.stats['files_skipped_filter'] += 1
                return False
        if self.before is not None:
            mtime = datetime.fromtimestamp(stat.st_mtime)
            if mtime > self.before:
                self.stats['files_skipped_filter'] += 1
                return False

        # 包含模式（白名单，任一匹配即可）
        if self.include_patterns:
            if not any(fnmatch.fnmatch(filename, p) for p in self.include_patterns):
                self.stats['files_skipped_filter'] += 1
                return False

        # 排除模式（黑名单，任一匹配就排除）
        if self.exclude_patterns:
            if any(fnmatch.fnmatch(filename, p) for p in self.exclude_patterns):
                self.stats['files_skipped_filter'] += 1
                return False

        return True

    def _search_single_file(self, file_path: str) -> Optional[FileResult]:
        """搜索单个文件，返回结果或 None"""
        try:
            is_text, encoding = TextDetector.is_text_file(file_path)
            self.stats['files_scanned'] += 1

            if not is_text:
                self.stats['files_skipped_binary'] += 1
                return None

            stat = os.stat(file_path)
            result = FileResult(
                path=file_path,
                encoding=encoding or 'unknown',
                size=stat.st_size,
                modified=stat.st_mtime,
                created=stat.st_ctime,
            )

            # 如果没有搜索模式，仅返回文件信息
            if self._compiled_pattern is None:
                return result

            # 读取文件内容
            content = TextDetector.read_text_file(file_path, encoding)
            if content is None:
                self.stats['files_skipped_error'] += 1
                return None

            lines = content.split('\n')
            matches_found = False

            for line_idx, line in enumerate(lines):
                match = self._compiled_pattern.search(line)

                if match:
                    matches_found = True
                    result.match_count += 1

                    if not self.invert:
                        # 构造上下文
                        ctx_start = max(0, line_idx - self.context_lines)
                        ctx_end = min(len(lines), line_idx + self.context_lines + 1)
                        context_before = lines[ctx_start:line_idx]
                        context_after = lines[line_idx + 1:ctx_end]

                        sm = SearchMatch(
                            line_number=line_idx + 1,
                            line_content=line,
                            match_start=match.start(),
                            match_end=match.end(),
                            context_before=context_before,
                            context_after=context_after,
                        )
                        result.matches.append(sm)

                        # 限制单文件匹配数
                        if (self.max_matches_per_file > 0
                                and len(result.matches) >= self.max_matches_per_file):
                            break

            # 反查模式：返回不含关键词的文件
            if self.invert:
                if not matches_found:
                    result.match_count = 0
                    return result
                return None

            # 正常模式：返回包含关键词的文件
            if matches_found:
                self.stats['total_matches'] += result.match_count
                return result
            return None

        except Exception as e:
            self.stats['files_skipped_error'] += 1
            logger.debug(f"搜索文件出错 {file_path}: {e}")
            return None

    def _search_sequential(self, files: List[str]) -> List[FileResult]:
        """顺序搜索"""
        results = []
        for fp in files:
            r = self._search_single_file(fp)
            if r is not None:
                results.append(r)
        return results

    def _search_parallel(self, files: List[str]) -> List[FileResult]:
        """并行搜索"""
        results = []
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            future_to_file = {
                executor.submit(self._search_single_file, fp): fp
                for fp in files
            }
            for future in as_completed(future_to_file):
                r = future.result()
                if r is not None:
                    results.append(r)
        return results

    def _sort_results(self, results: List[FileResult]) -> List[FileResult]:
        """按指定字段排序"""
        key_map = {
            'path': lambda r: r.path.lower(),
            'name': lambda r: os.path.basename(r.path).lower(),
            'size': lambda r: r.size,
            'date': lambda r: r.modified,
            'matches': lambda r: r.match_count,
        }
        key_func = key_map.get(self.sort_by, key_map['path'])
        return sorted(results, key=key_func, reverse=self.sort_reverse)

    def get_summary(self) -> Dict[str, Any]:
        """返回搜索统计摘要"""
        return {
            'target_path': self.target_path,
            'keyword': self.keyword,
            'regex': self.regex_pattern,
            'invert_mode': self.invert,
            'case_sensitive': self.case_sensitive,
            **self.stats,
        }


# ============================================================
# 工具函数
# ============================================================

def format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}PB"


def parse_size(size_str: str) -> int:
    """解析大小字符串，如 '10KB', '5MB', '1GB'"""
    size_str = size_str.strip().upper()
    units = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
    for unit, multiplier in sorted(units.items(), key=lambda x: -len(x[0])):
        if size_str.endswith(unit):
            num_str = size_str[:-len(unit)].strip()
            return int(float(num_str) * multiplier)
    return int(size_str)


def parse_date(date_str: str) -> datetime:
    """解析日期字符串，支持多种格式"""
    formats = [
        '%Y-%m-%d',
        '%Y-%m-%d %H:%M:%S',
        '%Y/%m/%d',
        '%Y%m%d',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析日期: {date_str}，支持格式: YYYY-MM-DD, YYYY/MM/DD, YYYYMMDD")


# ============================================================
# CLI 输出格式化
# ============================================================

class OutputFormatter:
    """搜索结果格式化输出"""

    @staticmethod
    def format_text(results: List[FileResult], summary: Dict[str, Any],
                    verbose: bool = False) -> str:
        """人类可读的文本格式输出"""
        lines = []
        sep = '=' * 72

        # 标题
        lines.append(sep)
        lines.append('  HIDRS 文档内容搜索器 - 搜索报告')
        lines.append(sep)

        # 搜索信息
        lines.append(f"  目标路径: {summary['target_path']}")
        if summary.get('keyword'):
            lines.append(f"  关键词:   {summary['keyword']}")
        if summary.get('regex'):
            lines.append(f"  正则:     {summary['regex']}")
        if summary.get('invert_mode'):
            lines.append(f"  模式:     反查（不包含关键词的文件）")
        lines.append(f"  区分大小写: {'是' if summary.get('case_sensitive') else '否'}")
        lines.append('')

        # 统计
        lines.append(f"  扫描文件数:     {summary['files_scanned']}")
        lines.append(f"  匹配文件数:     {summary['files_matched']}")
        lines.append(f"  跳过(二进制):   {summary['files_skipped_binary']}")
        lines.append(f"  跳过(筛选):     {summary['files_skipped_filter']}")
        lines.append(f"  跳过(错误):     {summary['files_skipped_error']}")
        lines.append(f"  总匹配次数:     {summary['total_matches']}")
        lines.append(f"  扫描耗时:       {summary['scan_time_seconds']}s")
        lines.append(sep)

        if not results:
            lines.append('  未找到匹配结果。')
            lines.append(sep)
            return '\n'.join(lines)

        # 结果列表
        for idx, r in enumerate(results, 1):
            lines.append('')
            lines.append(f"  [{idx}] {r.path}")
            meta_parts = [
                f"编码:{r.encoding}",
                f"大小:{format_size(r.size)}",
                f"修改:{datetime.fromtimestamp(r.modified).strftime('%Y-%m-%d %H:%M')}",
            ]
            if r.match_count > 0:
                meta_parts.append(f"匹配:{r.match_count}次")
            if r.translated_name:
                meta_parts.append(f"译名:{r.translated_name}")
            lines.append(f"      {' | '.join(meta_parts)}")

            # 显示匹配详情
            if r.matches and verbose:
                lines.append('      ' + '-' * 50)
                for m in r.matches:
                    # 上文
                    for cl in m.context_before:
                        lines.append(f"        {cl.rstrip()}")
                    # 匹配行高亮
                    line_str = m.line_content.rstrip('\n\r')
                    lines.append(f"   >>>  L{m.line_number}: {line_str}")
                    # 下文
                    for cl in m.context_after:
                        lines.append(f"        {cl.rstrip()}")
                    if m != r.matches[-1]:
                        lines.append('        ...')
            elif r.matches:
                # 简略模式：只显示前3个匹配
                shown = r.matches[:3]
                for m in shown:
                    snippet = m.line_content.rstrip('\n\r')
                    if len(snippet) > 100:
                        snippet = snippet[:100] + '...'
                    lines.append(f"      L{m.line_number}: {snippet}")
                if len(r.matches) > 3:
                    lines.append(f"      ... 还有 {len(r.matches) - 3} 处匹配")

        lines.append('')
        lines.append(sep)
        return '\n'.join(lines)

    @staticmethod
    def format_json(results: List[FileResult], summary: Dict[str, Any]) -> str:
        """Agent 可解析的 JSON 格式输出"""
        data = {
            'summary': summary,
            'results': [r.to_dict() for r in results],
        }
        return json.dumps(data, ensure_ascii=False, indent=2)


# ============================================================
# CLI 入口
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器"""
    parser = argparse.ArgumentParser(
        prog='doc_searcher',
        description='HIDRS 文档内容搜索器 - 类取证工具级别的全盘文本文件关键词搜索',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 在当前目录搜索关键词 "密码"
  python doc_searcher.py search "密码" .

  # 正则搜索邮箱地址
  python doc_searcher.py search -r "[\\w.]+@[\\w.]+" /home/user

  # 反查：找出不含 "copyright" 的文件
  python doc_searcher.py search --invert "copyright" /project

  # 按大小和日期筛选
  python doc_searcher.py search "TODO" . --min-size 1KB --max-size 1MB --after 2025-01-01

  # JSON 输出供 Agent 解析
  python doc_searcher.py search "error" /var/log --json

  # 扫描目录中的所有文本文件（不搜索内容）
  python doc_searcher.py scan /home/user/docs

  # 翻译文件名
  python doc_searcher.py search "数据" . --translate
        """)

    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # ---- search 子命令 ----
    sp_search = subparsers.add_parser('search', help='搜索文件内容')
    sp_search.add_argument('keyword', help='搜索关键词')
    sp_search.add_argument('path', help='搜索路径（目录或盘符）')

    # 搜索模式
    mode_group = sp_search.add_argument_group('搜索模式')
    mode_group.add_argument('-r', '--regex', action='store_true',
                            help='将关键词作为正则表达式')
    mode_group.add_argument('--invert', action='store_true',
                            help='反查模式：查找不包含关键词的文件')
    mode_group.add_argument('-s', '--case-sensitive', action='store_true',
                            help='区分大小写')
    mode_group.add_argument('-C', '--context', type=int, default=0, metavar='N',
                            help='显示匹配行前后 N 行上下文')
    mode_group.add_argument('--max-matches', type=int, default=0, metavar='N',
                            help='每个文件最多记录 N 个匹配（0=不限）')

    # 筛选
    filter_group = sp_search.add_argument_group('筛选条件')
    filter_group.add_argument('--min-size', type=str, default=None,
                              help='最小文件大小，如 1KB, 5MB')
    filter_group.add_argument('--max-size', type=str, default=None,
                              help='最大文件大小，如 100MB')
    filter_group.add_argument('--after', type=str, default=None,
                              help='只搜索此日期之后修改的文件 (YYYY-MM-DD)')
    filter_group.add_argument('--before', type=str, default=None,
                              help='只搜索此日期之前修改的文件 (YYYY-MM-DD)')
    filter_group.add_argument('-i', '--include', type=str, nargs='+', default=None,
                              help='文件名包含模式 (glob)，如 *.py *.txt')
    filter_group.add_argument('-e', '--exclude', type=str, nargs='+', default=None,
                              help='文件名排除模式 (glob)，如 *.log *.tmp')
    filter_group.add_argument('--exclude-dir', type=str, nargs='+', default=None,
                              help='排除目录名，如 .git node_modules')
    filter_group.add_argument('--no-recursive', action='store_true',
                              help='不递归搜索子目录')

    # 排序与输出
    output_group = sp_search.add_argument_group('排序与输出')
    output_group.add_argument('--sort', type=str, default='path',
                              choices=['path', 'name', 'size', 'date', 'matches'],
                              help='排序字段 (默认: path)')
    output_group.add_argument('--desc', action='store_true',
                              help='降序排列')
    output_group.add_argument('--max-results', type=int, default=0, metavar='N',
                              help='最大返回文件数（0=不限）')
    output_group.add_argument('--json', action='store_true',
                              help='JSON 格式输出（供 Agent 解析）')
    output_group.add_argument('-v', '--verbose', action='store_true',
                              help='显示详细匹配上下文')
    output_group.add_argument('--translate', action='store_true',
                              help='启用中英文文件名自动翻译')
    output_group.add_argument('-w', '--workers', type=int, default=4,
                              help='并行搜索线程数 (默认: 4)')

    # ---- scan 子命令 ----
    sp_scan = subparsers.add_parser('scan', help='扫描目录中的所有文本文件（不搜索内容）')
    sp_scan.add_argument('path', help='扫描路径')
    sp_scan.add_argument('--min-size', type=str, default=None)
    sp_scan.add_argument('--max-size', type=str, default=None)
    sp_scan.add_argument('--after', type=str, default=None)
    sp_scan.add_argument('--before', type=str, default=None)
    sp_scan.add_argument('-i', '--include', type=str, nargs='+', default=None)
    sp_scan.add_argument('-e', '--exclude', type=str, nargs='+', default=None)
    sp_scan.add_argument('--exclude-dir', type=str, nargs='+', default=None)
    sp_scan.add_argument('--no-recursive', action='store_true')
    sp_scan.add_argument('--sort', type=str, default='path',
                         choices=['path', 'name', 'size', 'date'])
    sp_scan.add_argument('--desc', action='store_true')
    sp_scan.add_argument('--max-results', type=int, default=0)
    sp_scan.add_argument('--json', action='store_true')
    sp_scan.add_argument('--translate', action='store_true')

    # ---- translate 子命令 ----
    sp_translate = subparsers.add_parser('translate', help='批量翻译文件名（中↔英）')
    sp_translate.add_argument('path', help='目标目录')
    sp_translate.add_argument('--json', action='store_true')

    return parser


def cli_main(argv: Optional[List[str]] = None) -> int:
    """CLI 主入口"""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    # 配置日志
    logging.basicConfig(
        level=logging.WARNING,
        format='%(levelname)s: %(message)s',
    )

    if args.command == 'search':
        return _cmd_search(args)
    elif args.command == 'scan':
        return _cmd_scan(args)
    elif args.command == 'translate':
        return _cmd_translate(args)

    parser.print_help()
    return 0


def _cmd_search(args) -> int:
    """执行 search 子命令"""
    # 解析筛选参数
    min_size = parse_size(args.min_size) if args.min_size else None
    max_size = parse_size(args.max_size) if args.max_size else None
    after = parse_date(args.after) if args.after else None
    before = parse_date(args.before) if args.before else None

    searcher = DocSearcher(
        target_path=args.path,
        keyword=None if args.regex else args.keyword,
        regex_pattern=args.keyword if args.regex else None,
        case_sensitive=args.case_sensitive,
        invert=args.invert,
        context_lines=args.context,
        max_matches_per_file=args.max_matches,
        recursive=not args.no_recursive,
        min_size=min_size,
        max_size=max_size,
        after=after,
        before=before,
        include_patterns=args.include,
        exclude_patterns=args.exclude,
        exclude_dirs=args.exclude_dir,
        sort_by=args.sort,
        sort_reverse=args.desc,
        translate=args.translate,
        max_results=args.max_results,
        workers=args.workers,
    )

    results = searcher.search()
    summary = searcher.get_summary()

    if args.json:
        print(OutputFormatter.format_json(results, summary))
    else:
        print(OutputFormatter.format_text(results, summary, verbose=args.verbose))

    return 0


def _cmd_scan(args) -> int:
    """执行 scan 子命令"""
    min_size = parse_size(args.min_size) if args.min_size else None
    max_size = parse_size(args.max_size) if args.max_size else None
    after = parse_date(args.after) if args.after else None
    before = parse_date(args.before) if args.before else None

    searcher = DocSearcher(
        target_path=args.path,
        recursive=not args.no_recursive,
        min_size=min_size,
        max_size=max_size,
        after=after,
        before=before,
        include_patterns=args.include,
        exclude_patterns=args.exclude,
        exclude_dirs=args.exclude_dir,
        sort_by=args.sort,
        sort_reverse=args.desc,
        translate=args.translate,
        max_results=args.max_results,
    )

    results = searcher.scan_text_files()
    summary = searcher.get_summary()

    if args.json:
        print(OutputFormatter.format_json(results, summary))
    else:
        print(OutputFormatter.format_text(results, summary))

    return 0


def _cmd_translate(args) -> int:
    """执行 translate 子命令"""
    translator = FilenameTranslator()
    if not translator.available:
        print("错误: 翻译库不可用，请安装: pip install deep-translator",
              file=sys.stderr)
        return 1

    target = os.path.abspath(args.path)
    results = []

    for entry in os.scandir(target):
        if entry.is_file():
            original = entry.name
            translated = translator.translate(original)
            if translated and translated != original:
                results.append({
                    'original': original,
                    'translated': translated,
                    'has_chinese': translator.contains_chinese(original),
                })

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        if not results:
            print("无需翻译的文件名。")
        else:
            max_orig = max(len(r['original']) for r in results)
            for r in results:
                direction = 'ZH→EN' if r['has_chinese'] else 'EN→ZH'
                print(f"  [{direction}] {r['original']:<{max_orig}}  →  {r['translated']}")
            print(f"\n  共 {len(results)} 个文件名可翻译。")

    return 0


if __name__ == '__main__':
    sys.exit(cli_main())
