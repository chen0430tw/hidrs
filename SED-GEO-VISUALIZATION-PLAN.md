# SED + 地理位置可视化 技术方案

## 📊 项目概述

将 **SED（Social Engineering Database）** 与 **地理位置可视化** 整合，在 FAIRY-DESK 中实现数据泄露事件的地理分布可视化。

---

## 🎯 核心功能

### 1️⃣ 数据泄露地理热力图
- 显示全球/国内数据泄露事件的地理分布
- 基于数据来源（source）的地理统计
- 实时更新热力密度

### 2️⃣ 邮箱域名地理分析
- 解析邮箱域名（suffix_email）的注册地理位置
- 统计各地区使用最多的邮箱服务商
- 可视化域名服务器分布

### 3️⃣ 泄露事件时间轴
- 按时间（xtime）和地理位置显示泄露事件演变
- 时间滑块控制显示时间段
- 动态播放泄露事件扩散过程

### 4️⃣ 交互式查询
- 点击地图区域查看该地区的泄露数据
- 支持圈选、框选区域批量查询
- 实时显示统计数据

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    FAIRY-DESK 左屏                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           SED 地理位置可视化 Tab                      │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │         Leaflet.js 地图                        │  │  │
│  │  │  - 热力图层（数据泄露密度）                     │  │  │
│  │  │  - 标记图层（重大泄露事件）                     │  │  │
│  │  │  - 聚类图层（邮箱域名分布）                     │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  │  ┌────────┬────────┬────────┬────────┐              │  │
│  │  │时间轴  │统计面板│过滤器  │图例    │              │  │
│  │  └────────┴────────┴────────┴────────┘              │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│              FAIRY-DESK Flask API (新增端点)                │
│  /api/sed/geo/sources        - 获取数据源地理分布          │
│  /api/sed/geo/domains        - 获取邮箱域名地理分布        │
│  /api/sed/geo/timeline       - 获取时间轴数据              │
│  /api/sed/geo/region/<name>  - 查询指定地区的数据          │
│  /api/sed/geo/heatmap        - 获取热力图数据              │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                  地理位置处理层（新增）                      │
│  - GeoIP 数据库 (GeoLite2-City.mmdb)                       │
│  - DNS 解析器 (dnspython)                                   │
│  - 域名 WHOIS 查询 (python-whois)                           │
│  - 地理编码缓存 (Redis/内存)                                │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                  SED Elasticsearch                          │
│  索引字段:                                                   │
│    - user, email, suffix_email                             │
│    - password, passwordHash                                │
│    - source (数据来源)                                      │
│    - xtime (泄露时间)                                       │
│    - [新增] geo_location { lat, lon, country, city }       │
│    - [新增] domain_ip                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 📐 数据模型设计

### SED 扩展字段

在现有 Elasticsearch 索引中新增地理位置相关字段：

```json
{
  "_index": "socialdb",
  "_source": {
    // 现有字段
    "user": "johndoe",
    "email": "john@example.com",
    "suffix_email": "example.com",
    "password": "pass123",
    "passwordHash": "5f4dcc3b5aa765d61d8327deb882cf99",
    "source": "某网站泄露2023",
    "xtime": "202301",
    "create_time": "2023/01/15 10:30:00",

    // 新增地理位置字段
    "geo_location": {
      "lat": 39.9042,
      "lon": 116.4074,
      "country": "China",
      "country_code": "CN",
      "city": "Beijing",
      "region": "Beijing",
      "source_type": "domain"  // domain/source/manual
    },

    // 新增域名IP字段
    "domain_ip": "93.184.216.34",
    "domain_asn": "AS15133",
    "domain_org": "Edgecast Inc."
  }
}
```

### 地理位置来源类型

| source_type | 说明 | 优先级 |
|-------------|------|--------|
| `manual` | 手动标注的泄露事件地理位置 | 🥇 高 |
| `source` | 从source字段提取的地理信息 | 🥈 中 |
| `domain` | 从邮箱域名解析的地理位置 | 🥉 低 |

---

## 🔌 API 端点设计

### 1. 获取数据源地理分布

```
GET /api/sed/geo/sources
```

**查询参数**:
- `time_range`: 时间范围（格式：202301-202312）
- `limit`: 返回数量限制（默认100）

