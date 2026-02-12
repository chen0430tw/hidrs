#!/usr/bin/env python3
"""
文档内容搜索器 (Document Content Searcher) - HIDRS
基于 ripgrep/grep 的全盘文本文件关键词搜索，附加编码检测与文件名翻译

设计原则:
  搜索本身交给 rg/grep（不重复造轮子）
  本工具专注于它们做不到的事：
  1. chardet 自动编码检测（rg 只认 UTF-8，遇到 GBK/Big5 会跳过）
  2. 无扩展名文件的文本/二进制判定
  3. 中英文文件名自动翻译
  4. Agent 友好的结构化 JSON 输出
  5. 对 rg 跳过的非 UTF-8 文件做回退搜索

搜索后端优先级: ripgrep → grep → Python 内置

作者: HIDRS Team
日期: 2026-02-12
"""

import os
import re
import sys
import json
import time
import shutil
import fnmatch
import argparse
import logging
import subprocess
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Set
from pathlib import Path

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
# 常量
# ============================================================

TEXT_DETECT_SAMPLE_SIZE = 8192
MAX_FILE_READ_BYTES = 100 * 1024 * 1024  # 100MB

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

FALLBACK_ENCODINGS = [
    'utf-8', 'gbk', 'gb2312', 'gb18030', 'big5',
    'shift_jis', 'euc-jp', 'euc-kr',
    'utf-16', 'utf-16-le', 'utf-16-be',
    'latin-1', 'iso-8859-1', 'ascii',
    'cp1252', 'cp1251', 'cp936',
]


# ============================================================
# 编码检测（rg/grep 做不到的事 #1）
# ============================================================

class TextDetector:
    """文件文本检测器：判定文件是否为文本，并识别编码"""

    ALLOWED_CONTROL_CHARS = {0x09, 0x0A, 0x0D}

    @staticmethod
    def is_text_file(file_path: str, sample_size: int = TEXT_DETECT_SAMPLE_SIZE) -> Tuple[bool, Optional[str]]:
        """
        判定文件是否为文本，返回 (is_text, encoding)
        不依赖扩展名，通过字节内容判定
        """
        try:
            ext = os.path.splitext(file_path)[1].lower()
            if ext in KNOWN_BINARY_EXTENSIONS:
                return False, None

            file_size = os.path.getsize(file_path)
            if file_size == 0:
                return True, 'utf-8'

            with open(file_path, 'rb') as f:
                sample = f.read(min(sample_size, file_size))

            # BOM 检查
            encoding = TextDetector._detect_bom(sample)
            if encoding:
                return True, encoding

            # 空字节 → 可能是二进制或 UTF-16 无 BOM
            null_ratio = sample.count(b'\x00') / len(sample) if sample else 0
            if null_ratio > 0.1:
                encoding = TextDetector._try_utf16_no_bom(sample)
                if encoding:
                    return True, encoding
                return False, None

            # 控制字符过多 → 二进制
            non_text = sum(1 for b in sample if b < 0x20 and b not in TextDetector.ALLOWED_CONTROL_CHARS)
            if len(sample) > 0 and non_text / len(sample) > 0.05:
                return False, None

            # chardet 检测
            if HAS_CHARDET:
                det = chardet.detect(sample)
                if det and det['encoding'] and det.get('confidence', 0) >= 0.5:
                    enc = det['encoding'].lower()
                    try:
                        sample.decode(enc)
                        return True, enc
                    except (UnicodeDecodeError, LookupError):
                        pass

            # 回退逐一尝试
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
        if data[:3] == b'\xef\xbb\xbf':
            return 'utf-8-sig'
        if data[:4] == b'\xff\xfe\x00\x00':
            return 'utf-32-le'
        if data[:4] == b'\x00\x00\xfe\xff':
            return 'utf-32-be'
        if data[:2] == b'\xff\xfe':
            return 'utf-16-le'
        if data[:2] == b'\xfe\xff':
            return 'utf-16-be'
        return None

    @staticmethod
    def _try_utf16_no_bom(data: bytes) -> Optional[str]:
        for enc in ('utf-16-le', 'utf-16-be'):
            try:
                text = data.decode(enc)
                printable = sum(1 for c in text if c.isprintable() or c in '\n\r\t')
                if len(text) > 0 and printable / len(text) > 0.8:
                    return enc
            except (UnicodeDecodeError, LookupError):
                continue
        return None

    @staticmethod
    def read_text_file(file_path: str, encoding: str,
                       max_bytes: int = MAX_FILE_READ_BYTES) -> Optional[str]:
        """以检测到的编码读取文件内容"""
        try:
            with open(file_path, 'rb') as f:
                raw = f.read(min(os.path.getsize(file_path), max_bytes))
            try:
                return raw.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                pass
            for enc in FALLBACK_ENCODINGS:
                try:
                    return raw.decode(enc)
                except (UnicodeDecodeError, LookupError):
                    continue
            return raw.decode('utf-8', errors='replace')
        except (OSError, PermissionError):
            return None


# ============================================================
# 文件名翻译（rg/grep 做不到的事 #2）
# ============================================================

class FilenameTranslator:
    """中英文文件名自动翻译"""

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
        return bool(self._CJK_PATTERN.search(text))

    def translate(self, filename: str) -> Optional[str]:
        """自动翻译文件名（保留扩展名），中→英 / 英→中"""
        if not self._available:
            return None
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
                translated = re.sub(r'[<>:"/\\|?*]', '_', translated.strip())
                result = translated + ext
                if len(self._cache) < self._cache_size:
                    self._cache[filename] = result
                return result
        except Exception as e:
            logger.debug(f"翻译失败 '{filename}': {e}")
        return None


