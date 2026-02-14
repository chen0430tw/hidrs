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

搜索后端优先级: ripgrep -> grep -> Python 内置

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

# 快速 JSON 解析: orjson > ujson > 标准库 json
_json_lib_name = 'json'  # 用于 debug 输出
try:
    import orjson as _fast_json
    _json_lib_name = 'orjson'
except ImportError:
    try:
        import ujson as _fast_json
        _json_lib_name = 'ujson'
    except ImportError:
        _fast_json = json  # type: ignore[assignment]

# 内存映射
import mmap
import atexit

logger = logging.getLogger(__name__)

# ============================================================
# Windows 控制台 UTF-8 强制（解决 GBK/cp936 中文乱码）
# ============================================================
if sys.platform == 'win32':
    # reconfigure（Python 3.7+）让 stdout/stderr 直接输出 UTF-8
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        # 旧版 Python 或特殊环境，设环境变量让子进程也用 UTF-8
        os.environ.setdefault('PYTHONUTF8', '1')
        os.environ.setdefault('PYTHONIOENCODING', 'utf-8')


# ============================================================
# 安全输出（编码不兼容时优雅降级）
# ============================================================

def safe_print(*args, **kwargs):
    """print() 的安全替代，自动处理 Windows 控制台编码问题。

    支持 file=sys.stderr 等参数，回退时使用目标流的 encoding。
    """
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        # 回退：把不可编码的字符替换为 ?
        target = kwargs.get('file', sys.stdout)
        enc = getattr(target, 'encoding', None) or 'utf-8'
        text = ' '.join(str(a) for a in args)
        safe_text = text.encode(enc, errors='replace').decode(enc, errors='replace')
        # 保留原有 kwargs (file, end, sep, flush 等)
        safe_kwargs = {k: v for k, v in kwargs.items() if k not in ('end',)}
        print(safe_text, **safe_kwargs, end=kwargs.get('end', '\n'))


def safe_write(text: str):
    """sys.stdout.write 的安全替代"""
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or 'utf-8'
        sys.stdout.write(text.encode(enc, errors='replace').decode(enc, errors='replace'))


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

    # 已知的文本格式扩展名 — 跳过控制字符比例检测，直接走编码检测
    # 这些格式（尤其 JSONL）可能含大量 JSON 转义序列，字节级控制字符比例
    # 容易超过 5% 阈值被误判为二进制
    KNOWN_TEXT_EXTENSIONS: Set[str] = {
        '.json', '.jsonl', '.ndjson',
        '.csv', '.tsv',
        '.log', '.out', '.err',
        '.txt', '.md', '.rst', '.tex',
        '.py', '.js', '.ts', '.html', '.css', '.xml', '.yaml', '.yml',
        '.toml', '.ini', '.cfg', '.conf', '.env', '.properties',
        '.sh', '.bash', '.zsh', '.bat', '.cmd', '.ps1',
        '.java', '.c', '.h', '.cpp', '.hpp', '.go', '.rs', '.rb', '.php',
        '.sql', '.proto', '.graphql',
        '.org', '.adoc',
    }

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

            # 已知文本扩展名：跳过控制字符/空字节启发式检测
            # JSONL 等格式含 JSON 转义字符，字节级检测会误判
            trust_ext = ext in TextDetector.KNOWN_TEXT_EXTENSIONS

            # 空字节 -> 可能是二进制或 UTF-16 无 BOM
            null_ratio = sample.count(b'\x00') / len(sample) if sample else 0
            if null_ratio > 0.1:
                encoding = TextDetector._try_utf16_no_bom(sample)
                if encoding:
                    return True, encoding
                if not trust_ext:
                    return False, None
                # 已知文本扩展名即使有空字节也继续尝试编码检测

            # 控制字符过多 -> 二进制（对已知文本扩展名跳过此检测）
            if not trust_ext:
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
        """自动翻译文件名（保留扩展名），中->英 / 英->中"""
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

    def translate_keyword(self, text: str) -> Optional[str]:
        """翻译搜索关键词（纯文本，中->英 / 英->中）"""
        if not self._available:
            return None
        text = text.strip()
        if not text:
            return None
        cache_key = f'__kw__{text}'
        if cache_key in self._cache:
            return self._cache[cache_key]
        try:
            if self.contains_chinese(text):
                translated = self._translator_zh_en.translate(text)
            else:
                translated = self._translator_en_zh.translate(text)
            if translated and translated.strip().lower() != text.lower():
                result = translated.strip()
                if len(self._cache) < self._cache_size:
                    self._cache[cache_key] = result
                return result
        except Exception as e:
            logger.debug(f"关键词翻译失败 '{text}': {e}")
        return None


# ============================================================
# 搜索后端
# ============================================================

