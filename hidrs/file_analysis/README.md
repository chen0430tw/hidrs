# HIDRS文件分析模块

基于[Xkeystroke](https://github.com/AIOSINT/Xkeystroke)项目改编的Python文件分析模块，为HIDRS爬虫系统提供深度文件分析和安全检测功能。

## 📋 功能特性

### 核心功能

1. **文件哈希计算**
   - MD5, SHA1, SHA256, SHA512
   - 用于文件指纹识别和去重

2. **熵值分析**
   - 计算文件随机性 (0-8)
   - 检测加密或压缩内容
   - 高熵值 (>7.5) 可能表示恶意混淆

3. **文件签名验证**
   - 基于魔术数字 (Magic Numbers)
   - 检测文件扩展名伪装
   - 支持30+常见文件格式

4. **EXIF元数据提取**
   - 支持图片文件 (JPEG, PNG等)
   - 提取GPS位置、相机信息、拍摄时间
   - 可用于图片溯源和地理定位

5. **安全模式检测**
   - EICAR测试病毒检测
   - 活跃内容检测 (脚本、eval等)
   - URL和Base64编码检测
   - 可疑字符串识别 (password, sql, exec等)
   - 代码混淆检测 (JSFuck, 长字符串等)

6. **ZIP/压缩包分析**
   - 递归扫描压缩包内容
   - 检测嵌套EICAR病毒
   - 计算压缩率和文件列表

7. **风险评估**
   - 4级风险等级: safe, low, medium, high
   - 风险分数计算
   - 具体风险因素列表
   - 安全建议

### 爬虫集成功能

- 自动分析爬取的文件
- MongoDB存储分析结果
- 高风险文件警报系统
- 自动删除高风险文件 (可选)
- 通过哈希值查重
- 批量分析
- 统计报表

## 📦 安装依赖

### 必需依赖

```bash
pip install pymongo  # MongoDB客户端
```

### 可选依赖 (推荐)

```bash
# 图片EXIF提取
pip install Pillow exifread
```

## 🚀 使用方法

### 方法1: 独立使用

```python
from hidrs.file_analysis import FileAnalyzer, analyze_file

# 简单分析
result = analyze_file('/path/to/file.pdf')
print(result['risk_assessment']['risk_level'])  # safe, low, medium, high

# 完整分析
analyzer = FileAnalyzer('/path/to/suspicious.exe')
result = analyzer.analyze()

print(f"文件大小: {result['file_stats']['size_formatted']}")
print(f"熵值: {result['file_stats']['entropy']}")
print(f"风险等级: {result['risk_assessment']['risk_level']}")
print(f"风险因素: {result['risk_assessment']['risk_factors']}")
print(f"SHA256: {result['hashes']['sha256']}")

# 保存为JSON
json_str = analyzer.to_json()
with open('analysis_result.json', 'w') as f:
    f.write(json_str)
```

### 方法2: 命令行使用

```bash
# 分析单个文件
python -m hidrs.file_analysis.file_analyzer /path/to/file.pdf

# 结果会保存为 file.pdf.analysis.json
```

### 方法3: 集成到HIDRS爬虫

```python
from hidrs.file_analysis.crawler_integration import CrawlerFileAnalyzer

# 初始化文件分析器
file_analyzer = CrawlerFileAnalyzer(
    mongodb_uri='mongodb://localhost:27017/',
    db_name='hidrs_db',
    auto_delete_high_risk=False  # 是否自动删除高风险文件
)

# 分析单个文件
result = file_analyzer.analyze_and_store(
    file_path='/path/to/downloaded_file.pdf',
    metadata={
        'source_url': 'https://example.com/file.pdf',
        'crawler': 'wikipedia',
        'timestamp': '2026-02-04T12:00:00'
    }
)

# 批量分析
file_paths = ['/path/to/file1.pdf', '/path/to/file2.exe']
results = file_analyzer.batch_analyze(file_paths)

# 获取高风险文件
high_risk_files = file_analyzer.get_high_risk_files(limit=10)
for alert in high_risk_files:
    print(f"⚠️ {alert['file_name']} - {alert['risk_level']}")

# 通过哈希查询
result = file_analyzer.query_by_hash('abc123...', hash_type='sha256')

# 获取统计信息
stats = file_analyzer.get_statistics()
print(f"总分析文件数: {stats['total_files_analyzed']}")
print(f"高风险警报数: {stats['high_risk_alerts']}")

file_analyzer.close()
```

### 方法4: 集成到分布式爬虫

```python
from hidrs.data_acquisition.distributed_crawler import DistributedCrawler
from hidrs.file_analysis.crawler_integration import integrate_with_crawler

# 初始化爬虫
crawler = DistributedCrawler(config)

# 集成文件分析器
file_analyzer = integrate_with_crawler(
    crawler,
    mongodb_uri='mongodb://localhost:27017/',
    auto_delete_high_risk=True  # 自动删除高风险文件
)

# 爬虫下载文件后自动分析
crawler.start()

# 在爬虫的文件下载回调中调用:
def on_file_downloaded(file_path, url):
    result = file_analyzer.analyze_and_store(
        file_path,
        metadata={'source_url': url}
    )
    if result['risk_assessment']['risk_level'] == 'high':
        # 触发警报
        send_alert(f"高风险文件检测: {file_path}")
```

## 📊 分析结果结构

```python
{
    "file_stats": {
        "size": 1024,
        "size_formatted": "1.00 KB",
        "type": "text/plain",
        "encoding": "UTF-8",
        "created": "2026-02-04T12:00:00",
        "modified": "2026-02-04T12:00:00",
        "accessed": "2026-02-04T12:00:00",
        "permissions": "644",
        "is_executable": False,
        "entropy": 5.234,
        "is_binary": False,
        "signature_valid": True
    },
    "content_analysis": {
        "file_type": "text/plain",
        "is_text": True,
        "line_count": 100,
        "character_count": 5000,
        "word_count": 800,
        "average_line_length": 50.0,
        "non_printable_chars": 0
    },
    "security_checks": {
        "is_eicar_test": False,
        "malicious_patterns": False,
        "contains_active_content": False,
        "contains_urls": True,
        "contains_base64": False,
        "contains_executables": False,
        "contains_compressed_files": False,
        "high_entropy": False,
        "signature_valid": True,
        "suspicious_strings": ["password", "eval"],
        "obfuscation_score": 0.2
    },
    "hashes": {
        "md5": "abc123...",
        "sha1": "def456...",
        "sha256": "ghi789...",
        "sha512": "jkl012..."
    },
    "exif_data": {
        "Make": "Canon",
        "Model": "EOS 5D",
        "GPSLatitude": 37.7749,
        "GPSLongitude": -122.4194
    },
    "zip_analysis": {
        "total_files": 5,
        "files": [...],
        "contains_eicar": False,
        "compression_ratio": 0.5
    },
    "risk_assessment": {
        "risk_level": "low",  // safe, low, medium, high
        "risk_score": 2,
        "risk_factors": [
            "包含可疑字符串: password, eval"
        ],
        "recommendation": "ℹ️ 低风险文件。发现一些可疑特征，但可能是正常文件。请谨慎使用。"
    },
    "timestamp": "2026-02-04T12:00:00"
}
```

## 🛡️ 风险评估规则

### 风险分数计算

| 检测项 | 分数 |
|--------|------|
| EICAR测试病毒 | +10 |
| 文件签名不匹配 | +5 |
| 可执行文件扩展名 | +4 |
| 代码混淆 (>0.5) | +4 |
| 高熵值 (>7.5) | +3 |
| 活跃内容(脚本) | +3 |
| 每个可疑字符串 | +1 |

### 风险等级

- **safe** (0分): 未发现威胁
- **low** (1-4分): 可疑特征较少
- **medium** (5-9分): 中等风险
- **high** (≥10分): 高风险文件

## 🔍 支持的文件类型

### 文件签名检测

支持以下文件格式的魔术数字验证:

- **图片**: JPG, PNG, GIF
- **文档**: PDF
- **压缩包**: ZIP, RAR, 7Z, TAR, GZ, BZ2
- **可执行文件**: EXE, ELF
- **音视频**: MP3, MP4, AVI, WAV

### EXIF元数据提取

- JPEG
- PNG
- TIFF
- BMP

## 📈 MongoDB数据结构

### file_analysis集合

```javascript
{
    _id: ObjectId("..."),
    file_path: "/path/to/file.pdf",
    file_stats: {...},
    content_analysis: {...},
    security_checks: {...},
    hashes: {...},
    risk_assessment: {...},
    crawler_metadata: {
        source_url: "https://example.com/file.pdf",
        crawler: "wikipedia",
        timestamp: "2026-02-04T12:00:00"
    },
    timestamp: ISODate("2026-02-04T12:00:00")
}
```

**索引**:
- `file_path` (唯一索引)
- `risk_level + timestamp` (复合索引)
- `hashes.sha256` (单字段索引)

### high_risk_alerts集合

```javascript
{
    _id: ObjectId("..."),
    file_path: "/path/to/suspicious.exe",
    file_name: "suspicious.exe",
    risk_level: "high",
    risk_score: 15,
    risk_factors: ["EICAR测试病毒签名", "高熵值检测 (7.89)"],
    recommendation: "⚠️ 高风险文件！不建议打开或执行。",
    file_hash_sha256: "abc123...",
    timestamp: ISODate("2026-02-04T12:00:00"),
    handled: false,
    action_taken: null  // "deleted", "quarantined", etc.
}
```

**索引**:
- `timestamp` (降序)
- `file_path` (单字段索引)

## 🔧 配置选项

### CrawlerFileAnalyzer配置

```python
file_analyzer = CrawlerFileAnalyzer(
    mongodb_uri='mongodb://localhost:27017/',  # MongoDB连接URI
    db_name='hidrs_db',                        # 数据库名称
    auto_delete_high_risk=False                # 是否自动删除高风险文件
)
```

### 环境变量

```bash
export MONGODB_URI="mongodb://localhost:27017/"
export HIDRS_DB_NAME="hidrs_db"
export AUTO_DELETE_HIGH_RISK="false"
```

## 📝 使用示例

### 示例1: 分析EICAR测试病毒

```python
# 创建EICAR测试文件
eicar = b'X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'
with open('eicar.txt', 'wb') as f:
    f.write(eicar)

# 分析
result = analyze_file('eicar.txt')
print(result['security_checks']['is_eicar_test'])  # True
print(result['risk_assessment']['risk_level'])     # high
print(result['risk_assessment']['risk_score'])     # 10
```

### 示例2: 批量分析下载文件

```python
import os
from hidrs.file_analysis.crawler_integration import CrawlerFileAnalyzer

file_analyzer = CrawlerFileAnalyzer()

# 扫描下载目录
download_dir = '/path/to/downloads'
file_paths = [
    os.path.join(download_dir, f)
    for f in os.listdir(download_dir)
    if os.path.isfile(os.path.join(download_dir, f))
]

# 批量分析
results = file_analyzer.batch_analyze(file_paths)

# 统计
high_risk_count = sum(1 for r in results if r.get('risk_assessment', {}).get('risk_level') == 'high')
print(f"高风险文件数: {high_risk_count}/{len(results)}")

file_analyzer.close()
```

### 示例3: 监控高风险文件

```python
from hidrs.file_analysis.crawler_integration import CrawlerFileAnalyzer
import time

file_analyzer = CrawlerFileAnalyzer()

def monitor_high_risk_files():
    while True:
        # 获取未处理的高风险警报
        alerts = file_analyzer.high_risk_alerts.find({'handled': False})

        for alert in alerts:
            print(f"⚠️ 高风险文件: {alert['file_name']}")
            print(f"   风险等级: {alert['risk_level']}")
            print(f"   风险因素: {', '.join(alert['risk_factors'])}")

            # 标记为已处理
            file_analyzer.high_risk_alerts.update_one(
                {'_id': alert['_id']},
                {'$set': {'handled': True}}
            )

        time.sleep(60)  # 每分钟检查一次

monitor_high_risk_files()
```

## 🎯 与Xkeystroke的对比

| 特性 | Xkeystroke (Node.js) | HIDRS Module (Python) |
|------|----------------------|----------------------|
| 文件哈希 | ✅ MD5, SHA1, SHA256 | ✅ MD5, SHA1, SHA256, SHA512 |
| 熵值分析 | ✅ | ✅ |
| 文件签名 | ✅ 基础 | ✅ 扩展 (30+格式) |
| EXIF提取 | ✅ exif-reader | ✅ PIL + exifread |
| EICAR检测 | ✅ | ✅ |
| ZIP分析 | ✅ yauzl | ✅ zipfile |
| 安全检测 | ✅ | ✅ 增强 |
| 代码混淆检测 | ✅ | ✅ |
| 数据库存储 | ❌ | ✅ MongoDB |
| 爬虫集成 | ❌ | ✅ |
| 批量分析 | ❌ | ✅ |
| 风险评估 | ✅ 基础 | ✅ 增强 |

## 🔒 安全注意事项

1. **高风险文件处理**
   - 建议在隔离环境中分析高风险文件
   - 启用 `auto_delete_high_risk` 前请确保有备份

2. **EICAR测试**
   - EICAR是国际标准测试病毒签名
   - 用于测试杀毒软件，非真实病毒
   - 某些杀毒软件可能会拦截

3. **性能考虑**
   - 大文件分析可能耗时较长
   - 建议设置文件大小限制
   - 使用批量分析时注意内存占用

4. **隐私保护**
   - EXIF数据可能包含敏感信息 (GPS位置)
   - 建议脱敏处理后再存储

## 📚 参考资料

- [Xkeystroke项目](https://github.com/AIOSINT/Xkeystroke)
- [文件签名列表](https://en.wikipedia.org/wiki/List_of_file_signatures)
- [EICAR测试文件](https://www.eicar.org/download-anti-malware-testfile/)
- [熵值计算](https://en.wikipedia.org/wiki/Entropy_(information_theory))
- [EXIF标准](https://www.exif.org/)

## 📞 支持

如有问题或建议，请提交Issue或联系HIDRS团队。

---

**版本**: 1.0.0
**更新日期**: 2026-02-04
**作者**: HIDRS Team (基于Xkeystroke改编)
