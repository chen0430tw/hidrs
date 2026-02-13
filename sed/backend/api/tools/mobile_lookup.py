"""
手机号归属地查询API
"""
import os
import json
import logging
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)
mobile_bp = Blueprint('mobile_lookup', __name__)

# 数据缓存
_mobile_data = None
_carrier_data = None

def _load_data():
    global _mobile_data, _carrier_data
    if _mobile_data is None:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        mobile_path = os.path.join(data_dir, 'mobile_location.json')
        carrier_path = os.path.join(data_dir, 'carrier_prefixes.json')
        try:
            if os.path.exists(mobile_path):
                with open(mobile_path, 'r', encoding='utf-8') as f:
                    _mobile_data = json.load(f)
            else:
                _mobile_data = {}
            if os.path.exists(carrier_path):
                with open(carrier_path, 'r', encoding='utf-8') as f:
                    _carrier_data = json.load(f)
            else:
                _carrier_data = {}
        except Exception as e:
            logger.error(f"加载手机号数据失败: {e}")
            _mobile_data = {}
            _carrier_data = {}

def _detect_carrier(prefix):
    """检测运营商"""
    _load_data()
    for carrier, prefixes in _carrier_data.items():
        if prefix in prefixes:
            return carrier
    return '未知'

def _lookup_mobile(number):
    """查询手机号归属地"""
    _load_data()
    number = number.strip().replace(' ', '').replace('-', '')
    
    if len(number) == 13 and number.startswith('+86'):
        number = number[3:]
    if len(number) == 14 and number.startswith('0086'):
        number = number[4:]
    
    if len(number) != 11 or not number.isdigit():
        return None, "无效的手机号码"
    
    prefix7 = number[:7]
    prefix3 = number[:3]
    
    # 查找归属地
    info = _mobile_data.get(prefix7, {})
    carrier = _detect_carrier(prefix3)
    
    if info:
        return {
            'number': number,
            'province': info.get('province', ''),
            'city': info.get('city', ''),
            'carrier': carrier,
            'prefix': prefix7,
            'areaCode': info.get('areaCode', ''),
            'zipCode': info.get('zipCode', '')
        }, None
    
    # 特殊号段处理
    special = {
        '852': {'province': '香港', 'city': '香港', 'carrier': '香港运营商'},
        '853': {'province': '澳门', 'city': '澳门', 'carrier': '澳门运营商'},
        '886': {'province': '台湾', 'city': '台湾', 'carrier': '台湾运营商'},
    }
    
    for code, sinfo in special.items():
        if number.startswith(code):
            return {**sinfo, 'number': number, 'prefix': code, 'areaCode': '', 'zipCode': ''}, None
    
    return {
        'number': number,
        'province': '未知',
        'city': '未知',
        'carrier': carrier,
        'prefix': prefix7,
        'areaCode': '',
        'zipCode': ''
    }, None


@mobile_bp.route('/tools/mobile/lookup', methods=['POST'])
def mobile_lookup():
    """手机号归属地查询"""
    try:
        data = request.get_json()
        number = data.get('number', '')
        
        if not number:
            return jsonify({'status': 'error', 'message': '请提供手机号码'}), 400
        
        result, error = _lookup_mobile(number)
        
        if error:
            return jsonify({'status': 'error', 'message': error}), 400
        
        return jsonify({'status': 'ok', 'data': result})
    except Exception as e:
        logger.error(f"手机号查询错误: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


def register_mobile_routes(app):
    app.register_blueprint(mobile_bp, url_prefix='/api')
