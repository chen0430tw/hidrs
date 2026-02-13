"""
身份证号地区查询API
"""
import os
import json
import logging
import re
from datetime import datetime
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)
idcard_bp = Blueprint('idcard_lookup', __name__)

_area_data = None

def _load_area_data():
    global _area_data
    if _area_data is None:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        area_path = os.path.join(data_dir, 'area_codes_full.json')
        if not os.path.exists(area_path):
            area_path = os.path.join(data_dir, 'area_codes.json')
        try:
            if os.path.exists(area_path):
                with open(area_path, 'r', encoding='utf-8') as f:
                    _area_data = json.load(f)
            else:
                _area_data = {}
        except Exception as e:
            logger.error(f"加载行政区划数据失败: {e}")
            _area_data = {}

def _validate_idcard(idcard):
    """校验18位身份证号"""
    if len(idcard) != 18:
        return False
    pattern = re.compile(r'^\d{17}[\dXx]$')
    if not pattern.match(idcard):
        return False
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_codes = '10X98765432'
    total = sum(int(idcard[i]) * weights[i] for i in range(17))
    expected = check_codes[total % 11]
    return idcard[-1].upper() == expected

def _lookup_idcard(idcard):
    """查询身份证地区信息"""
    _load_area_data()
    idcard = idcard.strip().upper()
    
    if len(idcard) == 15:
        # 15位转18位
        idcard = idcard[:6] + '19' + idcard[6:]
        # 简化处理，不计算校验码
        idcard += '0'
    
    if len(idcard) != 18:
        return None, "身份证号码长度不正确"
    
    if not _validate_idcard(idcard) and not idcard.endswith('0'):
        return None, "身份证号码校验不通过"
    
    # 解析地区
    code6 = idcard[:6]
    code4 = idcard[:4] + '00'
    code2 = idcard[:2] + '0000'
    
    province = _area_data.get(code2, {}).get('name', '未知')
    city = _area_data.get(code4, {}).get('name', '')
    district = _area_data.get(code6, {}).get('name', '')
    
    # 解析出生日期
    birth_str = idcard[6:14]
    try:
        birthday = datetime.strptime(birth_str, '%Y%m%d')
        birthday_str = birthday.strftime('%Y-%m-%d')
        age = (datetime.now() - birthday).days // 365
    except:
        birthday_str = birth_str
        age = 0
    
    # 解析性别
    gender_code = int(idcard[16])
    gender = '男' if gender_code % 2 == 1 else '女'
    
    return {
        'number': idcard,
        'province': province,
        'city': city,
        'district': district,
        'birthday': birthday_str,
        'age': age,
        'gender': gender,
        'areaCode': code6
    }, None


@idcard_bp.route('/tools/idcard/lookup', methods=['POST'])
def idcard_lookup():
    """身份证地区查询"""
    try:
        data = request.get_json()
        number = data.get('number', '')
        
        if not number:
            return jsonify({'status': 'error', 'message': '请提供身份证号码'}), 400
        
        result, error = _lookup_idcard(number)
        
        if error:
            return jsonify({'status': 'error', 'message': error}), 400
        
        return jsonify({'status': 'ok', 'data': result})
    except Exception as e:
        logger.error(f"身份证查询错误: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


def register_idcard_routes(app):
    app.register_blueprint(idcard_bp, url_prefix='/api')
