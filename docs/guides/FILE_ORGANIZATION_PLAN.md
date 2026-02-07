# 📁 HIDRS 文件整理方案

## 当前问题
根目录下有43个文件（.md, .py, .txt），缺乏组织结构

## 新目录结构

```
hidrs/
├── README.md                          # 项目主README（保留）
├── CLAUDE.md                          # Claude Code项目说明（保留）
├── requirements-compatible.txt        # 依赖文件（保留）
│
├── docs/                              # 📚 所有文档
│   ├── defense/                       # 🛡️ AEGIS防御系统文档
│   │   ├── AEGIS_VERIFICATION.md
│   │   ├── DISTRIBUTED_ARCHITECTURE.md
│   │   ├── HIDRS-ATTACK-MEMORY-SYSTEM.md
│   │   ├── HIDRS-INVERSE-GFW-DEFENSE.md
│   │   ├── HIDRS-SMART-RESOURCE-OPTIMIZATION.md
│   │   ├── HIDRS-V2-UPGRADE-SIGNATURE-DB.md
│   │   └── HIDRS-V3-FILTER-LISTS-GREYLIST.md
│   │
│   ├── scenarios/                     # 🎬 演绎场景
│   │   ├── GAME_THEORY_ANALYSIS.md
│   │   ├── SCENARIO_GFW_REALTIME.md
│   │   ├── SCENARIO_GFW_SMART_CONTROL.md
│   │   └── SCENARIO_GFW_UPGRADE.md
│   │
│   ├── planning/                      # 📋 功能计划
│   │   ├── FEDERATED_SEARCH_IMPLEMENTATION.md
│   │   ├── GLOBAL-BROADCAST-PLAN.md
│   │   ├── HIDRS-ADVANCED-SEARCH-PLAN.md
│   │   ├── HIDRS-LOCAL-FILE-SEARCH-PLUGIN-PLAN.md
│   │   ├── HIDRS-PLUGIN-SYSTEM-PLAN.md
│   │   ├── PERSON-AVOIDANCE-PLAN.md
│   │   ├── REALTIME-TRACKER-PLAN.md
│   │   ├── SED-FAIRY-INTEGRATION.md
│   │   └── SED-GEO-VISUALIZATION-PLAN.md
│   │
│   ├── analysis/                      # 📊 对比分析
│   │   ├── CRAWLER-SYSTEM-COMPARISON.md
│   │   ├── HIDRS-COMMONCRAWL-XKEYSCORE-ANALYSIS.md
│   │   ├── HIDRS-FAIRY-INTEGRATION.md
│   │   ├── HIDRS-VS-MAINSTREAM-OSINT-TOOLS.md
│   │   ├── OSINT-TOOLS-COMPARISON.md
│   │   ├── OSINT_INTEGRATION_GUIDE.md
│   │   ├── XKEYSCORE-GITHUB-INTEGRATION.md
│   │   ├── XKEYSCORE-VS-XKEYSTROKE.md
│   │   ├── XKEYSTROKE-ANALYSIS.md
│   │   └── XKEYSTROKE-INTEGRATION-GUIDE.md
│   │
│   └── guides/                        # 📖 使用指南
│       ├── DATA-ANALYSIS-FIX.md
│       ├── PERFORMANCE-OPTIMIZATION-SUMMARY.md
│       └── QUICKFIX-GUIDE.md
│
├── algorithms/                        # 🧮 算法实现（Python）
│   ├── et_cooling.py                  # ET-WCN冷却算法
│   └── spark_seed_sosa.py             # SOSA算法
│
├── tests/                             # 🧪 测试文件
│   ├── benchmark_aegis.py
│   ├── test_aegis_comprehensive.py
│   ├── test_distributed_aegis.py
│   └── test_spamhaus_email_integration.py
│
├── misc/                              # 📦 杂项文件
│   └── FAIRY-DESK.txt
│
├── backend/                           # （已存在）
├── frontend/                          # （已存在）
├── docs/ (GitHub Pages)               # （已存在）
└── hidrs/                             # （已存在，核心代码）
    ├── defense/                       # （已存在）
    ├── crawler/                       # （已存在）
    └── ...
```

