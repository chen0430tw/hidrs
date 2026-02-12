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
import hashlib
import base64
import argparse
import logging
import subprocess
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Set
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

# 文件类型预设 —— --type 快捷选择
FILE_TYPE_PRESETS: Dict[str, List[str]] = {
    'py':       ['*.py', '*.pyw', '*.pyi'],
    'js':       ['*.js', '*.jsx', '*.mjs', '*.cjs'],
    'ts':       ['*.ts', '*.tsx'],
    'web':      ['*.html', '*.htm', '*.css', '*.scss', '*.js', '*.jsx', '*.ts', '*.tsx', '*.vue', '*.svelte'],
    'java':     ['*.java', '*.kt', '*.scala', '*.gradle'],
    'c':        ['*.c', '*.h', '*.cpp', '*.hpp', '*.cc', '*.cxx'],
    'go':       ['*.go'],
    'rust':     ['*.rs'],
    'ruby':     ['*.rb', '*.erb', '*.gemspec'],
    'php':      ['*.php'],
    'shell':    ['*.sh', '*.bash', '*.zsh', '*.fish', '*.bat', '*.cmd', '*.ps1'],
    'config':   ['*.json', '*.yaml', '*.yml', '*.toml', '*.ini', '*.cfg', '*.conf', '*.env', '*.properties'],
    'xml':      ['*.xml', '*.xsl', '*.xsd', '*.svg', '*.plist'],
    'doc':      ['*.md', '*.rst', '*.txt', '*.tex', '*.adoc', '*.org'],
    'data':     ['*.csv', '*.tsv', '*.jsonl', '*.ndjson'],
    'sql':      ['*.sql'],
    'proto':    ['*.proto', '*.graphql'],
    'log':      ['*.log', '*.out', '*.err'],
    'all-text': ['*'],  # 不筛选扩展名，靠 TextDetector 判定
}


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
        """以检测到的编码读取文件内容（小文件一次性读取）"""
        try:
            file_size = os.path.getsize(file_path)
            with open(file_path, 'rb') as f:
                raw = f.read(min(file_size, max_bytes))
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

    @staticmethod
    def iter_lines(file_path: str, encoding: str,
                   max_bytes: int = MAX_FILE_READ_BYTES):
        """
        流式逐行读取文件（大文件优化，不一次性载入内存）

        Yields: (line_number, line_text)  line_number 从 1 开始
        """
        try:
            effective_enc = encoding
            bytes_read = 0
            # 先尝试指定编码，失败则逐个回退
            for try_enc in [encoding] + FALLBACK_ENCODINGS:
                try:
                    with open(file_path, 'r', encoding=try_enc, errors='strict',
                              buffering=8192) as f:
                        for line_num, line in enumerate(f, 1):
                            bytes_read += len(line.encode(try_enc, errors='replace'))
                            if bytes_read > max_bytes:
                                return
                            yield line_num, line.rstrip('\n\r')
                    return  # 成功读完
                except (UnicodeDecodeError, LookupError):
                    continue
            # 最后用 replace 模式兜底
            with open(file_path, 'r', encoding='utf-8', errors='replace',
                      buffering=8192) as f:
                for line_num, line in enumerate(f, 1):
                    yield line_num, line.rstrip('\n\r')
        except (OSError, PermissionError):
            return


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

    # 超过此大小的文件使用流式搜索，避免一次性载入内存卡顿
    STREAM_THRESHOLD = 10 * 1024 * 1024  # 10MB

    @staticmethod
    def search_file(file_path: str, pattern: 're.Pattern',
                    encoding: str, invert: bool = False,
                    context_lines: int = 0,
                    max_matches: int = 0) -> Optional[SearchResult]:
        """对单个文件执行 Python 正则搜索（大文件自动切换流式模式）"""
        try:
            file_size = os.path.getsize(file_path)
        except OSError:
            return None

        # 大文件 + 不需要上下文 → 流式搜索（节省内存，不卡）
        if file_size > PythonBackend.STREAM_THRESHOLD and context_lines == 0:
            return PythonBackend._search_file_stream(
                file_path, pattern, encoding, invert, max_matches)

        # 小文件 或 需要上下文 → 整体读取（上下文需要前后行）
        return PythonBackend._search_file_full(
            file_path, pattern, encoding, invert, context_lines, max_matches)

    @staticmethod
    def _search_file_stream(file_path: str, pattern: 're.Pattern',
                            encoding: str, invert: bool,
                            max_matches: int) -> Optional[SearchResult]:
        """流式搜索：逐行读取不载入整个文件，适合大文件"""
        result = SearchResult(path=file_path, encoding=encoding)
        has_match = False

        for line_num, line in TextDetector.iter_lines(file_path, encoding):
            if pattern.search(line):
                has_match = True
                if not invert:
                    result.matches.append({
                        'line': line_num,
                        'content': line,
                    })
                    if max_matches > 0 and len(result.matches) >= max_matches:
                        break

        if invert:
            return result if not has_match else None
        return result if has_match else None

    @staticmethod
    def _search_file_full(file_path: str, pattern: 're.Pattern',
                          encoding: str, invert: bool,
                          context_lines: int,
                          max_matches: int) -> Optional[SearchResult]:
        """整体读取搜索：支持上下文行，适合中小文件"""
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
# Hash / Base64 对比搜索
# ============================================================