class SearchResult:
    """统一的搜索结果结构"""

    def __init__(self, path: str, matches: Optional[List[Dict]] = None,
                 encoding: Optional[str] = None, source: Optional[str] = None):
        self.path = path
        self.matches = matches or []  # [{'line': int, 'content': str}]
        self.encoding = encoding
        self.source = source  # 'jsonl' = JSONL 大文件搜索结果, None = 普通
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

        logger.debug(f"rg 命令: {cmd}")

        try:
            proc = subprocess.run(
                cmd, capture_output=True, timeout=300,
                encoding='utf-8', errors='replace',
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

        if not output or not output.strip():
            return [], set()

        for line in output.strip().split('\n'):
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get('type')

            if msg_type == 'match':
                data = msg.get('data')
                if not data:
                    continue
                try:
                    fpath = data['path']['text']
                    line_number = data['line_number']
                    line_text = data['lines']['text'].rstrip('\n\r')
                except (KeyError, TypeError):
                    continue
                searched_files.add(fpath)

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
                    [self.bin, '--version'], capture_output=True,
                    encoding='utf-8', errors='replace', timeout=5,
                )
                self._is_gnu = 'GNU' in (ver.stdout or '')
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
            # -F 是 POSIX 标准，比 --fixed-strings 兼容性更好
            cmd.append('-F')

        if not case_sensitive:
            cmd.append('-i')

        if invert:
            cmd.append('-L')  # -L 比 --files-without-match 更兼容

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
        cmd.extend(['--', pattern, path])

        logger.debug(f"grep 命令: {cmd}")

        try:
            proc = subprocess.run(
                cmd, capture_output=True, timeout=300,
                # Windows: subprocess 默认用系统编码（cp936/cp1252），需显式指定
                encoding='utf-8', errors='replace',
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.debug(f"grep 执行失败: {e}")
            return []

        if proc.returncode not in (0, 1):
            # grep 返回 0=有匹配, 1=无匹配, 2=错误
            logger.debug(f"grep 返回错误 (rc={proc.returncode}): {proc.stderr}")
            return []

        return self._parse_output(proc.stdout, invert)

    # 正则匹配 grep -n 输出行: filepath:linenum:content
    # 需要处理 Windows 绝对路径 C:\...:10:content
    _LINE_PATTERN = re.compile(
        r'^(.+?):(\d+)[:](.*)', re.DOTALL
    )

    def _parse_output(self, output: str, invert: bool) -> List[SearchResult]:
        if not output or not output.strip():
            return []

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
            # Windows 路径含 C:\path\file:10:content -> 用正则而非 split
            m = self._parse_grep_line(line)
            if m:
                fpath, line_num, content = m
                if fpath not in results_by_path:
                    results_by_path[fpath] = SearchResult(path=fpath)
                results_by_path[fpath].matches.append({
                    'line': line_num,
                    'content': content.rstrip('\n\r'),
                })

        return list(results_by_path.values())

    @staticmethod
    def _parse_grep_line(line: str) -> Optional[Tuple[str, int, str]]:
        r"""
        解析 grep -n 的单行输出，正确处理 Windows 路径

        格式: filepath:linenum:content
        Windows: C:\path\file.py:10:import os
        Linux:   /path/file.py:10:import os
        """
        # 策略: 从右向左找 :数字: 模式
        # 因为文件路径可能含 C:\，行号一定是纯数字
        idx = 0
        while True:
            # 找下一个 : 的位置
            colon1 = line.find(':', idx)
            if colon1 < 0:
                break
            # 跳过 Windows 盘符 (C:)
            if colon1 == 1 and line[0].isalpha():
                idx = colon1 + 1
                continue
            # colon1 后面应该是行号
            colon2 = line.find(':', colon1 + 1)
            if colon2 < 0:
                break
            num_str = line[colon1 + 1:colon2]
            if num_str.isdigit():
                return line[:colon1], int(num_str), line[colon2 + 1:]
            idx = colon1 + 1
        return None


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
        if not output or not output.strip():
            return []

        results_by_path: Dict[str, SearchResult] = {}

        for line in output.strip().split('\n'):
            if not line:
                continue
            # findstr /N 输出: filepath:linenum:content
            # Windows 路径含 C:\，用与 grep 相同的解析策略
            m = GrepBackend._parse_grep_line(line)
            if m:
                fpath, line_num, content = m
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

        # 大文件 + 不需要上下文 -> 流式搜索（节省内存，不卡）
        if file_size > PythonBackend.STREAM_THRESHOLD and context_lines == 0:
            return PythonBackend._search_file_stream(
                file_path, pattern, encoding, invert, max_matches)

        # 小文件 或 需要上下文 -> 整体读取（上下文需要前后行）
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

        # query -> base64 编码
        try:
            encoded = base64.b64encode(query.encode('utf-8')).decode('ascii')
            search_terms.add(encoded)
        except Exception:
            pass

        # query 作为 base64 -> 解码为原文
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
# JSONL 大文件优化
# ============================================================

# 大 JSONL 文件阈值 (10MB)
_JSONL_LARGE_THRESHOLD = 10 * 1024 * 1024
# JSONL 流式读取最大行数
_JSONL_MAX_LINES = 1000
# mmap 阈值 (50MB)
_MMAP_THRESHOLD = 50 * 1024 * 1024
# 缓存有效期 (7 天)
_JSONL_CACHE_TTL = 7 * 24 * 3600

# 全局 JSONL 缓存
_jsonl_cache: Dict[str, Any] = {}
_jsonl_cache_path: Optional[str] = None
_jsonl_cache_dirty = False


def _load_jsonl_cache(search_dir: str) -> None:
    """加载 JSONL 索引缓存"""
    global _jsonl_cache, _jsonl_cache_path, _jsonl_cache_dirty
    cache_file = os.path.join(search_dir, '.doc_searcher_jsonl_cache.json')
    _jsonl_cache_path = cache_file
    if os.path.isfile(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 清除过期条目
            now = time.time()
            _jsonl_cache = {
                k: v for k, v in data.items()
                if now - v.get('cached_at', 0) < _JSONL_CACHE_TTL
            }
            logger.debug(f"加载 JSONL 缓存: {len(_jsonl_cache)} 条记录")
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"JSONL 缓存加载失败: {e}")
            _jsonl_cache = {}
    else:
        _jsonl_cache = {}


def _save_jsonl_cache() -> None:
    """保存 JSONL 索引缓存到磁盘"""
    global _jsonl_cache_dirty
    if not _jsonl_cache_dirty or not _jsonl_cache_path:
        return
    try:
        with open(_jsonl_cache_path, 'w', encoding='utf-8') as f:
            json.dump(_jsonl_cache, f, ensure_ascii=False, indent=2)
        logger.debug(f"保存 JSONL 缓存: {len(_jsonl_cache)} 条记录")
        _jsonl_cache_dirty = False
    except OSError as e:
        logger.debug(f"JSONL 缓存保存失败: {e}")


# 程序退出时自动保存缓存
atexit.register(_save_jsonl_cache)


def _find_large_jsonl_files(search_dir: str) -> List[str]:
    """扫描目录，找出所有大于阈值的 .jsonl/.ndjson 文件"""
    large_files = []
    for root, dirs, files in os.walk(search_dir):
        # 跳过隐藏目录和 .git
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in files:
            if fname.endswith(('.jsonl', '.ndjson')):
                fpath = os.path.join(root, fname)
                try:
                    if os.path.getsize(fpath) > _JSONL_LARGE_THRESHOLD:
                        large_files.append(fpath)
                except OSError:
                    pass
    return large_files


def _search_in_json_value(obj: Any, pattern: 're.Pattern') -> bool:
    """递归搜索 JSON 对象中的所有字符串值"""
    if isinstance(obj, str):
        return pattern.search(obj) is not None
    elif isinstance(obj, dict):
        return any(_search_in_json_value(v, pattern) for v in obj.values())
    elif isinstance(obj, (list, tuple)):
        return any(_search_in_json_value(item, pattern) for item in obj)
    return False


def _search_jsonl_file(fpath: str, pattern: 're.Pattern',
                       max_lines: int = _JSONL_MAX_LINES) -> Optional[SearchResult]:
    """流式读取 JSONL 文件，逐行解析 JSON 并在字符串值中搜索

    对大文件使用 mmap 读取以减少内存占用。
    """
    global _jsonl_cache, _jsonl_cache_dirty

    file_size = os.path.getsize(fpath)
    file_mtime = os.path.getmtime(fpath)

    # 检查缓存: 如果 mtime 没变且上次搜索无命中，跳过
    cache_key = fpath
    if cache_key in _jsonl_cache:
        cached = _jsonl_cache[cache_key]
        if cached.get('mtime') == file_mtime and not cached.get('had_matches', True):
            logger.debug(f"JSONL 缓存命中 (无匹配): {fpath}")
            return None

    matches = []
    lines_read = 0

    try:
        use_mmap = file_size > _MMAP_THRESHOLD
        if use_mmap:
            try:
                with open(fpath, 'rb') as f:
                    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                    try:
                        for line_bytes in iter(mm.readline, b''):
                            lines_read += 1
                            if lines_read > max_lines:
                                break
                            # 首行剥离 BOM
                            if lines_read == 1 and line_bytes.startswith(b'\xef\xbb\xbf'):
                                line_bytes = line_bytes[3:]
                            line = line_bytes.decode('utf-8', errors='replace').strip()
                            if not line:
                                continue
                            try:
                                obj = _fast_json.loads(line)
                            except (ValueError, TypeError):
                                # 非 JSON 行，用纯文本搜索
                                if pattern.search(line):
                                    matches.append({
                                        'line': lines_read,
                                        'content': line[:200],
                                    })
                                continue
                            if _search_in_json_value(obj, pattern):
                                matches.append({
                                    'line': lines_read,
                                    'content': line[:200],
                                })
                    finally:
                        mm.close()
            except (mmap.error, OSError):
                # mmap 失败，回退到普通读取
                use_mmap = False

        if not use_mmap:
            with open(fpath, 'r', encoding='utf-8-sig', errors='replace') as f:
                for line in f:
                    lines_read += 1
                    if lines_read > max_lines:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = _fast_json.loads(line)
                    except (ValueError, TypeError):
                        if pattern.search(line):
                            matches.append({
                                'line': lines_read,
                                'content': line[:200],
                            })
                        continue
                    if _search_in_json_value(obj, pattern):
                        matches.append({
                            'line': lines_read,
                            'content': line[:200],
                        })
    except OSError as e:
        logger.debug(f"JSONL 文件读取失败: {fpath}: {e}")
        return None

    # 更新缓存
    _jsonl_cache[cache_key] = {
        'mtime': file_mtime,
        'size': file_size,
        'had_matches': len(matches) > 0,
        'cached_at': time.time(),
    }
    _jsonl_cache_dirty = True

    if matches:
        r = SearchResult(path=fpath, source='jsonl')
        r.matches = matches
        r.encoding = 'utf-8'
        return r
    return None


def _has_chinese(text: str) -> bool:
    """检测文本是否包含中文字符 (CJK Unified Ideographs: U+4E00-U+9FFF)"""
    for c in text:
        if 0x4E00 <= ord(c) <= 0x9FFF:
            return True
    return False


# ============================================================
# 主搜索器（编排层，不重复造轮子）
# ============================================================

class DocSearcher:
    """
    文档内容搜索器 —— 编排 rg/grep + 编码检测 + 翻译

    搜索策略:
    1. 用 rg（或 grep）搜索目录 -> 得到 UTF-8 兼容文件的结果
    2. 用 TextDetector 扫描 rg 跳过的文件 -> 对非 UTF-8 文本用 Python 回退搜索
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
                 translate_keyword: bool = False,
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

        # 后端 (rg -> grep -> findstr -> python)
        self._rg = RipgrepBackend()
        self._grep = GrepBackend()
        self._findstr = FindstrBackend()

        # 提示安装 ripgrep（性能最佳的后端）
        if not self._rg.available:
            if self._grep.available:
                logger.info("提示: 未检测到 ripgrep (rg)，当前使用 grep。"
                            "安装 ripgrep 可大幅提升搜索速度: "
                            "https://github.com/BurntSushi/ripgrep#installation")
            else:
                logger.warning("未检测到 ripgrep 和 grep，将使用 Python 内置搜索（较慢）。"
                               "强烈建议安装 ripgrep: "
                               "https://github.com/BurntSushi/ripgrep#installation")

        # 翻译器（文件名翻译 + 关键词翻译共用）
        self._translator: Optional[FilenameTranslator] = None
        if translate or translate_keyword:
            self._translator = FilenameTranslator()
            if not self._translator.available:
                logger.warning("翻译库不可用，请安装: pip install deep-translator")

        # 关键词翻译：非正则模式下，将关键词翻译后组合成正则 (原词|翻译)
        self._translated_keyword: Optional[str] = None
        if (translate_keyword and self.keyword and not self.is_regex
                and self._translator and self._translator.available):
            translated = self._translator.translate_keyword(self.keyword)
            if translated:
                self._translated_keyword = translated
                # 组合原始关键词和翻译结果为正则
                combined = f"({re.escape(self.keyword)}|{re.escape(translated)})"
                self.pattern_str = combined
                self.is_regex = True
                # 更新 regex_pattern 以确保 _parallel_search 子搜索器也用翻译后的模式
                self.regex_pattern = combined
                logger.info(f"关键词翻译: '{self.keyword}' -> '{translated}'，"
                            f"搜索模式: {combined}")

        # 编译 Python 回退用的正则
        flags = 0 if case_sensitive else re.IGNORECASE
        if self.pattern_str:
            pat = self.pattern_str if self.is_regex else re.escape(self.pattern_str)
            self._py_pattern = re.compile(pat, flags)
        else:
            self._py_pattern = None

        self.stats = {
            'backend': 'unknown',
            'files_scanned': 0,
            'files_matched': 0,
            'files_fallback_searched': 0,
            'files_jsonl_searched': 0,
            'total_matches': 0,
            'scan_time_seconds': 0.0,
        }

        # 初始化 JSONL 缓存
        _load_jsonl_cache(self.target_path)

        logger.debug(f"快速JSON: {_json_lib_name}")

    def search(self) -> List[SearchResult]:
        """执行搜索 —— 自动降级: rg -> grep -> findstr -> python"""
        if not self.pattern_str:
            return self.scan_text_files()

        start = time.time()
        results: List[SearchResult] = []

        # 检测大 JSONL 文件，从外部搜索工具中排除
        large_jsonl = _find_large_jsonl_files(self.target_path)
        jsonl_results: List[SearchResult] = []
        extra_exclude_globs: List[str] = []

        if large_jsonl and self._py_pattern:
            for fpath in large_jsonl:
                fname = os.path.basename(fpath)
                extra_exclude_globs.append(fname)
                logger.debug(f"JSONL 大文件排除: {fname} "
                             f"({os.path.getsize(fpath) / 1024 / 1024:.1f}MB)")
            # 单独用 Python 流式搜索这些大 JSONL
            for fpath in large_jsonl:
                r = _search_jsonl_file(fpath, self._py_pattern)
                if r:
                    jsonl_results.append(r)
                self.stats['files_jsonl_searched'] += 1

        # 临时合并 exclude globs
        original_excludes = self.exclude_patterns
        if extra_exclude_globs:
            self.exclude_patterns = list(self.exclude_patterns) + extra_exclude_globs

        # 中文检测: rg 在某些 Windows 环境下处理中文不稳定，
        # 如果搜索词含中文且 grep 可用，优先使用 grep
        pattern_has_chinese = _has_chinese(self.pattern_str)
        prefer_grep = pattern_has_chinese and self._grep.available
        if prefer_grep:
            logger.debug(f"搜索包含中文，优先使用 grep")

        # 自动降级链：如果高优先级后端返回 0 结果但没有报错，
        # 可能是后端兼容性问题，尝试下一个后端
        if self._rg.available and not prefer_grep:
            results = self._search_with_rg()
            if results:
                pass  # rg 成功
            elif self._grep.available:
                logger.debug("rg 返回 0 结果，降级到 grep")
                results = self._search_with_grep()
        elif self._grep.available:
            results = self._search_with_grep()

        # 恢复原始 exclude 列表
        self.exclude_patterns = original_excludes

        # grep 也没结果 -> 尝试 findstr (Windows)
        if not results and self._findstr.available:
            logger.debug("降级到 findstr")
            results = self._search_with_findstr()

        # 所有外部工具都失败 -> Python 兜底
        if not results:
            logger.debug("所有外部后端返回 0 结果，降级到 Python 搜索")
            results = self._search_with_python()

        # 合并 JSONL 大文件搜索结果
        if jsonl_results:
            logger.debug(f"JSONL 大文件命中: {len(jsonl_results)} 个文件")
            results.extend(jsonl_results)

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
                # 应用 include/exclude glob 筛选（--type 和 -i/-e）
                if self.include_patterns:
                    if not any(fnmatch.fnmatch(fname, p) for p in self.include_patterns):
                        continue
                if self.exclude_patterns:
                    if any(fnmatch.fnmatch(fname, p) for p in self.exclude_patterns):
                        continue

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

        # rg 支持 --max-filesize 但不支持 min-size/日期筛选 -> 后续 Python 过滤
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
                # 应用 include/exclude glob 筛选（--type 和 -i/-e）
                if self.include_patterns:
                    if not any(fnmatch.fnmatch(fname, p) for p in self.include_patterns):
                        continue
                if self.exclude_patterns:
                    if any(fnmatch.fnmatch(fname, p) for p in self.exclude_patterns):
                        continue

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
        if self._translated_keyword:
            summary['translated_keyword'] = self._translated_keyword
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
    units = {'TB': 1024**4, 'GB': 1024**3, 'MB': 1024**2, 'KB': 1024,
             'T': 1024**4, 'G': 1024**3, 'M': 1024**2, 'K': 1024, 'B': 1}
    for unit, multiplier in sorted(units.items(), key=lambda x: -len(x[0])):
        if size_str.endswith(unit):
            num_part = size_str[:-len(unit)].strip()
            return int(float(num_part) * multiplier) if num_part else multiplier
    return int(size_str)


def parse_date(date_str: str) -> datetime:
    """
    解析日期字符串，支持:
    1. 标准格式: YYYY-MM-DD, YYYY/MM/DD, YYYYMMDD, YYYY-MM-DD HH:MM:SS
    2. 快捷符号 (缩写优先):
         td / today       -> 今天 00:00
         yd / yesterday   -> 昨天 00:00
         tw / thisweek    -> 本周一 00:00
         lw / lastweek    -> 上周一 00:00
         tm / thismonth   -> 本月1日 00:00
         lm / lastmonth   -> 上月1日 00:00
         ty / thisyear    -> 今年1月1日 00:00
         ly / lastyear    -> 去年1月1日 00:00
    3. 相对偏移:
         Nd  -> N 天前  (如 3d = 3天前, 7d = 一周前, 30d = 一个月前)
         Nh  -> N 小时前 (如 1h, 6h, 24h)
         Nw  -> N 周前   (如 1w, 2w)
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
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S',
                '%Y/%m/%d', '%Y/%m/%d %H:%M:%S', '%Y%m%d'):
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
            kw_line = f"  关键词:   {summary['keyword']}"
            if summary.get('translated_keyword'):
                kw_line += f"  (翻译: {summary['translated_keyword']})"
            lines.append(kw_line)
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

    parser.add_argument('-d', '--debug', action='store_true',
                        help='调试模式（输出后端选择、命令参数等信息）')

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
    sp.add_argument('--tk', '--translate-keyword', dest='translate_keyword',
                    action='store_true',
                    help='搜索关键词自动翻译（中->英/英->中），搜"爬虫"也匹配"crawler"')
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
    # JSONL 大文件结果导出阈值
    sp.add_argument('--jsonl-dump', type=int, default=50, metavar='N',
                    help='JSONL 大文件匹配超过 N 条时导出到 txt（默认50，0=全显示不存文件）')

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
    sp3 = sub.add_parser('translate', help='批量翻译文件名 (中<->英)')
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
    # session (Agent 会话日志搜索)
    sp7 = sub.add_parser('session', help='搜索 Claude Agent 会话日志 (JSONL)',
                         epilog='注意: keyword 和 path 必须写在所有选项之前，'
                                '例如: session crawler ./logs --role user --json'
                                '（不可写成 session crawler --role user ./logs）')
    sp7.add_argument('keyword', nargs='?', default=None,
                     help='搜索关键词 (可选，须写在选项之前)')
    sp7.add_argument('path', nargs='?', default='.',
                     help='会话目录或 JSONL 文件路径 (默认当前目录，须紧跟 keyword 之后)')
    sp7.add_argument('-r', '--regex', action='store_true', help='关键词作为正则')
    sp7.add_argument('-s', '--case-sensitive', action='store_true', help='区分大小写')
    sp7.add_argument('--tool', type=str, default=None,
                     help='按工具名过滤，逗号分隔 (Read,Edit,Write,Bash,Grep,Glob,...)')
    sp7.add_argument('--role', type=str, default=None, choices=['user', 'assistant'],
                     help='按角色过滤: user / assistant')
    sp7.add_argument('--session-id', type=str, default=None, help='按会话 ID 过滤 (部分匹配)')
    sp7.add_argument('--slug', type=str, default=None, help='按会话 slug 过滤 (部分匹配)')
    sp7.add_argument('--after', type=str, default=None,
                     help='时间下限 (支持快捷: td yd 3d 7d tw lw tm lm 或 ISO格式)')
    sp7.add_argument('--before', type=str, default=None,
                     help='时间上限 (支持快捷: td yd 3d 7d tw lw tm lm 或 ISO格式)')
    sp7.add_argument('--max-results', type=int, default=50, metavar='N',
                     help='最大返回条数 (默认 50, 0=不限)')
    sp7.add_argument('--thinking', action='store_true', help='显示 thinking 内容')
    sp7.add_argument('--no-subagents', action='store_true',
                     help='跳过 subagents/ 子代理文件')
    sp7.add_argument('--full-content', action='store_true',
                     help='显示 Write/Edit/NotebookEdit 的完整写入内容')
    sp7.add_argument('-v', '--verbose', action='store_true', help='显示完整内容')
    sp7.add_argument('--json', action='store_true', help='JSON 格式输出')

    # file-history (文件历史备份搜索)
    sp8 = sub.add_parser('file-history', help='搜索 Claude Code 文件历史备份 (file-history)')
    sp8.add_argument('path', nargs='?', default='.',
                     help='Claude 项目目录 (含 JSONL 的目录，默认当前目录)')
    sp8.add_argument('--file', type=str, default=None, metavar='PATTERN',
                     help='按文件路径过滤 (子串匹配)')
    sp8.add_argument('--session-id', type=str, default=None,
                     help='按会话 ID 过滤 (部分匹配)')
    sp8.add_argument('--after', type=str, default=None,
                     help='时间下限 (支持快捷符)')
    sp8.add_argument('--before', type=str, default=None,
                     help='时间上限 (支持快捷符)')
    sp8.add_argument('--cat', type=str, default=None, metavar='FILE_PATH',
                     help='输出指定文件最新备份的完整内容 (可配合 --version)')
    sp8.add_argument('--version', type=int, default=None, metavar='N',
                     help='配合 --cat 指定版本号')
    sp8.add_argument('--diff', action='store_true',
                     help='显示相邻版本之间的 diff')
    sp8.add_argument('-v', '--verbose', action='store_true',
                     help='显示文件内容预览')
    sp8.add_argument('--json', action='store_true', help='JSON 格式输出')

    sp6 = sub.add_parser('help', help='查看详细帮助')
    sp6.add_argument('topic', nargs='?', default='all',
                     help='帮助主题: search date type hash base64 format pipe parallel session file-history version all')

    return parser