**响应示例**:
```json
{
  "success": true,
  "data": [
    {
      "source": "某网站泄露2023",
      "location": {
        "lat": 39.9042,
        "lon": 116.4074,
        "country": "China",
        "city": "Beijing"
      },
      "count": 1250000,
      "time": "202301"
    }
  ],
  "total": 45
}
```

---

### 2. 获取邮箱域名地理分布

```
GET /api/sed/geo/domains
```

**查询参数**:
- `top_n`: 返回前N个域名（默认50）
- `country`: 按国家过滤

**响应示例**:
```json
{
  "success": true,
  "data": [
    {
      "domain": "qq.com",
      "location": {
        "lat": 22.5431,
        "lon": 114.0579,
        "country": "China",
        "city": "Shenzhen"
      },
      "count": 8500000,
      "ip": "58.250.137.66"
    },
    {
      "domain": "163.com",
      "location": {
        "lat": 30.2741,
        "lon": 120.1551,
        "country": "China",
        "city": "Hangzhou"
      },
      "count": 6200000,
      "ip": "123.58.180.77"
    }
  ]
}
```

---

### 3. 获取热力图数据

```
GET /api/sed/geo/heatmap
```

**查询参数**:
- `resolution`: 分辨率（country/province/city）
- `time_range`: 时间范围

**响应示例**:
```json
{
  "success": true,
  "data": [
    {
      "lat": 39.9042,
      "lon": 116.4074,
      "intensity": 0.95,
      "count": 12500000,
      "region": "Beijing"
    },
    {
      "lat": 31.2304,
      "lon": 121.4737,
      "intensity": 0.82,
      "count": 8900000,
      "region": "Shanghai"
    }
  ]
}
```

---

### 4. 获取时间轴数据

```
GET /api/sed/geo/timeline
```

**查询参数**:
- `start_time`: 起始时间（YYYYMM）
- `end_time`: 结束时间（YYYYMM）
- `interval`: 间隔（month/quarter/year）

**响应示例**:
```json
{
  "success": true,
  "data": [
    {
      "time": "202301",
      "events": [
        {
          "source": "某社交平台泄露",
          "location": { "lat": 37.7749, "lon": -122.4194, "city": "San Francisco" },
          "count": 5000000
        }
      ]
    },
    {
      "time": "202302",
      "events": [
        {
          "source": "某电商平台泄露",
          "location": { "lat": 39.9042, "lon": 116.4074, "city": "Beijing" },
          "count": 8000000
        }
      ]
    }
  ]
}
```

---

### 5. 区域查询

```
GET /api/sed/geo/region/<region_name>
POST /api/sed/geo/query/bounds
```

**POST请求体**（边界框查询）:
```json
{
  "bounds": {
    "north": 40.0,
    "south": 39.0,
    "east": 117.0,
    "west": 116.0
  },
  "limit": 100,
  "offset": 0
}
```

**响应示例**:
```json
{
  "success": true,
  "data": [
    {
      "user": "john***",
      "email": "j***@qq.com",
      "source": "某网站泄露2023",
      "time": "202301",
      "location": { "lat": 39.9042, "lon": 116.4074 }
    }
  ],
  "total": 1250000,
  "summary": {
    "top_domains": ["qq.com", "163.com", "sina.com"],
    "top_sources": ["某网站泄露2023", "某论坛泄露2022"]
  }
}
```

---

## 🎨 前端组件设计

### 组件文件: `fairy-desk/templates/widgets/sed_geo_map.html`

#### 1. 地图核心功能

```javascript
// 地图初始化
const map = L.map('map', {
  center: [35.8617, 104.1954],
  zoom: 4,
  minZoom: 2,
  maxZoom: 18
});

// 暗色主题瓦片
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  attribution: '&copy; OpenStreetMap'
}).addTo(map);

// 图层管理
const layers = {
  heatmap: L.heatLayer([], { radius: 25, blur: 35, maxZoom: 10 }),
  markers: L.markerClusterGroup(),
  sources: L.layerGroup(),
  timeline: L.layerGroup()
};
```

#### 2. 热力图渲染

```javascript
async function renderHeatmap() {
  const response = await fetch('/api/sed/geo/heatmap?resolution=city');
  const data = await response.json();

  const heatPoints = data.data.map(item => [
    item.lat,
    item.lon,
    item.intensity  // 0-1范围
  ]);

  layers.heatmap.setLatLngs(heatPoints);
  layers.heatmap.addTo(map);
}
```

