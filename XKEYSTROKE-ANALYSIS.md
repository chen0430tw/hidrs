# Xkeystroke 项目分析报告

**分析日期**: 2026-02-04
**项目来源**: https://github.com/AIOSINT/Xkeystroke
**项目类型**: OSINT (Open Source Intelligence) 工具

---

## 📋 项目概述

Xkeystroke是一个受NSA XKeyscore启发的开源情报收集工具，提供Web界面用于数据收集、分析和文件扫描。

**重要说明**:
- ❌ **不是**键盘记录工具（Keylogger）
- ✅ **是**合法的OSINT和文件分析平台
- ✅ MIT许可证，开源项目

---

## 🏗️ 技术架构

### 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| **前端** | React | 17.0.2 |
| **UI框架** | React Bootstrap | 1.6.1 |
| **路由** | React Router DOM | 5.2.0 |
| **后端** | Node.js + Express | - |
| **数据可视化** | React Vis Network Graph | 3.0.1 |
| **文件处理** | Multer, Yauzl, File-Type | - |
| **API通信** | Axios | 1.7.9 |
| **认证** | Custom (AES-256-CTR加密) | - |

### 项目结构

```
Xkeystroke/
├── backend/              # 后端逻辑（不完整，可能是遗留代码）
│   └── routes/
│       └── users.js
├── server/               # 主服务器
│   ├── server.js         # Express服务器（11KB，核心路由）
│   ├── routes/
│   │   └── scannerRoutes.js  # 文件扫描API路由
│   └── package.json
├── src/                  # React前端
│   ├── components/       # UI组件
│   │   ├── admin/        # 管理员功能（用户管理）
│   │   ├── dashboard/    # 仪表盘
│   │   ├── fileScanner/  # 文件扫描器（核心功能，33KB）
│   │   ├── login/        # 登录/注册
│   │   ├── profile/      # 用户配置
│   │   ├── report-panel/ # 报告面板
│   │   └── users/        # 用户列表
│   ├── App.js            # 主应用路由
│   ├── AuthContext.js    # 认证上下文
│   └── index.js          # 入口文件
├── public/               # 静态资源
└── package.json          # 项目配置
```

---

## 🔑 核心功能

### 1. 用户认证系统

**文件**: `server/server.js:102-132`

**功能**:
- 用户注册/登录
- AES-256-CTR密码加密
- UUID用户标识
- 角色管理（admin/user）
- 基于Header的角色验证

**安全机制**:
```javascript
// 密码加密
const encrypt = (text) => {
    const iv = crypto.randomBytes(16);
    const cipher = crypto.createCipheriv('aes-256-ctr', secretKey, iv);
    const encrypted = Buffer.concat([cipher.update(text), cipher.final()]);
    return `${iv.toString('hex')}:${encrypted.toString('hex')}`;
};

// 管理员验证
const validateAdmin = async (req, res, next) => {
    const userRole = req.headers['user-role'];
    if (userRole.toLowerCase() !== 'admin') {
        return res.status(403).json({ message: 'Not authorized' });
    }
    next();
};
```

**数据存储**: `server/users.json` (本地JSON文件)

---

### 2. 文件扫描器 (FileScanner)

**文件**: `src/components/fileScanner/FileScanner.js` (33KB)

**功能**:
- 文件上传和分析
- EXIF元数据提取
- 文件类型检测
- ZIP文件解压和递归分析
- 恶意文件检测（基础）
- 文件关系可视化

**支持的文件类型**:
- 图片: JPG, PNG, GIF, BMP
- 压缩文件: ZIP, RAR (通过yauzl)
- 文档: PDF, DOC, XLS (元数据)
- 其他: 通过file-type库自动检测

**分析流程**:
```
用户上传文件
  ↓
文件类型检测 (file-type)
  ↓
元数据提取 (exif-reader)
  ↓
内容分析
  ├─ ZIP → 递归解压分析
  ├─ 图片 → EXIF GPS/相机信息
  ├─ 文档 → 作者/创建时间
  └─ 其他 → MIME类型
  ↓
可视化展示 (Network Graph)
```