def cli_main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    log_level = logging.DEBUG if args.debug else logging.WARNING
    logging.basicConfig(level=log_level, format='%(levelname)s: %(message)s')

    if args.debug:
        rg = RipgrepBackend()
        grep = GrepBackend()
        fstr = FindstrBackend()
        logger.debug(f"搜索后端: rg={rg.bin} grep={grep.bin} (GNU={grep._is_gnu}) findstr={fstr.bin}")
        logger.debug(f"chardet={HAS_CHARDET} translator={HAS_TRANSLATOR}")
        logger.debug(f"平台={sys.platform} 编码={sys.getdefaultencoding()}")

    # 缺失库提示（每个功能首次用到时提醒）
    _missing_libs = []
    if not HAS_CHARDET:
        _missing_libs.append('chardet          - 编码检测 (GBK/Big5/Shift_JIS 等): pip install chardet')
    if not HAS_TRANSLATOR:
        _missing_libs.append('deep-translator  - 文件名/关键词翻译:              pip install deep-translator')
    if _json_lib_name == 'json':
        _missing_libs.append('orjson/ujson     - 快速 JSON 解析 (JSONL 搜索加速): pip install orjson')
    rg_check = RipgrepBackend()
    if not rg_check.available:
        _missing_libs.append('ripgrep (rg)     - 高速搜索后端:                    https://github.com/BurntSushi/ripgrep')
    if _missing_libs:
        safe_print("[提示] 以下可选依赖未安装，安装后可提升功能:", file=sys.stderr)
        for lib in _missing_libs:
            safe_print(f"  - {lib}", file=sys.stderr)
        safe_print("", file=sys.stderr)

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
    elif args.command == 'session':
        return _cmd_session(args)
    elif args.command == 'file-history':
        return _cmd_file_history(args)
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

    # --type 预设 -> include_patterns
    include_patterns = args.include or []
    if args.type:
        type_key = args.type.lower()
        if type_key not in FILE_TYPE_PRESETS:
            safe_print(f"未知文件类型: {type_key}", file=sys.stderr)
            safe_print(f"可选: {', '.join(sorted(FILE_TYPE_PRESETS.keys()))}", file=sys.stderr)
            return 1
        include_patterns = FILE_TYPE_PRESETS[type_key] + include_patterns

    # 管道输入模式：path 为 - 或 stdin 非终端
    stdin_files = None
    search_path = args.path
    if args.path == '-' or (args.path == '.' and not sys.stdin.isatty()):
        stdin_files = _read_stdin_file_list()
        if not stdin_files:
            safe_print("stdin 中无有效文件路径", file=sys.stderr)
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
        translate_keyword=getattr(args, 'translate_keyword', False),
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

    # JSONL 大文件结果分流: 超过阈值时导出到 txt，屏幕只显示摘要
    jsonl_dump_threshold = getattr(args, 'jsonl_dump', 50)
    jsonl_results = [r for r in results if r.source == 'jsonl']
    jsonl_total_matches = sum(r.match_count for r in jsonl_results)
    dump_file = None

    if jsonl_results and jsonl_dump_threshold > 0 and jsonl_total_matches > jsonl_dump_threshold:
        # 导出详细结果到 txt
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        kw_safe = re.sub(r'[^\w\-]', '_', searcher.pattern_str[:30])
        dump_file = os.path.join(
            searcher.target_path,
            f'.doc_searcher_jsonl_{kw_safe}_{ts}.txt'
        )
        try:
            with open(dump_file, 'w', encoding='utf-8') as f:
                f.write(f"# JSONL 大文件搜索结果\n")
                f.write(f"# 关键词: {searcher.pattern_str}\n")
                f.write(f"# 时间: {datetime.now().isoformat()}\n")
                f.write(f"# 匹配: {jsonl_total_matches} 条 / {len(jsonl_results)} 个文件\n")
                f.write(f"# 阈值: {jsonl_dump_threshold} (--jsonl-dump)\n\n")
                for r in jsonl_results:
                    f.write(f"=== {r.path} ({format_size(r.size)}) ===\n")
                    for m in r.matches:
                        f.write(f"  L{m.get('line', '?')}: {m.get('content', '')}\n")
                    f.write('\n')
            logger.debug(f"JSONL 结果导出到: {dump_file}")
        except OSError as e:
            logger.warning(f"JSONL 结果导出失败: {e}")
            dump_file = None

        # 屏幕上只保留 JSONL 的摘要（截断匹配列表，只留前几条）
        _JSONL_SCREEN_PREVIEW = 5
        for r in jsonl_results:
            original_count = r.match_count
            if original_count > _JSONL_SCREEN_PREVIEW:
                r.matches = r.matches[:_JSONL_SCREEN_PREVIEW]
                r.matches.append({
                    'line': 0,
                    'content': f'... 还有 {original_count - _JSONL_SCREEN_PREVIEW} 条匹配，'
                               f'详见: {dump_file}',
                })

    summary = searcher.get_summary()
    fmt = _resolve_format(args)

    output = OutputFormatter.format_output(
        results, summary,
        fmt=fmt, verbose=args.verbose,
        custom_template=args.format_str,
    )
    if fmt == 'path0':
        safe_write(output)
    else:
        safe_print(output)

    # 提示用户导出文件位置
    if dump_file:
        safe_print(f"\n[JSONL] {jsonl_total_matches} 条匹配已导出到: {dump_file}",
                   file=sys.stderr)

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
        safe_write(output)
    else:
        safe_print(output)
    return 0


def _cmd_translate(args) -> int:
    translator = FilenameTranslator()
    if not translator.available:
        safe_print("错误: 翻译库不可用，请安装: pip install deep-translator", file=sys.stderr)
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
        safe_print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        if not results:
            safe_print("无需翻译的文件名。")
        else:
            w = max(len(r['original']) for r in results)
            for r in results:
                d = 'ZH->EN' if r['has_chinese'] else 'EN->ZH'
                safe_print(f"  [{d}] {r['original']:<{w}}  ->  {r['translated']}")
            safe_print(f"\n  共 {len(results)} 个文件名可翻译。")
    return 0


