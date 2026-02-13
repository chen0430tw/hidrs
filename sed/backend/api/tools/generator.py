"""
身份证号码和手机号生成器
支持中国大陆、香港、澳门、台湾

用途：系统测试、接口调试、数据脱敏
注意：生成的号码仅用于测试，不可用于非法用途

参考资料:
- GB 11643-1999 公民身份号码
- https://github.com/jayknoxqu/id-number-util
- https://github.com/jxlwqq/id-validator.py
"""
import os
import json
import random
import string
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)
generator_bp = Blueprint('generator', __name__)

# 加载地区数据
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
                # 内置基础地区码
                _area_data = {
                    '110000': {'name': '北京市'},
                    '110101': {'name': '东城区'},
                    '110102': {'name': '西城区'},
                    '310000': {'name': '上海市'},
                    '310101': {'name': '黄浦区'},
                    '440000': {'name': '广东省'},
                    '440100': {'name': '广州市'},
                    '440103': {'name': '荔湾区'},
                    '440300': {'name': '深圳市'},
                    '440303': {'name': '罗湖区'},
                }
        except Exception as e:
            logger.error(f"加载地区数据失败: {e}")
            _area_data = {}
    return _area_data


# ============== 身份证号码生成器 ==============

def _calculate_check_digit(id17):
    """计算18位身份证校验码"""
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_codes = '10X98765432'
    total = sum(int(id17[i]) * weights[i] for i in range(17))
    return check_codes[total % 11]


def generate_mainland_idcard(
    area_code=None,
    birth_year=None,
    birth_month=None,
    birth_day=None,
    gender=None,
    age=None
):
    """
    生成中国大陆身份证号码

    Args:
        area_code: 6位地区码，None则随机
        birth_year: 出生年份 (1950-2010)
        birth_month: 出生月份 (1-12)
        birth_day: 出生日期 (1-28)
        gender: 'M'=男, 'F'=女, None=随机
        age: 年龄 (会覆盖birth_year)

    Returns:
        dict: 包含身份证号和详细信息
    """
    _load_area_data()

    # 地区码
    if area_code:
        if len(area_code) != 6:
            area_code = None
    if not area_code:
        # 随机选择一个县级地区码
        county_codes = [k for k in _area_data.keys() if not k.endswith('0000') and not k.endswith('00')]
        if county_codes:
            area_code = random.choice(county_codes)
        else:
            area_code = '110101'  # 默认北京东城区

    # 出生日期
    current_year = datetime.now().year
    if age is not None:
        birth_year = current_year - age

    if not birth_year:
        birth_year = random.randint(1960, 2005)
    if not birth_month:
        birth_month = random.randint(1, 12)
    if not birth_day:
        # 根据月份确定天数
        days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        max_day = days_in_month[birth_month - 1]
        if birth_month == 2 and birth_year % 4 == 0:
            max_day = 29
        birth_day = random.randint(1, max_day)

    birth_str = f"{birth_year:04d}{birth_month:02d}{birth_day:02d}"

    # 顺序码 (奇数=男, 偶数=女)
    if gender == 'M':
        seq = random.randint(0, 49) * 2 + 1  # 奇数
    elif gender == 'F':
        seq = random.randint(0, 49) * 2  # 偶数
    else:
        seq = random.randint(1, 999)

    seq_str = f"{seq:03d}"

    # 组合前17位
    id17 = area_code + birth_str + seq_str

    # 计算校验码
    check_digit = _calculate_check_digit(id17)

    id_number = id17 + check_digit

    # 获取地区名称
    area_name = _area_data.get(area_code, {}).get('name', '未知')
    province_code = area_code[:2] + '0000'
    city_code = area_code[:4] + '00'
    province = _area_data.get(province_code, {}).get('name', '')
    city = _area_data.get(city_code, {}).get('name', '')

    return {
        'number': id_number,
        'type': 'mainland',
        'region': 'CN',
        'province': province,
        'city': city,
        'district': area_name,
        'areaCode': area_code,
        'birthday': f"{birth_year}-{birth_month:02d}-{birth_day:02d}",
        'age': current_year - birth_year,
        'gender': '男' if int(seq_str) % 2 == 1 else '女'
    }