**API端点**:
- `POST /api/scanner/scan` - 上传和扫描文件
- 使用Multer处理文件上传（内存存储）

---

### 3. 仪表盘 (Dashboard)

**文件**: `src/components/dashboard/Dashboard.js`

**功能**:
- 用户活动概览
- 最近扫描文件
- 系统统计信息
- 快速访问各功能模块

**组件结构**:
```
Dashboard
├── Widgets/
│   ├── RecentScans
│   ├── UserActivity
│   └── SystemStats
└── QuickActions
```

---

### 4. 管理员功能

**文件**:
- `src/components/admin/UserList.js` (9KB)
- `src/components/users/UserList.js` (20KB)

**功能**:
- 查看所有用户
- 编辑用户角色
- 删除用户
- 用户活动监控
- 权限管理

**权限级别**:
- **Admin**: 完全访问权限
- **User**: 普通用户权限

---

### 5. 数据可视化

**库**: `react-vis-network-graph` (3.0.1)

**功能**:
- 文件关系图谱
- 网络拓扑可视化
- 数据关联展示

**应用场景**:
- 显示ZIP文件内容树
- 展示文件之间的关系
- OSINT数据关联分析

---

## 🔒 安全特性

### 已实现

1. **密码加密** ✅
   - AES-256-CTR加密算法
   - 随机IV（初始化向量）
   - 密钥存储在`server/config.json`

2. **CORS保护** ✅
   - 限制来源：`http://localhost:3000`
   - 仅允许特定方法和头部

3. **文件权限** ✅
   - `users.json`设置为0666权限

4. **角色验证** ✅
   - 基于Header的角色检查
   - 管理员端点保护

### 安全隐患

1. **密码存储** ⚠️
   - 使用对称加密（AES），不是单向哈希
   - 建议使用bcrypt/argon2

2. **Token机制** ⚠️
   - 返回假Token (`'dummy-token'`)
   - 无JWT或Session管理
   - 无Token过期机制

3. **本地文件存储** ⚠️
   - 用户数据存储在JSON文件
   - 没有数据库备份
   - 并发写入可能冲突

4. **缺少HTTPS** ⚠️
   - 开发环境使用HTTP
   - 生产环境应强制HTTPS

5. **缺少速率限制** ⚠️
   - 无登录尝试限制
   - 无API调用频率控制

---

## 🎯 OSINT功能分析

### 已实现

1. **文件元数据提取**
   - EXIF数据（GPS坐标、相机型号、拍摄时间）
   - 文档作者信息
   - 创建/修改时间

2. **文件类型识别**
   - 自动检测文件MIME类型
   - 识别伪装文件扩展名

3. **压缩包分析**
   - 递归解压ZIP文件
   - 分析内部文件结构

4. **数据可视化**
   - 文件关系图
   - 数据关联展示

### 缺失功能

1. **网络爬虫** ❌
   - README提到但未实现
   - 无动态内容抓取

2. **API集成** ❌
   - README提到但未实现
   - 无外部OSINT API调用

3. **数据库支持** ❌
   - 无持久化存储
   - 无历史记录查询

4. **高级分析** ❌
   - 无图像识别
   - 无人脸检测
   - 无文本情感分析

5. **团队协作** ❌
   - 无共享功能
   - 无评论/标注

---

## 🔍 与HIDRS的对比

| 功能 | Xkeystroke | HIDRS |
|------|-----------|-------|
| **技术栈** | React + Node.js | Flask + Vanilla JS |
| **数据存储** | JSON文件 | MongoDB + Elasticsearch |
| **用户系统** | 简单认证 | 无（计划添加） |
| **文件分析** | ✅ EXIF/元数据 | ❌ 无 |
| **网络爬虫** | ❌ 未实现 | ✅ 多平台爬虫 |
| **数据可视化** | Network Graph | 网络拓扑 + 全息映射 |
| **向量搜索** | ❌ 无 | ✅ HNSW |
| **实时流处理** | ❌ 无 | ✅ Kafka |
| **NLP分析** | ❌ 无 | ✅ TF-IDF/关键词提取 |