#### 3. 泄露事件标记

```javascript
async function renderSourceMarkers() {
  const response = await fetch('/api/sed/geo/sources?limit=100');
  const data = await response.json();

  data.data.forEach(source => {
    const marker = L.marker([source.location.lat, source.location.lon], {
      icon: createCustomIcon(source.count)
    });

    marker.bindPopup(`
      <div class="source-popup">
        <h3>${source.source}</h3>
        <p>📊 泄露数据: ${formatNumber(source.count)}条</p>
        <p>📍 位置: ${source.location.city}, ${source.location.country}</p>
        <p>🕐 时间: ${formatTime(source.time)}</p>
        <button onclick="queryRegion('${source.source}')">查看详情</button>
      </div>
    `);

    layers.markers.addLayer(marker);
  });

  map.addLayer(layers.markers);
}

function createCustomIcon(count) {
  const size = Math.min(50, 20 + Math.log10(count) * 5);
  const color = getColorByCount(count);

  return L.divIcon({
    className: 'custom-marker',
    html: `
      <div style="
        width: ${size}px;
        height: ${size}px;
        background: ${color};
        border: 3px solid white;
        border-radius: 50%;
        box-shadow: 0 0 12px rgba(0,240,255,0.8);
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-weight: bold;
        font-size: 10px;
      ">
        ${formatShortNumber(count)}
      </div>
    `,
    iconSize: [size, size],
    iconAnchor: [size/2, size/2]
  });
}

function getColorByCount(count) {
  if (count > 10000000) return '#ef4444';      // 红色（超1000万）
  if (count > 5000000) return '#f97316';       // 橙色（500-1000万）
  if (count > 1000000) return '#eab308';       // 黄色（100-500万）
  if (count > 100000) return '#22c55e';        // 绿色（10-100万）
  return '#3b82f6';                            // 蓝色（<10万）
}
```

#### 4. 时间轴控制

```javascript
class TimelineController {
  constructor() {
    this.currentTime = '202301';
    this.timeRange = ['202101', '202412'];
    this.playing = false;
    this.speed = 500; // ms per step
  }

  async loadTimelineData() {
    const response = await fetch(
      `/api/sed/geo/timeline?start_time=${this.timeRange[0]}&end_time=${this.timeRange[1]}`
    );
    this.data = await response.json();
  }

  renderTimeStep(time) {
    const events = this.data.data.find(d => d.time === time)?.events || [];

    layers.timeline.clearLayers();

    events.forEach(event => {
      const circle = L.circle([event.location.lat, event.location.lon], {
        color: '#00f0ff',
        fillColor: '#00f0ff',
        fillOpacity: 0.4,
        radius: Math.sqrt(event.count) * 100,
        className: 'timeline-event'
      }).addTo(layers.timeline);

      circle.bindPopup(`
        <b>${event.source}</b><br>
        泄露数据: ${formatNumber(event.count)}条<br>
        时间: ${formatTime(time)}
      `);
    });

    map.addLayer(layers.timeline);
  }

  play() {
    this.playing = true;
    this.animate();
  }

  pause() {
    this.playing = false;
  }

  animate() {
    if (!this.playing) return;

    const times = this.data.data.map(d => d.time);
    const currentIndex = times.indexOf(this.currentTime);
    const nextIndex = (currentIndex + 1) % times.length;

    this.currentTime = times[nextIndex];
    this.renderTimeStep(this.currentTime);

    setTimeout(() => this.animate(), this.speed);
  }
}

const timeline = new TimelineController();
```

#### 5. 交互式区域查询