def _cmd_hash(args) -> int:
    """hash 子命令：通过文件 hash 查找匹配文件"""
    target = os.path.abspath(args.path)
    if not os.path.isdir(target):
        safe_print(f"路径不存在: {target}", file=sys.stderr)
        return 1

    results = HashMatcher.find_by_hash(target, args.hash_value, algorithm=args.algo)

    if args.json:
        out = {
            'hash': args.hash_value,
            'algorithm': args.algo,
            'matches': [r.to_dict() for r in results],
        }
        safe_print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if not results:
            safe_print(f"未找到 hash 匹配的文件: {args.hash_value}")
        else:
            safe_print(f"找到 {len(results)} 个匹配文件:")
            for r in results:
                size_str = format_size(r.size)
                safe_print(f"  {r.path}  ({size_str})")
    return 0


def _cmd_base64(args) -> int:
    """base64 子命令：Base64 双向搜索"""
    target = os.path.abspath(args.path)
    if not os.path.isdir(target):
        safe_print(f"路径不存在: {target}", file=sys.stderr)
        return 1

    results = HashMatcher.find_by_base64(target, args.query)

    if args.json:
        out = {
            'query': args.query,
            'matches': [r.to_dict() for r in results],
        }
        safe_print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        if not results:
            safe_print(f"未找到 base64 相关匹配: {args.query}")
        else:
            safe_print(f"找到 {len(results)} 个文件包含匹配:")
            for r in results:
                safe_print(f"  {r.path}")
                shown = r.matches[:3] if not args.verbose else r.matches
                for m in shown:
                    form_tag = f" [{m.get('match_form', '')}]" if m.get('match_form') else ''
                    safe_print(f"    L{m.get('line', '?')}: {m.get('content', '')[:80]}{form_tag}")
                if not args.verbose and len(r.matches) > 3:
                    safe_print(f"    ... 还有 {len(r.matches) - 3} 处匹配")
    return 0


def _cmd_help(args) -> int:
    """详细帮助 -- 按主题输出使用说明 (纯 ASCII，兼容 Windows GBK 控制台)"""
    topics = {
        'search': """
=== search -- 搜索文件内容 ===

  基本用法:
    doc_searcher search "关键词" [路径]

  参数:
    关键词          要搜索的文本
    路径            搜索目录 (默认当前目录, 用 - 从 stdin 读文件列表)
    -r, --regex     关键词作为正则表达式
    --invert        反查: 查找不包含关键词的文件
    -s              区分大小写
    -C N            显示匹配行前后 N 行上下文
    --max-matches N 每文件最多匹配 N 次
    --max-results N 最多返回 N 个文件
    -v, --verbose   显示完整匹配内容
    --tk            搜索关键词自动翻译 (中->英/英->中, 需 deep-translator)

  JSONL 大文件:
    >10MB 的 .jsonl/.ndjson 文件会自动用 Python 流式搜索
    (递归搜索 JSON 所有字符串值, 最多读取 1000 行)
    --jsonl-dump N  匹配超过 N 条时导出到 .txt (默认 50, 0=全显示)

  示例:
    doc_searcher search "TODO" /project
    doc_searcher search -r "\\bpassw(or)?d\\b" /etc --type config
    doc_searcher search --invert "license" /src --type py
    doc_searcher search "key" /data --jsonl-dump 100  # JSONL超100条存文件
    doc_searcher search "key" /data --jsonl-dump 0    # JSONL全部显示
    doc_searcher search "爬虫" /project --tk          # 同时搜"爬虫"和"crawler"
    doc_searcher search "error" /src --tk             # 同时搜"error"和"错误"
""",

        'date': """
=== 日期筛选 -- --after / --before / --created-after/before ===

  --after  DATE    仅保留修改日期 >= DATE 的文件
  --before DATE    仅保留修改日期 <= DATE 的文件
  --created-after  仅保留创建日期 >= DATE 的文件
  --created-before 仅保留创建日期 <= DATE 的文件

  DATE 支持以下格式:

    格式            说明
    ----------      --------------------------------
    2026-02-12      标准日期 YYYY-MM-DD
    2026/02/12      斜线分隔
    20260212        紧凑格式
    @170000000      Unix 时间戳 (秒)
    ----------      --------------------------------
    td              今天 00:00 (today)
    yd              昨天 00:00 (yesterday)
    tw              本周一 00:00 (this week)
    lw              上周一 00:00 (last week)
    tm              本月 1 日 (this month)
    lm              上月 1 日 (last month)
    ty              今年 1/1 (this year)
    ly              去年 1/1 (last year)
    ----------      --------------------------------
    3d              3 天前
    7d              7 天前
    30d             30 天前
    1h              1 小时前
    6h              6 小时前
    1w              1 周前
    2w              2 周前

  示例:
    doc_searcher search "key" . --after td               # 今天修改的
    doc_searcher search "key" . --after 7d               # 最近 7 天
    doc_searcher search "key" . --after lw --before tw   # 上周修改的
    doc_searcher search "key" . --created-after tm       # 本月创建的
    doc_searcher scan . --after 30d --sort mtime --desc  # 近 30 天按修改时间倒序

  排序: --sort mtime (按修改时间), --sort ctime (按创建时间)
""",

        'type': """
=== --type -- 文件类型预设 ===

  -t TYPE, --type TYPE    按预设类型筛选文件

    类型        包含扩展名
    --------    ------------------------------------------
    py          .py .pyw .pyi
    js          .js .jsx .mjs .cjs
    ts          .ts .tsx
    web         .html .htm .css .scss .js .ts .vue .svelte
    java        .java .kt .scala .gradle
    c           .c .h .cpp .hpp .cc .cxx
    go          .go
    rust        .rs
    ruby        .rb .erb .gemspec
    php         .php
    shell       .sh .bash .zsh .fish .bat .cmd .ps1
    config      .json .yaml .yml .toml .ini .cfg .conf .env
    xml         .xml .xsl .xsd .svg .plist
    doc         .md .rst .txt .tex .adoc .org
    data        .csv .tsv .jsonl .ndjson
    sql         .sql
    proto       .proto .graphql
    log         .log .out .err
    all-text    * (不筛选扩展名, 靠内容判定)

  --type 可与 -i (include) 叠加使用。

  示例:
    doc_searcher search "TODO" . --type py
    doc_searcher search "password" . --type config
    doc_searcher search "SELECT" . --type sql
""",

        'hash': """
=== hash -- 文件 hash 指纹对比 (取证用) ===

  用法: doc_searcher hash <hash值> <搜索目录> [选项]

  根据文件的 MD5/SHA1/SHA256/SHA512 查找目录中所有副本。
  算法默认按 hash 长度自动检测:
    32字符 = MD5 | 40字符 = SHA1 | 64字符 = SHA256 | 128字符 = SHA512

  选项:
    -a, --algo ALGO   指定算法 (auto/md5/sha1/sha256/sha512)
    --json            JSON 输出
    -v                详细模式

  示例:
    doc_searcher hash d41d8cd98f00b204e9800998ecf8427e /target     # auto=MD5
    doc_searcher hash abc123... /dir --algo sha256 --json
""",

        'base64': """
=== base64 -- Base64 双向搜索 ===

  用法: doc_searcher base64 <内容> <搜索目录>

  同时搜索三种形式:
    1. 原文           "secret_key"
    2. 原文的 base64  "c2VjcmV0X2tleQ=="
    3. 若输入本身是 base64, 解码后的原文

  适合取证场景: 在代码中搜索被 base64 编码隐藏的敏感信息。

  示例:
    doc_searcher base64 "admin:password" /project
    doc_searcher base64 "YWRtaW46cGFzc3dvcmQ=" /project --json
""",

        'format': """
=== --format -- 输出格式 ===

  --format FORMAT   指定输出格式

    格式      说明
    ------    ------------------------------------------
    text      人类可读 (默认终端格式, 带统计和装饰)
    grep      path:line:content (grep 兼容, 管道自动切换)
    path      仅文件路径, 每行一个
    path0     路径以 \\0 分隔 (配合 xargs -0)
    csv       CSV 格式 path,line,encoding,size,content
    json      JSON 结构化输出 (含统计信息)
    custom    自定义模板 (需配合 --format-str)

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
=== 管道组合 ===

  输入管道 (stdin -> doc_searcher):
    将其他命令的文件列表输入给 doc_searcher 搜索:
    find /var/log -name "*.log" | doc_searcher search "error" -
    fd ".conf" | doc_searcher search "password" -

  输出管道 (doc_searcher -> 其他命令):
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
=== --parallel -- 并行加速搜索 ===

  --parallel N   使用 N 个线程并行搜索 (将目录按子目录分 chunk)

  原理: 将搜索目标的一级子目录拆分为 N 个独立任务, 并行执行。
  适用场景: 大目录 + Python 回退搜索 (rg 本身已内置并行)。

  建议线程数:
    SSD      8-16
    HDD      4-8
    网络盘   2-4

  示例:
    doc_searcher search "keyword" /large/dir --parallel 8
    doc_searcher search "TODO" . --type py --parallel 4
""",

        'session': """
=== session -- Agent 会话日志搜索 ===

  搜索 Claude Code 的 JSONL 会话日志。
  支持按工具名、角色、关键词、会话 slug、时间范围过滤。
  内置多层前置过滤 (session-id 文件名匹配、mtime 跳过、rg 预筛) 加速搜索。

  基本用法:
    doc_searcher session [关键词] [路径]

  路径可以是:
    - 单个 .jsonl 文件
    - 包含 .jsonl 的目录 (递归搜索)
    - Claude 项目目录 (自动发现 .jsonl):
      Windows: C:\\Users\\<user>\\.claude\\projects\\C--Users-<user>-<project>
      macOS:   ~/.claude/projects/-Users-<user>-<project>
      Linux:   ~/.claude/projects/-home-<user>-<project>

  Claude Code 会话目录结构:
    ~/.claude/projects/{encoded-path}/
    ├── {session-uuid}.jsonl           # 主会话文件 (文件名 = UUID)
    ├── {session-uuid}/
    │   └── subagents/
    │       └── agent-{hash}.jsonl     # 子代理 (Task 工具) 转录
    └── ...

    注: 一个 JSONL 可包含多个 sessionId (--continue/--resume 追加)

  参数:
    --tool NAME       按工具名过滤 (逗号分隔: Read,Edit,Write,Bash,Grep)
    --role ROLE       按角色过滤: user / assistant
    --slug TEXT       按会话 slug 过滤 (部分匹配)
    --session-id ID   按会话 ID 过滤 (部分匹配，同时做文件名前置过滤)
    --after TIME      时间下限 (支持快捷符，同时做 mtime 前置过滤)
    --before TIME     时间上限 (支持快捷符)
    --no-subagents    跳过 subagents/ 子代理文件
    --full-content    显示 Write/Edit/NotebookEdit 的完整写入内容
                      Write → content (整个文件)
                      Edit  → old_string + new_string
                      NotebookEdit → new_source
    --thinking        显示 thinking 内容
    --max-results N   最大返回条数 (默认 50, 0=不限)
    -v, --verbose     显示完整内容
    --json            JSON 格式输出

  时间快捷符 (--after / --before):
    td / today       今天 00:00
    yd / yesterday   昨天 00:00
    Nd               N 天前 (3d=3天前, 7d=一周前, 30d=一个月前)
    Nh               N 小时前 (1h, 6h, 24h)
    Nw               N 周前 (1w, 2w)
    tw / thisweek    本周一 00:00
    lw / lastweek    上周一 00:00
    tm / thismonth   本月1日
    lm / lastmonth   上月1日
    ty / thisyear    今年1月1日
    ly / lastyear    去年1月1日
    @1700000000      Unix 时间戳
    YYYY-MM-DD       标准日期格式
    YYYY-MM-DD HH:MM:SS  完整时间戳

  前置过滤机制:
    搜索大量 JSONL 文件时，以下过滤会在逐行读取前执行:
    1. --session-id  → 文件名/目录名匹配 (JSONL 文件名即 UUID)
    2. --after       → 跳过 mtime < after 的文件 (JSONL 追加写入)
    3. 关键词        → rg --files-with-matches 预筛 (需安装 ripgrep)
    4. --no-subagents → 跳过 subagents/ 目录

  示例:
    # 搜索所有 Write 操作
    doc_searcher session --tool Write ~/.claude/projects/-home-user-myproject

    # 搜索包含某关键词的所有消息
    doc_searcher session "test_vb_model" /path/to/sessions

    # 只看用户发言
    doc_searcher session --role user /path/to/sessions

    # 搜索特定会话的 Bash 操作
    doc_searcher session --tool Bash --slug "giggly-foraging" /path/to/sessions

    # 搜索昨天的 Edit 操作
    doc_searcher session --tool Edit --after yd /path/to/sessions

    # 搜索最近3天的内容
    doc_searcher session --after 3d /path/to/sessions

    # 按 session-id 快速定位 (文件名前置过滤)
    doc_searcher session --session-id 90b8d0a0 /path/to/sessions

    # 跳过子代理转录
    doc_searcher session "error" --no-subagents /path/to/sessions

    # 恢复 Write 写入的文件内容 (提取完整 content)
    doc_searcher session --tool Write --full-content -v "test_ai_dialogue" /path/to/sessions

    # 查看所有 Edit 操作的完整 diff
    doc_searcher session --tool Edit --full-content --after yd /path/to/sessions

    # JSON 格式导出完整写入内容 (可用 jq 提取)
    doc_searcher session --tool Write --full-content --json /path/to/sessions | jq '.results[].write_content'

    # 查看 agent 的思考过程
    doc_searcher session "error" --thinking --role assistant /path/to/sessions

    # JSON 格式输出供其他工具处理
    doc_searcher session --tool Read --json /path/to/sessions | python -m json.tool

  可用工具名 (--tool):
    Read, Edit, Write, Bash, Grep, Glob, WebFetch, WebSearch,
    Task, TodoWrite, NotebookEdit, AskUserQuestion
""",

        'file-history': """
=== file-history -- 文件历史备份搜索 ===

  搜索 Claude Code 的 file-history 备份。
  解析 JSONL 中的 file-history-snapshot 条目，交叉引用
  ~/.claude/file-history/{sessionId}/ 下的物理备份文件。

  Claude Code 修改文件时会自动创建备份:
    ~/.claude/file-history/{sessionId}/{sha256_16}@v{version}

  JSONL 中 file-history-snapshot 条目记录了:
    - trackedFileBackups: 文件相对路径 → backupFileName 映射
    - messageId: 关联到哪条 assistant 消息
    - version: 每次修改递增

  基本用法:
    doc_searcher file-history [项目目录]

  项目目录: 包含 JSONL 会话文件的 Claude 项目目录
    ~/.claude/projects/-home-user-myproject/

  参数:
    --file PATTERN    按文件路径过滤 (子串匹配)
    --session-id ID   按会话 ID 过滤 (部分匹配)
    --after TIME      时间下限 (支持快捷符: td yd 3d 7d 等)
    --before TIME     时间上限
    --cat FILE_PATH   输出指定文件最新备份的完整内容
    --version N       配合 --cat 指定版本号
    --diff            显示相邻版本之间的 diff
    -v, --verbose     显示文件内容预览
    --json            JSON 格式输出

  示例:
    # 列出所有文件历史备份
    doc_searcher file-history ~/.claude/projects/-home-user-myproject

    # 搜索特定文件的备份
    doc_searcher file-history --file "test_ai_dialogue.py" ~/.claude/projects/...

    # 查看特定文件最新备份的完整内容
    doc_searcher file-history --cat "tests/test_ai_dialogue.py" ~/.claude/projects/...

    # 查看特定版本
    doc_searcher file-history --cat "tests/test_ai_dialogue.py" --version 3 ~/.claude/projects/...

    # 恢复文件 (重定向到目标路径)
    doc_searcher file-history --cat "src/app.py" ~/.claude/projects/... > src/app.py

    # 查看文件各版本之间的 diff
    doc_searcher file-history --file "crawler.py" --diff ~/.claude/projects/...

    # 只看最近一天的备份
    doc_searcher file-history --after yd ~/.claude/projects/...

    # JSON 输出供脚本处理
    doc_searcher file-history --json ~/.claude/projects/... | jq '.files | keys'
""",

        'version': """
=== --version -- 版本号筛选 ===

  --version SPEC   仅保留路径中含匹配版本号的文件

  从文件路径中提取版本号 (如 v1.2.3, 1.0.0-beta), 然后匹配。

    规格        含义
    --------    --------------------------------
    1.2.3       精确匹配 1.2.3
    1.2         匹配 1.2 或 1.2.x
    >1.0        版本 > 1.0
    >=2.0       版本 >= 2.0
    <3.0        版本 < 3.0
    <=1.5       版本 <= 1.5
    1.x         1.开头的任意版本
    2.3.*       2.3.开头的任意版本

  示例:
    doc_searcher search "bug" /releases --version ">1.0"
    doc_searcher search "fix" /packages --version "2.x"
    doc_searcher scan /node_modules --version ">=3.0"
""",
    }

    topic = args.topic.lower() if args.topic else 'all'

    if topic == 'all':
        safe_print("""
============================================================
    HIDRS 文档内容搜索器 -- 完整帮助
============================================================

  子命令:
    search     搜索文件内容 (关键词/正则/反查)
    scan       列出目录下所有文本文件
    hash       通过 MD5/SHA 查找文件副本
    base64     Base64 双向搜索
    translate  批量翻译文件名 (中<->英)
    session       搜索 Claude Agent 会话日志 (JSONL)
    file-history  搜索 Claude Code 文件历史备份
    help          查看详细帮助

  帮助主题 (doc_searcher help <主题>):
    search     搜索功能详解
    date       日期筛选 + 快捷符号
    type       文件类型预设
    hash       Hash 指纹对比
    base64     Base64 搜索
    format     输出格式
    pipe       管道组合
    parallel      并行加速
    session       Agent 会话日志搜索
    file-history  文件历史备份搜索
    version       版本号筛选

  参数顺序 (重要):
    doc_searcher [全局选项] <子命令> [子命令选项] [参数]

    全局选项必须写在子命令之前:
      -d, --debug     调试模式 (显示后端选择、缓存命中等)

    正确:  doc_searcher -d search "key" .
    错误:  doc_searcher search "key" . -d    # -d 不是 search 的选项

  快速上手:
    doc_searcher search "关键词" /路径          基本搜索
    doc_searcher search "key" . --type py       按类型搜
    doc_searcher search "key" . --after 7d      最近7天
    doc_searcher search "key" . --format json   JSON输出
    doc_searcher -d search "key" .              调试模式
    doc_searcher hash <sha256> /dir             hash对比
    doc_searcher base64 "secret" /dir           base64搜索
    doc_searcher session "关键词" /会话目录      搜索会话日志
    doc_searcher session --tool Write /会话目录  按工具过滤
    doc_searcher file-history /项目目录          列出文件备份
    doc_searcher file-history --cat "src/app.py" /项目目录    查看备份内容
    doc_searcher file-history --cat "src/app.py" /项目目录 > src/app.py  恢复文件
    doc_searcher file-history --diff /项目目录   查看版本差异

  搜索后端 (自动降级):
    ripgrep (rg) -> grep -> findstr (Win) -> Python
    推荐安装 ripgrep 获得最佳性能: https://github.com/BurntSushi/ripgrep
  编码检测: UTF-8, GBK, Big5, Shift_JIS, EUC-KR 等自动识别
""")
        return 0

    if topic in topics:
        safe_print(topics[topic])
    else:
        safe_print(f"未知帮助主题: {topic}")
        safe_print(f"可用主题: {', '.join(sorted(topics.keys()))}")
        return 1
    return 0


