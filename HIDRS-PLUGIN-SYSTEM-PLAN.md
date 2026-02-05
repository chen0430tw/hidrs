# HIDRS插件系统规划：设备扫描与暗网功能

## 📋 执行摘要

本文档规划HIDRS的**插件化架构**，通过插件方式扩展设备扫描和暗网功能，保持核心系统的合法性和简洁性，同时提供高级OSINT能力。

**设计理念**：
- 核心系统保持合法、简洁、开源
- 高级功能通过插件按需加载
- 插件需要用户明确授权和配置
- 清晰的责任边界和使用条款

---

## 🎯 插件系统总体架构

### 核心架构图

```
┌─────────────────────────────────────────────────┐
│              HIDRS Core System                  │
│  • 拉普拉斯谱分析                                │
│  • 全息映射                                      │
│  • 多平台爬虫（公开Web）                          │
│  • 决策反馈                                      │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│            Plugin Manager（插件管理器）           │
│  • 插件注册与发现                                 │
│  • 生命周期管理（加载/卸载/更新）                  │
│  • 权限管理与沙箱                                 │
│  • 配置管理                                      │
└──────────────────┬──────────────────────────────┘
                   │
        ┌──────────┴──────────┬──────────┐
        ▼                     ▼          ▼
┌──────────────┐    ┌──────────────┐  ┌──────────────┐
│Device Scanner│    │ DarkWeb      │  │Third-party   │
│   Plugin     │    │ Crawler      │  │ API Plugin   │
│              │    │ Plugin       │  │              │
│• Shodan API  │    │• Tor支持     │  │• VirusTotal  │
│• Censys API  │    │• I2P支持     │  │• AlienVault  │
│• ZoomEye     │    │• Onion爬虫   │  │• AbuseIPDB   │
└──────────────┘    └──────────────┘  └──────────────┘
```

### 插件系统目录结构

```
hidrs/
├── core/                      # 核心系统（不变）
│   ├── crawler.py
│   ├── search_engine.py
│   └── ...
├── plugins/                   # 插件目录
│   ├── __init__.py
│   ├── base.py               # 插件基类
│   ├── manager.py            # 插件管理器
│   ├── device_scanner/       # 设备扫描插件
│   │   ├── __init__.py
│   │   ├── plugin.py
│   │   ├── shodan_client.py
│   │   ├── censys_client.py
│   │   └── config.yaml
│   ├── darkweb_crawler/      # 暗网爬虫插件
│   │   ├── __init__.py
│   │   ├── plugin.py
│   │   ├── tor_crawler.py
│   │   ├── i2p_crawler.py
│   │   └── config.yaml
│   └── api_integrations/     # 第三方API插件
│       ├── virustotal.py
│       ├── alienvault.py
│       └── config.yaml
├── plugin_configs/           # 用户配置（不提交到Git）
│   ├── device_scanner.yaml
│   └── darkweb_crawler.yaml
└── docs/
    └── plugin_development.md # 插件开发文档
```

---

## 🔌 插件1: 设备扫描插件（Device Scanner Plugin）

### 功能概述

集成Shodan、Censys、ZoomEye等设备搜索引擎API，提供互联网设备扫描和漏洞情报。

### 支持的API

| API服务 | 功能 | 费用 | 优先级 |
|---------|------|------|--------|
| **Shodan** | IoT设备、开放端口、漏洞 | 免费/付费 | ⭐⭐⭐ 高 |
| **Censys** | 证书、IP、域名扫描 | 免费/付费 | ⭐⭐⭐ 高 |
| **ZoomEye** | 设备指纹、漏洞情报 | 免费/付费 | ⭐⭐ 中 |
| **FOFA** | 中国版Shodan | 付费 | ⭐⭐ 中 |
| **BinaryEdge** | 威胁情报、漏洞扫描 | 付费 | ⭐ 低 |

### 技术实现

#### 插件基类

```python
# plugins/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any, List

class HIDRSPlugin(ABC):
    """HIDRS插件基类"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get('enabled', False)
        self.name = self.__class__.__name__

    @abstractmethod
    def initialize(self) -> bool:
        """插件初始化"""
        pass

    @abstractmethod
    def execute(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """执行查询"""
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """验证配置"""
        pass

    def get_capabilities(self) -> List[str]:
        """返回插件能力列表"""
        return []

    def shutdown(self):
        """插件清理"""
        pass
```