class HashMatcher:
    """
    文件指纹对比：通过 MD5/SHA1/SHA256 或 Base64 内容查找文件

    用途（取证场景）:
    - 已知一个文件的 hash，在目录中找出所有副本
    - 已知 base64 编码的内容，搜索原文或编码形式
    """

    ALGORITHMS = ('md5', 'sha1', 'sha256', 'sha512')

    @staticmethod
    def compute_file_hash(file_path: str, algorithm: str = 'sha256') -> Optional[str]:
        """计算文件 hash"""
        try:
            h = hashlib.new(algorithm)
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest()
        except (OSError, ValueError):
            return None

    @staticmethod
    def find_by_hash(target_path: str, target_hash: str,
                     algorithm: str = 'sha256',
                     exclude_dirs: Optional[Set[str]] = None) -> List[SearchResult]:
        """在目录中查找与给定 hash 匹配的文件"""
        exclude = exclude_dirs or {'.git'}
        target_hash = target_hash.lower().strip()
        results = []

        # 自动检测 hash 算法（按长度）
        if algorithm == 'auto':
            hash_len = len(target_hash)
            algo_by_len = {32: 'md5', 40: 'sha1', 64: 'sha256', 128: 'sha512'}
            algorithm = algo_by_len.get(hash_len, 'sha256')

        for root, dirs, files in os.walk(target_path, topdown=True):
            dirs[:] = [d for d in dirs if d not in exclude]
            for fname in files:
                fpath = os.path.join(root, fname)
                file_hash = HashMatcher.compute_file_hash(fpath, algorithm)
                if file_hash and file_hash == target_hash:
                    r = SearchResult(path=fpath)
                    r.encoding = algorithm
                    r.matches = [{'line': 0, 'content': f'{algorithm}:{file_hash}'}]
                    results.append(r)
        return results

    @staticmethod
    def find_by_base64(target_path: str, query: str,
                       exclude_dirs: Optional[Set[str]] = None) -> List[SearchResult]:
        """
        Base64 双向搜索:
        - 将 query 编码为 base64，在文件中搜索编码后的字符串
        - 将 query 作为 base64 尝试解码，搜索解码后的原文
        """
        exclude = exclude_dirs or {'.git'}
        search_terms = set()

        # 原文
        search_terms.add(query)

        # query → base64 编码
        try:
            encoded = base64.b64encode(query.encode('utf-8')).decode('ascii')
            search_terms.add(encoded)
        except Exception:
            pass

        # query 作为 base64 → 解码为原文
        try:
            decoded = base64.b64decode(query, validate=True).decode('utf-8')
            search_terms.add(decoded)
        except Exception:
            pass

        # 用所有 search_terms 搜索
        pattern = re.compile('|'.join(re.escape(t) for t in search_terms), re.IGNORECASE)
        results = []

        for root, dirs, files in os.walk(target_path, topdown=True):
            dirs[:] = [d for d in dirs if d not in exclude]
            for fname in files:
                fpath = os.path.join(root, fname)
                is_text, enc = TextDetector.is_text_file(fpath)
                if not is_text:
                    continue

                # 流式逐行搜索，不一次性载入大文件
                file_matches = []
                for line_num, line in TextDetector.iter_lines(fpath, enc):
                    m = pattern.search(line)
                    if m:
                        matched_term = m.group()
                        form = 'original'
                        if matched_term != query:
                            try:
                                base64.b64decode(matched_term, validate=True)
                                form = 'base64'
                            except Exception:
                                form = 'decoded'
                        file_matches.append({
                            'line': line_num,
                            'content': line,
                            'match_form': form,
                        })

                if file_matches:
                    r = SearchResult(path=fpath, matches=file_matches, encoding=enc)
                    results.append(r)

        return results


# ============================================================
# 并行分群搜索加速
# ============================================================

