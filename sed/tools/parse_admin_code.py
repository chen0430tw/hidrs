#!/usr/bin/env python3
"""
解析行政区划代码并生成JSON
用法: python parse_admin_code.py <input_file> <output_file>
"""
import json
import sys
import re

def parse_admin_codes(input_file, output_file):
    data = {}
    count = 0
    
    with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # 格式: 110000 北京市 或 110000|北京市
            match = re.match(r'(\d{6})\s*[|\t,]\s*(.+)', line)
            if match:
                code = match.group(1)
                name = match.group(2).strip()
                data[code] = {'name': name}
                count += 1
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"解析完成: {count} 条行政区划代码")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python parse_admin_code.py <input_file> <output_file>")
        sys.exit(1)
    parse_admin_codes(sys.argv[1], sys.argv[2])