#### 设备扫描插件实现

```python
# plugins/device_scanner/plugin.py
import shodan
import censys.search
from plugins.base import HIDRSPlugin

class DeviceScannerPlugin(HIDRSPlugin):
    """设备扫描插件"""

    REQUIRED_PERMISSIONS = [
        'network.scan',
        'api.external',
        'data.sensitive'
    ]

    def __init__(self, config):
        super().__init__(config)
        self.shodan_client = None
        self.censys_client = None

    def initialize(self) -> bool:
        """初始化API客户端"""
        if not self.validate_config():
            raise ValueError("Invalid plugin configuration")

        # 初始化Shodan
        if self.config.get('shodan', {}).get('api_key'):
            self.shodan_client = shodan.Shodan(
                self.config['shodan']['api_key']
            )
            logger.info("Shodan API initialized")

        # 初始化Censys
        if self.config.get('censys', {}).get('api_id'):
            self.censys_client = censys.search.CensysHosts(
                api_id=self.config['censys']['api_id'],
                api_secret=self.config['censys']['api_secret']
            )
            logger.info("Censys API initialized")

        return True

    def execute(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """执行设备搜索"""
        results = []
        search_type = kwargs.get('search_type', 'shodan')

        if search_type == 'shodan' and self.shodan_client:
            results.extend(self._search_shodan(query, **kwargs))

        if search_type == 'censys' and self.censys_client:
            results.extend(self._search_censys(query, **kwargs))

        # 结果标准化
        return self._normalize_results(results)

    def _search_shodan(self, query: str, **kwargs) -> List[Dict]:
        """Shodan搜索"""
        try:
            # Shodan查询
            results = self.shodan_client.search(
                query,
                limit=kwargs.get('limit', 100)
            )

            devices = []
            for result in results['matches']:
                devices.append({
                    'ip': result['ip_str'],
                    'port': result['port'],
                    'org': result.get('org', 'Unknown'),
                    'os': result.get('os', 'Unknown'),
                    'hostnames': result.get('hostnames', []),
                    'location': {
                        'country': result.get('location', {}).get('country_name'),
                        'city': result.get('location', {}).get('city'),
                    },
                    'vulns': result.get('vulns', []),
                    'services': result.get('data', ''),
                    'timestamp': result.get('timestamp'),
                    'source': 'shodan'
                })

            return devices
        except shodan.APIError as e:
            logger.error(f"Shodan API error: {e}")
            return []

    def _search_censys(self, query: str, **kwargs) -> List[Dict]:
        """Censys搜索"""
        try:
            results = []
            for page in self.censys_client.search(query, per_page=100):
                for host in page:
                    results.append({
                        'ip': host['ip'],
                        'services': host.get('services', []),
                        'protocols': host.get('protocols', []),
                        'location': host.get('location', {}),
                        'autonomous_system': host.get('autonomous_system', {}),
                        'source': 'censys'
                    })
            return results
        except Exception as e:
            logger.error(f"Censys API error: {e}")
            return []

    def _normalize_results(self, results: List[Dict]) -> List[Dict]:
        """标准化不同API的结果格式"""
        normalized = []
        for result in results:
            normalized.append({
                'type': 'device',
                'ip': result.get('ip'),
                'port': result.get('port'),
                'organization': result.get('org') or result.get('autonomous_system', {}).get('name'),
                'location': result.get('location'),
                'vulnerabilities': result.get('vulns', []),
                'services': result.get('services', []),
                'metadata': {
                    'source': result.get('source'),
                    'timestamp': result.get('timestamp'),
                    'raw_data': result
                }
            })
        return normalized

    def validate_config(self) -> bool:
        """验证配置"""
        # 至少需要一个API密钥
        has_shodan = bool(self.config.get('shodan', {}).get('api_key'))
        has_censys = bool(self.config.get('censys', {}).get('api_id'))
        return has_shodan or has_censys

    def get_capabilities(self) -> List[str]:
        """返回插件能力"""
        capabilities = ['device_search', 'vulnerability_scan']
        if self.shodan_client:
            capabilities.append('shodan')
        if self.censys_client:
            capabilities.append('censys')
        return capabilities
```

