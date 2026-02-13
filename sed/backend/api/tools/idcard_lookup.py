"""
身份证号码解析API
支持18位/15位身份证解析，含校验、地区、生日、性别、年龄

在线API来源 (可选验证):
- 极速数据 (jisuapi.com) - 100次/天免费
- 聚合数据 (juhe.cn) - 需API Key

本地解析完全离线可用，在线API仅用于实名验证
"""
import os
import json
import logging
import re
import requests
from datetime import datetime
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)
idcard_bp = Blueprint('idcard_lookup', __name__)

# API配置
API_TIMEOUT = 5
JUHE_API_KEY = os.getenv('JUHE_API_KEY', '')  # 聚合数据API Key

# 本地数据缓存
_area_data = None


def _load_area_data():
    """加载行政区划数据"""
    global _area_data
    if _area_data is None:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        # 优先使用完整版
        area_path = os.path.join(data_dir, 'area_codes_full.json')
        if not os.path.exists(area_path):
            area_path = os.path.join(data_dir, 'area_codes.json')
        try:
            if os.path.exists(area_path):
                with open(area_path, 'r', encoding='utf-8') as f:
                    _area_data = json.load(f)
            else:
                _area_data = {}
                logger.warning("未找到行政区划数据文件")
        except Exception as e:
            logger.error(f"加载行政区划数据失败: {e}")
            _area_data = {}


def _validate_idcard(idcard):
    """
    校验18位身份证号码
    使用GB 11643-1999标准校验码算法
    """
    if len(idcard) != 18:
        return False, "身份证号码长度不正确"

    pattern = re.compile(r'^\d{17}[\dXx]$')
    if not pattern.match(idcard):
        return False, "身份证号码格式不正确"

    # 加权因子
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    # 校验码对应值
    check_codes = '10X98765432'

    try:
        total = sum(int(idcard[i]) * weights[i] for i in range(17))
        expected = check_codes[total % 11]
        if idcard[-1].upper() != expected:
            return False, f"校验码错误，期望: {expected}"
    except ValueError:
        return False, "身份证号码包含非法字符"

    # 验证出生日期
    birth_str = idcard[6:14]
    try:
        birth_date = datetime.strptime(birth_str, '%Y%m%d')
        if birth_date > datetime.now():
            return False, "出生日期不能是未来"
        if birth_date.year < 1900:
            return False, "出生年份不合理"
    except ValueError:
        return False, "出生日期格式不正确"

    return True, None


def _convert_15_to_18(idcard15):
    """
    15位身份证转18位
    15位: 6位地区码 + 6位出生日期(YYMMDD) + 3位顺序码
    18位: 6位地区码 + 8位出生日期(YYYYMMDD) + 3位顺序码 + 1位校验码
    """
    if len(idcard15) != 15 or not idcard15.isdigit():
        return None

    # 补充世纪码
    year2 = idcard15[6:8]
    century = '19' if int(year2) > 20 else '20'  # 简单判断: >20认为是19xx年

    idcard17 = idcard15[:6] + century + idcard15[6:]

    # 计算校验码
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_codes = '10X98765432'
    total = sum(int(idcard17[i]) * weights[i] for i in range(17))
    check_code = check_codes[total % 11]

    return idcard17 + check_code


def _parse_area(code6):
    """解析6位行政区划代码"""
    _load_area_data()

    code2 = code6[:2] + '0000'  # 省级
    code4 = code6[:4] + '00'    # 市级
    code6_full = code6          # 县级

    province = _area_data.get(code2, {}).get('name', '')
    city = _area_data.get(code4, {}).get('name', '')
    district = _area_data.get(code6_full, {}).get('name', '')

    # 直辖市处理
    if province in ['北京市', '上海市', '天津市', '重庆市']:
        if not city:
            city = province
        if not district:
            district = _area_data.get(code6_full, {}).get('name', '')

    return province, city, district


def _get_constellation(month, day):
    """根据生日获取星座"""
    constellations = [
        (1, 20, '摩羯座'), (2, 19, '水瓶座'), (3, 21, '双鱼座'),
        (4, 20, '白羊座'), (5, 21, '金牛座'), (6, 22, '双子座'),
        (7, 23, '巨蟹座'), (8, 23, '狮子座'), (9, 23, '处女座'),
        (10, 24, '天秤座'), (11, 23, '天蝎座'), (12, 22, '射手座'),
        (12, 31, '摩羯座')
    ]
    for end_month, end_day, name in constellations:
        if month < end_month or (month == end_month and day <= end_day):
            return name
    return '摩羯座'


def _get_zodiac(year):
    """根据出生年获取生肖"""
    zodiacs = ['猴', '鸡', '狗', '猪', '鼠', '牛', '虎', '兔', '龙', '蛇', '马', '羊']
    return zodiacs[year % 12]