# ============================================================
# 搜索后端
# ============================================================

class SearchResult:
    """统一的搜索结果结构"""

    def __init__(self, path: str, matches: Optional[List[Dict]] = None,
                 encoding: Optional[str] = None):
        self.path = path
        self.matches = matches or []  # [{'line': int, 'content': str}]
        self.encoding = encoding
        self.size = 0
        self.modified = 0.0
        self.created = 0.0
        self.translated_name: Optional[str] = None

        try:
            stat = os.stat(path)
            self.size = stat.st_size
            self.modified = stat.st_mtime
            self.created = stat.st_ctime
        except OSError:
            pass

    @property
    def match_count(self) -> int:
        return len(self.matches)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            'path': self.path,
            'filename': os.path.basename(self.path),
            'encoding': self.encoding,
            'size': self.size,
            'size_display': format_size(self.size),
            'modified': datetime.fromtimestamp(self.modified).isoformat() if self.modified else None,
            'created': datetime.fromtimestamp(self.created).isoformat() if self.created else None,
            'match_count': self.match_count,
        }
        if self.translated_name:
            d['translated_name'] = self.translated_name
        if self.matches:
            d['matches'] = self.matches
        return d


class RipgrepBackend:
    """ripgrep 搜索后端 —— 速度最快，功能最全"""

    def __init__(self):
        self.bin = shutil.which('rg')

    @property
    def available(self) -> bool:
        return self.bin is not None

    def search(self, pattern: str, path: str, *,
               is_regex: bool = False,
               case_sensitive: bool = False,
               invert: bool = False,
               context_lines: int = 0,
               max_matches_per_file: int = 0,
               include_globs: Optional[List[str]] = None,
               exclude_globs: Optional[List[str]] = None,
               max_filesize: Optional[str] = None) -> Tuple[List[SearchResult], Set[str]]:
        """
        调用 rg 搜索，返回 (结果列表, rg已搜索的文件路径集合)
        rg 跳过的非 UTF-8 文件不在结果中，需要回退搜索
        """
        cmd = [self.bin, '--json']

        if not is_regex:
            cmd.append('--fixed-strings')

        if not case_sensitive:
            cmd.append('--ignore-case')

        if invert:
            cmd.append('--files-without-match')

        if context_lines > 0:
            cmd.extend(['-C', str(context_lines)])

        if max_matches_per_file > 0:
            cmd.extend(['--max-count', str(max_matches_per_file)])

        if max_filesize:
            cmd.extend(['--max-filesize', max_filesize])

        # 不跳过隐藏文件（取证场景需要）但跳过 .git
        cmd.extend(['--hidden', '--glob', '!.git/'])

        if include_globs:
            for g in include_globs:
                cmd.extend(['--glob', g])

        if exclude_globs:
            for g in exclude_globs:
                cmd.extend(['--glob', f'!{g}'])

        cmd.extend([pattern, path])

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300
            )
        except subprocess.TimeoutExpired:
            logger.warning("rg 搜索超时 (5分钟)")
            return [], set()
        except FileNotFoundError:
            return [], set()

        return self._parse_json_output(proc.stdout, invert)

    def _parse_json_output(self, output: str, invert: bool) -> Tuple[List[SearchResult], Set[str]]:
        """解析 rg --json 输出"""
        results_by_path: Dict[str, SearchResult] = {}
        searched_files: Set[str] = set()

        for line in output.strip().split('\n'):
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get('type')

            if msg_type == 'match':
                data = msg['data']
                fpath = data['path']['text']
                searched_files.add(fpath)
                line_number = data['line_number']
                line_text = data['lines']['text'].rstrip('\n\r')

                if fpath not in results_by_path:
                    results_by_path[fpath] = SearchResult(path=fpath)
                results_by_path[fpath].matches.append({
                    'line': line_number,
                    'content': line_text,
                })

            elif msg_type == 'context':
                # 上下文行 —— 附加到最近的匹配
                data = msg['data']
                fpath = data['path']['text']
                searched_files.add(fpath)

            elif msg_type == 'begin':
                fpath = msg['data']['path']['text']
                searched_files.add(fpath)

            elif msg_type == 'end':
                fpath = msg['data']['path']['text']
                searched_files.add(fpath)

            elif msg_type == 'summary':
                pass

        # 反查模式：rg --files-without-match 输出的是文件路径（非JSON match）
        if invert and not results_by_path:
            # 反查模式下 rg 输出格式不同，用非 JSON 模式重新处理
            for line in output.strip().split('\n'):
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if msg.get('type') == 'begin':
                        fpath = msg['data']['path']['text']
                        results_by_path[fpath] = SearchResult(path=fpath)
                        searched_files.add(fpath)
                except json.JSONDecodeError:
                    # 可能是纯路径输出
                    if os.path.isfile(line.strip()):
                        fpath = line.strip()
                        results_by_path[fpath] = SearchResult(path=fpath)
                        searched_files.add(fpath)

        return list(results_by_path.values()), searched_files