#### 配置文件

```yaml
# plugins/device_scanner/config.yaml
name: DeviceScannerPlugin
version: 1.0.0
enabled: false  # 默认禁用，需要用户主动启用
description: "设备扫描插件，集成Shodan、Censys等API"

permissions:
  - network.scan
  - api.external
  - data.sensitive

dependencies:
  - shodan>=1.28.0
  - censys>=2.1.0

# 用户配置（需要在plugin_configs/中创建）
shodan:
  api_key: ""  # 用户需要填写
  rate_limit: 100
  timeout: 30

censys:
  api_id: ""
  api_secret: ""
  rate_limit: 50

zoomeye:
  api_key: ""
  enabled: false

# 使用限制
usage_limits:
  max_requests_per_hour: 100
  max_results_per_query: 1000

# 合规性
compliance:
  require_user_consent: true
  log_all_queries: true
  data_retention_days: 30
```

#### Flask API端点

```python
# backend/crawler_server.py
@app.route('/api/plugins/device-scanner/search', methods=['POST'])
def device_scanner_search():
    """设备扫描API"""
    # 检查插件是否启用
    if not plugin_manager.is_enabled('DeviceScannerPlugin'):
        return jsonify({'error': 'Device scanner plugin not enabled'}), 403

    # 检查用户权限
    if not check_user_permission('network.scan'):
        return jsonify({'error': 'Permission denied'}), 403

    data = request.json
    query = data.get('query')
    search_type = data.get('search_type', 'shodan')
    limit = data.get('limit', 100)

    # 记录查询日志（合规性要求）
    logger.info(f"Device scan query: {query}, user: {get_current_user()}")

    try:
        plugin = plugin_manager.get_plugin('DeviceScannerPlugin')
        results = plugin.execute(
            query=query,
            search_type=search_type,
            limit=limit
        )

        return jsonify({
            'success': True,
            'query': query,
            'count': len(results),
            'results': results,
            'source': search_type
        })
    except Exception as e:
        logger.error(f"Device scanner error: {e}")
        return jsonify({'error': str(e)}), 500
```

---

## 🕸️ 插件2: 暗网爬虫插件（DarkWeb Crawler Plugin）

### 功能概述

支持Tor、I2P等匿名网络的爬虫功能，用于暗网情报收集（需严格合规审查）。

### 支持的匿名网络

| 网络类型 | 协议 | 用途 | 实现难度 |
|---------|------|------|---------|
| **Tor** | .onion | 暗网市场、论坛 | 中 |
| **I2P** | .i2p | P2P匿名网络 | 高 |
| **Freenet** | - | 审查抵抗 | 高 |

### 技术实现

#### Tor爬虫实现

```python
# plugins/darkweb_crawler/tor_crawler.py
import requests
from stem import Signal
from stem.control import Controller
import socks
import socket

class TorCrawler:
    """Tor网络爬虫"""

    def __init__(self, config):
        self.config = config
        self.tor_proxy = config.get('tor_proxy', 'socks5://127.0.0.1:9050')
        self.control_port = config.get('control_port', 9051)
        self.control_password = config.get('control_password', '')

    def initialize(self) -> bool:
        """初始化Tor连接"""
        # 设置SOCKS代理
        socks.set_default_proxy(
            socks.SOCKS5,
            "127.0.0.1",
            9050
        )
        socket.socket = socks.socksocket

        # 测试Tor连接
        try:
            response = requests.get(
                'https://check.torproject.org/api/ip',
                timeout=30
            )
            data = response.json()
            if data.get('IsTor'):
                logger.info(f"Tor connection established. IP: {data['IP']}")
                return True
        except Exception as e:
            logger.error(f"Tor connection failed: {e}")
            return False

    def crawl_onion_site(self, onion_url: str) -> Dict[str, Any]:
        """爬取.onion网站"""
        try:
            # 配置请求
            session = requests.Session()
            session.proxies = {
                'http': self.tor_proxy,
                'https': self.tor_proxy
            }

            # 发起请求
            response = session.get(
                onion_url,
                timeout=60,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; rv:91.0) Gecko/20100101 Firefox/91.0'
                }
            )

            return {
                'url': onion_url,
                'status_code': response.status_code,
                'content': response.text,
                'headers': dict(response.headers),
                'timestamp': datetime.now().isoformat(),
                'network': 'tor'
            }
        except Exception as e:
            logger.error(f"Failed to crawl {onion_url}: {e}")
            return {
                'url': onion_url,
                'error': str(e),
                'network': 'tor'
            }

    def renew_tor_identity(self):
        """更换Tor身份（IP地址）"""
        try:
            with Controller.from_port(port=self.control_port) as controller:
                controller.authenticate(password=self.control_password)
                controller.signal(Signal.NEWNYM)
                time.sleep(5)  # 等待新电路建立
                logger.info("Tor identity renewed")
        except Exception as e:
            logger.error(f"Failed to renew Tor identity: {e}")
```

