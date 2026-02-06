# HIDRS OSINT工具整合指南

本指南介绍如何将HIDRS与主流OSINT工具和平台整合。

## 目录

- [概述](#概述)
- [支持的工具](#支持的工具)
- [Maltego整合](#maltego整合)
- [SpiderFoot整合](#spiderfoot整合)
- [STIX 2.1导出](#stix-21导出)
- [通用REST API](#通用rest-api)
- [Kali Linux安装](#kali-linux安装)
- [常见问题](#常见问题)

## 概述

HIDRS提供多种方式与OSINT生态系统整合：

| 整合方式 | 描述 | 使用场景 |
|---------|------|---------|
| **Maltego Transform** | 将HIDRS数据转换为Maltego图谱 | 可视化关系网络 |
| **SpiderFoot模块** | HIDRS作为SpiderFoot的OSINT模块 | 自动化情报收集 |
| **STIX 2.1导出** | 导出标准威胁情报格式 | 威胁情报平台对接 |
| **REST API** | 通用API接口 | 自定义工具集成 |

## 支持的工具

### 商业工具
- ✅ [Maltego](https://www.maltego.com/) - 关系可视化和数据挖掘
- ✅ [Recorded Future](https://www.recordedfuture.com/) - 威胁情报平台（通过STIX）
- ✅ [Anomali ThreatStream](https://www.anomali.com/) - 威胁情报管理（通过STIX）

### 开源工具
- ✅ [SpiderFoot](https://github.com/smicallef/spiderfoot) - OSINT自动化（200+模块）
- ✅ [OpenCTI](https://www.opencti.io/) - 威胁情报平台（通过STIX）
- ✅ [MISP](https://www.misp-project.org/) - 威胁共享平台（通过STIX）
- ✅ [Kali Linux](https://www.kali.org/) - 渗透测试发行版

### 框架和标准
- ✅ STIX 2.1 - 威胁情报标准
- ✅ OpenCTI API - 威胁情报平台API
- ✅ RESTful API - 通用整合接口

## Maltego整合

### 1. 安装Transform

```bash
# 复制Transform脚本
cp hidrs/integrations/maltego_transform.py /path/to/maltego/transforms/

# 测试Transform
python maltego_transform.py "example.com" search
```

### 2. 配置Maltego

1. 打开Maltego Desktop
2. 进入 **Transforms > New Local Transform**
3. 配置参数：
   - **Display Name**: HIDRS Search
   - **Command**: `python`
   - **Parameters**: `/path/to/maltego_transform.py`
   - **Working Directory**: `/path/to/hidrs`

4. 设置输入实体类型：
   - Domain
   - Email Address
   - Person
   - Phrase

### 3. 使用Transform

1. 在Maltego画布上添加实体（例如：Domain）
2. 右键点击实体 > **Run Transform** > **HIDRS Search**
3. Transform将返回：
   - 相关URL实体
   - 域名实体
   - 带有HLIG Fiedler得分的属性

### 支持的Transform

| Transform | 输入 | 输出 | 描述 |
|-----------|------|------|------|
| `HIDRS Search` | Phrase/Domain | URL, Domain | HIDRS实时搜索 |
| `HIDRS Common Crawl` | Phrase | URL, Document | 历史网页查询 |
| `HIDRS Topology` | Domain | Domain, IP | 网络拓扑分析 |

## SpiderFoot整合

### 1. 安装模块

```bash
# 复制模块到SpiderFoot
cp hidrs/integrations/spiderfoot_module.py /path/to/spiderfoot/modules/sfp_hidrs.py

# 重启SpiderFoot
cd /path/to/spiderfoot
./sf.py -l 0.0.0.0:5001
```

### 2. 配置模块

1. 访问SpiderFoot Web界面：`http://localhost:5001`
2. 进入 **Settings** > **Modules**
3. 找到并启用 **HIDRS** 模块
4. 配置参数：
   - **HIDRS API URL**: `http://localhost:5000`
   - **HIDRS API Key**: (如果启用了认证)
   - **Search Limit**: `50`
   - **Enable Common Crawl**: `True`
   - **Min Fiedler Score**: `0.3`

### 3. 运行扫描

1. 创建新扫描任务
2. 输入目标（域名、IP、邮箱等）
3. 选择 **HIDRS** 模块
4. 开始扫描

### 模块功能

- **域名情报**: 搜索域名相关内容
- **邮箱情报**: 查找邮箱地址关联
- **IP情报**: IP地址历史记录
- **Common Crawl**: 历史网页数据
- **HLIG分析**: 基于拉普拉斯矩阵的相似度分析

## STIX 2.1导出

### 1. Python API使用

```python
from hidrs.integrations.stix_exporter import STIXExporter
from hidrs.realtime_search.search_engine import RealtimeSearchEngine

# 搜索
engine = RealtimeSearchEngine(
    elasticsearch_host='localhost:9200',
    enable_hlig=True
)
results = engine.search(query_text='example', limit=100)

# 导出STIX
exporter = STIXExporter(organization_name="My Org")
bundle = exporter.export_search_results(
    results['results'],
    tlp_level='green',
    confidence=75
)

# 保存文件
exporter.save_to_file(bundle, 'threat_intel.json')
```

### 2. 命令行使用

```bash
# 导出STIX文件
hidrs-export-stix "malware campaign" output.json

# 指定TLP级别
python -m hidrs.integrations.stix_exporter \
    --query "apt29" \
    --tlp amber \
    --output apt29_intel.json
```

### 3. 导入到OpenCTI

```python
from hidrs.integrations.stix_exporter import STIXExporter

exporter = STIXExporter()
bundle = exporter.export_search_results(results)

# 导入到OpenCTI
exporter.import_to_opencti(
    bundle,
    opencti_url='http://localhost:8080',
    opencti_token='your-token-here'
)
```

### 4. 导入到MISP

```bash
# 使用PyMISP
pip install pymisp

python << EOF
from pymisp import PyMISP
import json

# 加载STIX Bundle
with open('threat_intel.json') as f:
    stix_data = json.load(f)

# 连接MISP
misp = PyMISP('https://misp.example.com', 'your-api-key')

# 导入STIX
misp.upload_stix(json.dumps(stix_data))
EOF
```

### STIX对象映射

| HIDRS数据 | STIX对象 | 属性 |
|-----------|----------|------|
| URL | `ObservedData` + `URL` | value, title |
| Domain | `ObservedData` + `DomainName` | value |
| HLIG Score高 | `Indicator` | pattern, confidence |
| Common Crawl | `ObservedData` + 自定义 | crawl_id, warc_file |
| Network Topology | 自定义对象 | fiedler_value, node_count |

## 通用REST API

### 1. 启动API服务器

```bash
# 生成API密钥
python -m hidrs.integrations.osint_api genkey --name "my-tool"
# 输出: hidrs_xxxxxxxxxxxxxxxxxxxxx

# 启动服务器
python -m hidrs.integrations.osint_api run --host 0.0.0.0 --port 8080

# 或使用systemd（Kali安装后）
systemctl start hidrs-api
```

### 2. API端点

#### 健康检查
```bash
curl http://localhost:8080/api/v1/health
```

#### 搜索
```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:8080/api/v1/search?q=example&limit=20"

# 指定数据源
curl -H "X-API-Key: your-key" \
  "http://localhost:8080/api/v1/search?q=example&source=commoncrawl"
```

#### 域名情报
```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:8080/api/v1/domain/example.com"
```

#### IP情报
```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:8080/api/v1/ip/1.2.3.4"
```

#### 网络拓扑
```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:8080/api/v1/topology"
```

#### STIX导出
```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:8080/api/v1/export/stix?q=example&tlp=green" \
  -o threat_intel.json
```

### 3. Python客户端示例

```python
import requests

API_URL = 'http://localhost:8080'
API_KEY = 'your-hidrs-api-key'

headers = {'X-API-Key': API_KEY}

# 搜索
response = requests.get(
    f'{API_URL}/api/v1/search',
    params={'q': 'example', 'limit': 20},
    headers=headers
)

results = response.json()
print(f"找到 {results['total']} 个结果")

for result in results['results']:
    print(f"- {result['title']}: {result['url']}")
```

### 4. 速率限制

默认速率限制：**60请求/分钟**

响应头：
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
```

超过限制时返回：
```json
{
  "error": "Rate limit exceeded",
  "retry_after": 60
}
```

## Kali Linux安装

### 方法1：一键安装

```bash
curl -sSL https://raw.githubusercontent.com/your-repo/hidrs/main/kali_install.sh | sudo bash
```

### 方法2：手动安装

```bash
# 下载安装脚本
wget https://raw.githubusercontent.com/your-repo/hidrs/main/kali_install.sh
chmod +x kali_install.sh

# 运行安装
sudo ./kali_install.sh
```

### 安装后配置

```bash
# 生成API密钥
hidrs-api genkey my-first-key

# 启动服务
systemctl start hidrs
systemctl start hidrs-api

# 设置开机自启
systemctl enable hidrs
systemctl enable hidrs-api

# 检查状态
systemctl status hidrs
systemctl status hidrs-api
```

### Kali工具快捷方式

安装完成后，HIDRS将作为Kali工具可用：

```bash
# 快速搜索
hidrs-search "example query"

# 导出STIX
hidrs-export-stix "apt campaign" output.json

# 管理API服务
hidrs-api start
hidrs-api stop
hidrs-api genkey mykey
```

## 整合示例

### 示例1：Maltego + SpiderFoot工作流

```
1. SpiderFoot自动收集目标情报
   ↓
2. HIDRS模块提供HLIG相似度分析
   ↓
3. 将结果导出为STIX
   ↓
4. 在Maltego中可视化关系网络
```

### 示例2：威胁情报自动化流程

```python
from hidrs.integrations.stix_exporter import STIXExporter
from hidrs.realtime_search.search_engine import RealtimeSearchEngine

# 1. HIDRS搜索
engine = RealtimeSearchEngine(elasticsearch_host='localhost:9200')
results = engine.search(query_text='malware campaign', limit=100)

# 2. 导出STIX
exporter = STIXExporter(organization_name="SOC Team")
bundle = exporter.export_search_results(
    results['results'],
    tlp_level='amber',
    confidence=80
)

# 3. 推送到OpenCTI
exporter.import_to_opencti(
    bundle,
    opencti_url='https://opencti.internal',
    opencti_token='your-token'
)

# 4. 同时推送到MISP
from pymisp import PyMISP
misp = PyMISP('https://misp.internal', 'api-key')
misp.upload_stix(bundle.serialize())
```

### 示例3：Kali Linux渗透测试工作流

```bash
# 1. 使用HIDRS收集目标信息
hidrs-search "target.com" > recon.json

# 2. 结合Nmap扫描
nmap -sV target.com -oX nmap.xml

# 3. 使用其他Kali工具
theHarvester -d target.com -b all

# 4. 汇总情报并导出STIX
hidrs-export-stix "target.com" threat_profile.json

# 5. 导入到威胁情报平台
curl -X POST https://opencti.internal/api/import \
  -H "Authorization: Bearer token" \
  -F "file=@threat_profile.json"
```

## 常见问题

### Q: HIDRS API可以与哪些SIEM整合？

A: HIDRS API可以与任何支持REST API的SIEM整合，包括：
- Splunk (使用HTTP Event Collector)
- ELK Stack (Logstash HTTP输入)
- QRadar (Universal REST API)
- Sentinel (Data Connectors)

### Q: 如何在企业环境中部署HIDRS？

A: 推荐配置：
1. 使用Nginx作为反向代理和负载均衡
2. 启用API密钥认证
3. 配置适当的速率限制
4. 使用HTTPS加密传输
5. 集成到企业SSO（通过OAuth2）

### Q: STIX导出的可信度如何设置？

A: 可信度设置建议：
- 90-100: 人工验证的情报
- 70-90: HLIG高得分结果（Fiedler > 0.7）
- 50-70: 中等得分结果
- 30-50: 低得分但可能相关
- < 30: 仅供参考

### Q: 如何自定义SpiderFoot模块？

A: 编辑 `sfp_hidrs.py`:
```python
class sfp_hidrs(SpiderFootPlugin):
    opts = {
        'hidrs_api_url': 'http://your-server:5000',
        'search_limit': 100,  # 增加结果数量
        'min_fiedler_score': 0.5,  # 提高质量阈值
    }
```

## 参考资料

### 官方文档
- [STIX 2.1规范](https://docs.oasis-open.org/cti/stix/v2.1/stix-v2.1.html)
- [OpenCTI文档](https://docs.opencti.io/)
- [Maltego开发文档](https://docs.maltego.com/)
- [SpiderFoot模块开发](https://github.com/smicallef/spiderfoot/wiki/Developing-modules)

### 相关项目
- [MISP Project](https://www.misp-project.org/)
- [TheHive Project](https://thehive-project.org/)
- [OASIS CTI TC](https://www.oasis-open.org/committees/tc_home.php?wg_abbrev=cti)

---

**需要帮助？**
- GitHub Issues: https://github.com/your-repo/hidrs/issues
- 文档: https://hidrs-docs.example.com
- 邮件: support@example.com