class GrepBackend:
    """GNU/BSD grep 后备搜索后端（Linux + macOS）"""

    def __init__(self):
        self.bin = shutil.which('grep')
        self._is_gnu = False
        if self.bin:
            try:
                ver = subprocess.run(
                    [self.bin, '--version'], capture_output=True, text=True, timeout=5
                )
                self._is_gnu = 'GNU' in ver.stdout
            except Exception:
                pass

    @property
    def available(self) -> bool:
        return self.bin is not None

    def search(self, pattern: str, path: str, *,
               is_regex: bool = False,
               case_sensitive: bool = False,
               invert: bool = False,
               context_lines: int = 0,
               include_globs: Optional[List[str]] = None,
               exclude_globs: Optional[List[str]] = None) -> List[SearchResult]:
        """调用 grep 搜索（兼容 GNU grep 和 BSD grep）"""
        cmd = [self.bin, '-rn']

        # GNU grep 支持 --binary-files，BSD grep 不支持
        if self._is_gnu:
            cmd.append('--binary-files=without-match')

        if not is_regex:
            cmd.append('--fixed-strings')

        if not case_sensitive:
            cmd.append('--ignore-case')

        if invert:
            cmd.append('--files-without-match')

        if context_lines > 0:
            cmd.extend(['-C', str(context_lines)])

        if include_globs:
            for g in include_globs:
                cmd.extend(['--include', g])

        if exclude_globs:
            for g in exclude_globs:
                cmd.extend(['--exclude', g])

        # --exclude-dir 在 GNU grep 和较新的 BSD grep 上都支持
        cmd.append('--exclude-dir=.git')
        cmd.extend([pattern, path])

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

        return self._parse_output(proc.stdout, invert)

    def _parse_output(self, output: str, invert: bool) -> List[SearchResult]:
        results_by_path: Dict[str, SearchResult] = {}

        if invert:
            for line in output.strip().split('\n'):
                fpath = line.strip()
                if fpath and os.path.isfile(fpath):
                    results_by_path[fpath] = SearchResult(path=fpath)
            return list(results_by_path.values())

        for line in output.strip().split('\n'):
            if not line:
                continue
            # grep -n 输出: filepath:linenum:content
            # Windows 路径可能含 C:\，所以从右边找第二个冒号
            parts = line.split(':', 2)
            if len(parts) >= 3:
                fpath, line_num_str, content = parts[0], parts[1], parts[2]
                try:
                    line_num = int(line_num_str)
                except ValueError:
                    continue
                if fpath not in results_by_path:
                    results_by_path[fpath] = SearchResult(path=fpath)
                results_by_path[fpath].matches.append({
                    'line': line_num,
                    'content': content.rstrip('\n\r'),
                })

        return list(results_by_path.values())


class FindstrBackend:
    """Windows findstr 后备搜索后端"""

    def __init__(self):
        self.bin = shutil.which('findstr') if sys.platform == 'win32' else None

    @property
    def available(self) -> bool:
        return self.bin is not None

    def search(self, pattern: str, path: str, *,
               is_regex: bool = False,
               case_sensitive: bool = False,
               invert: bool = False) -> List[SearchResult]:
        """调用 Windows findstr 搜索"""
        cmd = [self.bin, '/S', '/N']  # /S=递归 /N=显示行号

        if is_regex:
            cmd.append('/R')  # 正则模式
        else:
            cmd.append('/C:' + pattern)  # 字面字符串（带空格也安全）

        if not case_sensitive:
            cmd.append('/I')

        if invert:
            cmd.append('/V')

        if is_regex:
            cmd.append(pattern)

        # findstr 搜索路径用 path\*.*
        search_target = os.path.join(path, '*.*')
        cmd.append(search_target)

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
                # Windows findstr 输出可能是系统编码
                encoding='utf-8', errors='replace',
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

        return self._parse_output(proc.stdout, invert)

    def _parse_output(self, output: str, invert: bool) -> List[SearchResult]:
        results_by_path: Dict[str, SearchResult] = {}

        for line in output.strip().split('\n'):
            if not line:
                continue
            # findstr /N 输出: filepath:linenum:content
            # Windows 路径含 C:\，用正则解析
            m = re.match(r'^(.+?):(\d+):(.*)', line)
            if m:
                fpath, line_num_str, content = m.group(1), m.group(2), m.group(3)
                line_num = int(line_num_str)
                fpath = fpath.strip()
                if fpath not in results_by_path:
                    results_by_path[fpath] = SearchResult(path=fpath)
                if not invert:
                    results_by_path[fpath].matches.append({
                        'line': line_num,
                        'content': content.rstrip('\n\r'),
                    })

        return list(results_by_path.values())


class PythonBackend:
    """Python 内置搜索 —— 最后的回退，专门处理非 UTF-8 文件"""

    @staticmethod
    def search_file(file_path: str, pattern: 're.Pattern',
                    encoding: str, invert: bool = False,
                    context_lines: int = 0,
                    max_matches: int = 0) -> Optional[SearchResult]:
        """对单个文件执行 Python 正则搜索"""
        content = TextDetector.read_text_file(file_path, encoding)
        if content is None:
            return None

        lines = content.split('\n')
        result = SearchResult(path=file_path, encoding=encoding)
        has_match = False

        for idx, line in enumerate(lines):
            if pattern.search(line):
                has_match = True
                if not invert:
                    match_info: Dict[str, Any] = {
                        'line': idx + 1,
                        'content': line.rstrip('\n\r'),
                    }
                    if context_lines > 0:
                        ctx_s = max(0, idx - context_lines)
                        ctx_e = min(len(lines), idx + context_lines + 1)
                        match_info['context_before'] = [
                            l.rstrip('\n\r') for l in lines[ctx_s:idx]
                        ]
                        match_info['context_after'] = [
                            l.rstrip('\n\r') for l in lines[idx + 1:ctx_e]
                        ]
                    result.matches.append(match_info)
                    if max_matches > 0 and len(result.matches) >= max_matches:
                        break

        if invert:
            return result if not has_match else None
        return result if has_match else None