```javascript
// 框选工具
let selectionBox = null;

function enableBoxSelection() {
  map.on('mousedown', startBoxSelection);
}

function startBoxSelection(e) {
  const startLatLng = e.latlng;

  selectionBox = L.rectangle([startLatLng, startLatLng], {
    color: '#00f0ff',
    weight: 2,
    fillOpacity: 0.1
  }).addTo(map);

  map.on('mousemove', updateBoxSelection);
  map.on('mouseup', finishBoxSelection);
}

function updateBoxSelection(e) {
  if (!selectionBox) return;
  const bounds = L.latLngBounds(
    selectionBox.getBounds().getSouthWest(),
    e.latlng
  );
  selectionBox.setBounds(bounds);
}

async function finishBoxSelection(e) {
  map.off('mousemove', updateBoxSelection);
  map.off('mouseup', finishBoxSelection);

  const bounds = selectionBox.getBounds();

  const response = await fetch('/api/sed/geo/query/bounds', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      bounds: {
        north: bounds.getNorth(),
        south: bounds.getSouth(),
        east: bounds.getEast(),
        west: bounds.getWest()
      },
      limit: 1000
    })
  });

  const data = await response.json();
  showRegionQueryResults(data);

  map.removeLayer(selectionBox);
  selectionBox = null;
}
```

#### 6. 控制面板UI

```html
<div class="control-panel">
  <!-- 图层切换 -->
  <div class="layer-controls">
    <label><input type="checkbox" id="layer-heatmap" checked> 热力图</label>
    <label><input type="checkbox" id="layer-markers" checked> 泄露事件</label>
    <label><input type="checkbox" id="layer-domains"> 邮箱域名</label>
  </div>

  <!-- 时间轴控制 -->
  <div class="timeline-controls">
    <button id="timeline-play">▶️ 播放</button>
    <button id="timeline-pause">⏸️ 暂停</button>
    <input type="range" id="timeline-slider" min="0" max="100">
    <span id="timeline-label">2023-01</span>
  </div>

  <!-- 过滤器 -->
  <div class="filter-controls">
    <select id="filter-country">
      <option value="">全部国家</option>
      <option value="CN">中国</option>
      <option value="US">美国</option>
    </select>
    <input type="number" id="filter-min-count" placeholder="最小数据量">
  </div>

  <!-- 统计面板 -->
  <div class="stats-panel">
    <div class="stat-item">
      <div class="stat-label">总泄露数据</div>
      <div class="stat-value" id="stat-total">0</div>
    </div>
    <div class="stat-item">
      <div class="stat-label">泄露事件</div>
      <div class="stat-value" id="stat-events">0</div>
    </div>
    <div class="stat-item">
      <div class="stat-label">覆盖国家</div>
      <div class="stat-value" id="stat-countries">0</div>
    </div>
  </div>
</div>
```

---

## 🔧 后端实现（fairy-desk/app.py）

### 1. 依赖安装

```bash
pip install geoip2 dnspython python-whois
```

### 2. 地理位置解析类

```python
import geoip2.database
import dns.resolver
import socket
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)

class GeoLocationResolver:
    """地理位置解析器"""

    def __init__(self, geoip_db_path='data/GeoLite2-City.mmdb'):
        self.geoip_reader = geoip2.database.Reader(geoip_db_path)
        self.dns_resolver = dns.resolver.Resolver()
        self.dns_resolver.timeout = 2
        self.dns_resolver.lifetime = 2

    @lru_cache(maxsize=10000)
    def resolve_ip(self, ip_address):
        """根据IP获取地理位置"""
        try:
            response = self.geoip_reader.city(ip_address)
            return {
                'lat': response.location.latitude,
                'lon': response.location.longitude,
                'country': response.country.name,
                'country_code': response.country.iso_code,
                'city': response.city.name,
                'region': response.subdivisions.most_specific.name if response.subdivisions else None
            }
        except Exception as e:
            logger.warning(f"IP地理解析失败 {ip_address}: {e}")
            return None

    @lru_cache(maxsize=10000)
    def resolve_domain(self, domain):
        """根据域名获取地理位置"""
        try:
            # DNS解析获取IP
            answers = self.dns_resolver.resolve(domain, 'A')
            if answers:
                ip = str(answers[0])
                location = self.resolve_ip(ip)
                if location:
                    location['domain_ip'] = ip
                    return location
        except Exception as e:
            logger.warning(f"域名地理解析失败 {domain}: {e}")

        return None

    def batch_resolve_domains(self, domains):
        """批量解析域名"""
        results = {}
        for domain in domains:
            results[domain] = self.resolve_domain(domain)
        return results

# 全局实例
geo_resolver = GeoLocationResolver()
```

### 3. API路由实现