#### 暗网爬虫插件主类

```python
# plugins/darkweb_crawler/plugin.py
from plugins.base import HIDRSPlugin
from .tor_crawler import TorCrawler

class DarkWebCrawlerPlugin(HIDRSPlugin):
    """暗网爬虫插件"""

    REQUIRED_PERMISSIONS = [
        'network.anonymous',
        'crawler.darkweb',
        'data.sensitive'
    ]

    # 合规性警告
    COMPLIANCE_WARNING = """
    ⚠️ 暗网爬虫插件仅用于合法的安全研究和威胁情报收集。
    使用本插件前，请确保：
    1. 您有合法的研究目的
    2. 遵守当地法律法规
    3. 不访问非法内容（儿童色情、毒品交易等）
    4. 不参与非法活动

    使用本插件即表示您同意上述条款。
    """

    def __init__(self, config):
        super().__init__(config)
        self.tor_crawler = None
        self.user_consent = config.get('user_consent', False)

    def initialize(self) -> bool:
        """初始化暗网爬虫"""
        # 强制要求用户同意
        if not self.user_consent:
            raise ValueError(
                "DarkWeb Crawler requires explicit user consent. "
                "Set 'user_consent: true' in config after reading the terms."
            )

        # 显示合规性警告
        logger.warning(self.COMPLIANCE_WARNING)

        # 初始化Tor爬虫
        if self.config.get('tor', {}).get('enabled'):
            self.tor_crawler = TorCrawler(self.config['tor'])
            if not self.tor_crawler.initialize():
                logger.error("Tor initialization failed")
                return False

        return True

    def execute(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """执行暗网爬取"""
        network = kwargs.get('network', 'tor')

        # 验证URL格式
        if network == 'tor' and not query.endswith('.onion'):
            raise ValueError("Invalid Tor URL. Must end with .onion")

        # 记录合规日志
        logger.info(f"DarkWeb crawl: {query}, network: {network}, user: {get_current_user()}")

        results = []

        if network == 'tor' and self.tor_crawler:
            result = self.tor_crawler.crawl_onion_site(query)
            results.append(result)

            # 定期更换身份
            if kwargs.get('renew_identity', True):
                self.tor_crawler.renew_tor_identity()

        return results

    def validate_config(self) -> bool:
        """验证配置"""
        # 必须明确启用并同意条款
        return (
            self.config.get('enabled', False) and
            self.config.get('user_consent', False)
        )

    def get_capabilities(self) -> List[str]:
        """返回插件能力"""
        capabilities = []
        if self.tor_crawler:
            capabilities.append('tor')
        return capabilities
```

#### 配置文件

```yaml
# plugins/darkweb_crawler/config.yaml
name: DarkWebCrawlerPlugin
version: 1.0.0
enabled: false  # 默认禁用
description: "暗网爬虫插件，支持Tor、I2P网络"

permissions:
  - network.anonymous
  - crawler.darkweb
  - data.sensitive

dependencies:
  - stem>=1.8.0
  - PySocks>=1.7.1
  - requests[socks]>=2.28.0

# 用户必须主动同意合规条款
user_consent: false  # 用户需要改为true

tor:
  enabled: false
  proxy: "socks5://127.0.0.1:9050"
  control_port: 9051
  control_password: ""  # Tor控制密码
  renew_identity_interval: 300  # 5分钟

i2p:
  enabled: false
  proxy: "http://127.0.0.1:4444"

# 安全限制
security:
  # 黑名单（不允许爬取的内容类型）
  content_blacklist:
    - "child_exploitation"
    - "illegal_drugs"
    - "weapons_trafficking"
    - "human_trafficking"

  # 访问速率限制
  rate_limit: 10  # 每分钟最多10个请求

  # 超时设置
  timeout: 60  # 秒

  # 最大重试次数
  max_retries: 3

# 合规性
compliance:
  require_user_consent: true
  log_all_requests: true
  data_retention_days: 90
  report_illegal_content: true  # 发现非法内容时报告
```