# ============================================================
# 主搜索器（编排层，不重复造轮子）
# ============================================================

class DocSearcher:
    """
    文档内容搜索器 —— 编排 rg/grep + 编码检测 + 翻译

    搜索策略:
    1. 用 rg（或 grep）搜索目录 → 得到 UTF-8 兼容文件的结果
    2. 用 TextDetector 扫描 rg 跳过的文件 → 对非 UTF-8 文本用 Python 回退搜索
    3. 合并结果，附加编码信息和翻译
    """

    def __init__(self, target_path: str, *,
                 keyword: Optional[str] = None,
                 regex_pattern: Optional[str] = None,
                 case_sensitive: bool = False,
                 invert: bool = False,
                 context_lines: int = 0,
                 max_matches_per_file: int = 0,
                 recursive: bool = True,
                 min_size: Optional[int] = None,
                 max_size: Optional[int] = None,
                 after: Optional[datetime] = None,
                 before: Optional[datetime] = None,
                 include_patterns: Optional[List[str]] = None,
                 exclude_patterns: Optional[List[str]] = None,
                 exclude_dirs: Optional[List[str]] = None,
                 sort_by: str = 'path',
                 sort_reverse: bool = False,
                 translate: bool = False,
                 max_results: int = 0):

        self.target_path = os.path.abspath(target_path)
        self.keyword = keyword
        self.regex_pattern = regex_pattern
        self.pattern_str = regex_pattern or keyword or ''
        self.is_regex = regex_pattern is not None
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
        self.exclude_dirs = set(exclude_dirs or [])
        self.sort_by = sort_by
        self.sort_reverse = sort_reverse
        self.max_results = max_results

        # 后端 (rg → grep → findstr → python)
        self._rg = RipgrepBackend()
        self._grep = GrepBackend()
        self._findstr = FindstrBackend()

        # 编译 Python 回退用的正则
        flags = 0 if case_sensitive else re.IGNORECASE
        if self.pattern_str:
            pat = self.pattern_str if self.is_regex else re.escape(self.pattern_str)
            self._py_pattern = re.compile(pat, flags)
        else:
            self._py_pattern = None

        # 翻译器
        self._translator: Optional[FilenameTranslator] = None
        if translate:
            self._translator = FilenameTranslator()
            if not self._translator.available:
                logger.warning("翻译库不可用，请安装: pip install deep-translator")

        self.stats = {
            'backend': 'unknown',
            'files_scanned': 0,
            'files_matched': 0,
            'files_fallback_searched': 0,
            'total_matches': 0,
            'scan_time_seconds': 0.0,
        }

    def search(self) -> List[SearchResult]:
        """执行搜索"""
        if not self.pattern_str:
            return self.scan_text_files()

        start = time.time()
        results: List[SearchResult] = []

        if self._rg.available:
            results = self._search_with_rg()
        elif self._grep.available:
            results = self._search_with_grep()
        elif self._findstr.available:
            results = self._search_with_findstr()
        else:
            results = self._search_with_python()

        # 应用 Python 层面的筛选（大小、日期等 rg 不直接支持的）
        results = self._apply_filters(results)

        # 编码检测（为每个结果附加编码信息）
        for r in results:
            if r.encoding is None:
                _, enc = TextDetector.is_text_file(r.path)
                r.encoding = enc or 'utf-8'

        # 排序
        results = self._sort(results)

        # 限制结果数
        if self.max_results > 0:
            results = results[:self.max_results]

        # 翻译
        if self._translator and self._translator.available:
            for r in results:
                r.translated_name = self._translator.translate(os.path.basename(r.path))

        self.stats['files_matched'] = len(results)
        self.stats['total_matches'] = sum(r.match_count for r in results)
        self.stats['scan_time_seconds'] = round(time.time() - start, 3)
        return results

    def scan_text_files(self) -> List[SearchResult]:
        """扫描目录下所有文本文件（不搜索内容）"""
        start = time.time()
        self.stats['backend'] = 'scan'
        results: List[SearchResult] = []

        for root, dirs, files in os.walk(self.target_path, topdown=True):
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs and d != '.git']
            if not self.recursive:
                dirs.clear()

            for fname in files:
                fpath = os.path.join(root, fname)
                is_text, enc = TextDetector.is_text_file(fpath)
                self.stats['files_scanned'] += 1
                if is_text:
                    r = SearchResult(path=fpath, encoding=enc)
                    results.append(r)

        results = self._apply_filters(results)
        results = self._sort(results)

        if self.max_results > 0:
            results = results[:self.max_results]

        if self._translator and self._translator.available:
            for r in results:
                r.translated_name = self._translator.translate(os.path.basename(r.path))

        self.stats['files_matched'] = len(results)
        self.stats['scan_time_seconds'] = round(time.time() - start, 3)
        return results

    def _search_with_rg(self) -> List[SearchResult]:
        """rg 搜索 + Python 回退非 UTF-8 文件"""
        self.stats['backend'] = 'ripgrep'

        # rg 支持 --max-filesize 但不支持 min-size/日期筛选 → 后续 Python 过滤
        max_fs = None
        if self.max_size:
            max_fs = format_size(self.max_size).replace(' ', '')

        rg_results, searched_files = self._rg.search(
            self.pattern_str, self.target_path,
            is_regex=self.is_regex,
            case_sensitive=self.case_sensitive,
            invert=self.invert,
            context_lines=self.context_lines,
            max_matches_per_file=self.max_matches_per_file,
            include_globs=self.include_patterns,
            exclude_globs=self.exclude_patterns,
            max_filesize=max_fs,
        )
        self.stats['files_scanned'] = len(searched_files)

        # 回退搜索：找出 rg 跳过的非 UTF-8 文本文件
        if self._py_pattern:
            fallback_results = self._fallback_search_non_utf8(searched_files)
            rg_results.extend(fallback_results)

        return rg_results

    def _search_with_grep(self) -> List[SearchResult]:
        """grep 搜索"""
        self.stats['backend'] = 'grep'
        results = self._grep.search(
            self.pattern_str, self.target_path,
            is_regex=self.is_regex,
            case_sensitive=self.case_sensitive,
            invert=self.invert,
            context_lines=self.context_lines,
            include_globs=self.include_patterns,
            exclude_globs=self.exclude_patterns,
        )
        self.stats['files_scanned'] = len(results)
        return results

    def _search_with_findstr(self) -> List[SearchResult]:
        """Windows findstr 搜索"""
        self.stats['backend'] = 'findstr'
        results = self._findstr.search(
            self.pattern_str, self.target_path,
            is_regex=self.is_regex,
            case_sensitive=self.case_sensitive,
            invert=self.invert,
        )
        self.stats['files_scanned'] = len(results)
        return results

    def _search_with_python(self) -> List[SearchResult]:
        """纯 Python 搜索（最后的回退）"""
        self.stats['backend'] = 'python'
        results = []

        if not self._py_pattern:
            return results

        for root, dirs, files in os.walk(self.target_path, topdown=True):
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs and d != '.git']
            if not self.recursive:
                dirs.clear()

            for fname in files:
                fpath = os.path.join(root, fname)
                is_text, enc = TextDetector.is_text_file(fpath)
                self.stats['files_scanned'] += 1
                if not is_text:
                    continue

                r = PythonBackend.search_file(
                    fpath, self._py_pattern, enc,
                    invert=self.invert,
                    context_lines=self.context_lines,
                    max_matches=self.max_matches_per_file,
                )
                if r:
                    results.append(r)

        return results

    def _fallback_search_non_utf8(self, already_searched: Set[str]) -> List[SearchResult]:
        """对 rg 跳过的非 UTF-8 文本文件做 Python 回退搜索"""
        results = []

        for root, dirs, files in os.walk(self.target_path, topdown=True):
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs and d != '.git']
            if not self.recursive:
                dirs.clear()

            for fname in files:
                fpath = os.path.join(root, fname)
                if fpath in already_searched:
                    continue

                # 应用 glob 筛选
                if self.include_patterns:
                    if not any(fnmatch.fnmatch(fname, p) for p in self.include_patterns):
                        continue
                if self.exclude_patterns:
                    if any(fnmatch.fnmatch(fname, p) for p in self.exclude_patterns):
                        continue

                is_text, enc = TextDetector.is_text_file(fpath)
                if not is_text:
                    continue

                self.stats['files_fallback_searched'] += 1
                r = PythonBackend.search_file(
                    fpath, self._py_pattern, enc,
                    invert=self.invert,
                    context_lines=self.context_lines,
                    max_matches=self.max_matches_per_file,
                )
                if r:
                    results.append(r)

        return results

    def _apply_filters(self, results: List[SearchResult]) -> List[SearchResult]:
        """应用 rg/grep 不支持的筛选条件"""
        filtered = []
        for r in results:
            if self.min_size is not None and r.size < self.min_size:
                continue
            if self.max_size is not None and r.size > self.max_size:
                continue
            if self.after is not None:
                if datetime.fromtimestamp(r.modified) < self.after:
                    continue
            if self.before is not None:
                if datetime.fromtimestamp(r.modified) > self.before:
                    continue
            filtered.append(r)
        return filtered

    def _sort(self, results: List[SearchResult]) -> List[SearchResult]:
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
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}PB"