# ============================================================
# Agent 会话日志搜索器 (Claude Code JSONL Session Logs)
# ============================================================

class SessionLogEntry:
    """解析后的单条会话日志"""

    __slots__ = ('type', 'role', 'tool_name', 'tool_input', 'content_text',
                 'thinking', 'timestamp', 'session_id', 'slug', 'model',
                 'file_path', 'uuid', 'line_num', 'raw_size',
                 'write_content')

    def __init__(self):
        self.type: str = ''           # 'assistant', 'user', 'file-history-snapshot'
        self.role: str = ''           # 'assistant', 'user'
        self.tool_name: str = ''      # 'Read', 'Edit', 'Write', 'Bash', 'Grep', 'Glob', ...
        self.tool_input: str = ''     # 工具输入参数摘要
        self.content_text: str = ''   # 文本内容 / 工具结果
        self.thinking: str = ''       # thinking 内容
        self.timestamp: str = ''      # ISO 时间
        self.session_id: str = ''
        self.slug: str = ''
        self.model: str = ''
        self.file_path: str = ''      # 涉及的文件路径
        self.uuid: str = ''
        self.line_num: int = 0        # JSONL 行号
        self.raw_size: int = 0        # 原始 JSON 字节大小
        self.write_content: str = ''  # Write/Edit/NotebookEdit 的完整文件内容