---

## 🎁 可集成到HIDRS的功能

### 1. 文件分析模块 ⭐⭐⭐⭐⭐

**优先级**: 高

**集成方式**:
```python
# 在HIDRS中添加文件分析层
hidrs/
  file_analysis/
    file_analyzer.py          # 主分析器
    metadata_extractor.py     # 元数据提取
    exif_parser.py            # EXIF解析
    file_type_detector.py     # 文件类型检测
    zip_analyzer.py           # 压缩包分析
```

**技术方案**:
- 使用Python的`exifread`库提取EXIF
- 使用`python-magic`检测文件类型
- 使用`zipfile`处理压缩文件
- 集成到现有的`data_acquisition`层

**API端点**:
```
POST /api/file/analyze
POST /api/file/upload
GET  /api/file/metadata/{file_id}
```

---

### 2. 用户认证系统 ⭐⭐⭐⭐

**优先级**: 中高

**集成方式**:
- 在HIDRS和SED中添加用户登录
- 使用Flask-Login或Flask-JWT-Extended
- MongoDB存储用户数据

**改进建议**:
```python
# 使用bcrypt替代AES加密
from werkzeug.security import generate_password_hash, check_password_hash

# 使用JWT替代dummy-token
from flask_jwt_extended import create_access_token

# 添加角色权限管理
from flask_principal import Principal, Permission, RoleNeed
```

---

### 3. 数据可视化增强 ⭐⭐⭐

**优先级**: 中

**集成方式**:
- 引入React Vis Network Graph
- 或使用Python的`networkx` + `matplotlib`
- 增强HIDRS的网络拓扑可视化

**应用场景**:
- 显示爬虫数据关联
- 展示文档引用关系
- 可视化社交网络图

---

### 4. 仪表盘界面 ⭐⭐⭐

**优先级**: 中

**集成方式**:
- 改进HIDRS的前端界面
- 添加Widgets系统
- 统一SED和HIDRS的UI风格

---

## 🚀 集成方案

### 方案A: 独立部署（推荐）

```yaml
# docker-compose.yml
services:
  xkeystroke:
    build: ./Xkeystroke
    ports:
      - "3000:3000"
      - "3001:3001"
    volumes:
      - xkey_data:/app/data
    networks:
      - hidrs_network

  hidrs:
    # 现有HIDRS配置
    depends_on:
      - xkeystroke
```

**优点**:
- 保持项目独立性
- 易于维护和更新
- 可以共享网络和数据

**缺点**:
- 需要额外端口
- 跨服务通信开销

---

### 方案B: 模块化集成

```python
# hidrs/xkey_integration/
__init__.py
file_analyzer.py      # 移植文件分析功能
auth_manager.py       # 移植认证系统
visualization.py      # 移植可视化组件
```

**优点**:
- 深度集成
- 统一技术栈
- 共享数据库

**缺点**:
- 需要重写前端（React → Vanilla JS）
- 工作量较大

---

### 方案C: API集成（最简单）

```python
# HIDRS调用Xkeystroke API
import requests

class XkeystrokeClient:
    def __init__(self, base_url='http://localhost:3001'):
        self.base_url = base_url

    def analyze_file(self, file_path):
        with open(file_path, 'rb') as f:
            files = {'file': f}
            response = requests.post(
                f'{self.base_url}/api/scanner/scan',
                files=files
            )
        return response.json()
```

**优点**:
- 实现简单
- 松耦合
- 易于测试

**缺点**:
- 依赖外部服务
- 网络延迟

---

## 📊 性能评估

### 优点

1. ✅ **React前端** - 现代化UI，响应式设计
2. ✅ **模块化架构** - 组件清晰分离
3. ✅ **文件分析** - EXIF/元数据提取完整
4. ✅ **轻量级** - 无重型依赖

