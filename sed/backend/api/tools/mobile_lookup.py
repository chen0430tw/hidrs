"""
手机号归属地查询API
支持多个免费在线API + 本地数据备用

在线API来源:
- 米人API (api.mir6.com) - 免费、稳定
- 360接口 (cx.shouji.360.cn) - 免费、精确到省市
- 淘宝接口 - 备用
"""
import os
import json
import logging
import requests
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)
mobile_bp = Blueprint('mobile_lookup', __name__)

# API超时设置
API_TIMEOUT = 5

# 本地数据缓存
_mobile_data = None
_carrier_data = None


def _load_local_data():
    """加载本地数据作为备用"""
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
            logger.error(f"加载本地手机号数据失败: {e}")
            _mobile_data = {}
            _carrier_data = {}


def _detect_carrier(prefix):
    """检测运营商"""
    _load_local_data()
    for carrier, prefixes in _carrier_data.items():
        if prefix in prefixes:
            return carrier
    return '未知'


def _query_mir6_api(number):
    """
    米人API - 免费、永久稳定
    https://api.mir6.com/doc/mobile.html
    """
    try:
        url = f"https://api.mir6.com/api/mobile?mobile={number}"
        resp = requests.get(url, timeout=API_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('code') == 200:
                info = data.get('data', {})
                return {
                    'number': number,
                    'province': info.get('province', ''),
                    'city': info.get('city', ''),
                    'carrier': info.get('isp', ''),
                    'prefix': number[:7],
                    'areaCode': info.get('areacode', ''),
                    'zipCode': info.get('zip', ''),
                    'source': '米人API'
                }
    except Exception as e:
        logger.debug(f"米人API查询失败: {e}")
    return None


def _query_360_api(number):
    """
    360接口 - 免费、精确到省市
    https://cx.shouji.360.cn/phonearea.php
    """
    try:
        url = f"https://cx.shouji.360.cn/phonearea.php?number={number}"
        resp = requests.get(url, timeout=API_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('code') == 0:
                info = data.get('data', {})
                return {
                    'number': number,
                    'province': info.get('province', ''),
                    'city': info.get('city', ''),
                    'carrier': info.get('sp', ''),
                    'prefix': number[:7],
                    'areaCode': '',
                    'zipCode': '',
                    'source': '360接口'
                }
    except Exception as e:
        logger.debug(f"360接口查询失败: {e}")
    return None


def _query_taobao_api(number):
    """
    淘宝接口 - 备用 (只能查到省级)
    https://tcc.taobao.com/cc/json/mobile_tel_segment.htm
    """
    try:
        url = f"https://tcc.taobao.com/cc/json/mobile_tel_segment.htm?tel={number}"
        resp = requests.get(url, timeout=API_TIMEOUT)
        if resp.status_code == 200:
            # 淘宝返回的是 JSONP 格式
            text = resp.text
            # 解析 __GetZoneResult_ = {...}
            import re
            match = re.search(r'\{.*\}', text)
            if match:
                data = json.loads(match.group())
                carrier_map = {
                    'CHINA_MOBILE': '中国移动',
                    'CHINA_UNICOM': '中国联通',
                    'CHINA_TELECOM': '中国电信'
                }
                return {
                    'number': number,
                    'province': data.get('province', ''),
                    'city': '',  # 淘宝接口不返回城市
                    'carrier': carrier_map.get(data.get('catName', ''), data.get('catName', '')),
                    'prefix': data.get('telString', number[:7]),
                    'areaCode': data.get('areaVid', ''),
                    'zipCode': '',
                    'source': '淘宝接口'
                }
    except Exception as e:
        logger.debug(f"淘宝接口查询失败: {e}")
    return None


def _lookup_local(number):
    """本地数据查询"""
    _load_local_data()
    prefix7 = number[:7]
    prefix3 = number[:3]

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
            'zipCode': info.get('zipCode', ''),
            'source': '本地数据'
        }
    return None


def _lookup_mobile(number, use_online=True):
    """
    查询手机号归属地
    优先使用在线API，失败时回退到本地数据
    """
    # 清理号码格式
    number = number.strip().replace(' ', '').replace('-', '')

    if len(number) == 13 and number.startswith('+86'):
        number = number[3:]
    if len(number) == 14 and number.startswith('0086'):
        number = number[4:]

    if len(number) != 11 or not number.isdigit():
        return None, "无效的手机号码"

    # 特殊号段处理 (港澳台)
    special = {
        '852': {'province': '香港', 'city': '香港', 'carrier': '香港运营商'},
        '853': {'province': '澳门', 'city': '澳门', 'carrier': '澳门运营商'},
        '886': {'province': '台湾', 'city': '台湾', 'carrier': '台湾运营商'},
    }

    for code, sinfo in special.items():
        if number.startswith(code):
            return {
                **sinfo,
                'number': number,
                'prefix': code,
                'areaCode': '',
                'zipCode': '',
                'source': '特殊号段'
            }, None

    # 在线查询
    if use_online:
        # 尝试米人API
        result = _query_mir6_api(number)
        if result and result.get('province'):
            return result, None

        # 尝试360接口
        result = _query_360_api(number)
        if result and result.get('province'):
            return result, None

        # 尝试淘宝接口
        result = _query_taobao_api(number)
        if result and result.get('province'):
            return result, None

    # 本地数据查询
    result = _lookup_local(number)
    if result:
        return result, None

    # 未找到
    prefix3 = number[:3]
    carrier = _detect_carrier(prefix3)
    return {
        'number': number,
        'province': '未知',
        'city': '未知',
        'carrier': carrier,
        'prefix': number[:7],
        'areaCode': '',
        'zipCode': '',
        'source': '未找到'
    }, None


@mobile_bp.route('/tools/mobile/lookup', methods=['POST'])
def mobile_lookup():
    """
    手机号归属地查询

    POST /api/tools/mobile/lookup
    Body: {"number": "13800138000", "online": true}

    Response: {
        "status": "ok",
        "data": {
            "number": "13800138000",
            "province": "北京",
            "city": "北京",
            "carrier": "中国移动",
            "prefix": "1380013",
            "areaCode": "010",
            "zipCode": "100000",
            "source": "米人API"
        }
    }
    """
    try:
        data = request.get_json()
        number = data.get('number', '')
        use_online = data.get('online', True)

        if not number:
            return jsonify({'status': 'error', 'message': '请提供手机号码'}), 400

        result, error = _lookup_mobile(number, use_online)

        if error:
            return jsonify({'status': 'error', 'message': error}), 400

        return jsonify({'status': 'ok', 'data': result})
    except Exception as e:
        logger.error(f"手机号查询错误: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@mobile_bp.route('/tools/mobile/batch', methods=['POST'])
def mobile_batch_lookup():
    """
    批量手机号归属地查询

    POST /api/tools/mobile/batch
    Body: {"numbers": ["13800138000", "13900139000"], "online": false}
    """
    try:
        data = request.get_json()
        numbers = data.get('numbers', [])
        use_online = data.get('online', False)  # 批量默认用本地，避免API限流

        if not numbers:
            return jsonify({'status': 'error', 'message': '请提供手机号码列表'}), 400

        if len(numbers) > 100:
            return jsonify({'status': 'error', 'message': '批量查询最多100个号码'}), 400

        results = []
        for number in numbers:
            result, _ = _lookup_mobile(number, use_online)
            if result:
                results.append(result)

        return jsonify({
            'status': 'ok',
            'data': results,
            'total': len(results)
        })
    except Exception as e:
        logger.error(f"批量查询错误: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


def register_mobile_routes(app):
    app.register_blueprint(mobile_bp, url_prefix='/api')
