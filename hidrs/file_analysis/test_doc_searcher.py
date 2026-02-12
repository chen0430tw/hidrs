#!/usr/bin/env python3
"""
doc_searcher 功能测试
"""
import os
import sys
import json
import hashlib
import base64
import tempfile
import shutil
import time
import importlib.util
from datetime import datetime, timedelta

# 直接加载模块（避开 hidrs/__init__.py 的缺失依赖）
spec = importlib.util.spec_from_file_location(
    'doc_searcher',
    os.path.join(os.path.dirname(__file__), 'doc_searcher.py')
)
ds = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ds)

PASS = 0
FAIL = 0


def check(name, condition, detail=''):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}  {detail}")


def create_test_dir():
    """创建临时测试目录结构"""
    tmp = tempfile.mkdtemp(prefix='doc_searcher_test_')

    # 基本文本文件
    write(tmp, 'hello.py', '# Python file\nprint("hello world")\n# TODO: fix bug\n')
    write(tmp, 'config.yaml', 'database:\n  host: localhost\n  password: secret123\n')
    write(tmp, 'readme.md', '# Project README\nThis is a test project.\n')
    write(tmp, 'data.csv', 'name,value\nalpha,100\nbeta,200\n')
    write(tmp, 'noext', 'This file has no extension but is text.\nSearch me!\n')

    # 子目录
    os.makedirs(os.path.join(tmp, 'src'))
    write(tmp, 'src/main.py', 'import os\ndef main():\n    pass\n# TODO: implement\n')
    write(tmp, 'src/utils.js', 'function helper() { return "TODO"; }\n')

    os.makedirs(os.path.join(tmp, 'v1.2.3'))
    write(tmp, 'v1.2.3/release.txt', 'Release notes for v1.2.3\n')

    os.makedirs(os.path.join(tmp, 'v2.0.0'))
    write(tmp, 'v2.0.0/release.txt', 'Release notes for v2.0.0\n')

    # Base64 内容
    secret = base64.b64encode(b'admin:password').decode()
    write(tmp, 'encoded.conf', f'# Config\nauth_token = {secret}\nnormal_key = value\n')

    # GBK 编码文件
    write_bytes(tmp, 'chinese_gbk.txt', '这是一个GBK编码的文件\n搜索测试\n'.encode('gbk'))

    # 大文件模拟（用重复行填充）
    big_content = ('Line of text number {n}\n' * 1000).format(n='X')
    big_content += 'NEEDLE_IN_HAYSTACK\n'
    big_content += ('Another line {n}\n' * 500).format(n='Y')
    write(tmp, 'bigfile.log', big_content)

    return tmp


def write(base, name, content):
    path = os.path.join(base, name)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def write_bytes(base, name, data):
    path = os.path.join(base, name)
    with open(path, 'wb') as f:
        f.write(data)


def test_basic_search(tmp):
    print("\n[1] 基本搜索")
    searcher = ds.DocSearcher(target_path=tmp, keyword='TODO')
    results = searcher.search()
    paths = [r.path for r in results]
    check('找到含 TODO 的文件', len(results) >= 2,
          f'got {len(results)}')
    check('hello.py 在结果中', any('hello.py' in p for p in paths))
    check('main.py 在结果中', any('main.py' in p for p in paths))
    check('readme.md 不在结果中', not any('readme.md' in p for p in paths))


def test_regex_search(tmp):
    print("\n[2] 正则搜索")
    searcher = ds.DocSearcher(target_path=tmp, regex_pattern=r'password|secret\d+')
    results = searcher.search()
    check('正则搜索找到结果', len(results) >= 1)
    check('config.yaml 命中', any('config.yaml' in r.path for r in results))


def test_invert_search(tmp):
    print("\n[3] 反查搜索")
    searcher = ds.DocSearcher(target_path=tmp, keyword='TODO', invert=True)
    results = searcher.search()
    paths = [r.path for r in results]
    check('反查结果不含 hello.py', not any('hello.py' in p for p in paths))
    check('反查结果含 config.yaml', any('config.yaml' in p for p in paths))


def test_type_preset(tmp):
    print("\n[4] --type 文件类型预设")
    # 搜索 py 类型
    searcher = ds.DocSearcher(
        target_path=tmp, keyword='TODO',
        include_patterns=ds.FILE_TYPE_PRESETS['py']
    )
    results = searcher.search()
    check('--type py 仅找到 .py 文件',
          all(r.path.endswith('.py') for r in results),
          f'got {[os.path.basename(r.path) for r in results]}')
    check('至少找到 1 个 py 文件', len(results) >= 1)