class SessionLogSearcher:
    """Claude Code 会话日志搜索器

    支持搜索 ~/.claude/projects/*/sessions/ 下的 JSONL 会话文件。
    每行一个 JSON 对象，包含 assistant/user 消息、tool_use、tool_result 等。
    """

    # 已知的工具名称（用于 --tool 过滤提示）
    KNOWN_TOOLS = {
        'Read', 'Edit', 'Write', 'Bash', 'Grep', 'Glob',
        'WebFetch', 'WebSearch', 'Task', 'TodoWrite',
        'NotebookEdit', 'AskUserQuestion',
    }

    def __init__(self, session_dir: str, *,
                 keyword: Optional[str] = None,
                 regex_pattern: Optional[str] = None,
                 case_sensitive: bool = False,
                 tool_filter: Optional[List[str]] = None,
                 role_filter: Optional[str] = None,
                 session_id_filter: Optional[str] = None,
                 slug_filter: Optional[str] = None,
                 after: Optional[datetime] = None,
                 before: Optional[datetime] = None,
                 max_results: int = 0,
                 content_only: bool = False,
                 show_thinking: bool = False,
                 skip_subagents: bool = False,
                 full_content: bool = False):

        self.session_dir = os.path.abspath(session_dir)
        self.full_content = full_content
        self.keyword = keyword
        self.regex_pattern = regex_pattern
        self.case_sensitive = case_sensitive
        self.tool_filter = [t.lower() for t in tool_filter] if tool_filter else None
        self.role_filter = role_filter  # 'user', 'assistant', None=all
        self.session_id_filter = session_id_filter
        self.slug_filter = slug_filter
        self.after = after
        self.before = before
        self.max_results = max_results
        self.content_only = content_only
        self.show_thinking = show_thinking
        self.skip_subagents = skip_subagents

        # 编译搜索模式
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            if regex_pattern:
                self._pattern = re.compile(regex_pattern, flags)
            elif keyword:
                self._pattern = re.compile(re.escape(keyword), flags)
            else:
                self._pattern = None
        except re.error as e:
            logger.warning(f"正则编译失败: {e}，改用纯文本搜索")
            self._pattern = re.compile(re.escape(regex_pattern or keyword), flags)

        self.stats = {
            'files_found': 0,     # 前置过滤后的文件数
            'files_scanned': 0,   # 实际逐行读取的文件数
            'lines_scanned': 0,
            'lines_matched': 0,
            'lines_parse_error': 0,
            'scan_time_seconds': 0.0,
        }

    def _find_session_files(self) -> List[str]:
        """
        查找所有 JSONL 会话文件，支持多层前置过滤以减少 I/O:

        1. session-id 文件名过滤: Claude Code JSONL 文件名即 UUID，
           --session-id 可直接匹配文件名，跳过无关文件
        2. mtime 前置过滤: --after 时文件 mtime < after 的肯定没有新条目可跳过
        3. rg 关键词预筛: 有搜索关键词时先用 ripgrep --files-with-matches
           找出包含关键词的文件，避免 Python 逐行读不匹配的大文件
        """
        files = []
        target = self.session_dir

        if os.path.isfile(target) and target.endswith('.jsonl'):
            return [target]

        # --- 阶段 1: 收集 .jsonl 文件 ---
        # 跳过 file-history 目录（文件编辑备份，不是聊天记录）
        _skip_dirs = {'file-history'}
        if self.skip_subagents:
            _skip_dirs.add('subagents')
        for root, dirs, fnames in os.walk(target):
            dirs[:] = [d for d in dirs if d not in _skip_dirs]
            for fname in fnames:
                if fname.endswith('.jsonl'):
                    files.append(os.path.join(root, fname))

        if not files:
            return []

        # --- 阶段 2: session-id 文件名前置过滤 ---
        # Claude Code 的 JSONL 文件名格式: {session-uuid}.jsonl
        # 子代理文件: subagents/agent-{shortHash}.jsonl
        # 一个 JSONL 内可能有多个 sessionId（--continue/--resume 追加），
        # 但文件名 UUID 是首个 session 的 ID，部分匹配仍可缩小范围
        if self.session_id_filter:
            sid = self.session_id_filter.lower()
            filtered = [f for f in files
                        if sid in os.path.basename(f).lower()
                        or sid in os.path.basename(os.path.dirname(f)).lower()]
            if filtered:
                files = filtered
                logger.debug(f"session-id 文件名过滤: {len(files)} 个文件匹配 '{sid}'")
            else:
                # 文件名没匹配到，可能是 --continue 追加的 sessionId，
                # 回退到全量扫描让行级过滤处理
                logger.debug(f"session-id '{sid}' 未匹配任何文件名，回退全量扫描")

        # --- 阶段 3: mtime 前置过滤 ---
        # 如果设了 --after，文件最后修改时间 < after 的文件中
        # 不可能有 after 之后的条目（JSONL 是追加写入的）
        if self.after:
            after_ts = self.after.timestamp()
            before_count = len(files)
            files = [f for f in files if os.path.getmtime(f) >= after_ts]
            skipped = before_count - len(files)
            if skipped > 0:
                logger.debug(f"mtime 前置过滤: 跳过 {skipped} 个旧文件")

        if not files:
            return []

        # --- 阶段 4: ripgrep 关键词预筛 ---
        # 有搜索关键词且 rg 可用时，先用 rg --files-with-matches 快速筛出
        # 包含关键词的文件，避免 Python 逐行读大量不匹配的 JSONL
        pattern = self.keyword or self.regex_pattern
        if pattern and len(files) > 1:
            rg_bin = shutil.which('rg')
            if rg_bin:
                try:
                    cmd = [rg_bin, '--files-with-matches', '--no-messages']
                    if not (self.regex_pattern):
                        cmd.append('--fixed-strings')
                    if not self.case_sensitive:
                        cmd.append('--ignore-case')
                    cmd.append(pattern)
                    cmd.extend(files)
                    proc = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=30)
                    if proc.returncode == 0 and proc.stdout.strip():
                        rg_files = set(proc.stdout.strip().splitlines())
                        before_count = len(files)
                        files = [f for f in files if f in rg_files]
                        skipped = before_count - len(files)
                        if skipped > 0:
                            logger.debug(f"rg 预筛: 跳过 {skipped} 个无匹配文件")
                    elif proc.returncode == 1:
                        # rg 返回 1 表示没有任何匹配
                        logger.debug("rg 预筛: 所有文件均无匹配")
                        return []
                except (subprocess.TimeoutExpired, OSError) as e:
                    logger.debug(f"rg 预筛失败，回退全量扫描: {e}")

        # 按修改时间排序（最新在前）
        files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        self.stats['files_found'] = len(files)
        return files

    def _parse_entry(self, line: str, line_num: int) -> Optional[SessionLogEntry]:
        """解析单行 JSONL 为 SessionLogEntry"""
        try:
            obj = _fast_json.loads(line)
        except (json.JSONDecodeError, ValueError, TypeError):
            self.stats['lines_parse_error'] += 1
            return None

        if not isinstance(obj, dict):
            return None

        entry = SessionLogEntry()
        entry.line_num = line_num
        entry.raw_size = len(line)
        entry.type = obj.get('type', '')
        entry.session_id = obj.get('sessionId', '')
        entry.slug = obj.get('slug', '')
        entry.uuid = obj.get('uuid', '')
        entry.timestamp = obj.get('timestamp', '')

        # 跳过非消息类型
        if entry.type == 'file-history-snapshot':
            return None

        # history.jsonl 格式: {"display": "用户输入", "timestamp": epoch_ms, ...}
        msg = obj.get('message', {})
        if not msg and 'display' in obj:
            entry.role = 'user'
            entry.type = 'history'
            entry.content_text = obj.get('display', '')
            # epoch ms -> ISO
            ts_ms = obj.get('timestamp', 0)
            if ts_ms:
                try:
                    entry.timestamp = datetime.fromtimestamp(ts_ms / 1000).isoformat()
                except (OSError, ValueError):
                    pass
            return entry

        if not msg:
            return None

        entry.role = msg.get('role', '')
        entry.model = msg.get('model', '')

        contents = msg.get('content', [])
        if isinstance(contents, str):
            # 有时 content 是纯字符串
            entry.content_text = contents
            return entry

        if not isinstance(contents, list):
            return None

        # 解析 content blocks
        text_parts = []
        for block in contents:
            if not isinstance(block, dict):
                continue

            block_type = block.get('type', '')

            if block_type == 'text':
                text_parts.append(block.get('text', ''))

            elif block_type == 'thinking':
                entry.thinking = block.get('thinking', '')

            elif block_type == 'tool_use':
                entry.tool_name = block.get('name', '')
                inp = block.get('input', {})
                if isinstance(inp, dict):
                    # 提取关键参数（强制 str 防止 JSON 字段类型异常）
                    fp = str(inp.get('file_path', '') or inp.get('notebook_path', '') or inp.get('path', '') or '')
                    if fp:
                        entry.file_path = fp
                    cmd = str(inp.get('command', '') or '')
                    pattern = str(inp.get('pattern', '') or inp.get('keyword', '') or '')
                    content = str(inp.get('content', '') or '')
                    # Task 工具特有字段
                    description = str(inp.get('description', '') or '')
                    prompt = str(inp.get('prompt', '') or '')
                    subagent = str(inp.get('subagent_type', '') or '')
                    # TodoWrite 特有字段
                    todos = inp.get('todos', [])
                    # 组装摘要
                    parts = []
                    if fp:
                        parts.append(fp)
                    if cmd:
                        parts.append(cmd[:200])
                    if pattern:
                        parts.append(f'pattern="{pattern}"')
                    if description:
                        tag = f'[{subagent}] ' if subagent else ''
                        parts.append(f'{tag}{description}')
                    if prompt and not description:
                        parts.append(prompt[:200])
                    if todos and isinstance(todos, list):
                        todo_summary = '; '.join(
                            str(t.get('content', ''))[:40]
                            for t in todos[:5] if isinstance(t, dict)
                        )
                        if todo_summary:
                            parts.append(todo_summary)
                    if content and not fp:
                        parts.append(content[:100])
                    entry.tool_input = ' | '.join(parts) if parts else json.dumps(inp, ensure_ascii=False)[:200]

                    # --full-content: 保存 Write/Edit/NotebookEdit 的完整写入内容
                    if self.full_content and entry.tool_name in ('Write', 'Edit', 'NotebookEdit'):
                        wc_parts = []
                        if content:  # Write.content / NotebookEdit.new_source 共用 'content' 键
                            wc_parts.append(content)
                        new_source = str(inp.get('new_source', '') or '')
                        if new_source:  # NotebookEdit
                            wc_parts.append(new_source)
                        old_string = str(inp.get('old_string', '') or '')
                        new_string = str(inp.get('new_string', '') or '')
                        if old_string or new_string:  # Edit
                            edit_parts = []
                            if old_string:
                                edit_parts.append(f'--- old_string ---\n{old_string}')
                            if new_string:
                                edit_parts.append(f'+++ new_string +++\n{new_string}')
                            wc_parts.append('\n'.join(edit_parts))
                        if wc_parts:
                            entry.write_content = '\n'.join(wc_parts)

            elif block_type == 'tool_result':
                # 用户消息中的 tool_result
                result_content = block.get('content', '')
                if isinstance(result_content, str):
                    text_parts.append(result_content)
                elif isinstance(result_content, list):
                    for rc in result_content:
                        if isinstance(rc, dict) and rc.get('type') == 'text':
                            text_parts.append(rc.get('text', ''))

        # 也检查 toolUseResult（旧格式）
        tool_result = obj.get('toolUseResult', {})
        if isinstance(tool_result, dict):
            tr_text = tool_result.get('type', '')
            if tr_text == 'text':
                file_info = tool_result.get('file', {})
                if isinstance(file_info, dict):
                    fp = str(file_info.get('filePath', '') or '')
                    if fp:
                        entry.file_path = entry.file_path or fp
                    fc = str(file_info.get('content', '') or '')
                    if fc:
                        text_parts.append(fc[:500])

        entry.content_text = '\n'.join(text_parts)
        return entry

    def _match_entry(self, entry: SessionLogEntry) -> bool:
        """检查条目是否匹配所有过滤条件"""
        # 角色过滤
        if self.role_filter:
            if entry.role != self.role_filter:
                return False

        # 工具过滤
        if self.tool_filter:
            if not entry.tool_name:
                return False
            if entry.tool_name.lower() not in self.tool_filter:
                return False

        # 会话 ID 过滤
        if self.session_id_filter:
            if self.session_id_filter not in entry.session_id:
                return False

        # slug 过滤
        if self.slug_filter:
            if self.slug_filter.lower() not in entry.slug.lower():
                return False

        # 日期过滤（datetime 对象比较）
        if self.after or self.before:
            ts = entry.timestamp
            if ts:
                try:
                    # 解析 ISO 格式时间戳
                    ts_dt = datetime.fromisoformat(ts[:19])
                    if self.after and ts_dt < self.after:
                        return False
                    if self.before and ts_dt > self.before:
                        return False
                except (ValueError, TypeError):
                    pass  # 时间戳格式异常时不过滤

        # 关键词过滤（thinking 始终参与搜索，不受 --thinking 显示开关影响）
        if self._pattern:
            searchable = '\n'.join(filter(None, [
                entry.content_text,
                entry.tool_input,
                entry.tool_name,
                entry.file_path,
                entry.thinking,
                entry.write_content,
            ]))
            if not self._pattern.search(searchable):
                return False

        return True

    def search(self) -> List[SessionLogEntry]:
        """搜索会话日志"""
        start = time.time()
        files = self._find_session_files()
        self.stats['files_scanned'] = len(files)

        results: List[SessionLogEntry] = []

        for fpath in files:
            try:
                # utf-8-sig 自动剥离 BOM (Windows 记事本等生成的文件可能有 BOM)
                with open(fpath, 'r', encoding='utf-8-sig', errors='replace') as f:
                    for line_num, line in enumerate(f, 1):
                        self.stats['lines_scanned'] += 1
                        line = line.strip()
                        if not line:
                            continue

                        entry = self._parse_entry(line, line_num)
                        if entry is None:
                            continue

                        if self._match_entry(entry):
                            self.stats['lines_matched'] += 1
                            results.append(entry)

                            if self.max_results > 0 and len(results) >= self.max_results:
                                break
            except OSError as e:
                logger.debug(f"读取会话文件失败: {fpath}: {e}")
                continue

            if self.max_results > 0 and len(results) >= self.max_results:
                break

        self.stats['scan_time_seconds'] = round(time.time() - start, 3)
        return results

    def format_results(self, results: List[SessionLogEntry],
                       verbose: bool = False) -> str:
        """格式化搜索结果"""
        lines = []
        sep = '=' * 72

        lines.append(sep)
        lines.append('  HIDRS Agent 会话日志搜索器')
        lines.append(sep)
        if self.keyword:
            lines.append(f"  关键词: {self.keyword}")
        if self.regex_pattern:
            lines.append(f"  正则:   {self.regex_pattern}")
        if self.tool_filter:
            lines.append(f"  工具:   {', '.join(self.tool_filter)}")
        if self.role_filter:
            lines.append(f"  角色:   {self.role_filter}")
        if self.slug_filter:
            lines.append(f"  会话:   {self.slug_filter}")
        found = self.stats.get('files_found', 0)
        scanned = self.stats['files_scanned']
        pre_filter = f" (预筛后 {found})" if found and found != scanned else ""
        lines.append(f"  扫描: {scanned} 个文件{pre_filter} | "
                     f"{self.stats['lines_scanned']} 行 | "
                     f"命中: {self.stats['lines_matched']} | "
                     f"解析错误: {self.stats['lines_parse_error']} | "
                     f"耗时: {self.stats['scan_time_seconds']}s")
        lines.append(sep)

        if not results:
            lines.append('  未找到匹配结果。')
            lines.append(sep)
            return '\n'.join(lines)

        for idx, e in enumerate(results, 1):
            lines.append('')

            # 标题行: [序号] 角色/工具 @ 时间
            ts_short = e.timestamp[:19].replace('T', ' ') if e.timestamp else '?'
            if e.tool_name:
                tag = f"{e.role}:{e.tool_name}"
            else:
                tag = e.role or e.type
            slug_tag = f" [{e.slug}]" if e.slug else ''
            model_tag = f" ({e.model})" if e.model and verbose else ''

            lines.append(f"  [{idx}] {tag}{model_tag}  {ts_short}{slug_tag}")

            # 文件路径
            if e.file_path:
                lines.append(f"       文件: {e.file_path}")

            # 工具输入
            if e.tool_input:
                inp_display = e.tool_input
                if not verbose and len(inp_display) > 120:
                    inp_display = inp_display[:120] + '...'
                lines.append(f"       输入: {inp_display}")

            # 内容
            if e.content_text:
                content = e.content_text
                if not verbose:
                    # 截断长内容
                    content_lines = content.split('\n')
                    if len(content_lines) > 5:
                        content = '\n'.join(content_lines[:5]) + f'\n       ... ({len(content_lines)} 行)'
                    if len(content) > 300:
                        content = content[:300] + '...'
                for cl in content.split('\n'):
                    lines.append(f"       {cl}")

            # 写入内容: --full-content 时显示
            if e.write_content:
                lines.append(f"       ┌── 写入内容 ({len(e.write_content)} 字符) ──")
                for cl in e.write_content.split('\n'):
                    lines.append(f"       │ {cl}")
                lines.append(f"       └──────────────────")

            # thinking: --thinking 时始终显示，否则仅当关键词匹配到 thinking 时显示
            if e.thinking:
                show_it = self.show_thinking
                if not show_it and self._pattern and self._pattern.search(e.thinking):
                    show_it = True  # 关键词命中了 thinking，自动显示
                if show_it:
                    thinking = e.thinking
                    if not verbose and len(thinking) > 200:
                        thinking = thinking[:200] + '...'
                    lines.append(f"       [思考] {thinking}")

        lines.append('')
        lines.append(sep)
        return '\n'.join(lines)

    def format_json(self, results: List[SessionLogEntry]) -> str:
        """JSON 格式输出"""
        data = []
        for e in results:
            d = {
                'type': e.type,
                'role': e.role,
                'tool_name': e.tool_name or None,
                'tool_input': e.tool_input or None,
                'file_path': e.file_path or None,
                'content': e.content_text[:1000] if e.content_text else None,
                'write_content': e.write_content if e.write_content else None,
                'thinking': e.thinking[:500] if e.thinking else None,
                'timestamp': e.timestamp,
                'session_id': e.session_id,
                'slug': e.slug,
                'model': e.model or None,
                'line_num': e.line_num,
            }
            data.append(d)

        output = {
            'stats': self.stats,
            'results': data,
        }
        return json.dumps(output, ensure_ascii=False, indent=2)

    def format_grep(self, results: List[SessionLogEntry]) -> str:
        """grep 兼容格式: slug:timestamp:tool:content"""
        lines = []
        for e in results:
            content = (e.tool_input or e.content_text or '').replace('\n', ' ')[:200]
            tool = e.tool_name or e.role
            ts = e.timestamp[:19] if e.timestamp else '?'
            slug = e.slug or e.session_id[:8]
            lines.append(f"{slug}:{ts}:{tool}:{content}")
        return '\n'.join(lines)


