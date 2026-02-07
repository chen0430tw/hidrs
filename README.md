# HIDRS - Holographic Internet Discovery & Retrieval System

全息拉普拉斯互联网爬虫系统 + AEGIS智能防御系统

## 📁 项目结构

```
hidrs/
├── README.md                          # 项目说明（本文件）
├── CLAUDE.md                          # Claude Code项目说明
├── requirements-compatible.txt        # Python依赖
│
├── docs/                              # 📚 所有文档
│   ├── defense/        (7 files)      # 🛡️ AEGIS防御系统文档
│   ├── scenarios/      (4 files)      # 🎬 演绎场景（GFW博弈论分析等）
│   ├── planning/       (9 files)      # 📋 功能计划
│   ├── analysis/       (10 files)     # 📊 对比分析
│   └── guides/         (4 files)      # 📖 使用指南
│
├── algorithms/         (2 files)      # 🧮 核心算法实现
│   ├── et_cooling.py                  # ET-WCN冷却算法
│   └── spark_seed_sosa.py             # SOSA自组织稀疏马尔可夫算法
│
├── tests/              (4 files)      # 🧪 测试套件
│   ├── benchmark_aegis.py             # AEGIS性能基准测试
│   ├── test_aegis_comprehensive.py    # AEGIS综合测试
│   ├── test_distributed_aegis.py      # 分布式系统测试
│   └── test_spamhaus_email_integration.py
│
├── misc/               (1 file)       # 📦 杂项文件
│
├── hidrs/                             # 核心代码
│   ├── defense/                       # AEGIS防御系统
│   │   ├── aegis_root_server.py       # 根协调服务器
│   │   ├── attack_memory.py           # 攻击记忆系统
│   │   ├── cc_server_detector.py      # C&C服务器检测
│   │   ├── defense_logger.py          # 防御日志系统
│   │   ├── inverse_gfw.py             # GFW逆向分析
│   │   └── redis_sync_client.py       # Redis同步客户端
│   ├── crawler/                       # 爬虫模块
│   └── ...
│
├── sed/                               # 前端UI（Smart Eye Dashboard）
├── fairy-desk/                        # Fairy Desk集成
├── Xkeystroke/                        # XKeystroke分析
├── crawler-system/                    # 爬虫系统对比
└── scripts/                           # 工具脚本
```

## 🚀 核心技术

### HIDRS 爬虫系统
- **HLIG** (Holographic Laplacian Internet Graph) - 拉普拉斯谱分析
- **SOSA** (Spark Seed Self-Organizing Sparse Markov Algorithm) - 自组织稀疏马尔可夫
- **ET-WCN** (Equation Theory with Weighted Chain Network) - 方程论冷却算法

### AEGIS 防御系统
- **分布式架构** - 13个Anycast地址（模仿DNS根服务器）
- **攻击记忆系统** - 全局威胁情报共享
- **C&C检测** - 心跳模式识别 + 网络拓扑分析
- **Redis实时同步** - <100ms全球同步

## 📚 关键文档

### 防御系统
- [AEGIS验证报告](docs/defense/AEGIS_VERIFICATION.md) - 技术实现验证
- [分布式架构](docs/defense/DISTRIBUTED_ARCHITECTURE.md) - 完整架构设计
- [攻击记忆系统](docs/defense/HIDRS-ATTACK-MEMORY-SYSTEM.md)

### 演绎场景
- [博弈论分析](docs/scenarios/GAME_THEORY_ANALYSIS.md) - GFW-翻墙博弈分析
- [智能管控演绎](docs/scenarios/SCENARIO_GFW_SMART_CONTROL.md) - "水至清则无鱼"策略
- [实时对抗日志](docs/scenarios/SCENARIO_GFW_REALTIME.md)

### 使用指南
- [快速修复指南](docs/guides/QUICKFIX-GUIDE.md)
- [性能优化总结](docs/guides/PERFORMANCE-OPTIMIZATION-SUMMARY.md)
- [文件整理方案](docs/guides/FILE_ORGANIZATION_PLAN.md)

## 🧪 运行测试

```bash
# AEGIS性能基准测试
python tests/benchmark_aegis.py

# 分布式系统测试
python tests/test_distributed_aegis.py

# 综合测试
python tests/test_aegis_comprehensive.py
```

## 🛠️ 开发说明

详见 [CLAUDE.md](CLAUDE.md)

## 📜 许可证

开源项目，用于研究和教育目的

---

**警告**: 本项目包含防御系统演绎场景，技术本身是中性的，使用者需承担道德责任。