def test_date_shortcuts():
    print("\n[5] 日期快捷符号")
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    check('td = 今天', ds.parse_date('td') == today_start)
    check('yd = 昨天', ds.parse_date('yd') == today_start - timedelta(days=1))
    check('tw = 本周一', ds.parse_date('tw').weekday() == 0)  # Monday
    check('tm = 本月1日', ds.parse_date('tm').day == 1)
    check('ty = 今年1/1', ds.parse_date('ty').month == 1 and ds.parse_date('ty').day == 1)
    check('ly = 去年1/1', ds.parse_date('ly').year == now.year - 1)
    check('lm = 上月', ds.parse_date('lm').month == (now.month - 1 if now.month > 1 else 12))

    # 相对偏移
    d3 = ds.parse_date('3d')
    check('3d ≈ 3天前', abs((now - d3).total_seconds() - 3 * 86400) < 5)
    d1h = ds.parse_date('1h')
    check('1h ≈ 1小时前', abs((now - d1h).total_seconds() - 3600) < 5)
    d2w = ds.parse_date('2w')
    check('2w ≈ 2周前', abs((now - d2w).total_seconds() - 14 * 86400) < 5)

    # 时间戳
    ts = ds.parse_date('@1700000000')
    check('@1700000000 解析', ts.year == 2023)

    # 标准格式
    check('YYYY-MM-DD', ds.parse_date('2026-01-15').day == 15)
    check('YYYYMMDD', ds.parse_date('20260115').day == 15)


def test_date_filter(tmp):
    print("\n[6] 日期筛选")
    # --after td 应该能找到我们刚创建的文件
    searcher = ds.DocSearcher(
        target_path=tmp, keyword='TODO',
        after=ds.parse_date('td')
    )
    results = searcher.search()
    check('--after td 能找到刚创建的文件', len(results) >= 1)

    # --before ly 应该找不到
    searcher2 = ds.DocSearcher(
        target_path=tmp, keyword='TODO',
        before=ds.parse_date('ly')
    )
    results2 = searcher2.search()
    check('--before ly 找不到刚创建的文件', len(results2) == 0)


def test_version_filter(tmp):
    print("\n[7] 版本号筛选")

    # 精确匹配
    check('_match_version 1.2.3 精确',
          ds.DocSearcher._match_version('/path/v1.2.3/file.txt', '1.2.3'))
    check('_match_version 2.0.0 不匹配 1.2.3',
          not ds.DocSearcher._match_version('/path/v2.0.0/file.txt', '1.2.3'))

    # 比较
    check('_match_version >1.0',
          ds.DocSearcher._match_version('/path/v2.0.0/file.txt', '>1.0'))
    check('_match_version >=2.0',
          ds.DocSearcher._match_version('/path/v2.0.0/file.txt', '>=2.0'))
    check('_match_version <2.0 on 1.2.3',
          ds.DocSearcher._match_version('/path/v1.2.3/file.txt', '<2.0'))

    # 通配
    check('_match_version 1.x',
          ds.DocSearcher._match_version('/path/v1.2.3/file.txt', '1.x'))
    check('_match_version 2.x 不匹配 1.2.3',
          not ds.DocSearcher._match_version('/path/v1.2.3/file.txt', '2.x'))

    # 版本比较函数
    check('compare 1.2.3 vs 1.2.3 = 0',
          ds.DocSearcher._compare_versions('1.2.3', '1.2.3') == 0)
    check('compare 2.0.0 vs 1.9.9 = 1',
          ds.DocSearcher._compare_versions('2.0.0', '1.9.9') == 1)
    check('compare 1.0 vs 2.0 = -1',
          ds.DocSearcher._compare_versions('1.0', '2.0') == -1)


def test_hash_search(tmp):
    print("\n[8] Hash 对比搜索")
    # 计算 hello.py 的 hash
    hello_path = os.path.join(tmp, 'hello.py')
    h = ds.HashMatcher.compute_file_hash(hello_path, 'sha256')
    check('compute_file_hash 返回 hex', h is not None and len(h) == 64)

    results = ds.HashMatcher.find_by_hash(tmp, h, algorithm='sha256')
    check('find_by_hash 找到文件', len(results) == 1)
    check('find_by_hash 路径正确', results[0].path == hello_path)

    # 算法自动检测
    md5 = ds.HashMatcher.compute_file_hash(hello_path, 'md5')
    results2 = ds.HashMatcher.find_by_hash(tmp, md5, algorithm='auto')
    check('auto 检测 MD5 (32字符)', len(results2) == 1)


def test_base64_search(tmp):
    print("\n[9] Base64 双向搜索")
    results = ds.HashMatcher.find_by_base64(tmp, 'admin:password')
    check('base64 搜索找到 encoded.conf',
          any('encoded.conf' in r.path for r in results))
    if results:
        matches = [m for r in results for m in r.matches if 'encoded.conf' in r.path]
        check('匹配标记了 match_form',
              any(m.get('match_form') for m in matches))


def test_parallel_search(tmp):
    print("\n[10] 并行搜索")
    # 标准搜索
    s1 = ds.DocSearcher(target_path=tmp, keyword='TODO')
    r1 = s1.search()

    # 通过 CLI args 模拟
    rc = ds.cli_main(['search', 'TODO', tmp, '--parallel', '4', '--format', 'json'])
    check('并行搜索 CLI 返回 0', rc == 0)