def _cmd_session(args) -> int:
    """session 子命令: 搜索 Claude Agent 会话日志"""
    # 参数修正: 只传一个参数时，检查 keyword 是否其实是路径
    # 例: doc_searcher session /path/to/sessions
    #   -> argparse 把 /path/to/sessions 解析为 keyword，path 为 '.'
    keyword = args.keyword
    path = args.path
    if keyword and os.path.exists(keyword) and path == '.':
        # keyword 其实是路径
        path = keyword
        keyword = None
    elif keyword and not os.path.exists(path) and path != '.':
        # 两个参数都给了但 path 不存在 -> 可能顺序搞反了
        if os.path.exists(keyword):
            keyword, path = path, keyword

    session_dir = os.path.abspath(path)
    if not os.path.exists(session_dir):
        safe_print(f"路径不存在: {session_dir}", file=sys.stderr)
        return 1

    # 工具过滤
    tool_filter = None
    if args.tool:
        tool_filter = [t.strip() for t in args.tool.split(',')]

    # 日期格式处理（支持快捷符: td yd 3d 7d tw lw tm lm 等）
    after_ts = parse_date(args.after) if args.after else None
    before_ts = parse_date(args.before) if args.before else None

    searcher = SessionLogSearcher(
        session_dir,
        keyword=None if args.regex else keyword,
        regex_pattern=keyword if args.regex else None,
        case_sensitive=args.case_sensitive,
        tool_filter=tool_filter,
        role_filter=args.role,
        session_id_filter=args.session_id,
        slug_filter=args.slug,
        after=after_ts,
        before=before_ts,
        max_results=args.max_results,
        show_thinking=args.thinking,
        skip_subagents=getattr(args, 'no_subagents', False),
        full_content=getattr(args, 'full_content', False),
    )

    results = searcher.search()

    # 输出格式
    # --verbose / --full-content 强制 text（不走 grep 缩略格式）
    fmt = 'text'
    if getattr(args, 'json', False):
        fmt = 'json'
    elif OutputFormatter.is_piped() and not args.verbose and not getattr(args, 'full_content', False):
        fmt = 'grep'

    if fmt == 'json':
        safe_print(searcher.format_json(results))
    elif fmt == 'grep':
        safe_print(searcher.format_grep(results))
    else:
        safe_print(searcher.format_results(results, verbose=args.verbose))

    return 0


# ============================================================
# file-history: Claude Code 文件历史备份搜索
# ============================================================

class FileHistoryEntry:
    """单条文件历史备份记录"""

    __slots__ = ('file_path', 'backup_filename', 'version', 'backup_time',
                 'message_id', 'session_id', 'session_slug',
                 'backup_full_path', 'exists', 'is_deleted')

    def __init__(self):
        self.file_path: str = ''         # 文件相对路径 (相对于项目 cwd)
        self.backup_filename: str = ''   # hash@v{n}
        self.version: int = 0
        self.backup_time: str = ''       # ISO 时间戳
        self.message_id: str = ''        # 关联的消息 UUID
        self.session_id: str = ''        # 会话 UUID (来自 JSONL 文件名)
        self.session_slug: str = ''
        self.backup_full_path: str = ''  # 备份文件物理路径
        self.exists: bool = False        # 备份文件是否存在
        self.is_deleted: bool = False    # 该快照表示文件被删除 (backupFileName=null)