def generate_hk_idcard(birth_year=None, gender=None):
    """
    生成香港身份证号码 (HKID)

    格式: X123456(A)
    - 1-2位: 英文字母 (新证为2位，旧证为1位)
    - 3-8位: 6位数字
    - 括号内: 校验码 (0-9 或 A)
    """
    # 字母部分 (常见首字母: A, B, C, D, E, G, H, K, M, N, O, P, R, S, T, W, Y, Z)
    first_letters = ['A', 'B', 'C', 'D', 'E', 'G', 'H', 'K', 'M', 'N', 'O', 'P', 'R', 'S']
    prefix = random.choice(first_letters)

    # 6位数字
    digits = ''.join([str(random.randint(0, 9)) for _ in range(6)])

    # 计算校验码
    # 香港身份证校验算法
    def calc_hk_check(prefix, digits):
        # 字母转数字: A=10, B=11, ...
        letter_val = ord(prefix) - ord('A') + 10
        total = letter_val * 8

        for i, d in enumerate(digits):
            total += int(d) * (7 - i)

        remainder = total % 11
        if remainder == 0:
            return '0'
        elif remainder == 1:
            return 'A'
        else:
            return str(11 - remainder)

    check = calc_hk_check(prefix, digits)

    return {
        'number': f"{prefix}{digits}({check})",
        'numberPlain': f"{prefix}{digits}{check}",
        'type': 'hkid',
        'region': 'HK',
        'regionName': '香港',
        'gender': '男' if gender == 'M' else ('女' if gender == 'F' else random.choice(['男', '女']))
    }


def generate_macau_idcard(birth_year=None, gender=None):
    """
    生成澳门身份证号码

    格式: 1234567(X)
    - 7位数字
    - 括号内: 校验码 (0-9)
    """
    # 第1位: 1, 5, 7 开头
    first = random.choice(['1', '5', '7'])
    # 后6位随机
    rest = ''.join([str(random.randint(0, 9)) for _ in range(6)])

    digits = first + rest

    # 澳门身份证校验码计算
    def calc_macau_check(digits):
        weights = [7, 6, 5, 4, 3, 2, 1]
        total = sum(int(digits[i]) * weights[i] for i in range(7))
        return str((11 - total % 11) % 10)

    check = calc_macau_check(digits)

    return {
        'number': f"{digits}({check})",
        'numberPlain': f"{digits}{check}",
        'type': 'macau',
        'region': 'MO',
        'regionName': '澳门',
        'gender': '男' if gender == 'M' else ('女' if gender == 'F' else random.choice(['男', '女']))
    }


def generate_taiwan_idcard(gender=None):
    """
    生成台湾身份证号码

    格式: A123456789
    - 第1位: 英文字母 (代表户籍地)
    - 第2位: 1=男, 2=女
    - 第3-9位: 7位数字
    - 第10位: 校验码
    """
    # 户籍地字母对应数字
    region_codes = {
        'A': 10, 'B': 11, 'C': 12, 'D': 13, 'E': 14, 'F': 15, 'G': 16, 'H': 17,
        'I': 34, 'J': 18, 'K': 19, 'L': 20, 'M': 21, 'N': 22, 'O': 35, 'P': 23,
        'Q': 24, 'R': 25, 'S': 26, 'T': 27, 'U': 28, 'V': 29, 'W': 32, 'X': 30,
        'Y': 31, 'Z': 33
    }

    # 常见户籍地
    common_regions = ['A', 'B', 'C', 'D', 'E', 'F', 'H', 'J', 'K', 'N', 'P', 'T']
    region = random.choice(common_regions)

    # 性别码
    if gender == 'M':
        gender_code = '1'
    elif gender == 'F':
        gender_code = '2'
    else:
        gender_code = random.choice(['1', '2'])

    # 7位随机数字
    digits = ''.join([str(random.randint(0, 9)) for _ in range(7)])

    # 计算校验码
    def calc_tw_check(region, gender_code, digits):
        region_val = region_codes[region]
        n1 = region_val // 10
        n2 = region_val % 10

        # 加权计算
        total = n1 * 1 + n2 * 9 + int(gender_code) * 8
        weights = [7, 6, 5, 4, 3, 2, 1]
        for i, d in enumerate(digits):
            total += int(d) * weights[i]

        return str((10 - total % 10) % 10)

    check = calc_tw_check(region, gender_code, digits)

    return {
        'number': f"{region}{gender_code}{digits}{check}",
        'type': 'taiwan',
        'region': 'TW',
        'regionName': '台湾',
        'gender': '男' if gender_code == '1' else '女'
    }


# ============== 手机号生成器 ==============

# 中国大陆号段 (2024年更新)
MAINLAND_PREFIXES = {
    '中国移动': [
        '134', '135', '136', '137', '138', '139',
        '147', '148', '150', '151', '152', '157', '158', '159',
        '172', '178', '182', '183', '184', '187', '188',
        '195', '197', '198'
    ],
    '中国联通': [
        '130', '131', '132', '145', '146', '155', '156',
        '166', '167', '171', '175', '176', '185', '186',
        '196'
    ],
    '中国电信': [
        '133', '149', '153', '173', '174', '177',
        '180', '181', '189', '190', '191', '193', '199'
    ],
    '中国广电': ['192']
}