---

## 🔧 插件管理器（Plugin Manager）

### 核心功能

```python
# plugins/manager.py
import importlib
import os
import yaml
from typing import Dict, List, Optional
from plugins.base import HIDRSPlugin

class PluginManager:
    """HIDRS插件管理器"""

    def __init__(self, plugin_dir: str = 'plugins'):
        self.plugin_dir = plugin_dir
        self.plugins: Dict[str, HIDRSPlugin] = {}
        self.plugin_configs: Dict[str, Dict] = {}

    def discover_plugins(self) -> List[str]:
        """发现可用插件"""
        discovered = []
        for item in os.listdir(self.plugin_dir):
            plugin_path = os.path.join(self.plugin_dir, item)
            if os.path.isdir(plugin_path):
                config_file = os.path.join(plugin_path, 'config.yaml')
                if os.path.exists(config_file):
                    discovered.append(item)
        return discovered

    def load_plugin(self, plugin_name: str) -> bool:
        """加载插件"""
        try:
            # 读取插件配置
            config_path = os.path.join(
                self.plugin_dir,
                plugin_name,
                'config.yaml'
            )
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            # 检查是否启用
            if not config.get('enabled', False):
                logger.info(f"Plugin {plugin_name} is disabled")
                return False

            # 动态导入插件模块
            module_path = f"plugins.{plugin_name}.plugin"
            module = importlib.import_module(module_path)

            # 获取插件类
            plugin_class_name = config['name']
            plugin_class = getattr(module, plugin_class_name)

            # 读取用户配置（如果存在）
            user_config_path = f"plugin_configs/{plugin_name}.yaml"
            if os.path.exists(user_config_path):
                with open(user_config_path, 'r') as f:
                    user_config = yaml.safe_load(f)
                config.update(user_config)

            # 实例化插件
            plugin_instance = plugin_class(config)

            # 验证权限
            if not self._check_permissions(plugin_instance):
                raise PermissionError(
                    f"Plugin {plugin_name} requires additional permissions"
                )

            # 初始化插件
            if plugin_instance.initialize():
                self.plugins[plugin_name] = plugin_instance
                self.plugin_configs[plugin_name] = config
                logger.info(f"Plugin {plugin_name} loaded successfully")
                return True
            else:
                logger.error(f"Plugin {plugin_name} initialization failed")
                return False

        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_name}: {e}")
            return False

    def unload_plugin(self, plugin_name: str):
        """卸载插件"""
        if plugin_name in self.plugins:
            self.plugins[plugin_name].shutdown()
            del self.plugins[plugin_name]
            logger.info(f"Plugin {plugin_name} unloaded")

    def get_plugin(self, plugin_name: str) -> Optional[HIDRSPlugin]:
        """获取插件实例"""
        return self.plugins.get(plugin_name)

    def is_enabled(self, plugin_name: str) -> bool:
        """检查插件是否启用"""
        return plugin_name in self.plugins

    def list_plugins(self) -> Dict[str, Dict]:
        """列出所有插件"""
        return {
            name: {
                'enabled': self.is_enabled(name),
                'capabilities': plugin.get_capabilities() if self.is_enabled(name) else [],
                'config': self.plugin_configs.get(name, {})
            }
            for name, plugin in self.plugins.items()
        }

    def _check_permissions(self, plugin: HIDRSPlugin) -> bool:
        """检查插件权限"""
        # 实现权限检查逻辑
        required_perms = getattr(plugin, 'REQUIRED_PERMISSIONS', [])
        # 这里可以添加用户授权流程
        return True  # 暂时返回True
```

### Flask API端点