```python
from flask import Flask, jsonify, request
import requests

# SED API配置
SED_API_BASE = config.get('sed', {}).get('api_endpoint', 'http://localhost:5000')

@app.route('/api/sed/geo/sources')
def sed_geo_sources():
    """获取数据源地理分布"""
    try:
        time_range = request.args.get('time_range', '')
        limit = request.args.get('limit', 100, type=int)

        # 从SED API获取source聚合数据
        # 注意：需要SED后端支持聚合查询
        response = requests.get(
            f"{SED_API_BASE}/api/analysis/sources",
            params={'time_range': time_range, 'limit': limit},
            timeout=10
        )

        sources_data = response.json()

        # 为每个source添加地理位置（手动映射或从数据库读取）
        result = []
        for source in sources_data.get('data', []):
            location = get_source_location(source['source'])
            if location:
                result.append({
                    'source': source['source'],
                    'location': location,
                    'count': source['count'],
                    'time': source.get('time', '')
                })

        return jsonify({
            'success': True,
            'data': result,
            'total': len(result)
        })

    except Exception as e:
        logger.error(f"获取数据源地理分布失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/sed/geo/domains')
def sed_geo_domains():
    """获取邮箱域名地理分布"""
    try:
        top_n = request.args.get('top_n', 50, type=int)
        country = request.args.get('country', '')

        # 从SED API获取域名统计
        response = requests.get(
            f"{SED_API_BASE}/api/analysis/domains",
            params={'top': top_n},
            timeout=10
        )

        domains_data = response.json()

        # 批量解析域名地理位置
        domains = [d['domain'] for d in domains_data.get('data', [])]
        locations = geo_resolver.batch_resolve_domains(domains)

        # 组合结果
        result = []
        for domain_stat in domains_data.get('data', []):
            domain = domain_stat['domain']
            location = locations.get(domain)

            if location:
                # 如果指定了国家过滤
                if country and location.get('country_code') != country:
                    continue

                result.append({
                    'domain': domain,
                    'location': location,
                    'count': domain_stat['count'],
                    'ip': location.get('domain_ip')
                })

        return jsonify({
            'success': True,
            'data': result[:top_n]
        })

    except Exception as e:
        logger.error(f"获取域名地理分布失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/sed/geo/heatmap')
def sed_geo_heatmap():
    """获取热力图数据"""
    try:
        resolution = request.args.get('resolution', 'city')
        time_range = request.args.get('time_range', '')

        # 从SED获取聚合统计
        # 根据resolution决定聚合粒度
        response = requests.get(
            f"{SED_API_BASE}/api/analysis/geo_distribution",
            params={'resolution': resolution, 'time_range': time_range},
            timeout=10
        )

        geo_data = response.json()

        # 归一化intensity值
        max_count = max([d['count'] for d in geo_data.get('data', [])], default=1)

        result = []
        for item in geo_data.get('data', []):
            result.append({
                'lat': item['lat'],
                'lon': item['lon'],
                'intensity': min(1.0, item['count'] / max_count),
                'count': item['count'],
                'region': item.get('region', '')
            })

        return jsonify({
            'success': True,
            'data': result
        })

    except Exception as e:
        logger.error(f"获取热力图数据失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/sed/geo/timeline')
def sed_geo_timeline():
    """获取时间轴数据"""
    try:
        start_time = request.args.get('start_time', '202101')
        end_time = request.args.get('end_time', '202412')
        interval = request.args.get('interval', 'month')

        response = requests.get(
            f"{SED_API_BASE}/api/analysis/timeline",
            params={
                'start': start_time,
                'end': end_time,
                'interval': interval
            },
            timeout=10
        )

        timeline_data = response.json()

        # 为每个时间点的事件添加地理位置
        result = []
        for time_point in timeline_data.get('data', []):
            events_with_geo = []
            for event in time_point.get('events', []):
                location = get_source_location(event['source'])
                if location:
                    events_with_geo.append({
                        'source': event['source'],
                        'location': location,
                        'count': event['count']
                    })

            if events_with_geo:
                result.append({
                    'time': time_point['time'],
                    'events': events_with_geo
                })

        return jsonify({
            'success': True,
            'data': result
        })

    except Exception as e:
        logger.error(f"获取时间轴数据失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/sed/geo/query/bounds', methods=['POST'])
def sed_geo_query_bounds():
    """边界框查询"""
    try:
        bounds = request.json.get('bounds', {})
        limit = request.json.get('limit', 100)
        offset = request.json.get('offset', 0)

        # 构建Elasticsearch地理边界查询
        # 注意：需要SED的Elasticsearch索引包含geo_location字段
        response = requests.post(
            f"{SED_API_BASE}/api/query/geo_bounds",
            json={
                'bounds': bounds,
                'limit': limit,
                'offset': offset
            },
            timeout=30
        )

        query_result = response.json()

        # 脱敏处理
        for item in query_result.get('data', []):
            item['user'] = mask_string(item.get('user', ''), 3)
            item['email'] = mask_email(item.get('email', ''))

        return jsonify(query_result)

    except Exception as e:
        logger.error(f"边界框查询失败: {e}")
        return jsonify({'error': str(e)}), 500


# 辅助函数
def get_source_location(source_name):
    """根据source名称获取地理位置（手动映射或数据库）"""
    # 这里可以维护一个source -> location的映射表
    # 或者从数据库中读取预先标注的地理位置
    source_locations = {
        '某社交平台泄露2023': {'lat': 37.7749, 'lon': -122.4194, 'country': 'USA', 'city': 'San Francisco'},
        '某电商平台泄露2023': {'lat': 39.9042, 'lon': 116.4074, 'country': 'China', 'city': 'Beijing'},
        # ... 更多映射
    }

    return source_locations.get(source_name)


def mask_string(text, keep_chars=3):
    """字符串脱敏"""
    if len(text) <= keep_chars:
        return text
    return text[:keep_chars] + '***'


def mask_email(email):
    """邮箱脱敏"""
    if '@' not in email:
        return email
    user, domain = email.split('@', 1)
    return mask_string(user, 1) + '@' + domain
```