def generate_mainland_phone(carrier=None, prefix=None):
    """
    生成中国大陆手机号

    Args:
        carrier: 运营商 ('移动', '联通', '电信', '广电')
        prefix: 指定号段前缀
    """
    if prefix:
        selected_prefix = prefix[:3]
        carrier_name = '未知'
        for name, prefixes in MAINLAND_PREFIXES.items():
            if selected_prefix in prefixes:
                carrier_name = name
                break
    elif carrier:
        carrier_map = {
            '移动': '中国移动', '联通': '中国联通',
            '电信': '中国电信', '广电': '中国广电'
        }
        carrier_name = carrier_map.get(carrier, carrier)
        if carrier_name in MAINLAND_PREFIXES:
            selected_prefix = random.choice(MAINLAND_PREFIXES[carrier_name])
        else:
            selected_prefix = random.choice(MAINLAND_PREFIXES['中国移动'])
            carrier_name = '中国移动'
    else:
        all_prefixes = []
        for prefixes in MAINLAND_PREFIXES.values():
            all_prefixes.extend(prefixes)
        selected_prefix = random.choice(all_prefixes)
        carrier_name = '未知'
        for name, prefixes in MAINLAND_PREFIXES.items():
            if selected_prefix in prefixes:
                carrier_name = name
                break

    # 生成后8位
    suffix = ''.join([str(random.randint(0, 9)) for _ in range(8)])

    return {
        'number': selected_prefix + suffix,
        'formatted': f"+86 {selected_prefix} {suffix[:4]} {suffix[4:]}",
        'type': 'mainland',
        'region': 'CN',
        'regionName': '中国大陆',
        'carrier': carrier_name,
        'prefix': selected_prefix
    }


def generate_hk_phone():
    """
    生成香港手机号

    格式: 9XXX XXXX 或 6XXX XXXX
    - 9开头: 较早期
    - 6开头: 较新
    """
    prefix = random.choice(['9', '6', '5'])
    rest = ''.join([str(random.randint(0, 9)) for _ in range(7)])
    number = prefix + rest

    return {
        'number': number,
        'formatted': f"+852 {number[:4]} {number[4:]}",
        'type': 'hk',
        'region': 'HK',
        'regionName': '香港',
        'carrier': '香港运营商'
    }


def generate_macau_phone():
    """
    生成澳门手机号

    格式: 6XXX XXXX
    """
    prefix = '6'
    rest = ''.join([str(random.randint(0, 9)) for _ in range(7)])
    number = prefix + rest

    return {
        'number': number,
        'formatted': f"+853 {number[:4]} {number[4:]}",
        'type': 'macau',
        'region': 'MO',
        'regionName': '澳门',
        'carrier': '澳门运营商'
    }


def generate_taiwan_phone():
    """
    生成台湾手机号

    格式: 09XX XXX XXX
    - 09开头
    """
    prefix = '09'
    second = random.choice(['0', '1', '2', '3', '5', '6', '7', '8', '9'])
    rest = ''.join([str(random.randint(0, 9)) for _ in range(7)])
    number = prefix + second + rest

    return {
        'number': number,
        'formatted': f"+886 {number[1:4]} {number[4:7]} {number[7:]}",
        'type': 'taiwan',
        'region': 'TW',
        'regionName': '台湾',
        'carrier': '台湾运营商'
    }


# ============== API 路由 ==============