def parse_size(size_str: str) -> int:
    size_str = size_str.strip().upper()
    units = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
    for unit, multiplier in sorted(units.items(), key=lambda x: -len(x[0])):
        if size_str.endswith(unit):
            return int(float(size_str[:-len(unit)].strip()) * multiplier)
    return int(size_str)


def parse_date(date_str: str) -> datetime:
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d', '%Y%m%d'):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析日期: {date_str}，支持: YYYY-MM-DD, YYYY/MM/DD, YYYYMMDD")


# ============================================================
# CLI 输出格式化
# ============================================================

class OutputFormatter:
    """
    输出格式化器

    预设格式 (--format):
      grep     grep 兼容格式: path:line:content（可直接管道给其他工具）
      path     仅输出文件路径，每行一个（管道友好）
      path0    路径以 \\0 分隔（配合 xargs -0）
      csv      CSV 格式: path,line,encoding,content
      custom   自定义模板，用 {path} {line} {content} {encoding} {size} {filename} {date} 占位

    管道检测:
      stdout 不是终端时自动切换为 grep 格式（无装饰、无统计头）
    """

    # 预设格式名
    PRESETS = ('grep', 'path', 'path0', 'csv', 'json', 'text')

    @staticmethod
    def is_piped() -> bool:
        """检测 stdout 是否被管道/重定向（不是终端）"""
        return not sys.stdout.isatty()

    @staticmethod
    def format_output(results: List[SearchResult], summary: Dict[str, Any],
                      fmt: str = 'text', verbose: bool = False,
                      custom_template: Optional[str] = None) -> str:
        """统一输出入口"""
        if fmt == 'json':
            return OutputFormatter.format_json(results, summary)
        elif fmt == 'grep':
            return OutputFormatter.format_grep(results)
        elif fmt == 'path':
            return OutputFormatter.format_paths(results, separator='\n')
        elif fmt == 'path0':
            return OutputFormatter.format_paths(results, separator='\0')
        elif fmt == 'csv':
            return OutputFormatter.format_csv(results)
        elif fmt == 'custom' and custom_template:
            return OutputFormatter.format_custom(results, custom_template)
        else:
            return OutputFormatter.format_text(results, summary, verbose)

    @staticmethod
    def format_grep(results: List[SearchResult]) -> str:
        """grep 兼容格式: path:line:content — 可直接管道给 awk/sed/cut 等"""
        lines = []
        for r in results:
            if r.matches:
                for m in r.matches:
                    lines.append(f"{r.path}:{m.get('line', 0)}:{m.get('content', '')}")
            else:
                lines.append(r.path)
        return '\n'.join(lines)

    @staticmethod
    def format_paths(results: List[SearchResult], separator: str = '\n') -> str:
        """仅输出路径 — 管道给 xargs / while read 等"""
        return separator.join(r.path for r in results)

    @staticmethod
    def format_csv(results: List[SearchResult]) -> str:
        """CSV 格式输出"""
        lines = ['path,line,encoding,size,content']
        for r in results:
            if r.matches:
                for m in r.matches:
                    content = m.get('content', '').replace('"', '""')
                    lines.append(
                        f'"{r.path}",{m.get("line", 0)},"{r.encoding or ""}",'
                        f'{r.size},"{content}"'
                    )
            else:
                lines.append(f'"{r.path}",,"{r.encoding or ""}",{r.size},')
        return '\n'.join(lines)

    @staticmethod
    def format_custom(results: List[SearchResult], template: str) -> str:
        """
        自定义模板格式

        占位符: {path} {filename} {line} {content} {encoding} {size} {date} {matches}
        示例: --format-str "{path}\t{line}\t{content}"
        """
        lines = []
        for r in results:
            date_str = (datetime.fromtimestamp(r.modified).strftime('%Y-%m-%d %H:%M')
                        if r.modified else '')
            if r.matches:
                for m in r.matches:
                    line = template.format(
                        path=r.path,
                        filename=os.path.basename(r.path),
                        line=m.get('line', ''),
                        content=m.get('content', ''),
                        encoding=r.encoding or '',
                        size=r.size,
                        date=date_str,
                        matches=r.match_count,
                    )
                    lines.append(line)
            else:
                line = template.format(
                    path=r.path,
                    filename=os.path.basename(r.path),
                    line='',
                    content='',
                    encoding=r.encoding or '',
                    size=r.size,
                    date=date_str,
                    matches=r.match_count,
                )
                lines.append(line)
        return '\n'.join(lines)

    @staticmethod
    def format_text(results: List[SearchResult], summary: Dict[str, Any],
                    verbose: bool = False) -> str:
        """人类可读格式（终端交互用）"""
        lines = []
        sep = '=' * 72

        lines.append(sep)
        lines.append('  HIDRS 文档内容搜索器')
        lines.append(sep)
        lines.append(f"  目标路径: {summary['target_path']}")
        if summary.get('keyword'):
            lines.append(f"  关键词:   {summary['keyword']}")
        if summary.get('regex'):
            lines.append(f"  正则:     {summary['regex']}")
        if summary.get('invert_mode'):
            lines.append(f"  模式:     反查（不包含关键词的文件）")
        lines.append(f"  后端:     {summary.get('backend', 'unknown')}")
        lines.append(f"  扫描: {summary['files_scanned']} | "
                     f"匹配: {summary['files_matched']} | "
                     f"总命中: {summary['total_matches']} | "
                     f"回退搜索: {summary.get('files_fallback_searched', 0)} | "
                     f"耗时: {summary['scan_time_seconds']}s")
        lines.append(sep)

        if not results:
            lines.append('  未找到匹配结果。')
            lines.append(sep)
            return '\n'.join(lines)

        for idx, r in enumerate(results, 1):
            lines.append('')
            lines.append(f"  [{idx}] {r.path}")
            meta = [
                f"编码:{r.encoding or '?'}",
                f"大小:{format_size(r.size)}",
                f"修改:{datetime.fromtimestamp(r.modified).strftime('%Y-%m-%d %H:%M') if r.modified else '?'}",
            ]
            if r.match_count > 0:
                meta.append(f"匹配:{r.match_count}次")
            if r.translated_name:
                meta.append(f"译名:{r.translated_name}")
            lines.append(f"      {' | '.join(meta)}")

            if r.matches:
                shown = r.matches if verbose else r.matches[:3]
                for m in shown:
                    content = m.get('content', '')
                    if not verbose and len(content) > 100:
                        content = content[:100] + '...'
                    lines.append(f"      L{m.get('line', '?')}: {content}")
                    if verbose:
                        for cl in m.get('context_before', []):
                            lines.append(f"        {cl}")
                        for cl in m.get('context_after', []):
                            lines.append(f"        {cl}")
                if not verbose and len(r.matches) > 3:
                    lines.append(f"      ... 还有 {len(r.matches) - 3} 处匹配")

        lines.append('')
        lines.append(sep)
        return '\n'.join(lines)

    @staticmethod
    def format_json(results: List[SearchResult], summary: Dict[str, Any]) -> str:
        return json.dumps({
            'summary': summary,
            'results': [r.to_dict() for r in results],
        }, ensure_ascii=False, indent=2)