---

## 🗄️ SED数据库扩展

### Elasticsearch索引映射更新

```json
PUT /socialdb
{
  "mappings": {
    "properties": {
      "user": { "type": "keyword" },
      "email": { "type": "keyword" },
      "suffix_email": { "type": "keyword" },
      "password": { "type": "keyword" },
      "passwordHash": { "type": "keyword" },
      "source": { "type": "keyword" },
      "xtime": { "type": "keyword" },
      "create_time": { "type": "date", "format": "yyyy/MM/dd HH:mm:ss" },

      "geo_location": {
        "type": "geo_point"
      },
      "geo_country": { "type": "keyword" },
      "geo_city": { "type": "keyword" },
      "domain_ip": { "type": "ip" },
      "domain_asn": { "type": "keyword" }
    }
  }
}
```

### 数据迁移脚本

```python
# sed/backend/migrate_geo_data.py
from es_utils import ESClient
from geo_resolver import GeoLocationResolver

es_client = ESClient()
geo_resolver = GeoLocationResolver()

def migrate_add_geo_locations():
    """为现有数据添加地理位置信息"""

    # 1. 获取所有唯一的suffix_email
    query = {
        "size": 0,
        "aggs": {
            "unique_domains": {
                "terms": {
                    "field": "suffix_email",
                    "size": 10000
                }
            }
        }
    }

    result = es_client.es.search(index=es_client.index, body=query)
    domains = [bucket['key'] for bucket in result['aggregations']['unique_domains']['buckets']]

    print(f"找到 {len(domains)} 个唯一域名")

    # 2. 批量解析域名地理位置
    domain_locations = geo_resolver.batch_resolve_domains(domains)

    # 3. 更新Elasticsearch文档
    for domain, location in domain_locations.items():
        if not location:
            continue

        # 构建更新查询
        update_query = {
            "script": {
                "source": """
                    ctx._source.geo_location = params.geo_location;
                    ctx._source.geo_country = params.country;
                    ctx._source.geo_city = params.city;
                    ctx._source.domain_ip = params.domain_ip;
                """,
                "params": {
                    "geo_location": {
                        "lat": location['lat'],
                        "lon": location['lon']
                    },
                    "country": location['country'],
                    "city": location['city'],
                    "domain_ip": location.get('domain_ip', '')
                }
            },
            "query": {
                "term": {
                    "suffix_email": domain
                }
            }
        }

        # 执行批量更新
        es_client.es.update_by_query(
            index=es_client.index,
            body=update_query,
            conflicts='proceed'
        )

        print(f"已更新域名 {domain} 的地理位置")

if __name__ == '__main__':
    migrate_add_geo_locations()
```