### 缺点

1. ❌ **无数据库** - JSON文件存储不适合生产
2. ❌ **假Token** - 认证机制不完善
3. ❌ **缺少API** - 承诺的OSINT API未实现
4. ❌ **无测试** - 没有单元测试或集成测试
5. ❌ **并发问题** - 文件锁未处理

---

## ⚠️ 安全建议

### 立即修复

1. **密码存储** 🔴 严重
   ```javascript
   // 使用bcrypt替代AES
   const bcrypt = require('bcrypt');
   const hashedPassword = await bcrypt.hash(password, 10);
   const isMatch = await bcrypt.compare(password, hashedPassword);
   ```

2. **Token系统** 🔴 严重
   ```javascript
   // 使用JWT
   const jwt = require('jsonwebtoken');
   const token = jwt.sign({ userId: user.uuid }, SECRET_KEY, { expiresIn: '1h' });
   ```

3. **数据库** 🟠 高
   ```javascript
   // 使用MongoDB或PostgreSQL
   const mongoose = require('mongoose');
   // 或
   const { Pool } = require('pg');
   ```

4. **HTTPS** 🟠 高
   - 生产环境强制HTTPS
   - 使用Let's Encrypt证书

5. **速率限制** 🟡 中
   ```javascript
   const rateLimit = require('express-rate-limit');
   const limiter = rateLimit({
       windowMs: 15 * 60 * 1000,
       max: 100
   });
   app.use('/login', limiter);
   ```

---

## 🎓 学习价值

### 适合学习

1. ✅ React组件设计
2. ✅ Express.js后端架构
3. ✅ 文件处理和EXIF提取
4. ✅ 加密算法应用（虽然有问题）
5. ✅ 数据可视化实现

### 不适合生产

1. ❌ 认证系统不安全
2. ❌ 数据存储不可靠
3. ❌ 无扩展性
4. ❌ 缺少关键功能

---

## 📝 总结

### 项目定位

**Xkeystroke** 是一个**教育性质**的OSINT工具原型，适合：
- ✅ 学习Web应用开发
- ✅ 了解文件元数据分析
- ✅ 研究React组件架构
- ❌ **不适合**直接用于生产环境

### 与HIDRS的关系

**建议**:
1. **不要直接集成整个项目** - 代码质量和安全性不足
2. **提取有价值的模块** - 文件分析功能可以移植
3. **参考UI设计** - React仪表盘设计不错
4. **学习项目结构** - 前后端分离的模式值得借鉴

### 优先集成功能

1. **文件分析模块** ⭐⭐⭐⭐⭐ - 移植到Python，集成到HIDRS
2. **EXIF提取** ⭐⭐⭐⭐⭐ - 使用`exifread`库实现
3. **数据可视化** ⭐⭐⭐ - 增强HIDRS的图表展示
4. **认证系统** ⭐⭐⭐⭐ - 改进后添加到HIDRS和SED

---

## 🔗 相关资源

- **项目地址**: https://github.com/AIOSINT/Xkeystroke
- **许可证**: MIT License
- **文档**: README.md（项目内）
- **依赖**: package.json

---

## 📅 下一步行动

### 短期（本周）

1. ✅ 分析完成项目结构
2. ⏳ 测试运行Xkeystroke
3. ⏳ 评估文件分析功能
4. ⏳ 设计集成方案

### 中期（本月）

1. ⏳ 在HIDRS中添加文件分析模块
2. ⏳ 实现EXIF元数据提取
3. ⏳ 添加用户认证系统
4. ⏳ 增强数据可视化

### 长期（季度）

1. ⏳ 完整的OSINT工具集
2. ⏳ 团队协作功能
3. ⏳ API市场集成
4. ⏳ 高级分析功能

---

**分析完成日期**: 2026-02-04
**分析作者**: Claude Code Agent
**会话ID**: session_017KHwuf6oyC7DjAqMXfFGK4
