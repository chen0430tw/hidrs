#!/usr/bin/env python3
"""
从CSV/TXT导入手机号归属地数据到JSON
用法: python import_data.py <input_file> <output_file>
"""
import csv
import json
import sys
import os

def import_mobile_data(input_file, output_file):
    """导入手机号归属地数据"""
    data = {}
    count = 0
    
    ext = os.path.splitext(input_file)[1].lower()
    
    with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
        if ext == '.csv':
            reader = csv.DictReader(f)
            for row in reader:
                prefix = row.get('prefix', row.get('号段', '')).strip()
                if prefix and len(prefix) == 7:
                    data[prefix] = {
                        'province': row.get('province', row.get('省份', '')).strip(),
                        'city': row.get('city', row.get('城市', '')).strip(),
                        'areaCode': row.get('areaCode', row.get('区号', '')).strip(),
                        'zipCode': row.get('zipCode', row.get('邮编', '')).strip()
                    }
                    count += 1
        else:
            # TXT格式: prefix|province|city|areaCode|zipCode
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('|')
                if len(parts) >= 3:
                    prefix = parts[0].strip()
                    if len(prefix) == 7:
                        data[prefix] = {
                            'province': parts[1].strip(),
                            'city': parts[2].strip(),
                            'areaCode': parts[3].strip() if len(parts) > 3 else '',
                            'zipCode': parts[4].strip() if len(parts) > 4 else ''
                        }
                        count += 1
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"导入完成: {count} 条号段数据")
    return count

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python import_data.py <input_file> <output_file>")
        print("  input_file: CSV或TXT格式的手机号段数据")
        print("  output_file: 输出JSON文件路径")
        sys.exit(1)
    
    import_mobile_data(sys.argv[1], sys.argv[2])