## 移动命令（批量执行）

```bash
# 创建新目录
mkdir -p docs/{defense,scenarios,planning,analysis,guides}
mkdir -p algorithms tests misc

# 移动防御系统文档
mv AEGIS_VERIFICATION.md docs/defense/
mv DISTRIBUTED_ARCHITECTURE.md docs/defense/
mv HIDRS-ATTACK-MEMORY-SYSTEM.md docs/defense/
mv HIDRS-INVERSE-GFW-DEFENSE.md docs/defense/
mv HIDRS-SMART-RESOURCE-OPTIMIZATION.md docs/defense/
mv HIDRS-V2-UPGRADE-SIGNATURE-DB.md docs/defense/
mv HIDRS-V3-FILTER-LISTS-GREYLIST.md docs/defense/

# 移动演绎场景
mv GAME_THEORY_ANALYSIS.md docs/scenarios/
mv SCENARIO_GFW_REALTIME.md docs/scenarios/
mv SCENARIO_GFW_SMART_CONTROL.md docs/scenarios/
mv SCENARIO_GFW_UPGRADE.md docs/scenarios/

# 移动功能计划
mv FEDERATED_SEARCH_IMPLEMENTATION.md docs/planning/
mv GLOBAL-BROADCAST-PLAN.md docs/planning/
mv HIDRS-ADVANCED-SEARCH-PLAN.md docs/planning/
mv HIDRS-LOCAL-FILE-SEARCH-PLUGIN-PLAN.md docs/planning/
mv HIDRS-PLUGIN-SYSTEM-PLAN.md docs/planning/
mv PERSON-AVOIDANCE-PLAN.md docs/planning/
mv REALTIME-TRACKER-PLAN.md docs/planning/
mv SED-FAIRY-INTEGRATION.md docs/planning/
mv SED-GEO-VISUALIZATION-PLAN.md docs/planning/

# 移动对比分析
mv CRAWLER-SYSTEM-COMPARISON.md docs/analysis/
mv HIDRS-COMMONCRAWL-XKEYSCORE-ANALYSIS.md docs/analysis/
mv HIDRS-FAIRY-INTEGRATION.md docs/analysis/
mv HIDRS-VS-MAINSTREAM-OSINT-TOOLS.md docs/analysis/
mv OSINT-TOOLS-COMPARISON.md docs/analysis/
mv OSINT_INTEGRATION_GUIDE.md docs/analysis/
mv XKEYSCORE-GITHUB-INTEGRATION.md docs/analysis/
mv XKEYSCORE-VS-XKEYSTROKE.md docs/analysis/
mv XKEYSTROKE-ANALYSIS.md docs/analysis/
mv XKEYSTROKE-INTEGRATION-GUIDE.md docs/analysis/

# 移动使用指南
mv DATA-ANALYSIS-FIX.md docs/guides/
mv PERFORMANCE-OPTIMIZATION-SUMMARY.md docs/guides/
mv QUICKFIX-GUIDE.md docs/guides/

# 移动算法实现
mv et_cooling.py algorithms/
mv spark_seed_sosa.py algorithms/

# 移动测试文件
mv benchmark_aegis.py tests/
mv test_aegis_comprehensive.py tests/
mv test_distributed_aegis.py tests/
mv test_spamhaus_email_integration.py tests/

# 移动杂项
mv FAIRY-DESK.txt misc/
```

## 需要更新的引用

### CLAUDE.md
- 更新文件路径引用（如果有）

### 测试文件import路径
- `tests/` 下的文件需要更新相对import

### 算法文件可能的引用
- 检查是否有其他文件import了这些算法

## 根目录最终状态

```
hidrs/
├── README.md
├── CLAUDE.md
├── requirements-compatible.txt
├── docs/          (7个子目录, 34个文件)
├── algorithms/    (2个文件)
├── tests/         (4个文件)
├── misc/          (1个文件)
├── backend/
├── frontend/
└── hidrs/
```

**清爽！从43个文件 → 3个文件 + 4个目录**
