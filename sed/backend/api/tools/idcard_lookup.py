"""
身份证号码解析API
支持中国大陆、香港、澳门、台湾身份证解析与校验

校验算法参考:
- 大陆: GB 11643-1999 标准
- 香港: HKID 加权校验算法
- 台湾: 字母转码 + 加权校验算法
- 澳门: 格式校验 (校验码算法未公开)

Sources:
- https://blog.csdn.net/Hope_lee/article/details/103547081
- https://blog.csdn.net/u014663362/article/details/40074593
- https://bajiu.cn/sfz/
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
JUHE_API_KEY = os.getenv('JUHE_API_KEY', '')

# 本地数据缓存
_area_data = None


def _load_area_data():
    """加载行政区划数据"""
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


# ============== 自动检测身份证类型 ==============

def _detect_id_type(id_number):
    """
    自动检测身份证类型
    返回: 'CN', 'HK', 'MO', 'TW', 或 None
    """
    id_number = id_number.strip().upper().replace(' ', '').replace('(', '').replace(')', '').replace('（', '').replace('）', '')

    # 大陆: 15位数字 或 17位数字+1位数字/X
    if re.match(r'^\d{15}$', id_number):
        return 'CN'
    if re.match(r'^\d{17}[\dX]$', id_number):
        return 'CN'

    # 香港: 1-2个字母 + 6位数字 + 1位校验码(数字或A)
    if re.match(r'^[A-Z]{1,2}\d{6}[\dA]$', id_number):
        return 'HK'

    # 台湾: 1个字母 + 9位数字
    if re.match(r'^[A-Z]\d{9}$', id_number):
        return 'TW'

    # 澳门: 1位数字(1/5/7) + 6位数字 + 1位校验码
    if re.match(r'^[157]\d{6}[\dA]$', id_number):
        return 'MO'

    return None


# ============== 大陆身份证 ==============

def _validate_cn_idcard(idcard):
    """校验18位大陆身份证 (GB 11643-1999)"""
    if len(idcard) != 18:
        return False, "身份证号码长度不正确"

    pattern = re.compile(r'^\d{17}[\dXx]$')
    if not pattern.match(idcard):
        return False, "身份证号码格式不正确"

    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_codes = '10X98765432'

    try:
        total = sum(int(idcard[i]) * weights[i] for i in range(17))
        expected = check_codes[total % 11]
        if idcard[-1].upper() != expected:
            return False, f"校验码错误，期望: {expected}"
    except ValueError:
        return False, "身份证号码包含非法字符"

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
    """15位身份证转18位"""
    if len(idcard15) != 15 or not idcard15.isdigit():
        return None

    year2 = idcard15[6:8]
    century = '19' if int(year2) > 20 else '20'
    idcard17 = idcard15[:6] + century + idcard15[6:]

    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_codes = '10X98765432'
    total = sum(int(idcard17[i]) * weights[i] for i in range(17))
    check_code = check_codes[total % 11]

    return idcard17 + check_code


def _get_constellation(month, day):
    """获取星座"""
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
    """获取生肖"""
    zodiacs = ['猴', '鸡', '狗', '猪', '鼠', '牛', '虎', '兔', '龙', '蛇', '马', '羊']
    return zodiacs[year % 12]


def _parse_area(code6):
    """解析6位地区码"""
    _load_area_data()
    code2 = code6[:2] + '0000'
    code4 = code6[:4] + '00'

    province = _area_data.get(code2, {}).get('name', '')
    city = _area_data.get(code4, {}).get('name', '')
    district = _area_data.get(code6, {}).get('name', '')

    if province in ['北京市', '上海市', '天津市', '重庆市']:
        if not city:
            city = province

    return province, city, district


def _lookup_cn_idcard(idcard):
    """解析大陆身份证"""
    idcard = idcard.strip().upper().replace(' ', '')

    if len(idcard) == 15:
        idcard18 = _convert_15_to_18(idcard)
        if not idcard18:
            return None, "15位身份证格式不正确"
        original = idcard
        idcard = idcard18
    else:
        original = idcard

    if len(idcard) != 18:
        return None, "身份证号码长度不正确"

    valid, error = _validate_cn_idcard(idcard)
    if not valid:
        return None, error

    code6 = idcard[:6]
    province, city, district = _parse_area(code6)

    birth_str = idcard[6:14]
    try:
        birthday = datetime.strptime(birth_str, '%Y%m%d')
        birthday_formatted = birthday.strftime('%Y-%m-%d')
        year, month, day = birthday.year, birthday.month, birthday.day

        today = datetime.now()
        age = today.year - year
        if (today.month, today.day) < (month, day):
            age -= 1

        constellation = _get_constellation(month, day)
        zodiac = _get_zodiac(year)
    except ValueError:
        return None, "出生日期解析失败"

    gender_code = int(idcard[16])
    gender = '男' if gender_code % 2 == 1 else '女'

    return {
        'number': idcard,
        'original': original if original != idcard else None,
        'type': 'CN',
        'typeName': '中国大陆居民身份证',
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


# ============== 香港身份证 (HKID) ==============

def _validate_hk_idcard(idcard):
    """
    校验香港身份证
    格式: X123456(A) 或 XY123456(A)
    算法:
    - 单字母: 字母值×8 + 数字加权求和
    - 双字母: 第一字母×9 + 第二字母×8 + 数字加权求和
    - 余数0→0, 余数1→A, 其他→11-余数
    """
    # 清理格式
    idcard = idcard.strip().upper().replace(' ', '')
    idcard = idcard.replace('(', '').replace(')', '').replace('（', '').replace('）', '')

    # 匹配格式
    match = re.match(r'^([A-Z]{1,2})(\d{6})([\dA])$', idcard)
    if not match:
        return False, "香港身份证格式不正确"

    prefix = match.group(1)
    digits = match.group(2)
    check = match.group(3)

    # 计算校验码
    if len(prefix) == 1:
        # 单字母: 36×9 + 字母值×8
        total = 36 * 9 + (ord(prefix) - ord('A') + 10) * 8
    else:
        # 双字母
        total = (ord(prefix[0]) - ord('A') + 10) * 9 + (ord(prefix[1]) - ord('A') + 10) * 8

    # 数字加权 (7,6,5,4,3,2)
    weights = [7, 6, 5, 4, 3, 2]
    for i, d in enumerate(digits):
        total += int(d) * weights[i]

    remainder = total % 11
    if remainder == 0:
        expected = '0'
    elif remainder == 1:
        expected = 'A'
    else:
        expected = str(11 - remainder)

    if check != expected:
        return False, f"校验码错误，期望: {expected}"

    return True, None


def _lookup_hk_idcard(idcard):
    """解析香港身份证"""
    idcard_clean = idcard.strip().upper().replace(' ', '')
    idcard_clean = idcard_clean.replace('(', '').replace(')', '').replace('（', '').replace('）', '')

    valid, error = _validate_hk_idcard(idcard_clean)
    if not valid:
        return None, error

    match = re.match(r'^([A-Z]{1,2})(\d{6})([\dA])$', idcard_clean)
    prefix = match.group(1)
    digits = match.group(2)
    check = match.group(3)

    # 格式化显示
    formatted = f"{prefix}{digits}({check})"

    return {
        'number': idcard_clean,
        'formatted': formatted,
        'type': 'HK',
        'typeName': '香港身份证 (HKID)',
        'valid': True,
        'region': '香港特别行政区',
        'prefix': prefix,
        'checkDigit': check
    }, None


# ============== 台湾身份证 ==============

# 台湾地区码对照表
TW_REGION_CODES = {
    'A': (10, '台北市'), 'B': (11, '台中市'), 'C': (12, '基隆市'),
    'D': (13, '台南市'), 'E': (14, '高雄市'), 'F': (15, '新北市'),
    'G': (16, '宜兰县'), 'H': (17, '桃园市'), 'I': (34, '嘉义市'),
    'J': (18, '新竹县'), 'K': (19, '苗栗县'), 'L': (20, '台中县'),
    'M': (21, '南投县'), 'N': (22, '彰化县'), 'O': (35, '新竹市'),
    'P': (23, '云林县'), 'Q': (24, '嘉义县'), 'R': (25, '台南县'),
    'S': (26, '高雄县'), 'T': (27, '屏东县'), 'U': (28, '花莲县'),
    'V': (29, '台东县'), 'W': (32, '金门县'), 'X': (30, '澎湖县'),
    'Y': (31, '阳明山'), 'Z': (33, '连江县')
}


def _validate_tw_idcard(idcard):
    """
    校验台湾身份证
    格式: A123456789 (1个字母 + 9位数字)
    算法:
    - 字母转为两位数字 (A=10, B=11, ...)
    - n1×1 + n2×9 + 性别码×8 + d1×7 + d2×6 + ... + d7×1
    - 校验码 = (10 - total%10) % 10
    """
    idcard = idcard.strip().upper()

    if not re.match(r'^[A-Z]\d{9}$', idcard):
        return False, "台湾身份证格式不正确 (应为1个字母+9位数字)"

    letter = idcard[0]
    if letter not in TW_REGION_CODES:
        return False, f"无效的地区码: {letter}"

    digits = idcard[1:]

    # 性别码检查 (1=男, 2=女)
    gender_code = digits[0]
    if gender_code not in ['1', '2']:
        return False, "性别码不正确 (应为1或2)"

    # 计算校验码
    region_code = TW_REGION_CODES[letter][0]
    n1 = region_code // 10
    n2 = region_code % 10

    total = n1 * 1 + n2 * 9

    weights = [8, 7, 6, 5, 4, 3, 2, 1]
    for i in range(8):
        total += int(digits[i]) * weights[i]

    expected_check = (10 - total % 10) % 10

    if int(digits[8]) != expected_check:
        return False, f"校验码错误，期望: {expected_check}"

    return True, None


def _lookup_tw_idcard(idcard):
    """解析台湾身份证"""
    idcard = idcard.strip().upper()

    valid, error = _validate_tw_idcard(idcard)
    if not valid:
        return None, error

    letter = idcard[0]
    digits = idcard[1:]

    region_info = TW_REGION_CODES.get(letter, (0, '未知'))
    region_name = region_info[1]

    gender = '男' if digits[0] == '1' else '女'

    return {
        'number': idcard,
        'type': 'TW',
        'typeName': '台湾身份证',
        'valid': True,
        'region': region_name,
        'regionCode': letter,
        'gender': gender,
        'genderCode': int(digits[0])
    }, None


# ============== 澳门身份证 ==============

def _validate_mo_idcard(idcard):
    """
    校验澳门身份证
    格式: X/NNNNNN/Y 或 XNNNNNN(Y)
    - X: 首位数字 (1, 5, 7)
    - NNNNNN: 6位数字
    - Y: 校验码 (算法未公开,仅做格式校验)
    """
    # 清理格式
    idcard = idcard.strip().upper().replace(' ', '')
    idcard = idcard.replace('/', '').replace('(', '').replace(')', '').replace('（', '').replace('）', '')

    if not re.match(r'^[157]\d{6}[\dA]$', idcard):
        return False, "澳门身份证格式不正确"

    first = idcard[0]
    if first not in ['1', '5', '7']:
        return False, "首位数字应为1、5或7"

    return True, None


def _lookup_mo_idcard(idcard):
    """解析澳门身份证"""
    idcard_clean = idcard.strip().upper().replace(' ', '')
    idcard_clean = idcard_clean.replace('/', '').replace('(', '').replace(')', '').replace('（', '').replace('）', '')

    valid, error = _validate_mo_idcard(idcard_clean)
    if not valid:
        return None, error

    first = idcard_clean[0]
    main = idcard_clean[1:7]
    check = idcard_clean[7]

    # 首位数字含义
    first_meanings = {
        '1': '1992年后领取或龙的行动时期',
        '5': '持有或曾持有葡萄牙身份证',
        '7': '曾取得蓝卡 (1970-80年代从内地合法到澳)'
    }

    formatted = f"{first}/{main}/({check})"

    return {
        'number': idcard_clean,
        'formatted': formatted,
        'type': 'MO',
        'typeName': '澳门身份证',
        'valid': True,
        'region': '澳门特别行政区',
        'firstDigit': first,
        'firstDigitMeaning': first_meanings.get(first, '未知'),
        'checkDigit': check
    }, None


# ============== 统一查询接口 ==============

def _lookup_idcard(idcard, region=None):
    """
    统一身份证查询接口
    自动检测类型或指定地区
    """
    idcard = idcard.strip()

    if not region:
        region = _detect_id_type(idcard)

    if not region:
        return None, "无法识别身份证类型，请指定地区 (CN/HK/MO/TW)"

    if region == 'CN':
        return _lookup_cn_idcard(idcard)
    elif region == 'HK':
        return _lookup_hk_idcard(idcard)
    elif region == 'TW':
        return _lookup_tw_idcard(idcard)
    elif region == 'MO':
        return _lookup_mo_idcard(idcard)
    else:
        return None, f"不支持的地区: {region}"


# ============== API 路由 ==============

@idcard_bp.route('/tools/idcard/lookup', methods=['POST'])
def idcard_lookup():
    """
    身份证号码解析 (支持CN/HK/MO/TW)

    POST /api/tools/idcard/lookup
    Body: {
        "number": "A123456(7)",
        "region": "HK"  // 可选，自动检测
    }
    """
    try:
        data = request.get_json()
        number = data.get('number', '')
        region = data.get('region', '').upper() if data.get('region') else None

        if not number:
            return jsonify({'status': 'error', 'message': '请提供身份证号码'}), 400

        result, error = _lookup_idcard(number, region)

        if error:
            return jsonify({'status': 'error', 'message': error}), 400

        return jsonify({'status': 'ok', 'data': result})
    except Exception as e:
        logger.error(f"身份证查询错误: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@idcard_bp.route('/tools/idcard/validate', methods=['POST'])
def idcard_validate():
    """
    仅校验身份证格式

    POST /api/tools/idcard/validate
    Body: {"number": "...", "region": "CN"}
    """
    try:
        data = request.get_json()
        number = data.get('number', '').strip()
        region = data.get('region', '').upper() if data.get('region') else None

        if not number:
            return jsonify({'status': 'error', 'message': '请提供身份证号码'}), 400

        if not region:
            region = _detect_id_type(number)

        if not region:
            return jsonify({
                'status': 'ok',
                'data': {'valid': False, 'message': '无法识别身份证类型'}
            })

        # 根据类型校验
        if region == 'CN':
            number_clean = number.upper()
            if len(number_clean) == 15:
                number_clean = _convert_15_to_18(number_clean)
                if not number_clean:
                    return jsonify({
                        'status': 'ok',
                        'data': {'valid': False, 'message': '15位身份证格式不正确', 'type': 'CN'}
                    })
            valid, error = _validate_cn_idcard(number_clean)
        elif region == 'HK':
            valid, error = _validate_hk_idcard(number)
        elif region == 'TW':
            valid, error = _validate_tw_idcard(number)
        elif region == 'MO':
            valid, error = _validate_mo_idcard(number)
        else:
            return jsonify({
                'status': 'ok',
                'data': {'valid': False, 'message': f'不支持的地区: {region}'}
            })

        return jsonify({
            'status': 'ok',
            'data': {
                'valid': valid,
                'message': '校验通过' if valid else error,
                'type': region
            }
        })
    except Exception as e:
        logger.error(f"身份证校验错误: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@idcard_bp.route('/tools/idcard/batch', methods=['POST'])
def idcard_batch_lookup():
    """批量身份证解析"""
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


@idcard_bp.route('/tools/idcard/detect', methods=['POST'])
def idcard_detect():
    """检测身份证类型"""
    try:
        data = request.get_json()
        number = data.get('number', '').strip()

        if not number:
            return jsonify({'status': 'error', 'message': '请提供身份证号码'}), 400

        id_type = _detect_id_type(number)

        type_names = {
            'CN': '中国大陆',
            'HK': '香港',
            'MO': '澳门',
            'TW': '台湾'
        }

        return jsonify({
            'status': 'ok',
            'data': {
                'type': id_type,
                'typeName': type_names.get(id_type, '未知') if id_type else None,
                'detected': id_type is not None
            }
        })
    except Exception as e:
        logger.error(f"类型检测错误: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


def register_idcard_routes(app):
    app.register_blueprint(idcard_bp, url_prefix='/api')
