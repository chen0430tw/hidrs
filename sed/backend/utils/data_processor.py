"""
优化和简化的数据处理模块
"""
import re
import time
import hashlib
from typing import Dict, Any, Optional

def parse_record(line: str, split_sign: str = None, fields: list = None, 
               regex_patterns: Dict = None, custom_fields: Dict = None,
               is_parsed: bool = False, record: Dict = None) -> Optional[Dict[str, Any]]:
    """
    解析和处理记录
    
    Args:
        line: 要解析的行
        split_sign: 分隔符
        fields: 字段列表
        regex_patterns: 正则表达式模式
        custom_fields: 自定义字段
        is_parsed: 记录是否已经解析(如Excel导入)
        record: 已解析的记录(如Excel导入)
        
    Returns:
        解析后的记录或None
    """
    try:
        # 初始化参数
        regex_patterns = regex_patterns or {}
        custom_fields = custom_fields or {}
        
        # 如果已提供解析后的记录
        if is_parsed and record:
            parsed_record = record
        else:
            # 跳过空行
            line = line.strip() if line else ""
            if not line:
                return None
            
            # 分割行
            parts = line.split(split_sign) if split_sign else [line]
            
            # 创建记录
            parsed_record = custom_fields.copy()
            
            # 添加字段
            if fields:
                for i, field in enumerate(fields):
                    if i < len(parts):
                        parsed_record[field] = parts[i].strip()
        
        # 处理邮箱字段
        if 'email' in parsed_record and isinstance(parsed_record['email'], str):
            parts = parsed_record['email'].split('@')
            if len(parts) > 1:
                parsed_record['user'] = parsed_record.get('user', parts[0])
                parsed_record['suffix_email'] = parts[1].lower()
                
        # 处理用户名字段
        if 'user' in parsed_record and '@' in parsed_record['user'] and 'email' not in parsed_record:
            # 如果用户名看起来像邮箱但没有email字段，则处理它
            parts = parsed_record['user'].split('@')
            if len(parts) > 1:
                parsed_record['email'] = parsed_record['user']
                parsed_record['user'] = parts[0]
                parsed_record['suffix_email'] = parts[1].lower()
        
        # 处理密码哈希
        if 'password' in parsed_record and 'passwordHash' not in parsed_record:
            try:
                password = str(parsed_record['password']).encode('utf-8')
                parsed_record['passwordHash'] = hashlib.md5(password).hexdigest()
            except Exception:
                pass
        
        # 应用正则表达式处理
        for field, pattern_config in regex_patterns.items():
            target_field = pattern_config.get('target')
            pattern = pattern_config.get('re')
            
            if target_field in parsed_record:
                try:
                    matches = re.findall(pattern, parsed_record[target_field])
                    if matches:
                        if isinstance(matches[0], tuple):
                            parsed_record[field] = matches[0][0]
                        else:
                            parsed_record[field] = matches[0]
                except Exception:
                    pass
        
        # 添加时间字段
        if 'create_time' not in parsed_record:
            parsed_record['create_time'] = time.strftime('%Y/%m/%d %H:%M:%S', time.localtime())
            
        # 添加源字段
        if 'source' not in parsed_record:
            parsed_record['source'] = 'import_script'
            
        # 添加泄露时间字段
        if 'xtime' not in parsed_record:
            parsed_record['xtime'] = time.strftime('%Y%m', time.localtime())
        
        return parsed_record
        
    except Exception as e:
        print(f"记录解析失败: {e}")
        return None