def _lookup_idcard(idcard):
    """
    解析身份证号码
    返回: (result_dict, error_message)
    """
    idcard = idcard.strip().upper().replace(' ', '')

    # 15位转18位
    if len(idcard) == 15:
        idcard18 = _convert_15_to_18(idcard)
        if not idcard18:
            return None, "15位身份证号码格式不正确"
        original = idcard
        idcard = idcard18
    else:
        original = idcard

    # 长度检查
    if len(idcard) != 18:
        return None, "身份证号码长度不正确 (应为15或18位)"

    # 校验
    valid, error = _validate_idcard(idcard)
    if not valid:
        return None, error

    # 解析地区
    code6 = idcard[:6]
    province, city, district = _parse_area(code6)

    # 解析出生日期
    birth_str = idcard[6:14]
    try:
        birthday = datetime.strptime(birth_str, '%Y%m%d')
        birthday_formatted = birthday.strftime('%Y-%m-%d')
        year = birthday.year
        month = birthday.month
        day = birthday.day

        # 计算年龄
        today = datetime.now()
        age = today.year - year
        if (today.month, today.day) < (month, day):
            age -= 1

        # 星座和生肖
        constellation = _get_constellation(month, day)
        zodiac = _get_zodiac(year)
    except ValueError:
        return None, "出生日期解析失败"

    # 解析性别 (第17位: 奇数=男, 偶数=女)
    gender_code = int(idcard[16])
    gender = '男' if gender_code % 2 == 1 else '女'

    return {
        'number': idcard,
        'original': original if original != idcard else None,
        'valid': True,
        'province': province or '未知',
        'city': city or '',
        'district': district or '',
        'fullAddress': f"{province}{city}{district}".replace('市市', '市'),
        'birthday': birthday_formatted,
        'year': year,
        'month': month,
        'day': day,
        'age': age,
        'gender': gender,
        'genderCode': gender_code % 2,
        'constellation': constellation,
        'zodiac': zodiac,
        'areaCode': code6
    }, None


def _verify_online(name, idcard):
    """
    在线实名验证 (可选)
    使用聚合数据API验证姓名与身份证是否匹配
    """
    if not JUHE_API_KEY:
        return None, "未配置API Key"

    try:
        url = "http://op.juhe.cn/idcard/query"
        params = {
            'key': JUHE_API_KEY,
            'idcard': idcard,
            'realname': name
        }
        resp = requests.get(url, params=params, timeout=API_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('error_code') == 0:
                result = data.get('result', {})
                return {
                    'verified': result.get('res') == 1,
                    'message': '验证通过' if result.get('res') == 1 else '姓名与身份证不匹配'
                }, None
            else:
                return None, data.get('reason', 'API错误')
    except Exception as e:
        logger.error(f"在线验证失败: {e}")
        return None, str(e)

    return None, "验证失败"


@idcard_bp.route('/tools/idcard/lookup', methods=['POST'])
def idcard_lookup():
    """
    身份证号码解析

    POST /api/tools/idcard/lookup
    Body: {"number": "110101199001011234"}

    Response: {
        "status": "ok",
        "data": {
            "number": "110101199001011234",
            "valid": true,
            "province": "北京市",
            "city": "北京市",
            "district": "东城区",
            "fullAddress": "北京市东城区",
            "birthday": "1990-01-01",
            "age": 35,
            "gender": "男",
            "constellation": "摩羯座",
            "zodiac": "马",
            "areaCode": "110101"
        }
    }
    """
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


@idcard_bp.route('/tools/idcard/verify', methods=['POST'])
def idcard_verify():
    """
    身份证实名验证 (需要API Key)

    POST /api/tools/idcard/verify
    Body: {"name": "张三", "number": "110101199001011234"}
    """
    try:
        data = request.get_json()
        name = data.get('name', '')
        number = data.get('number', '')

        if not name or not number:
            return jsonify({'status': 'error', 'message': '请提供姓名和身份证号码'}), 400

        # 先本地校验格式
        result, error = _lookup_idcard(number)
        if error:
            return jsonify({'status': 'error', 'message': error}), 400

        # 在线验证
        verify_result, verify_error = _verify_online(name, number)
        if verify_error:
            return jsonify({
                'status': 'ok',
                'data': {
                    **result,
                    'verified': None,
                    'verifyError': verify_error
                }
            })

        return jsonify({
            'status': 'ok',
            'data': {
                **result,
                **verify_result
            }
        })
    except Exception as e:
        logger.error(f"实名验证错误: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@idcard_bp.route('/tools/idcard/batch', methods=['POST'])
def idcard_batch_lookup():
    """
    批量身份证解析

    POST /api/tools/idcard/batch
    Body: {"numbers": ["110101199001011234", "310101199002022345"]}
    """
    try:
        data = request.get_json()
        numbers = data.get('numbers', [])

        if not numbers:
            return jsonify({'status': 'error', 'message': '请提供身份证号码列表'}), 400

        if len(numbers) > 100:
            return jsonify({'status': 'error', 'message': '批量查询最多100个号码'}), 400

        results = []
        errors = []
        for number in numbers:
            result, error = _lookup_idcard(number)
            if result:
                results.append(result)
            else:
                errors.append({'number': number, 'error': error})

        return jsonify({
            'status': 'ok',
            'data': results,
            'errors': errors,
            'total': len(results),
            'failed': len(errors)
        })
    except Exception as e:
        logger.error(f"批量查询错误: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@idcard_bp.route('/tools/idcard/validate', methods=['POST'])
def idcard_validate():
    """
    仅校验身份证格式 (不解析详细信息)

    POST /api/tools/idcard/validate
    Body: {"number": "110101199001011234"}
    """
    try:
        data = request.get_json()
        number = data.get('number', '').strip().upper()

        if not number:
            return jsonify({'status': 'error', 'message': '请提供身份证号码'}), 400

        # 15位转18位
        if len(number) == 15:
            number = _convert_15_to_18(number)
            if not number:
                return jsonify({
                    'status': 'ok',
                    'data': {'valid': False, 'message': '15位身份证格式不正确'}
                })

        valid, error = _validate_idcard(number)
        return jsonify({
            'status': 'ok',
            'data': {
                'valid': valid,
                'message': '校验通过' if valid else error
            }
        })
    except Exception as e:
        logger.error(f"身份证校验错误: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


def register_idcard_routes(app):
    app.register_blueprint(idcard_bp, url_prefix='/api')