# ============================================================
# CLI
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='doc_searcher',
        description='HIDRS 文档内容搜索器 (基于 rg/grep + chardet 编码检测 + 文件名翻译)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 基本搜索
  python doc_searcher.py search "密码" /home/user
  python doc_searcher.py search -r "[\\w.]+@[\\w.]+" /project
  python doc_searcher.py search --invert "copyright" /project

  # 管道组合
  python doc_searcher.py search "TODO" . --format path | xargs wc -l
  python doc_searcher.py search "error" . --format grep | sort -t: -k1
  python doc_searcher.py search "key" . -0 | xargs -0 ls -la
  find . -name "*.conf" | python doc_searcher.py search "password" -

  # 自定义输出格式
  python doc_searcher.py search "def " . --format custom --format-str "{filename}:{line} {content}"

  # 格式化输出
  python doc_searcher.py search "TODO" . --format csv > results.csv
  python doc_searcher.py search "error" /var/log --json | jq '.results[].path'

输出格式 (--format):
  text     人类可读（默认，终端交互）
  grep     path:line:content（兼容 grep，管道友好）
  path     仅路径，每行一个
  path0    路径以 \\0 分隔（配合 xargs -0）
  csv      CSV 格式
  json     JSON 格式
  custom   自定义模板（需配合 --format-str）