---

## 📦 部署步骤

### 1. 安装依赖

```bash
# Python依赖
pip install geoip2 dnspython python-whois

# 下载GeoIP数据库
wget https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-City.mmdb \
  -O fairy-desk/data/GeoLite2-City.mmdb
```

### 2. 配置fairy-desk

```json
// fairy-desk/config.json
{
  "sed": {
    "enabled": true,
    "api_endpoint": "http://localhost:5000",
    "geo_enabled": true
  },
  "geoip": {
    "database_path": "data/GeoLite2-City.mmdb",
    "cache_size": 10000
  }
}
```

### 3. SED数据迁移

```bash
cd /home/user/hidrs/sed/backend
python migrate_geo_data.py
```

### 4. 添加Tab到FAIRY-DESK

```json
// fairy-desk/config.json
{
  "left_screen": {
    "tabs": [
      {
        "id": "sed-geo",
        "name": "SED地理分析",
        "icon": "🗺️",
        "url": "/widget/sed-geo-map",
        "loadStrategy": "lazy",
        "category": "security",
        "builtIn": false
      }
    ]
  }
}
```

### 5. 启动服务

```bash
# 启动SED
cd /home/user/hidrs/sed
docker-compose up -d

# 启动FAIRY-DESK
cd /home/user/hidrs/fairy-desk
python app.py
```

---

## 🎯 使用场景

### 场景1: 全球数据泄露态势分析
- 查看全球范围内的数据泄露热点地区
- 分析不同国家/地区的泄露事件密度
- 识别高风险地理区域

### 场景2: 邮箱服务商分布分析
- 统计各地区最常用的邮箱服务提供商
- 分析域名服务器的地理分布
- 识别可疑的邮箱服务商集中区域

### 场景3: 泄露事件时间演变追踪
- 播放泄露事件的时间演变过程
- 分析泄露事件的传播路径
- 预测未来可能的泄露热点

### 场景4: 特定区域深度分析
- 框选某个地理区域查看详细数据
- 统计该区域的泄露数据特征
- 生成区域安全报告

---

## 🔒 安全与隐私

### 数据脱敏
- 用户名显示前3个字符，其余用 `***` 替代
- 邮箱用户名仅显示首字母
- 密码和哈希不在地图上显示

### 访问控制
- 地理查询功能需要认证
- 详细数据查看需要高权限
- 记录所有地理查询操作日志

### 数据保护
- 不记录查询者的IP和地理位置
- 查询结果限制返回数量
- 敏感区域数据模糊化处理

---

## 📊 性能优化

### 1. 地理位置缓存
```python
# 使用LRU缓存减少重复解析
@lru_cache(maxsize=10000)
def resolve_domain(domain):
    # ...
```

### 2. Elasticsearch聚合优化
```json
{
  "size": 0,
  "aggs": {
    "geo_grid": {
      "geohash_grid": {
        "field": "geo_location",
        "precision": 5
      }
    }
  }
}
```

### 3. 前端渲染优化
- 使用 MarkerCluster 聚合大量标记
- 热力图使用WebGL加速渲染
- 按视图范围动态加载数据

---

## 📝 后续扩展

1. **AI预测分析** - 基于历史数据预测下一个泄露热点
2. **实时告警** - 新增泄露事件时在地图上实时显示
3. **3D地球视图** - 使用Cesium.js实现3D地球可视化
4. **导出功能** - 将地理分析结果导出为PDF报告
5. **关联分析** - 结合HIDRS的网络拓扑和SED的地理分布进行关联分析

---

## 📚 技术栈总结

| 层级 | 技术 | 用途 |
|------|------|------|
| **前端地图** | Leaflet.js | 地图渲染 |
| **前端可视化** | Leaflet.heat | 热力图 |
| **前端聚类** | Leaflet.markercluster | 标记聚类 |
| **后端框架** | Flask | API服务 |
| **地理解析** | GeoIP2 | IP地理定位 |
| **DNS解析** | dnspython | 域名解析 |
| **数据存储** | Elasticsearch | 地理数据索引 |
| **缓存** | LRU Cache | 地理位置缓存 |

---

**文档版本**: v1.0
**创建日期**: 2026-02-03
**状态**: 📋 规划完成，待实施