```python
# backend/crawler_server.py
@app.route('/api/plugins', methods=['GET'])
def list_plugins():
    """列出所有插件"""
    return jsonify(plugin_manager.list_plugins())

@app.route('/api/plugins/<plugin_name>/enable', methods=['POST'])
def enable_plugin(plugin_name):
    """启用插件"""
    if plugin_manager.load_plugin(plugin_name):
        return jsonify({'success': True})
    return jsonify({'error': 'Failed to load plugin'}), 500

@app.route('/api/plugins/<plugin_name>/disable', methods=['POST'])
def disable_plugin(plugin_name):
    """禁用插件"""
    plugin_manager.unload_plugin(plugin_name)
    return jsonify({'success': True})
```

---

## 🎨 前端UI设计

### 插件管理页面

```html
<!-- frontend/plugins.html -->
<div class="plugins-manager">
  <h2>插件管理</h2>

  <!-- 插件列表 -->
  <div class="plugin-list">
    <!-- 设备扫描插件 -->
    <div class="plugin-card">
      <div class="plugin-header">
        <h3>
          <i class="bi bi-router"></i> 设备扫描插件
        </h3>
        <div class="plugin-status">
          <span class="badge bg-danger">未启用</span>
        </div>
      </div>
      <div class="plugin-body">
        <p>集成Shodan、Censys等API，提供互联网设备扫描和漏洞情报。</p>
        <div class="plugin-capabilities">
          <span class="badge bg-info">Shodan</span>
          <span class="badge bg-info">Censys</span>
          <span class="badge bg-info">漏洞扫描</span>
        </div>
      </div>
      <div class="plugin-footer">
        <button class="btn btn-sm btn-primary" onclick="configurePlugin('device_scanner')">
          <i class="bi bi-gear"></i> 配置
        </button>
        <button class="btn btn-sm btn-success" onclick="enablePlugin('device_scanner')">
          <i class="bi bi-check-circle"></i> 启用
        </button>
      </div>
    </div>

    <!-- 暗网爬虫插件 -->
    <div class="plugin-card">
      <div class="plugin-header">
        <h3>
          <i class="bi bi-incognito"></i> 暗网爬虫插件
        </h3>
        <div class="plugin-status">
          <span class="badge bg-warning">需要配置</span>
        </div>
      </div>
      <div class="plugin-body">
        <p>支持Tor、I2P等匿名网络的爬虫功能，用于暗网情报收集。</p>
        <div class="alert alert-danger mt-2">
          <i class="bi bi-exclamation-triangle"></i>
          <strong>警告：</strong>仅用于合法的安全研究和威胁情报收集。
        </div>
        <div class="plugin-capabilities">
          <span class="badge bg-dark">Tor</span>
          <span class="badge bg-dark">I2P</span>
        </div>
      </div>
      <div class="plugin-footer">
        <button class="btn btn-sm btn-primary" onclick="configurePlugin('darkweb_crawler')">
          <i class="bi bi-gear"></i> 配置
        </button>
        <button class="btn btn-sm btn-warning" onclick="showConsentDialog('darkweb_crawler')">
          <i class="bi bi-file-text"></i> 查看条款
        </button>
      </div>
    </div>
  </div>
</div>

<!-- 插件配置对话框 -->
<div class="modal" id="plugin-config-modal">
  <div class="modal-dialog modal-lg">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">插件配置</h5>
      </div>
      <div class="modal-body">
        <form id="plugin-config-form">
          <!-- 动态生成配置表单 -->
        </form>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
        <button class="btn btn-primary" onclick="savePluginConfig()">保存</button>
      </div>
    </div>
  </div>
</div>
```

### 设备扫描界面

```html
<!-- 设备扫描专用界面 -->
<div class="device-scanner-panel">
  <h4>
    <i class="bi bi-router"></i> 设备扫描
  </h4>

  <div class="search-form">
    <div class="input-group">
      <select class="form-select" style="max-width: 150px;" id="scan-type">
        <option value="shodan">Shodan</option>
        <option value="censys">Censys</option>
        <option value="zoomeye">ZoomEye</option>
      </select>
      <input type="text" class="form-control" id="scan-query"
             placeholder="例如: apache country:CN">
      <button class="btn btn-primary" onclick="performDeviceScan()">
        <i class="bi bi-search"></i> 扫描
      </button>
    </div>

    <div class="mt-2">
      <small class="text-muted">
        <strong>示例查询：</strong>
        "apache country:CN" | "port:22" | "org:\"Amazon\"" | "product:nginx"
      </small>
    </div>
  </div>

  <!-- 扫描结果 -->
  <div class="scan-results mt-4" id="scan-results">
    <!-- 动态加载 -->
  </div>
</div>
```