注: stdout 被管道/重定向时自动切换为 grep 格式
        """)

    sub = parser.add_subparsers(dest='command', help='子命令')

    # search
    sp = sub.add_parser('search', help='搜索文件内容')
    sp.add_argument('keyword', help='搜索关键词')
    sp.add_argument('path', nargs='?', default='.',
                    help='搜索路径（用 - 从 stdin 读取文件列表）')
    sp.add_argument('-r', '--regex', action='store_true', help='关键词作为正则表达式')
    sp.add_argument('--invert', action='store_true', help='反查：查找不包含关键词的文件')
    sp.add_argument('-s', '--case-sensitive', action='store_true', help='区分大小写')
    sp.add_argument('-C', '--context', type=int, default=0, metavar='N', help='上下文行数')
    sp.add_argument('--max-matches', type=int, default=0, metavar='N', help='每文件最大匹配数')
    sp.add_argument('--min-size', type=str, default=None, help='最小文件大小 (如 1KB, 5MB)')
    sp.add_argument('--max-size', type=str, default=None, help='最大文件大小')
    sp.add_argument('--after', type=str, default=None, help='修改日期下限 (YYYY-MM-DD)')
    sp.add_argument('--before', type=str, default=None, help='修改日期上限')
    sp.add_argument('-i', '--include', type=str, nargs='+', default=None, help='文件名 glob 白名单')
    sp.add_argument('-e', '--exclude', type=str, nargs='+', default=None, help='文件名 glob 黑名单')
    sp.add_argument('--exclude-dir', type=str, nargs='+', default=None, help='排除目录')
    sp.add_argument('--no-recursive', action='store_true', help='不递归')
    sp.add_argument('--sort', default='path', choices=['path', 'name', 'size', 'date', 'matches'])
    sp.add_argument('--desc', action='store_true', help='降序')
    sp.add_argument('--max-results', type=int, default=0, metavar='N')
    sp.add_argument('-v', '--verbose', action='store_true', help='详细输出')
    sp.add_argument('--translate', action='store_true', help='文件名中英翻译')
    # 输出格式
    sp.add_argument('--json', action='store_true', help='JSON 输出（等同 --format json）')
    sp.add_argument('-0', '--null', action='store_true',
                    help='路径以 \\0 分隔输出（等同 --format path0，配合 xargs -0）')
    sp.add_argument('--format', default=None,
                    choices=['text', 'grep', 'path', 'path0', 'csv', 'json', 'custom'],
                    help='输出格式（默认: text，管道时自动切 grep）')
    sp.add_argument('--format-str', default=None, metavar='TEMPLATE',
                    help='自定义格式模板，占位符: {path} {filename} {line} {content} '
                         '{encoding} {size} {date} {matches}')

    # scan
    sp2 = sub.add_parser('scan', help='列出目录下所有文本文件')
    sp2.add_argument('path', help='扫描路径')
    sp2.add_argument('--min-size', type=str, default=None)
    sp2.add_argument('--max-size', type=str, default=None)
    sp2.add_argument('--after', type=str, default=None)
    sp2.add_argument('--before', type=str, default=None)
    sp2.add_argument('-i', '--include', type=str, nargs='+', default=None)
    sp2.add_argument('-e', '--exclude', type=str, nargs='+', default=None)
    sp2.add_argument('--exclude-dir', type=str, nargs='+', default=None)
    sp2.add_argument('--no-recursive', action='store_true')
    sp2.add_argument('--sort', default='path', choices=['path', 'name', 'size', 'date'])
    sp2.add_argument('--desc', action='store_true')
    sp2.add_argument('--max-results', type=int, default=0)
    sp2.add_argument('--translate', action='store_true')
    sp2.add_argument('--json', action='store_true', help='JSON 输出')
    sp2.add_argument('-0', '--null', action='store_true', help='\\0 分隔输出')
    sp2.add_argument('--format', default=None,
                     choices=['text', 'path', 'path0', 'csv', 'json'],
                     help='输出格式')
    sp2.add_argument('-v', '--verbose', action='store_true', help='详细输出')

    # translate
    sp3 = sub.add_parser('translate', help='批量翻译文件名（中↔英）')
    sp3.add_argument('path', help='目标目录')
    sp3.add_argument('--json', action='store_true')

    return parser


def cli_main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')

    if args.command == 'search':
        return _cmd_search(args)
    elif args.command == 'scan':
        return _cmd_scan(args)
    elif args.command == 'translate':
        return _cmd_translate(args)
    return 0


def _resolve_format(args) -> str:
    """决定输出格式：显式指定 > 快捷标志 > 管道自动检测 > text"""
    if args.format:
        return args.format
    if args.json:
        return 'json'
    if getattr(args, 'null', False):
        return 'path0'
    # stdout 被管道/重定向时自动切换为 grep 格式
    if OutputFormatter.is_piped():
        return 'grep'
    return 'text'


def _read_stdin_file_list() -> List[str]:
    """从 stdin 读取文件路径列表（支持换行和 \\0 分隔）"""
    raw = sys.stdin.read()
    # 同时支持 \n 和 \0 分隔
    if '\0' in raw:
        paths = raw.split('\0')
    else:
        paths = raw.split('\n')
    return [p.strip() for p in paths if p.strip() and os.path.isfile(p.strip())]


def _cmd_search(args) -> int:
    min_size = parse_size(args.min_size) if args.min_size else None
    max_size = parse_size(args.max_size) if args.max_size else None
    after = parse_date(args.after) if args.after else None
    before = parse_date(args.before) if args.before else None

    # 管道输入模式：path 为 - 或 stdin 非终端
    stdin_files = None
    search_path = args.path
    if args.path == '-' or (args.path == '.' and not sys.stdin.isatty()):
        stdin_files = _read_stdin_file_list()
        if not stdin_files:
            print("stdin 中无有效文件路径", file=sys.stderr)
            return 1
        # 用第一个文件的目录做 target，后续用文件列表覆盖
        search_path = os.path.dirname(stdin_files[0]) or '.'

    searcher = DocSearcher(
        target_path=search_path,
        keyword=None if args.regex else args.keyword,
        regex_pattern=args.keyword if args.regex else None,
        case_sensitive=args.case_sensitive,
        invert=args.invert,
        context_lines=args.context,
        max_matches_per_file=args.max_matches,
        recursive=not args.no_recursive,
        min_size=min_size, max_size=max_size,
        after=after, before=before,
        include_patterns=args.include,
        exclude_patterns=args.exclude,
        exclude_dirs=args.exclude_dir,
        sort_by=args.sort, sort_reverse=args.desc,
        translate=args.translate,
        max_results=args.max_results,
    )

    # stdin 文件列表模式：直接搜索指定文件
    if stdin_files:
        results = _search_file_list(searcher, stdin_files)
        searcher.stats['files_matched'] = len(results)
        searcher.stats['total_matches'] = sum(r.match_count for r in results)
    else:
        results = searcher.search()

    summary = searcher.get_summary()
    fmt = _resolve_format(args)

    output = OutputFormatter.format_output(
        results, summary,
        fmt=fmt, verbose=args.verbose,
        custom_template=args.format_str,
    )
    # path0 格式不要加末尾换行
    if fmt == 'path0':
        sys.stdout.write(output)
    else:
        print(output)
    return 0


def _search_file_list(searcher: DocSearcher, files: List[str]) -> List[SearchResult]:
    """对 stdin 传入的文件列表逐个搜索"""
    results = []
    for fpath in files:
        is_text, enc = TextDetector.is_text_file(fpath)
        searcher.stats['files_scanned'] += 1
        if not is_text:
            continue
        if searcher._py_pattern:
            r = PythonBackend.search_file(
                fpath, searcher._py_pattern, enc,
                invert=searcher.invert,
                context_lines=searcher.context_lines,
                max_matches=searcher.max_matches_per_file,
            )
            if r:
                results.append(r)
        else:
            results.append(SearchResult(path=fpath, encoding=enc))
    return results


def _cmd_scan(args) -> int:
    min_size = parse_size(args.min_size) if args.min_size else None
    max_size = parse_size(args.max_size) if args.max_size else None
    after = parse_date(args.after) if args.after else None
    before = parse_date(args.before) if args.before else None

    searcher = DocSearcher(
        target_path=args.path,
        recursive=not args.no_recursive,
        min_size=min_size, max_size=max_size,
        after=after, before=before,
        include_patterns=args.include,
        exclude_patterns=args.exclude,
        exclude_dirs=args.exclude_dir,
        sort_by=args.sort, sort_reverse=args.desc,
        translate=args.translate,
        max_results=args.max_results,
    )

    results = searcher.scan_text_files()
    summary = searcher.get_summary()

    # scan 也支持格式选择
    fmt = _resolve_format(args)
    output = OutputFormatter.format_output(
        results, summary, fmt=fmt,
        verbose=getattr(args, 'verbose', False),
    )
    if fmt == 'path0':
        sys.stdout.write(output)
    else:
        print(output)
    return 0


def _cmd_translate(args) -> int:
    translator = FilenameTranslator()
    if not translator.available:
        print("错误: 翻译库不可用，请安装: pip install deep-translator", file=sys.stderr)
        return 1

    target = os.path.abspath(args.path)
    results = []
    for entry in os.scandir(target):
        if entry.is_file():
            translated = translator.translate(entry.name)
            if translated and translated != entry.name:
                results.append({
                    'original': entry.name,
                    'translated': translated,
                    'has_chinese': translator.contains_chinese(entry.name),
                })

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        if not results:
            print("无需翻译的文件名。")
        else:
            w = max(len(r['original']) for r in results)
            for r in results:
                d = 'ZH→EN' if r['has_chinese'] else 'EN→ZH'
                print(f"  [{d}] {r['original']:<{w}}  →  {r['translated']}")
            print(f"\n  共 {len(results)} 个文件名可翻译。")
    return 0


if __name__ == '__main__':
    sys.exit(cli_main())
