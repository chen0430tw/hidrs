import re
import hashlib
import time
from typing import Dict, Any, Optional

def parse_line(line: str, split_sign: str, fields: list, regex_patterns=None, custom_fields=None) -> Optional[Dict[str, Any]]:
    """
    解析单行数据为记录
    
    Args:
        line: 要解析的行
        split_sign: 分隔符
        fields: 字段列表
        regex_patterns: 正则表达式模式
        custom_fields: 自定义字段
        
    Returns:
        解析后的记录或None
    """
    try:
        # 初始化
        regex_patterns = regex_patterns or {}
        custom_fields = custom_fields or {}
        
        # 跳过空行
        line = line.strip()
        if not line:
            return None
        
        # 分割行
        parts = line.split(split_sign)
        
        # 创建记录
        record = custom_fields.copy()
        
        # 添加字段
        for i, field in enumerate(fields):
            if i < len(parts):
                record[field] = parts[i].strip()
        
        # 处理邮箱字段
        if 'email' in record and isinstance(record['email'], str):
            parts = record['email'].split('@')
            if len(parts) > 1:
                record['user'] = record.get('user', parts[0])
                record['suffix_email'] = parts[1].lower()
                
        # 处理用户名字段
        if 'user' in record and '@' in record['user'] and 'email' not in record:
            # 如果用户名看起来像邮箱但没有email字段，则处理它
            parts = record['user'].split('@')
            if len(parts) > 1:
                record['email'] = record['user']
                record['user'] = parts[0]
                record['suffix_email'] = parts[1].lower()
        
        # 处理密码哈希
        if 'password' in record and 'passwordHash' not in record:
            try:
                password = str(record['password']).encode('utf-8')
                record['passwordHash'] = hashlib.md5(password).hexdigest()
            except Exception:
                pass
        
        # 应用正则表达式处理
        for field, pattern_config in regex_patterns.items():
            target_field = pattern_config.get('target')
            pattern = pattern_config.get('re')
            
            if target_field in record:
                try:
                    matches = re.findall(pattern, record[target_field])
                    if matches:
                        if isinstance(matches[0], tuple):
                            record[field] = matches[0][0]
                        else:
                            record[field] = matches[0]
                except Exception:
                    pass
        
        # 添加时间字段
        if 'create_time' not in record:
            record['create_time'] = time.strftime('%Y/%m/%d %H:%M:%S', time.localtime())
            
        # 添加源字段
        if 'source' not in record:
            record['source'] = 'import_script'
            
        # 添加泄露时间字段
        if 'xtime' not in record:
            record['xtime'] = time.strftime('%Y%m', time.localtime())
        
        return record
    except Exception:
        return None

def get_record_from_file(file_path: str, line_number: int, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    从文件中获取特定行的完整记录
    
    Args:
        file_path: 文件路径
        line_number: 行号（从1开始）
        config: 处理配置
        
    Returns:
        解析后的记录或None
    """
    try:
        split_sign = config.get('split', '----')
        fields = config.get('fields', ['email', 'password'])
        regex_patterns = config.get('regex', {})
        custom_fields = config.get('custom_field', {})
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f, 1):
                if i == line_number:
                    return parse_line(line, split_sign, fields, regex_patterns, custom_fields)
        
        return None
    except Exception as e:
        print(f"获取记录失败: {str(e)}")
        return None