def parallel_chunk_search(target_path: str, searcher_factory,
                          max_workers: int = 8) -> List[SearchResult]:
    """
    并行分群搜索：将目录按子目录分 chunk，每个 chunk 并行搜索

    比单线程 os.walk + 逐文件搜索快，因为:
    1. I/O 密集型任务天然适合多线程
    2. 每个子目录独立搜索，无锁竞争
    3. rg 已经内部并行，这里主要加速 Python 回退路径
    """
    # 收集一级子目录作为并行 chunk
    chunks = []
    try:
        for entry in os.scandir(target_path):
            if entry.is_dir() and entry.name != '.git':
                chunks.append(entry.path)
            elif entry.is_file():
                chunks.append(entry.path)  # 根目录下的文件单独一组
    except PermissionError:
        return []

    if not chunks:
        return []

    all_results: List[SearchResult] = []

    with ThreadPoolExecutor(max_workers=min(max_workers, len(chunks))) as executor:
        futures = {}
        for chunk in chunks:
            searcher = searcher_factory(chunk)
            futures[executor.submit(searcher.search)] = chunk

        for future in as_completed(futures):
            try:
                results = future.result()
                all_results.extend(results)
            except Exception as e:
                logger.debug(f"分群搜索出错 {futures[future]}: {e}")

    return all_results


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
                 created_after: Optional[datetime] = None,
                 created_before: Optional[datetime] = None,
                 date_field: str = 'mtime',
                 version_filter: Optional[str] = None,
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
        self.created_after = created_after
        self.created_before = created_before
        self.date_field = date_field  # 'mtime', 'ctime', 'both'
        self.version_filter = version_filter
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

            # 修改日期筛选 (--after / --before)
            if self.after is not None:
                if datetime.fromtimestamp(r.modified) < self.after:
                    continue
            if self.before is not None:
                if datetime.fromtimestamp(r.modified) > self.before:
                    continue

            # 创建日期筛选 (--created-after / --created-before)
            if self.created_after is not None:
                if datetime.fromtimestamp(r.created) < self.created_after:
                    continue
            if self.created_before is not None:
                if datetime.fromtimestamp(r.created) > self.created_before:
                    continue

            # 版本号筛选 (--version)
            if self.version_filter is not None:
                if not self._match_version(r.path, self.version_filter):
                    continue

            filtered.append(r)
        return filtered

    @staticmethod
    def _match_version(file_path: str, version_spec: str) -> bool:
        """
        检查文件路径或内容是否匹配版本号规格

        version_spec 格式:
          "1.2.3"   精确匹配
          ">1.0"    大于
          ">=2.0"   大于等于
          "<3.0"    小于
          "1.x"     1.开头的任意版本
          "1.2.*"   通配
        """
        # 从路径中提取版本号
        m = VERSION_PATTERN.search(file_path)
        if not m:
            return False
        file_ver = m.group(1)

        spec = version_spec.strip()

        # 通配: 1.x, 1.2.*, 2.x.x — 允许后续有更多子版本号
        if 'x' in spec.lower() or '*' in spec:
            pat = spec.lower().replace('.', r'\.').replace('x', r'\d+').replace('*', r'\d+')
            return bool(re.match(pat + r'(\.\d+)*$', file_ver))

        # 比较运算: >=, >, <=, <
        cmp_m = re.match(r'^(>=|<=|>|<)\s*(.+)$', spec)
        if cmp_m:
            op, ver = cmp_m.group(1), cmp_m.group(2)
            cmp = DocSearcher._compare_versions(file_ver, ver)
            if op == '>' and cmp <= 0:
                return False
            if op == '>=' and cmp < 0:
                return False
            if op == '<' and cmp >= 0:
                return False
            if op == '<=' and cmp > 0:
                return False
            return True

        # 精确匹配（前缀）
        return file_ver == spec or file_ver.startswith(spec + '.')

    @staticmethod
    def _compare_versions(a: str, b: str) -> int:
        """比较两个版本号，返回 -1, 0, 1"""
        # 去掉 pre-release 后缀先比数字部分
        a_parts = [int(x) for x in re.split(r'[-+]', a)[0].split('.') if x.isdigit()]
        b_parts = [int(x) for x in re.split(r'[-+]', b)[0].split('.') if x.isdigit()]
        # 补齐长度
        max_len = max(len(a_parts), len(b_parts))
        a_parts.extend([0] * (max_len - len(a_parts)))
        b_parts.extend([0] * (max_len - len(b_parts)))
        for av, bv in zip(a_parts, b_parts):
            if av < bv:
                return -1
            if av > bv:
                return 1
        return 0

    def _sort(self, results: List[SearchResult]) -> List[SearchResult]:
        key_map = {
            'path': lambda r: r.path.lower(),
            'name': lambda r: os.path.basename(r.path).lower(),
            'size': lambda r: r.size,
            'date': lambda r: r.modified,
            'mtime': lambda r: r.modified,
            'ctime': lambda r: r.created,
            'matches': lambda r: r.match_count,
        }
        key_func = key_map.get(self.sort_by, key_map['path'])
        return sorted(results, key=key_func, reverse=self.sort_reverse)

    def get_summary(self) -> Dict[str, Any]:
        summary = {
            'target_path': self.target_path,
            'keyword': self.keyword,
            'regex': self.regex_pattern,
            'invert_mode': self.invert,
            'case_sensitive': self.case_sensitive,
            **self.stats,
        }
        if self.version_filter:
            summary['version_filter'] = self.version_filter
        return summary


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
    """
    解析日期字符串，支持:
    1. 标准格式: YYYY-MM-DD, YYYY/MM/DD, YYYYMMDD, YYYY-MM-DD HH:MM:SS
    2. 快捷符号 (缩写优先):
         td / today       → 今天 00:00
         yd / yesterday   → 昨天 00:00
         tw / thisweek    → 本周一 00:00
         lw / lastweek    → 上周一 00:00
         tm / thismonth   → 本月1日 00:00
         lm / lastmonth   → 上月1日 00:00
         ty / thisyear    → 今年1月1日 00:00
         ly / lastyear    → 去年1月1日 00:00
    3. 相对偏移:
         Nd  → N 天前  (如 3d = 3天前, 7d = 一周前, 30d = 一个月前)
         Nh  → N 小时前 (如 1h, 6h, 24h)
         Nw  → N 周前   (如 1w, 2w)
    4. Unix 时间戳: @1700000000 (以 @ 开头的纯数字)
    """
    s = date_str.strip().lower()
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # 快捷符号表
    shortcuts = {
        'td':        today_start,
        'today':     today_start,
        'yd':        today_start - timedelta(days=1),
        'yesterday': today_start - timedelta(days=1),
        'tw':        today_start - timedelta(days=today_start.weekday()),
        'thisweek':  today_start - timedelta(days=today_start.weekday()),
        'lw':        today_start - timedelta(days=today_start.weekday() + 7),
        'lastweek':  today_start - timedelta(days=today_start.weekday() + 7),
        'tm':        today_start.replace(day=1),
        'thismonth': today_start.replace(day=1),
        'ty':        today_start.replace(month=1, day=1),
        'thisyear':  today_start.replace(month=1, day=1),
    }

    # lm / lastmonth
    if s in ('lm', 'lastmonth'):
        if now.month == 1:
            return today_start.replace(year=now.year - 1, month=12, day=1)
        return today_start.replace(month=now.month - 1, day=1)

    # ly / lastyear
    if s in ('ly', 'lastyear'):
        return today_start.replace(year=now.year - 1, month=1, day=1)

    if s in shortcuts:
        return shortcuts[s]

    # 相对偏移: Nd, Nh, Nw
    rel = re.match(r'^(\d+)\s*(d|h|w)$', s)
    if rel:
        n = int(rel.group(1))
        unit = rel.group(2)
        if unit == 'd':
            return now - timedelta(days=n)
        elif unit == 'h':
            return now - timedelta(hours=n)
        elif unit == 'w':
            return now - timedelta(weeks=n)

    # Unix 时间戳: @1700000000
    if s.startswith('@') and s[1:].isdigit():
        return datetime.fromtimestamp(int(s[1:]))

    # 标准日期格式
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d', '%Y%m%d'):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue

    # 列出所有快捷符号帮助
    raise ValueError(
        f"无法解析日期: {date_str}\n"
        f"支持格式: YYYY-MM-DD | YYYY/MM/DD | YYYYMMDD | @timestamp\n"
        f"快捷符号: td(今天) yd(昨天) tw(本周) lw(上周) tm(本月) lm(上月) "
        f"ty(今年) ly(去年)\n"
        f"相对偏移: 3d(3天前) 7d 30d 1h 6h 24h 1w 2w"
    )