@generator_bp.route('/tools/generate/idcard', methods=['POST'])
def api_generate_idcard():
    """
    生成身份证号码

    POST /api/tools/generate/idcard
    Body: {
        "region": "CN",  // CN=大陆, HK=香港, MO=澳门, TW=台湾
        "count": 1,      // 生成数量 (1-100)
        "areaCode": "110101",  // 大陆地区码 (可选)
        "age": 25,       // 年龄 (可选)
        "gender": "M"    // M=男, F=女 (可选)
    }
    """
    try:
        data = request.get_json() or {}
        region = data.get('region', 'CN').upper()
        count = min(int(data.get('count', 1)), 100)
        area_code = data.get('areaCode')
        age = data.get('age')
        gender = data.get('gender')

        results = []
        for _ in range(count):
            if region == 'CN':
                result = generate_mainland_idcard(
                    area_code=area_code,
                    age=age,
                    gender=gender
                )
            elif region == 'HK':
                result = generate_hk_idcard(gender=gender)
            elif region == 'MO':
                result = generate_macau_idcard(gender=gender)
            elif region == 'TW':
                result = generate_taiwan_idcard(gender=gender)
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'不支持的地区: {region}'
                }), 400

            results.append(result)

        return jsonify({
            'status': 'ok',
            'data': results if count > 1 else results[0],
            'count': count
        })
    except Exception as e:
        logger.error(f"生成身份证号失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@generator_bp.route('/tools/generate/phone', methods=['POST'])
def api_generate_phone():
    """
    生成手机号码

    POST /api/tools/generate/phone
    Body: {
        "region": "CN",      // CN=大陆, HK=香港, MO=澳门, TW=台湾
        "count": 1,          // 生成数量 (1-100)
        "carrier": "移动",   // 运营商 (大陆可选: 移动/联通/电信/广电)
        "prefix": "138"      // 号段前缀 (可选)
    }
    """
    try:
        data = request.get_json() or {}
        region = data.get('region', 'CN').upper()
        count = min(int(data.get('count', 1)), 100)
        carrier = data.get('carrier')
        prefix = data.get('prefix')

        results = []
        for _ in range(count):
            if region == 'CN':
                result = generate_mainland_phone(carrier=carrier, prefix=prefix)
            elif region == 'HK':
                result = generate_hk_phone()
            elif region == 'MO':
                result = generate_macau_phone()
            elif region == 'TW':
                result = generate_taiwan_phone()
            else:
                return jsonify({
                    'status': 'error',
                    'message': f'不支持的地区: {region}'
                }), 400

            results.append(result)

        return jsonify({
            'status': 'ok',
            'data': results if count > 1 else results[0],
            'count': count
        })
    except Exception as e:
        logger.error(f"生成手机号失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@generator_bp.route('/tools/generate/person', methods=['POST'])
def api_generate_person():
    """
    生成完整虚拟身份 (身份证+手机号+姓名)

    POST /api/tools/generate/person
    Body: {
        "region": "CN",
        "count": 1,
        "gender": "M"
    }
    """
    try:
        data = request.get_json() or {}
        region = data.get('region', 'CN').upper()
        count = min(int(data.get('count', 1)), 50)
        gender = data.get('gender')

        # 常见姓氏
        surnames = ['王', '李', '张', '刘', '陈', '杨', '赵', '黄', '周', '吴',
                    '徐', '孙', '胡', '朱', '高', '林', '何', '郭', '马', '罗']
        male_names = ['伟', '强', '磊', '军', '勇', '明', '杰', '涛', '鹏', '超',
                      '浩', '华', '建', '志', '文', '斌', '俊', '健', '宇', '轩']
        female_names = ['芳', '娟', '敏', '静', '婷', '丽', '燕', '玲', '艳', '红',
                        '梅', '莉', '萍', '秀', '英', '霞', '娜', '雪', '琳', '慧']

        results = []
        for _ in range(count):
            # 生成身份证
            if region == 'CN':
                idcard = generate_mainland_idcard(gender=gender)
            elif region == 'HK':
                idcard = generate_hk_idcard(gender=gender)
            elif region == 'MO':
                idcard = generate_macau_idcard(gender=gender)
            elif region == 'TW':
                idcard = generate_taiwan_idcard(gender=gender)
            else:
                return jsonify({'status': 'error', 'message': f'不支持的地区: {region}'}), 400

            # 生成手机号
            if region == 'CN':
                phone = generate_mainland_phone()
            elif region == 'HK':
                phone = generate_hk_phone()
            elif region == 'MO':
                phone = generate_macau_phone()
            elif region == 'TW':
                phone = generate_taiwan_phone()

            # 生成姓名
            actual_gender = idcard.get('gender', '男')
            surname = random.choice(surnames)
            if actual_gender == '男':
                given_name = random.choice(male_names) + random.choice(male_names[:10])
            else:
                given_name = random.choice(female_names) + random.choice(female_names[:10])

            name = surname + given_name

            results.append({
                'name': name,
                'idcard': idcard,
                'phone': phone,
                'gender': actual_gender
            })

        return jsonify({
            'status': 'ok',
            'data': results if count > 1 else results[0],
            'count': count
        })
    except Exception as e:
        logger.error(f"生成虚拟身份失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@generator_bp.route('/tools/generate/carriers', methods=['GET'])
def api_list_carriers():
    """获取支持的运营商和号段"""
    return jsonify({
        'status': 'ok',
        'data': {
            'mainland': MAINLAND_PREFIXES,
            'regions': ['CN', 'HK', 'MO', 'TW']
        }
    })


def register_generator_routes(app):
    app.register_blueprint(generator_bp, url_prefix='/api')