class FileHistorySearcher:
    """Claude Code 文件历史备份搜索器

    解析 JSONL 中的 file-history-snapshot 条目，交叉引用
    ~/.claude/file-history/{sessionId}/ 下的物理备份文件。
    """

    def __init__(self, project_dir: str, *,
                 file_pattern: Optional[str] = None,
                 session_id_filter: Optional[str] = None,
                 after: Optional[datetime] = None,
                 before: Optional[datetime] = None):

        self.project_dir = os.path.abspath(project_dir)
        self.file_pattern = file_pattern.lower() if file_pattern else None
        self.session_id_filter = session_id_filter
        self.after = after
        self.before = before

        # Claude Code 的 file-history 根目录
        claude_home = os.environ.get('CLAUDE_CONFIG_DIR',
                                     os.path.expanduser('~/.claude'))
        self.file_history_root = os.path.join(claude_home, 'file-history')

        self.stats = {
            'jsonl_files': 0,
            'snapshots_parsed': 0,
            'entries_total': 0,
            'entries_matched': 0,
            'backups_found': 0,
            'backups_missing': 0,
        }

    def _find_jsonl_files(self) -> List[str]:
        """在项目目录下找到所有 JSONL 文件"""
        files = []
        skip_dirs = {'file-history'}
        target = self.project_dir

        if os.path.isfile(target) and target.endswith('.jsonl'):
            return [target]

        for root, dirs, fnames in os.walk(target):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for fname in fnames:
                if fname.endswith('.jsonl'):
                    files.append(os.path.join(root, fname))

        # session-id 前置过滤：JSONL 文件名即 session UUID
        if self.session_id_filter and files:
            sid = self.session_id_filter.lower()
            filtered = [f for f in files
                        if sid in os.path.basename(f).lower()
                        or sid in os.path.basename(os.path.dirname(f)).lower()]
            if filtered:
                files = filtered

        return files

    def _extract_session_id_from_path(self, jsonl_path: str) -> str:
        """从 JSONL 文件路径提取 session UUID

        文件名格式: {session-uuid}.jsonl
        子代理路径: {session-uuid}/subagents/agent-{hash}.jsonl
        """
        fname = os.path.basename(jsonl_path)
        stem = fname.rsplit('.', 1)[0]  # 去掉 .jsonl

        # 主会话文件: 文件名本身就是 UUID
        # 检测 UUID 格式 (8-4-4-4-12)
        if len(stem) == 36 and stem.count('-') == 4:
            return stem

        # 子代理文件: 从父级目录取 session UUID
        parent = os.path.basename(os.path.dirname(jsonl_path))
        if len(parent) == 36 and parent.count('-') == 4:
            return parent

        # 再往上一级（subagents/ 的父目录）
        grandparent = os.path.basename(
            os.path.dirname(os.path.dirname(jsonl_path)))
        if len(grandparent) == 36 and grandparent.count('-') == 4:
            return grandparent

        return stem  # 回退

    def _parse_snapshots(self, jsonl_path: str) -> List[FileHistoryEntry]:
        """从单个 JSONL 文件解析 file-history-snapshot 条目"""
        entries = []
        session_id = self._extract_session_id_from_path(jsonl_path)

        # 快速预检: 文件中是否有 file-history-snapshot
        try:
            with open(jsonl_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            if 'file-history-snapshot' not in content:
                return []
        except (OSError, IOError):
            return []

        # 从文件中提取 slug（读第一行获取）
        slug = ''
        for raw_line in content.split('\n'):
            if not raw_line.strip():
                continue
            try:
                first_obj = json.loads(raw_line)
                slug = first_obj.get('sessionSlug', '') or first_obj.get('slug', '')
                if slug:
                    break
            except (json.JSONDecodeError, ValueError):
                pass

        for line_text in content.split('\n'):
            if 'file-history-snapshot' not in line_text:
                continue
            try:
                obj = json.loads(line_text)
            except (json.JSONDecodeError, ValueError):
                continue

            if obj.get('type') != 'file-history-snapshot':
                continue

            self.stats['snapshots_parsed'] += 1
            snapshot = obj.get('snapshot', {})
            if not isinstance(snapshot, dict):
                continue

            message_id = snapshot.get('messageId', '') or obj.get('messageId', '')
            snap_ts = snapshot.get('timestamp', '') or ''
            tracked = snapshot.get('trackedFileBackups', {})
            if not isinstance(tracked, dict):
                continue

            for rel_path, backup_info in tracked.items():
                if not isinstance(backup_info, dict):
                    continue

                e = FileHistoryEntry()
                e.file_path = rel_path
                e.session_id = session_id
                e.session_slug = slug
                e.message_id = message_id
                e.backup_time = backup_info.get('backupTime', snap_ts) or snap_ts

                bfn = backup_info.get('backupFileName')
                if bfn is None:
                    # backupFileName=null 表示文件在此快照时不存在（被删除）
                    e.is_deleted = True
                    e.version = backup_info.get('version', 0) or 0
                else:
                    e.backup_filename = str(bfn)
                    e.version = backup_info.get('version', 0) or 0
                    # 构建物理备份路径
                    e.backup_full_path = os.path.join(
                        self.file_history_root, session_id, e.backup_filename)
                    e.exists = os.path.isfile(e.backup_full_path)

                entries.append(e)
                self.stats['entries_total'] += 1

        return entries

    def _match_entry(self, entry: FileHistoryEntry) -> bool:
        """过滤单条记录"""
        # 文件路径过滤
        if self.file_pattern:
            if self.file_pattern not in entry.file_path.lower():
                return False

        # session-id 过滤
        if self.session_id_filter:
            if self.session_id_filter not in entry.session_id:
                return False

        # 时间过滤
        if (self.after or self.before) and entry.backup_time:
            try:
                ts_str = entry.backup_time
                if ts_str.endswith('Z'):
                    ts_str = ts_str[:-1]
                ts_dt = datetime.fromisoformat(ts_str[:19])
                if self.after and ts_dt < self.after:
                    return False
                if self.before and ts_dt > self.before:
                    return False
            except (ValueError, TypeError):
                pass

        return True

    def search(self) -> List[FileHistoryEntry]:
        """搜索文件历史备份"""
        jsonl_files = self._find_jsonl_files()
        self.stats['jsonl_files'] = len(jsonl_files)

        all_entries = []
        for jf in jsonl_files:
            entries = self._parse_snapshots(jf)
            for e in entries:
                if self._match_entry(e):
                    all_entries.append(e)
                    self.stats['entries_matched'] += 1
                    if e.exists:
                        self.stats['backups_found'] += 1
                    elif not e.is_deleted:
                        self.stats['backups_missing'] += 1

        # 按时间排序（最新在前），然后按文件路径分组
        all_entries.sort(key=lambda e: (e.file_path, e.backup_time or ''))
        return all_entries

    def read_backup(self, entry: FileHistoryEntry) -> Optional[str]:
        """读取备份文件内容"""
        if not entry.exists or not entry.backup_full_path:
            return None
        try:
            with open(entry.backup_full_path, 'r', encoding='utf-8',
                      errors='replace') as f:
                return f.read()
        except (OSError, IOError) as e:
            logger.warning(f"读取备份文件失败: {entry.backup_full_path}: {e}")
            return None

    def find_entry(self, file_path: str,
                   version: Optional[int] = None) -> Optional[FileHistoryEntry]:
        """查找指定文件（可选版本）的备份记录"""
        results = self.search()
        fp_lower = file_path.lower()
        candidates = [e for e in results
                      if fp_lower in e.file_path.lower() and not e.is_deleted]

        if not candidates:
            return None

        if version is not None:
            for c in candidates:
                if c.version == version:
                    return c
            return None

        # 默认返回最高版本
        candidates.sort(key=lambda e: e.version, reverse=True)
        return candidates[0]

    def get_file_timeline(self, results: List[FileHistoryEntry]
                          ) -> Dict[str, List[FileHistoryEntry]]:
        """将结果按文件路径分组为时间线"""
        timeline: Dict[str, List[FileHistoryEntry]] = {}
        for e in results:
            timeline.setdefault(e.file_path, []).append(e)
        # 每个文件内按版本排序
        for entries in timeline.values():
            entries.sort(key=lambda e: e.version)
        return timeline

    def format_results(self, results: List[FileHistoryEntry], *,
                       verbose: bool = False,
                       show_diff: bool = False) -> str:
        """文本格式输出"""
        lines = []
        sep = '─' * 72

        # 统计头
        lines.append(sep)
        lines.append(f"  file-history | JSONL: {self.stats['jsonl_files']} 个 | "
                     f"快照: {self.stats['snapshots_parsed']} 条 | "
                     f"备份: {self.stats['backups_found']} 存在 / "
                     f"{self.stats['backups_missing']} 缺失")
        lines.append(sep)

        if not results:
            lines.append('  未找到文件历史备份。')
            lines.append(sep)
            return '\n'.join(lines)

        timeline = self.get_file_timeline(results)

        for fp, entries in sorted(timeline.items()):
            lines.append('')
            lines.append(f"  {fp}  ({len(entries)} 个版本)")

            prev_content = None
            for e in entries:
                ts_short = ''
                if e.backup_time:
                    ts_short = e.backup_time[:19].replace('T', ' ')

                if e.is_deleted:
                    status = '[已删除]'
                elif e.exists:
                    status = '[存在]'
                else:
                    status = '[缺失]'

                slug_tag = f" [{e.session_slug}]" if e.session_slug else ''
                sid_short = e.session_id[:8] if e.session_id else ''

                lines.append(
                    f"    v{e.version}  {ts_short}  {status}  "
                    f"{e.backup_filename or '(null)'}{slug_tag}  @{sid_short}")

                if verbose and e.exists:
                    content = self.read_backup(e)
                    if content is not None:
                        preview_lines = content.split('\n')
                        if len(preview_lines) > 10:
                            for cl in preview_lines[:10]:
                                lines.append(f"      │ {cl}")
                            lines.append(
                                f"      │ ... ({len(preview_lines)} 行, "
                                f"{len(content)} 字符)")
                        else:
                            for cl in preview_lines:
                                lines.append(f"      │ {cl}")

                if show_diff and e.exists and prev_content is not None:
                    curr_content = self.read_backup(e)
                    if curr_content is not None:
                        import difflib
                        prev_lines = prev_content.split('\n')
                        curr_lines = curr_content.split('\n')
                        diff = difflib.unified_diff(
                            prev_lines, curr_lines,
                            fromfile=f'v{e.version - 1}',
                            tofile=f'v{e.version}',
                            lineterm='')
                        diff_lines = list(diff)
                        if diff_lines:
                            for dl in diff_lines[:30]:
                                lines.append(f"      {dl}")
                            if len(diff_lines) > 30:
                                lines.append(
                                    f"      ... ({len(diff_lines)} 行 diff)")
                        prev_content = curr_content

                if show_diff and e.exists and prev_content is None:
                    prev_content = self.read_backup(e)

        lines.append('')
        lines.append(sep)
        return '\n'.join(lines)

    def format_json(self, results: List[FileHistoryEntry]) -> str:
        """JSON 格式输出"""
        timeline = self.get_file_timeline(results)
        data = {}
        for fp, entries in timeline.items():
            data[fp] = []
            for e in entries:
                d = {
                    'version': e.version,
                    'backup_filename': e.backup_filename or None,
                    'backup_time': e.backup_time or None,
                    'session_id': e.session_id,
                    'session_slug': e.session_slug or None,
                    'message_id': e.message_id or None,
                    'backup_path': e.backup_full_path or None,
                    'exists': e.exists,
                    'is_deleted': e.is_deleted,
                }
                data[fp].append(d)

        output = {
            'stats': self.stats,
            'file_history_root': self.file_history_root,
            'files': data,
        }
        return json.dumps(output, ensure_ascii=False, indent=2)


def _cmd_file_history(args) -> int:
    """file-history 子命令: 搜索 Claude Code 文件历史备份"""
    project_dir = os.path.abspath(args.path)

    if not os.path.exists(project_dir):
        safe_print(f"错误: 路径不存在: {project_dir}", file=sys.stderr)
        return 1

    after_ts = parse_date(args.after) if args.after else None
    before_ts = parse_date(args.before) if args.before else None

    searcher = FileHistorySearcher(
        project_dir,
        file_pattern=getattr(args, 'file', None),
        session_id_filter=args.session_id,
        after=after_ts,
        before=before_ts,
    )

    # --cat 模式: 输出指定文件的备份内容
    cat_path = getattr(args, 'cat', None)
    if cat_path:
        entry = searcher.find_entry(cat_path, version=args.version)
        if entry is None:
            safe_print(f"错误: 未找到 '{cat_path}' 的备份"
                       + (f" (v{args.version})" if args.version else ''),
                       file=sys.stderr)
            safe_print(f"  JSONL 搜索目录: {project_dir}", file=sys.stderr)
            safe_print(f"  备份文件根目录: {searcher.file_history_root}", file=sys.stderr)
            # 提示可用文件
            all_results = searcher.search()
            all_files = sorted(set(e.file_path for e in all_results if e.file_path))
            if all_files:
                safe_print(f"  可用文件 ({len(all_files)} 个):", file=sys.stderr)
                for fp in all_files[:10]:
                    safe_print(f"    - {fp}", file=sys.stderr)
                if len(all_files) > 10:
                    safe_print(f"    ... 还有 {len(all_files)-10} 个", file=sys.stderr)
            else:
                safe_print("  (未找到任何文件历史记录)", file=sys.stderr)
            return 1
        if not entry.exists:
            safe_print(f"错误: 备份文件不存在: {entry.backup_full_path}",
                       file=sys.stderr)
            safe_print(f"  备份文件根目录: {searcher.file_history_root}", file=sys.stderr)
            return 1
        content = searcher.read_backup(entry)
        if content is None:
            safe_print("错误: 无法读取备份文件", file=sys.stderr)
            return 1
        safe_print(content)
        return 0

    # 列表模式
    results = searcher.search()

    fmt = 'text'
    if getattr(args, 'json', False):
        fmt = 'json'

    if fmt == 'json':
        safe_print(searcher.format_json(results))
    else:
        safe_print(searcher.format_results(
            results,
            verbose=args.verbose,
            show_diff=getattr(args, 'diff', False),
        ))

    return 0


if __name__ == '__main__':
    sys.exit(cli_main())