# 版本号正则: v1.2.3, 1.0.0-beta, 2.3.4.5 等
VERSION_PATTERN = re.compile(
    r'(?:^|[/\\])v?(\d+\.\d+(?:\.\d+){0,3}(?:-[\w.]+)?)'
)


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

  # 按文件类型搜索
  python doc_searcher.py search "TODO" . --type py
  python doc_searcher.py search "password" . --type config

  # 日期筛选 (支持快捷符号)
  python doc_searcher.py search "key" . --after td          # 今天修改的
  python doc_searcher.py search "key" . --after 7d          # 最近7天修改的
  python doc_searcher.py search "key" . --after lw --before tw  # 上周修改的
  python doc_searcher.py search "key" . --created-after tm  # 本月创建的
  python doc_searcher.py search "key" . --after @1700000000 # Unix时间戳

  # 版本号筛选
  python doc_searcher.py search "bug" . --version ">1.0"
  python doc_searcher.py search "fix" . --version "2.x"

  # 管道组合
  python doc_searcher.py search "TODO" . --format path | xargs wc -l
  find . -name "*.conf" | python doc_searcher.py search "password" -

  # Hash 对比
  python doc_searcher.py hash abc123def456... /target/dir
  python doc_searcher.py hash abc123def456... /target/dir --algo md5

  # Base64 双向搜索
  python doc_searcher.py base64 "secret_key" /project

  # 并行加速
  python doc_searcher.py search "keyword" /large/dir --parallel 8

日期快捷: td(今天) yd(昨天) tw(本周) lw(上周) tm(本月) lm(上月) ty(今年) ly(去年)
          3d(3天前) 7d 30d 1h 6h 24h 1w 2w @timestamp