---

## 📊 插件开发指南

### 创建新插件的步骤

1. **创建插件目录**
   ```bash
   mkdir -p plugins/my_plugin
   cd plugins/my_plugin
   ```

2. **创建插件文件**
   ```bash
   touch __init__.py
   touch plugin.py
   touch config.yaml
   ```

3. **实现插件类**
   ```python
   # plugins/my_plugin/plugin.py
   from plugins.base import HIDRSPlugin

   class MyPlugin(HIDRSPlugin):
       def initialize(self) -> bool:
           # 初始化逻辑
           return True

       def execute(self, query: str, **kwargs):
           # 执行逻辑
           return []

       def validate_config(self) -> bool:
           # 配置验证
           return True
   ```

4. **编写配置文件**
   ```yaml
   # plugins/my_plugin/config.yaml
   name: MyPlugin
   version: 1.0.0
   enabled: false
   ```

5. **测试插件**
   ```python
   from plugins.manager import PluginManager

   pm = PluginManager()
   pm.load_plugin('my_plugin')
   ```

---

## ⚖️ 合规性与安全

### 法律合规

| 插件 | 法律风险 | 合规措施 |
|------|---------|---------|
| 设备扫描 | ⚠️ 中 | • 记录所有查询<br>• 用户同意条款<br>• 速率限制 |
| 暗网爬虫 | 🔴 高 | • 强制同意<br>• 内容黑名单<br>• 访问日志<br>• 非法内容报告 |

### 数据保护

- 所有插件查询日志保留90天
- API密钥加密存储
- 敏感数据脱敏处理
- 定期安全审计

### 用户责任声明

```
HIDRS插件系统用户协议

使用HIDRS插件系统即表示您同意：

1. 仅将插件用于合法目的
2. 遵守当地法律法规
3. 不侵犯他人隐私
4. 不参与非法活动
5. 对使用插件的后果负全部责任

特别警告：
- 设备扫描插件可能触发目标系统的入侵检测
- 暗网爬虫插件访问的内容可能涉及非法活动
- 插件作者和HIDRS项目不对用户行为负责
```

---

## 🚀 实施路线图

### Phase 1: 基础架构（2-3周）

- [ ] 实现插件基类和管理器
- [ ] 设计插件配置系统
- [ ] 实现权限管理机制
- [ ] 编写插件开发文档

### Phase 2: 设备扫描插件（1-2周）

- [ ] 实现Shodan API集成
- [ ] 实现Censys API集成
- [ ] 设计设备扫描UI
- [ ] 编写使用文档和示例

### Phase 3: 暗网爬虫插件（2-3周）

- [ ] 实现Tor爬虫
- [ ] 实现合规性检查
- [ ] 设计暗网搜索UI
- [ ] 编写安全使用指南

### Phase 4: 测试与优化（1-2周）

- [ ] 单元测试
- [ ] 集成测试
- [ ] 安全审计
- [ ] 性能优化

### 总计开发时间：6-10周

---

## 📚 参考资料

### 技术文档
- [Shodan API文档](https://developer.shodan.io/)
- [Censys API文档](https://search.censys.io/api)
- [Tor Project](https://www.torproject.org/docs/)
- [Stem库文档](https://stem.torproject.org/)

### 相关文件
- `/home/user/hidrs/HIDRS-VS-MAINSTREAM-OSINT-TOOLS.md` - OSINT工具对比
- `/home/user/hidrs/CLAUDE.md` - HIDRS项目说明
- `/home/user/hidrs/HIDRS-ADVANCED-SEARCH-PLAN.md` - 高级搜索规划

---

**文档版本**: 1.0.0
**创建时间**: 2026-02-05
**作者**: HIDRS Team
**状态**: 规划阶段
