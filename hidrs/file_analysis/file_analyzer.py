#!/usr/bin/env python3
"""
文件分析器 - HIDRS File Analysis Module
基于Xkeystroke项目的Python实现，用于深度文件分析和安全检测

功能:
- 文件哈希计算 (MD5, SHA1, SHA256, SHA512)
- 熵值分析 (检测加密或混淆)
- 文件签名验证 (魔术数字检查)
- EXIF元数据提取 (图片、视频)
- 安全模式检测 (可疑内容、脚本、编码字符串)
- ZIP/压缩包分析
- 内容统计 (行数、字数、字符数)

作者: HIDRS Team (基于Xkeystroke改编)
日期: 2026-02-04
"""

import os
import io
import re
import math
import hashlib
import mimetypes
import zipfile
import base64
import json
from collections import Counter
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

# 可选依赖
try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import exifread
    HAS_EXIFREAD = True
except ImportError:
    HAS_EXIFREAD = False


class FileAnalyzer:
    """
    文件分析器主类
    """

    # EICAR测试病毒签名
    EICAR_SIGNATURE = b'X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'

    # 文件签名 (Magic Numbers)
    FILE_SIGNATURES = {
        'jpg': [[0xFF, 0xD8, 0xFF, 0xE0], [0xFF, 0xD8, 0xFF, 0xE1]],
        'png': [[0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]],
        'gif': [[0x47, 0x49, 0x46, 0x38]],
        'pdf': [[0x25, 0x50, 0x44, 0x46]],
        'zip': [[0x50, 0x4B, 0x03, 0x04], [0x50, 0x4B, 0x05, 0x06]],
        'rar': [[0x52, 0x61, 0x72, 0x21, 0x1A, 0x07]],
        'exe': [[0x4D, 0x5A]],
        'elf': [[0x7F, 0x45, 0x4C, 0x46]],
        '7z': [[0x37, 0x7A, 0xBC, 0xAF, 0x27, 0x1C]],
        'tar': [[0x75, 0x73, 0x74, 0x61, 0x72]],
        'gz': [[0x1F, 0x8B]],
        'bz2': [[0x42, 0x5A, 0x68]],
        'mp3': [[0x49, 0x44, 0x33], [0xFF, 0xFB]],
        'mp4': [[0x66, 0x74, 0x79, 0x70]],
        'avi': [[0x52, 0x49, 0x46, 0x46]],
        'wav': [[0x52, 0x49, 0x46, 0x46]],
    }

    # 危险文件扩展名
    EXECUTABLE_EXTENSIONS = {
        '.exe', '.dll', '.com', '.bat', '.cmd', '.vbs', '.vbe', '.js', '.jse',
        '.wsf', '.wsh', '.msi', '.scr', '.pif', '.app', '.deb', '.rpm', '.sh',
        '.ps1', '.psm1', '.psd1', '.jar', '.apk', '.so', '.dylib'
    }

    def __init__(self, file_path: str):
        """
        初始化文件分析器

        Args:
            file_path: 要分析的文件路径
        """
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        self.file_size = os.path.getsize(file_path)
        self.file_stat = os.stat(file_path)
        self.mime_type, _ = mimetypes.guess_type(file_path)

        # 读取文件内容
        with open(file_path, 'rb') as f:
            self.file_buffer = f.read()

        # 尝试解码为文本
        self.file_content = None
        self.is_text = False
        if self.mime_type and self.mime_type.startswith('text'):
            try:
                self.file_content = self.file_buffer.decode('utf-8')
                self.is_text = True
            except UnicodeDecodeError:
                try:
                    self.file_content = self.file_buffer.decode('latin-1')
                    self.is_text = True
                except:
                    pass

    def analyze(self) -> Dict[str, Any]:
        """
        执行完整文件分析

        Returns:
            分析结果字典
        """
        result = {
            'file_stats': self._analyze_file_stats(),
            'content_analysis': self._analyze_content(),
            'security_checks': self._security_checks(),
            'hashes': self._calculate_hashes(),
            'exif_data': self._extract_exif() if self._is_image() else None,
            'zip_analysis': self._analyze_zip() if self._is_zip() else None,
            'risk_assessment': None,
            'timestamp': datetime.now().isoformat()
        }

        # 风险评估
        result['risk_assessment'] = self._assess_risk(result)

        return result

    def _analyze_file_stats(self) -> Dict[str, Any]:
        """
        分析文件统计信息
        """
        entropy = self._calculate_entropy()

        return {
            'size': self.file_size,
            'size_formatted': self._format_size(self.file_size),
            'type': self.mime_type or 'Unknown',
            'encoding': 'UTF-8' if self.is_text else 'Binary',
            'created': datetime.fromtimestamp(self.file_stat.st_ctime).isoformat(),
            'modified': datetime.fromtimestamp(self.file_stat.st_mtime).isoformat(),
            'accessed': datetime.fromtimestamp(self.file_stat.st_atime).isoformat(),
            'permissions': oct(self.file_stat.st_mode)[-3:],
            'is_executable': os.access(self.file_path, os.X_OK),
            'entropy': round(entropy, 4),
            'is_binary': not self.is_text,
            'signature_valid': self._verify_file_signature()
        }

    def _analyze_content(self) -> Dict[str, Any]:
        """
        分析文件内容
        """
        if not self.is_text or not self.file_content:
            return {
                'file_type': self.mime_type or 'Binary',
                'is_text': False
            }

        lines = self.file_content.split('\n')
        words = self.file_content.split()

        return {
            'file_type': self.mime_type,
            'is_text': True,
            'line_count': len(lines),
            'character_count': len(self.file_content),
            'word_count': len(words),
            'average_line_length': round(len(self.file_content) / max(len(lines), 1), 2),
            'non_printable_chars': len([c for c in self.file_content if not c.isprintable() and c not in '\n\r\t'])
        }

    def _security_checks(self) -> Dict[str, Any]:
        """
        执行安全检查
        """
        checks = {
            'is_eicar_test': self._check_eicar(),
            'malicious_patterns': False,
            'contains_active_content': False,
            'contains_urls': False,
            'contains_base64': False,
            'contains_executables': self._has_executable_extension(),
            'contains_compressed_files': self._is_zip(),
            'high_entropy': self._calculate_entropy() > 7.5,
            'signature_valid': self._verify_file_signature(),
            'suspicious_strings': [],
            'obfuscation_score': 0.0
        }

        if self.is_text and self.file_content:
            checks['contains_active_content'] = self._detect_active_content()
            checks['contains_urls'] = self._detect_urls()
            checks['contains_base64'] = self._detect_base64()
            checks['suspicious_strings'] = self._find_suspicious_strings()
            checks['obfuscation_score'] = self._detect_obfuscation()
            checks['malicious_patterns'] = len(checks['suspicious_strings']) > 0

        return checks

    def _calculate_hashes(self) -> Dict[str, str]:
        """
        计算文件哈希值
        """
        return {
            'md5': hashlib.md5(self.file_buffer).hexdigest(),
            'sha1': hashlib.sha1(self.file_buffer).hexdigest(),
            'sha256': hashlib.sha256(self.file_buffer).hexdigest(),
            'sha512': hashlib.sha512(self.file_buffer).hexdigest()
        }

    def _calculate_entropy(self) -> float:
        """
        计算文件熵值 (0-8, 值越高表示随机性越强)
        高熵值可能表示加密或压缩内容
        """
        if len(self.file_buffer) == 0:
            return 0.0

        # 统计字节频率
        byte_counts = Counter(self.file_buffer)

        # 计算熵
        entropy = 0.0
        for count in byte_counts.values():
            probability = count / len(self.file_buffer)
            entropy -= probability * math.log2(probability)

        return entropy

    def _verify_file_signature(self) -> bool:
        """
        验证文件签名是否与扩展名匹配
        """
        extension = os.path.splitext(self.file_name)[1].lower().lstrip('.')

        if extension not in self.FILE_SIGNATURES:
            return True  # 未知类型，假定有效

        signatures = self.FILE_SIGNATURES[extension]

        for signature in signatures:
            if len(self.file_buffer) >= len(signature):
                if all(self.file_buffer[i] == byte for i, byte in enumerate(signature)):
                    return True

        return False

    def _check_eicar(self) -> bool:
        """
        检测EICAR测试病毒签名
        """
        return self.EICAR_SIGNATURE in self.file_buffer

    def _detect_active_content(self) -> bool:
        """
        检测活跃内容 (脚本、代码)
        """
        if not self.file_content:
            return False

        patterns = [
            r'<script[^>]*>',
            r'eval\s*\(',
            r'exec\s*\(',
            r'system\s*\(',
            r'setTimeout\s*\(',
            r'setInterval\s*\(',
            r'Function\s*\(',
            r'javascript:',
            r'onerror\s*=',
            r'onload\s*='
        ]

        return any(re.search(pattern, self.file_content, re.IGNORECASE) for pattern in patterns)

    def _detect_urls(self) -> bool:
        """
        检测URL
        """
        if not self.file_content:
            return False

        url_pattern = r'https?://[^\s/$.?#].[^\s]*'
        return bool(re.search(url_pattern, self.file_content, re.IGNORECASE))

    def _detect_base64(self) -> bool:
        """
        检测Base64编码内容
        """
        if not self.file_content:
            return False

        # Base64长字符串检测
        base64_pattern = r'[A-Za-z0-9+/]{40,}={0,2}'
        matches = re.findall(base64_pattern, self.file_content)

        # 验证是否为有效Base64
        for match in matches[:5]:  # 只检查前5个匹配
            try:
                base64.b64decode(match, validate=True)
                return True
            except:
                pass

        return False

    def _find_suspicious_strings(self) -> List[str]:
        """
        查找可疑字符串
        """
        if not self.file_content:
            return []

        suspicious = []
        patterns = {
            'eval': r'\beval\s*\(',
            'exec': r'\b(exec|system|spawn|child_process)\s*\(',
            'shell': r'\b(cmd|powershell|bash|sh)\s',
            'network': r'\b(socket|connect|bind|listen)\s*\(',
            'crypto': r'\b(encrypt|decrypt|cipher|AES|RSA|MD5|SHA)\s',
            'password': r'\b(password|passwd|pwd|secret|token|api[_-]?key)\s*[=:]',
            'sql': r'\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION)\s',
        }

        for name, pattern in patterns.items():
            if re.search(pattern, self.file_content, re.IGNORECASE):
                suspicious.append(name)

        return suspicious

    def _detect_obfuscation(self) -> float:
        """
        检测代码混淆程度 (0-1)
        """
        if not self.file_content:
            return 0.0

        score = 0.0
        indicators = {
            r'eval\s*\(': 0.2,
            r'(fromCharCode|charCodeAt)': 0.2,
            r'\\x[0-9a-f]{2}': 0.15,
            r'\\u[0-9a-f]{4}': 0.15,
            r'[\'"][^\'"]{200,}[\'"]': 0.1,  # 长字符串
            r'\[\]\+\[\]|\!\[\]|\+\[\]': 0.2,  # JSFuck
        }

        for pattern, weight in indicators.items():
            if re.search(pattern, self.file_content, re.IGNORECASE):
                score += weight

        return min(score, 1.0)

    def _has_executable_extension(self) -> bool:
        """
        检查是否为可执行文件扩展名
        """
        extension = os.path.splitext(self.file_name)[1].lower()
        return extension in self.EXECUTABLE_EXTENSIONS

    def _is_image(self) -> bool:
        """
        检查是否为图片文件
        """
        return self.mime_type and self.mime_type.startswith('image/')

    def _is_zip(self) -> bool:
        """
        检查是否为ZIP文件
        """
        return zipfile.is_zipfile(self.file_path)

    def _extract_exif(self) -> Optional[Dict[str, Any]]:
        """
        提取EXIF元数据 (图片)
        """
        if not HAS_PIL and not HAS_EXIFREAD:
            return {'error': 'PIL or exifread not installed'}

        exif_data = {}

        # 尝试使用PIL
        if HAS_PIL:
            try:
                image = Image.open(self.file_path)
                exif = image.getexif()

                if exif:
                    for tag_id, value in exif.items():
                        tag = TAGS.get(tag_id, tag_id)
                        # 转换bytes为字符串
                        if isinstance(value, bytes):
                            try:
                                value = value.decode('utf-8')
                            except:
                                value = str(value)
                        exif_data[tag] = value

                # 添加基本信息
                exif_data['Width'] = image.width
                exif_data['Height'] = image.height
                exif_data['Format'] = image.format
                exif_data['Mode'] = image.mode

            except Exception as e:
                exif_data['error'] = str(e)

        # 尝试使用exifread (更详细)
        elif HAS_EXIFREAD:
            try:
                with open(self.file_path, 'rb') as f:
                    tags = exifread.process_file(f)
                    for tag, value in tags.items():
                        exif_data[tag] = str(value)
            except Exception as e:
                exif_data['error'] = str(e)

        return exif_data if exif_data else None

    def _analyze_zip(self) -> Optional[Dict[str, Any]]:
        """
        分析ZIP压缩包
        """
        try:
            with zipfile.ZipFile(self.file_path, 'r') as zf:
                files = []
                contains_eicar = False

                for info in zf.infolist():
                    file_info = {
                        'filename': info.filename,
                        'size': info.file_size,
                        'compressed_size': info.compress_size,
                        'date_time': datetime(*info.date_time).isoformat(),
                        'is_dir': info.is_dir()
                    }

                    # 检查EICAR
                    if not info.is_dir():
                        try:
                            content = zf.read(info.filename)
                            if self.EICAR_SIGNATURE in content:
                                contains_eicar = True
                                file_info['contains_eicar'] = True
                        except:
                            pass

                    files.append(file_info)

                return {
                    'total_files': len(files),
                    'files': files,
                    'contains_eicar': contains_eicar,
                    'compression_ratio': round(
                        sum(f['compressed_size'] for f in files) / max(sum(f['size'] for f in files), 1),
                        4
                    )
                }
        except Exception as e:
            return {'error': str(e)}

    def _assess_risk(self, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        风险评估
        """
        risk_score = 0
        risk_factors = []

        security = analysis_result['security_checks']
        stats = analysis_result['file_stats']

        # EICAR检测
        if security['is_eicar_test']:
            risk_score += 10
            risk_factors.append('EICAR测试病毒签名')

        # 高熵值
        if security['high_entropy']:
            risk_score += 3
            risk_factors.append(f'高熵值检测 ({stats["entropy"]:.2f})')

        # 可执行文件
        if security['contains_executables']:
            risk_score += 4
            risk_factors.append('可执行文件扩展名')

        # 签名不匹配
        if not security['signature_valid']:
            risk_score += 5
            risk_factors.append('文件签名与扩展名不匹配')

        # 活跃内容
        if security['contains_active_content']:
            risk_score += 3
            risk_factors.append('包含活跃内容(脚本)')

        # 可疑字符串
        if security['suspicious_strings']:
            risk_score += len(security['suspicious_strings'])
            risk_factors.append(f'包含可疑字符串: {", ".join(security["suspicious_strings"])}')

        # 混淆检测
        if security['obfuscation_score'] > 0.5:
            risk_score += 4
            risk_factors.append(f'代码混淆检测 ({security["obfuscation_score"]:.2f})')

        # ZIP中的EICAR
        if analysis_result['zip_analysis'] and analysis_result['zip_analysis'].get('contains_eicar'):
            risk_score += 10
            risk_factors.append('ZIP中包含EICAR测试病毒')

        # 风险等级
        if risk_score >= 10:
            risk_level = 'high'
        elif risk_score >= 5:
            risk_level = 'medium'
        elif risk_score > 0:
            risk_level = 'low'
        else:
            risk_level = 'safe'

        return {
            'risk_level': risk_level,
            'risk_score': risk_score,
            'risk_factors': risk_factors,
            'recommendation': self._get_recommendation(risk_level)
        }

    def _get_recommendation(self, risk_level: str) -> str:
        """
        获取安全建议
        """
        recommendations = {
            'high': '⚠️ 高风险文件！不建议打开或执行。请使用专业安全工具进一步分析。',
            'medium': '⚠️ 中等风险文件。建议在隔离环境中打开，并进行进一步检查。',
            'low': 'ℹ️ 低风险文件。发现一些可疑特征，但可能是正常文件。请谨慎使用。',
            'safe': '✅ 未发现明显安全威胁。文件看起来是安全的。'
        }
        return recommendations.get(risk_level, '未知风险等级')

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """
        格式化文件大小
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"

    def to_json(self) -> str:
        """
        将分析结果转换为JSON
        """
        result = self.analyze()
        return json.dumps(result, indent=2, ensure_ascii=False)


def analyze_file(file_path: str) -> Dict[str, Any]:
    """
    便捷函数: 分析文件

    Args:
        file_path: 文件路径

    Returns:
        分析结果字典
    """
    analyzer = FileAnalyzer(file_path)
    return analyzer.analyze()


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("用法: python file_analyzer.py <文件路径>")
        sys.exit(1)

    file_path = sys.argv[1]

    if not os.path.exists(file_path):
        print(f"错误: 文件不存在: {file_path}")
        sys.exit(1)

    print(f"正在分析文件: {file_path}\n")

    analyzer = FileAnalyzer(file_path)
    result = analyzer.analyze()

    # 打印结果
    print("=" * 80)
    print(f"文件分析报告: {analyzer.file_name}")
    print("=" * 80)
    print(f"\n📊 文件统计:")
    for key, value in result['file_stats'].items():
        print(f"  • {key}: {value}")

    print(f"\n🔍 内容分析:")
    for key, value in result['content_analysis'].items():
        print(f"  • {key}: {value}")

    print(f"\n🛡️ 安全检查:")
    for key, value in result['security_checks'].items():
        if isinstance(value, list) and len(value) > 0:
            print(f"  • {key}: {', '.join(value)}")
        elif isinstance(value, bool):
            print(f"  • {key}: {'✓' if value else '✗'}")
        else:
            print(f"  • {key}: {value}")

    print(f"\n⚠️ 风险评估:")
    risk = result['risk_assessment']
    print(f"  • 风险等级: {risk['risk_level'].upper()}")
    print(f"  • 风险分数: {risk['risk_score']}")
    print(f"  • 建议: {risk['recommendation']}")
    if risk['risk_factors']:
        print(f"  • 风险因素:")
        for factor in risk['risk_factors']:
            print(f"    - {factor}")

    print(f"\n🔐 文件哈希:")
    for hash_type, hash_value in result['hashes'].items():
        print(f"  • {hash_type.upper()}: {hash_value}")

    if result['exif_data']:
        print(f"\n📷 EXIF数据:")
        for key, value in list(result['exif_data'].items())[:10]:
            print(f"  • {key}: {value}")

    if result['zip_analysis']:
        print(f"\n📦 ZIP分析:")
        zip_info = result['zip_analysis']
        print(f"  • 文件总数: {zip_info['total_files']}")
        print(f"  • 压缩率: {zip_info['compression_ratio']}")
        print(f"  • 包含EICAR: {'是' if zip_info['contains_eicar'] else '否'}")

    print("\n" + "=" * 80)

    # 保存JSON结果
    json_output = file_path + '.analysis.json'
    with open(json_output, 'w', encoding='utf-8') as f:
        f.write(analyzer.to_json())
    print(f"\n✅ 完整分析结果已保存到: {json_output}")