def test_output_formats(tmp):
    print("\n[11] 输出格式")
    searcher = ds.DocSearcher(target_path=tmp, keyword='TODO')
    results = searcher.search()
    summary = searcher.get_summary()

    # grep 格式
    grep_out = ds.OutputFormatter.format_grep(results)
    check('grep 格式含冒号分隔',
          all(':' in line for line in grep_out.strip().split('\n') if line))

    # path 格式
    path_out = ds.OutputFormatter.format_paths(results)
    check('path 格式每行一个路径',
          all(os.path.isfile(p) for p in path_out.strip().split('\n') if p))

    # json 格式
    json_out = ds.OutputFormatter.format_json(results, summary)
    parsed = json.loads(json_out)
    check('JSON 格式可解析', 'summary' in parsed and 'results' in parsed)

    # csv 格式
    csv_out = ds.OutputFormatter.format_csv(results)
    check('CSV 格式有 header', csv_out.startswith('path,line,encoding,size,content'))


def test_text_detector(tmp):
    print("\n[12] TextDetector 编码检测")
    # UTF-8
    is_text, enc = ds.TextDetector.is_text_file(os.path.join(tmp, 'hello.py'))
    check('hello.py 是文本', is_text)
    check('hello.py 编码含 utf', enc is not None and 'utf' in enc.lower())

    # GBK
    is_text2, enc2 = ds.TextDetector.is_text_file(os.path.join(tmp, 'chinese_gbk.txt'))
    check('chinese_gbk.txt 是文本', is_text2)
    if ds.HAS_CHARDET:
        check('GBK 编码检测', enc2 is not None, f'got {enc2}')

    # 无扩展名
    is_text3, enc3 = ds.TextDetector.is_text_file(os.path.join(tmp, 'noext'))
    check('无扩展名文件判定为文本', is_text3)


def test_streaming_search(tmp):
    print("\n[13] 大文件流式搜索")
    # 用 iter_lines 读取大文件
    bigfile = os.path.join(tmp, 'bigfile.log')
    lines = list(ds.TextDetector.iter_lines(bigfile, 'utf-8'))
    check('iter_lines 能读取', len(lines) > 100)

    # 搜索大文件中的关键词
    searcher = ds.DocSearcher(target_path=tmp, keyword='NEEDLE_IN_HAYSTACK')
    results = searcher.search()
    check('大文件中找到 NEEDLE',
          any('bigfile.log' in r.path for r in results))


def test_cli_help():
    print("\n[14] CLI help 子命令")
    # 测试各个帮助主题
    for topic in ['all', 'search', 'date', 'type', 'hash', 'base64', 'format', 'pipe', 'parallel', 'version']:
        rc = ds.cli_main(['help', topic])
        check(f'help {topic} 返回 0', rc == 0)


def test_cli_search(tmp):
    print("\n[15] CLI 完整搜索")
    rc = ds.cli_main(['search', 'TODO', tmp, '--type', 'py', '--format', 'json'])
    check('CLI search --type py 返回 0', rc == 0)

    rc2 = ds.cli_main(['search', 'TODO', tmp, '--after', 'td', '--format', 'json'])
    check('CLI search --after td 返回 0', rc2 == 0)


def test_size_filter(tmp):
    print("\n[16] 大小筛选")
    searcher = ds.DocSearcher(
        target_path=tmp, keyword='TODO',
        min_size=1, max_size=1024 * 1024
    )
    results = searcher.search()
    check('大小筛选有结果', len(results) >= 1)

    # 极小 min_size 排除所有
    searcher2 = ds.DocSearcher(
        target_path=tmp, keyword='TODO',
        min_size=100 * 1024 * 1024
    )
    results2 = searcher2.search()
    check('min_size=100MB 无结果', len(results2) == 0)


def main():
    global PASS, FAIL
    print("=" * 60)
    print("  HIDRS doc_searcher 功能测试")
    print("=" * 60)

    # 检测搜索后端
    rg = ds.RipgrepBackend()
    grep = ds.GrepBackend()
    print(f"\n  搜索后端: rg={'✓' if rg.available else '✗'}  grep={'✓' if grep.available else '✗'}")
    print(f"  chardet: {'✓' if ds.HAS_CHARDET else '✗'}")
    print(f"  translator: {'✓' if ds.HAS_TRANSLATOR else '✗'}")

    tmp = create_test_dir()
    try:
        test_basic_search(tmp)
        test_regex_search(tmp)
        test_invert_search(tmp)
        test_type_preset(tmp)
        test_date_shortcuts()
        test_date_filter(tmp)
        test_version_filter(tmp)
        test_hash_search(tmp)
        test_base64_search(tmp)
        test_parallel_search(tmp)
        test_output_formats(tmp)
        test_text_detector(tmp)
        test_streaming_search(tmp)
        test_cli_help()
        test_cli_search(tmp)
        test_size_filter(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 60)
    print(f"  结果: {PASS} 通过 / {FAIL} 失败 / {PASS + FAIL} 总计")
    print("=" * 60)
    return 1 if FAIL > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