文件类型:  py js ts web java c go rust ruby php shell config xml doc data sql log
输出格式:  text grep path path0 csv json custom
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
    sp.add_argument('--after', type=str, default=None,
                    help='修改日期下限 (YYYY-MM-DD 或快捷: td yd tw lw tm lm ty ly 3d 7d 1h @ts)')
    sp.add_argument('--before', type=str, default=None,
                    help='修改日期上限')
    sp.add_argument('--created-after', type=str, default=None,
                    help='创建日期下限 (同 --after 格式)')
    sp.add_argument('--created-before', type=str, default=None,
                    help='创建日期上限')
    sp.add_argument('--version', type=str, default=None, metavar='SPEC',
                    help='版本号筛选 (如 1.2.3, >1.0, >=2.0, 1.x, 1.2.*)')
    sp.add_argument('-i', '--include', type=str, nargs='+', default=None, help='文件名 glob 白名单')
    sp.add_argument('-e', '--exclude', type=str, nargs='+', default=None, help='文件名 glob 黑名单')
    sp.add_argument('--exclude-dir', type=str, nargs='+', default=None, help='排除目录')
    sp.add_argument('--no-recursive', action='store_true', help='不递归')
    sp.add_argument('--sort', default='path',
                    choices=['path', 'name', 'size', 'date', 'mtime', 'ctime', 'matches'])
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
    # 文件类型
    type_names = ', '.join(sorted(FILE_TYPE_PRESETS.keys()))
    sp.add_argument('-t', '--type', default=None, metavar='TYPE',
                    help=f'文件类型预设: {type_names}')
    # 并行加速
    sp.add_argument('--parallel', type=int, default=0, metavar='N',
                    help='并行分群搜索线程数（0=不启用，建议 4-16）')

    # scan
    sp2 = sub.add_parser('scan', help='列出目录下所有文本文件')
    sp2.add_argument('path', help='扫描路径')
    sp2.add_argument('--min-size', type=str, default=None)
    sp2.add_argument('--max-size', type=str, default=None)
    sp2.add_argument('--after', type=str, default=None, help='修改日期下限 (支持快捷: td yd 3d 7d 等)')
    sp2.add_argument('--before', type=str, default=None)
    sp2.add_argument('--created-after', type=str, default=None)
    sp2.add_argument('--created-before', type=str, default=None)
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

    # hash
    sp4 = sub.add_parser('hash', help='通过文件 hash 查找匹配文件（取证用）')
    sp4.add_argument('hash_value', help='目标 hash 值 (MD5/SHA1/SHA256/SHA512)')
    sp4.add_argument('path', help='搜索目录')
    sp4.add_argument('-a', '--algo', default='auto',
                     choices=['auto', 'md5', 'sha1', 'sha256', 'sha512'],
                     help='hash 算法 (auto=按长度自动检测)')
    sp4.add_argument('--json', action='store_true', help='JSON 输出')
    sp4.add_argument('-v', '--verbose', action='store_true')

    # base64
    sp5 = sub.add_parser('base64', help='Base64 双向搜索（同时搜原文和编码形式）')
    sp5.add_argument('query', help='搜索内容（会同时搜索其 base64 编码/解码形式）')
    sp5.add_argument('path', help='搜索目录')
    sp5.add_argument('--json', action='store_true', help='JSON 输出')
    sp5.add_argument('-v', '--verbose', action='store_true')

    # help (详细帮助)
    sp6 = sub.add_parser('help', help='查看详细帮助')
    sp6.add_argument('topic', nargs='?', default='all',
                     help='帮助主题: search date type hash base64 format pipe parallel version all')

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
    elif args.command == 'hash':
        return _cmd_hash(args)
    elif args.command == 'base64':
        return _cmd_base64(args)
    elif args.command == 'help':
        return _cmd_help(args)
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
    created_after = parse_date(args.created_after) if args.created_after else None
    created_before = parse_date(args.created_before) if args.created_before else None

    # --type 预设 → include_patterns
    include_patterns = args.include or []
    if args.type:
        type_key = args.type.lower()
        if type_key not in FILE_TYPE_PRESETS:
            print(f"未知文件类型: {type_key}", file=sys.stderr)
            print(f"可选: {', '.join(sorted(FILE_TYPE_PRESETS.keys()))}", file=sys.stderr)
            return 1
        include_patterns = FILE_TYPE_PRESETS[type_key] + include_patterns

    # 管道输入模式：path 为 - 或 stdin 非终端
    stdin_files = None
    search_path = args.path
    if args.path == '-' or (args.path == '.' and not sys.stdin.isatty()):
        stdin_files = _read_stdin_file_list()
        if not stdin_files:
            print("stdin 中无有效文件路径", file=sys.stderr)
            return 1
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
        created_after=created_after, created_before=created_before,
        version_filter=args.version,
        include_patterns=include_patterns or None,
        exclude_patterns=args.exclude,
        exclude_dirs=args.exclude_dir,
        sort_by=args.sort, sort_reverse=args.desc,
        translate=args.translate,
        max_results=args.max_results,
    )

    # stdin 文件列表模式
    if stdin_files:
        results = _search_file_list(searcher, stdin_files)
        searcher.stats['files_matched'] = len(results)
        searcher.stats['total_matches'] = sum(r.match_count for r in results)
    # 并行分群搜索模式
    elif args.parallel > 0:
        results = _parallel_search(searcher, args)
    else:
        results = searcher.search()

    summary = searcher.get_summary()
    fmt = _resolve_format(args)

    output = OutputFormatter.format_output(
        results, summary,
        fmt=fmt, verbose=args.verbose,
        custom_template=args.format_str,
    )
    if fmt == 'path0':
        sys.stdout.write(output)
    else:
        print(output)
    return 0


def _parallel_search(searcher: DocSearcher, args) -> List[SearchResult]:
    """并行分群搜索：将目录按子目录分 chunk，每个 chunk 独立搜索"""
    target = searcher.target_path
    max_workers = args.parallel

    # 收集一级子目录
    chunks = []
    root_files = []
    try:
        for entry in os.scandir(target):
            if entry.is_dir() and entry.name != '.git' and entry.name not in searcher.exclude_dirs:
                chunks.append(entry.path)
            elif entry.is_file():
                root_files.append(entry.path)
    except PermissionError:
        return []

    if not chunks and not root_files:
        return []

    all_results: List[SearchResult] = []

    def search_chunk(chunk_path: str) -> List[SearchResult]:
        """创建子搜索器搜索一个子目录"""
        sub = DocSearcher(
            target_path=chunk_path,
            keyword=searcher.keyword,
            regex_pattern=searcher.regex_pattern,
            case_sensitive=searcher.case_sensitive,
            invert=searcher.invert,
            context_lines=searcher.context_lines,
            max_matches_per_file=searcher.max_matches_per_file,
            recursive=searcher.recursive,
            min_size=searcher.min_size, max_size=searcher.max_size,
            after=searcher.after, before=searcher.before,
            created_after=searcher.created_after, created_before=searcher.created_before,
            version_filter=searcher.version_filter,
            include_patterns=searcher.include_patterns or None,
            exclude_patterns=list(searcher.exclude_patterns) if searcher.exclude_patterns else None,
            exclude_dirs=list(searcher.exclude_dirs) if searcher.exclude_dirs else None,
            sort_by='path', sort_reverse=False,
        )
        return sub.search()

    with ThreadPoolExecutor(max_workers=min(max_workers, max(len(chunks), 1))) as executor:
        futures = {executor.submit(search_chunk, c): c for c in chunks}
        for future in as_completed(futures):
            try:
                all_results.extend(future.result())
            except Exception as e:
                logger.debug(f"并行搜索出错 {futures[future]}: {e}")

    # 搜索根目录下的文件
    if root_files and searcher._py_pattern:
        for fpath in root_files:
            is_text, enc = TextDetector.is_text_file(fpath)
            if not is_text:
                continue
            r = PythonBackend.search_file(
                fpath, searcher._py_pattern, enc,
                invert=searcher.invert,
                context_lines=searcher.context_lines,
                max_matches=searcher.max_matches_per_file,
            )
            if r:
                all_results.append(r)

    # 统计合并
    searcher.stats['backend'] = f'parallel({max_workers})'
    searcher.stats['files_matched'] = len(all_results)
    searcher.stats['total_matches'] = sum(r.match_count for r in all_results)

    # 应用排序
    all_results = searcher._sort(all_results)
    if searcher.max_results > 0:
        all_results = all_results[:searcher.max_results]
    return all_results


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
    created_after = parse_date(args.created_after) if args.created_after else None
    created_before = parse_date(args.created_before) if args.created_before else None

    searcher = DocSearcher(
        target_path=args.path,
        recursive=not args.no_recursive,
        min_size=min_size, max_size=max_size,
        after=after, before=before,
        created_after=created_after, created_before=created_before,
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


def _cmd_hash(args) -> int:
    """hash 子命令：通过文件 hash 查找匹配文件"""
    target = os.path.abspath(args.path)
    if not os.path.isdir(target):
        print(f"路径不存在: {target}", file=sys.stderr)
        return 1

    results = HashMatcher.find_by_hash(target, args.hash_value, algorithm=args.algo)

    if args.json:
        out = {
            'hash': args.hash_value,
            'algorithm': args.algo,
            'matches': [r.to_dict() for r in results],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if not results:
            print(f"未找到 hash 匹配的文件: {args.hash_value}")
        else:
            print(f"找到 {len(results)} 个匹配文件:")
            for r in results:
                size_str = format_size(r.size)
                print(f"  {r.path}  ({size_str})")
    return 0


def _cmd_base64(args) -> int:
    """base64 子命令：Base64 双向搜索"""
    target = os.path.abspath(args.path)
    if not os.path.isdir(target):
        print(f"路径不存在: {target}", file=sys.stderr)
        return 1

    results = HashMatcher.find_by_base64(target, args.query)

    if args.json:
        out = {
            'query': args.query,
            'matches': [r.to_dict() for r in results],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if not results:
            print(f"未找到 base64 相关匹配: {args.query}")
        else:
            print(f"找到 {len(results)} 个文件包含匹配:")
            for r in results:
                print(f"  {r.path}")
                shown = r.matches[:3] if not args.verbose else r.matches
                for m in shown:
                    form_tag = f" [{m.get('match_form', '')}]" if m.get('match_form') else ''
                    print(f"    L{m.get('line', '?')}: {m.get('content', '')[:80]}{form_tag}")
                if not args.verbose and len(r.matches) > 3:
                    print(f"    ... 还有 {len(r.matches) - 3} 处匹配")
    return 0


def _cmd_help(args) -> int:
    """详细帮助 —— 按主题输出使用说明"""
    topics = {
        'search': """
╔══════════════════════════════════════════════════════════════╗
║  search — 搜索文件内容                                      ║
╚══════════════════════════════════════════════════════════════╝

  基本用法:
    doc_searcher search "关键词" [路径]

  参数:
    关键词          要搜索的文本
    路径            搜索目录（默认当前目录，用 - 从 stdin 读文件列表）
    -r, --regex     关键词作为正则表达式
    --invert        反查：找不包含关键词的文件
    -s              区分大小写
    -C N            显示匹配行前后 N 行上下文
    --max-matches N 每文件最多匹配 N 次
    --max-results N 最多返回 N 个文件
    -v, --verbose   显示完整匹配内容

  示例:
    doc_searcher search "TODO" /project
    doc_searcher search -r "\\bpassw(or)?d\\b" /etc --type config
    doc_searcher search --invert "license" /src --type py
""",

        'date': """
╔══════════════════════════════════════════════════════════════╗
║  日期筛选 — --after / --before / --created-after/before     ║
╚══════════════════════════════════════════════════════════════╝

  --after  DATE    仅保留修改日期 >= DATE 的文件
  --before DATE    仅保留修改日期 <= DATE 的文件
  --created-after  仅保留创建日期 >= DATE 的文件
  --created-before 仅保留创建日期 <= DATE 的文件

  DATE 支持以下格式:

  ┌────────────┬──────────────────────────────┐
  │ 格式        │ 说明                          │
  ├────────────┼──────────────────────────────┤
  │ 2026-02-12 │ 标准日期 YYYY-MM-DD          │
  │ 2026/02/12 │ 斜线分隔                      │
  │ 20260212   │ 紧凑格式                      │
  │ @170000000 │ Unix 时间戳 (秒)              │
  ├────────────┼──────────────────────────────┤
  │ td         │ 今天 00:00 (today)           │
  │ yd         │ 昨天 00:00 (yesterday)       │
  │ tw         │ 本周一 00:00 (this week)     │
  │ lw         │ 上周一 00:00 (last week)     │
  │ tm         │ 本月 1 日 (this month)       │
  │ lm         │ 上月 1 日 (last month)       │
  │ ty         │ 今年 1/1 (this year)         │
  │ ly         │ 去年 1/1 (last year)         │
  ├────────────┼──────────────────────────────┤
  │ 3d         │ 3 天前                        │
  │ 7d         │ 7 天前                        │
  │ 30d        │ 30 天前                       │
  │ 1h         │ 1 小时前                      │
  │ 6h         │ 6 小时前                      │
  │ 1w         │ 1 周前                        │
  │ 2w         │ 2 周前                        │
  └────────────┴──────────────────────────────┘

  示例:
    doc_searcher search "key" . --after td               # 今天修改的
    doc_searcher search "key" . --after 7d               # 最近 7 天
    doc_searcher search "key" . --after lw --before tw   # 上周修改的
    doc_searcher search "key" . --created-after tm       # 本月创建的
    doc_searcher scan . --after 30d --sort mtime --desc  # 近 30 天按修改时间倒序

  排序: --sort mtime (按修改时间), --sort ctime (按创建时间)
""",

        'type': """
╔══════════════════════════════════════════════════════════════╗
║  --type — 文件类型预设                                      ║
╚══════════════════════════════════════════════════════════════╝

  -t TYPE, --type TYPE    按预设类型筛选文件

  ┌──────────┬──────────────────────────────────────────────┐
  │ 类型      │ 包含扩展名                                    │
  ├──────────┼──────────────────────────────────────────────┤
  │ py       │ .py .pyw .pyi                                │
  │ js       │ .js .jsx .mjs .cjs                           │
  │ ts       │ .ts .tsx                                      │
  │ web      │ .html .htm .css .scss .js .ts .vue .svelte   │
  │ java     │ .java .kt .scala .gradle                     │
  │ c        │ .c .h .cpp .hpp .cc .cxx                     │
  │ go       │ .go                                           │
  │ rust     │ .rs                                           │
  │ ruby     │ .rb .erb .gemspec                             │
  │ php      │ .php                                          │
  │ shell    │ .sh .bash .zsh .fish .bat .cmd .ps1           │
  │ config   │ .json .yaml .yml .toml .ini .cfg .conf .env  │
  │ xml      │ .xml .xsl .xsd .svg .plist                   │
  │ doc      │ .md .rst .txt .tex .adoc .org                │
  │ data     │ .csv .tsv .jsonl .ndjson                     │
  │ sql      │ .sql                                          │
  │ proto    │ .proto .graphql                               │
  │ log      │ .log .out .err                                │
  │ all-text │ * (不筛选扩展名，靠内容判定)                    │
  └──────────┴──────────────────────────────────────────────┘

  --type 可与 -i (include) 叠加使用。

  示例:
    doc_searcher search "TODO" . --type py
    doc_searcher search "password" . --type config
    doc_searcher search "SELECT" . --type sql
""",

        'hash': """
╔══════════════════════════════════════════════════════════════╗
║  hash — 文件 hash 指纹对比 (取证用)                         ║
╚══════════════════════════════════════════════════════════════╝

  用法: doc_searcher hash <hash值> <搜索目录> [选项]

  根据文件的 MD5/SHA1/SHA256/SHA512 查找目录中所有副本。
  算法默认按 hash 长度自动检测:
    32字符 → MD5 | 40字符 → SHA1 | 64字符 → SHA256 | 128字符 → SHA512

  选项:
    -a, --algo ALGO   指定算法 (auto/md5/sha1/sha256/sha512)
    --json            JSON 输出
    -v                详细模式

  示例:
    doc_searcher hash d41d8cd98f00b204e9800998ecf8427e /target     # auto=MD5
    doc_searcher hash abc123... /dir --algo sha256 --json
""",

        'base64': """
╔══════════════════════════════════════════════════════════════╗
║  base64 — Base64 双向搜索                                   ║
╚══════════════════════════════════════════════════════════════╝

  用法: doc_searcher base64 <内容> <搜索目录>

  同时搜索三种形式:
    1. 原文           → "secret_key"
    2. 原文的 base64  → "c2VjcmV0X2tleQ=="
    3. 若输入本身是 base64，解码后的原文

  适合取证场景: 在代码中搜索被 base64 编码隐藏的敏感信息。

  示例:
    doc_searcher base64 "admin:password" /project
    doc_searcher base64 "YWRtaW46cGFzc3dvcmQ=" /project --json
""",

        'format': """
╔══════════════════════════════════════════════════════════════╗
║  --format — 输出格式                                        ║
╚══════════════════════════════════════════════════════════════╝

  --format FORMAT   指定输出格式

  ┌────────┬──────────────────────────────────────────────┐
  │ 格式    │ 说明                                          │
  ├────────┼──────────────────────────────────────────────┤
  │ text   │ 人类可读（默认终端格式，带统计和装饰）        │
  │ grep   │ path:line:content（grep 兼容，管道自动切换） │
  │ path   │ 仅文件路径，每行一个                          │
  │ path0  │ 路径以 \\0 分隔（配合 xargs -0）              │
  │ csv    │ CSV 格式 path,line,encoding,size,content      │
  │ json   │ JSON 结构化输出（含统计信息）                 │
  │ custom │ 自定义模板（需配合 --format-str）             │
  └────────┴──────────────────────────────────────────────┘

  --format-str 占位符: {path} {filename} {line} {content}
                       {encoding} {size} {date} {matches}

  快捷标志:
    --json   等同 --format json
    -0       等同 --format path0

  自动检测: stdout 被管道重定向时自动切换为 grep 格式。

  示例:
    doc_searcher search "TODO" . --format path | wc -l
    doc_searcher search "key" . --format csv > results.csv
    doc_searcher search "key" . --format custom --format-str "{filename}:{line} {content}"
""",

        'pipe': """
╔══════════════════════════════════════════════════════════════╗
║  管道组合                                                    ║
╚══════════════════════════════════════════════════════════════╝

  输入管道 (stdin → doc_searcher):
    将其他命令的文件列表输入给 doc_searcher 搜索:
    find /var/log -name "*.log" | doc_searcher search "error" -
    fd ".conf" | doc_searcher search "password" -

  输出管道 (doc_searcher → 其他命令):
    doc_searcher search "TODO" . --format path | xargs wc -l
    doc_searcher search "key" . -0 | xargs -0 rm
    doc_searcher scan . --format path | head -20

  组合示例:
    # 找所有含 TODO 的 Python 文件并统计行数
    doc_searcher search "TODO" . --type py --format path | xargs wc -l

    # 找最近 7 天修改的配置文件中的密码
    doc_searcher search "password" . --type config --after 7d --format grep

    # 用 fzf 交互选择搜索结果
    doc_searcher search "class" . --type py --format path | fzf | xargs code
""",

        'parallel': """
╔══════════════════════════════════════════════════════════════╗
║  --parallel — 并行加速搜索                                   ║
╚══════════════════════════════════════════════════════════════╝

  --parallel N   使用 N 个线程并行搜索（将目录按子目录分 chunk）

  原理: 将搜索目标的一级子目录拆分为 N 个独立任务，并行执行。
  适用场景: 大目录 + Python 回退搜索（rg 本身已内置并行）。

  建议线程数:
    SSD     →  8-16
    HDD     →  4-8
    网络盘  →  2-4

  示例:
    doc_searcher search "keyword" /large/dir --parallel 8
    doc_searcher search "TODO" . --type py --parallel 4
""",

        'version': """
╔══════════════════════════════════════════════════════════════╗
║  --version — 版本号筛选                                      ║
╚══════════════════════════════════════════════════════════════╝

  --version SPEC   仅保留路径中含匹配版本号的文件

  从文件路径中提取版本号（如 v1.2.3, 1.0.0-beta），然后匹配。

  ┌──────────┬──────────────────────────────────────────┐
  │ 规格      │ 含义                                      │
  ├──────────┼──────────────────────────────────────────┤
  │ 1.2.3    │ 精确匹配 1.2.3                            │
  │ 1.2      │ 匹配 1.2 或 1.2.x                        │
  │ >1.0     │ 版本 > 1.0                                │
  │ >=2.0    │ 版本 >= 2.0                               │
  │ <3.0     │ 版本 < 3.0                                │
  │ <=1.5    │ 版本 <= 1.5                               │
  │ 1.x      │ 1.开头的任意版本                           │
  │ 2.3.*    │ 2.3.开头的任意版本                         │
  └──────────┴──────────────────────────────────────────┘

  示例:
    doc_searcher search "bug" /releases --version ">1.0"
    doc_searcher search "fix" /packages --version "2.x"
    doc_searcher scan /node_modules --version ">=3.0"
""",
    }

    topic = args.topic.lower() if args.topic else 'all'

    if topic == 'all':
        # 输出概览
        print("""
╔══════════════════════════════════════════════════════════════╗
║          HIDRS 文档内容搜索器 — 完整帮助                     ║
╚══════════════════════════════════════════════════════════════╝

  子命令:
    search     搜索文件内容（关键词/正则/反查）
    scan       列出目录下所有文本文件
    hash       通过 MD5/SHA 查找文件副本
    base64     Base64 双向搜索
    translate  批量翻译文件名（中↔英）
    help       查看详细帮助

  帮助主题 (doc_searcher help <主题>):
    search     搜索功能详解
    date       日期筛选 + 快捷符号
    type       文件类型预设
    hash       Hash 指纹对比
    base64     Base64 搜索
    format     输出格式
    pipe       管道组合
    parallel   并行加速
    version    版本号筛选

  快速上手:
    doc_searcher search "关键词" /路径          基本搜索
    doc_searcher search "key" . --type py       按类型搜
    doc_searcher search "key" . --after 7d      最近7天
    doc_searcher search "key" . --format json   JSON输出
    doc_searcher hash <sha256> /dir             hash对比
    doc_searcher base64 "secret" /dir           base64搜索

  搜索后端: ripgrep → grep → findstr(Win) → Python (自动选择)
  编码检测: UTF-8, GBK, Big5, Shift_JIS, EUC-KR 等自动识别
""")
        return 0

    if topic in topics:
        print(topics[topic])
    else:
        print(f"未知帮助主题: {topic}")
        print(f"可用主题: {', '.join(sorted(topics.keys()))}")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(cli_main())
