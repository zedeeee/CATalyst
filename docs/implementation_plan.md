# CATalyst: 开源 CATIA V5 Automation 知识库与 AI Agent 工具链架构规划

## 1. 项目定位与核心目标

面向 **CATIA V5 全系列（R20–R30+）** 的 Automation COM 接口知识库转换与 AI 极速调用引擎。

* **专注 CATIA V5 体系**：精准适配 V5 Automation COM/IDL 接口规范。
* **单槽位即插即用（Single-Slot Design）**：仓库固定一个 CHM 槽位和一套产物路径，默认内置 R27 版本的 CHM 及预编译数据库，克隆即用。用户如需适配其他版本，覆盖 CHM 后一行命令重建。
* **继承链与签名无损修复**：自动解构并合并 `generatedFatherClass` 继承树，消除 API 遗漏与参数缺失。
* **Token 极致优化**：CLI + MCP Server + Agent Skill，"0 预载 → 按需毫秒级召回"，单类卡片 < 300 Tokens。
* **完善复刻指引**：详细的 CHM 本地提取 SOP，让任何 CATIA V5 用户都能在自己的环境中一键复刻。
* **开源协议**：MIT License。

---

## 2. 单槽位架构设计理念

### 为什么不搞多版本子文件夹？

CATIA V5 Automation 是 COM/IDL 体系，**接口严格向后兼容、单调递增**。R27 基本是 R20/R21 的超集，跨版本重复度 > 95%。多版本子文件夹是典型的过度设计，徒增仓库体积和使用复杂度。

### 单槽位运作模式

| 使用场景 | 操作 | 结果 |
| :--- | :--- | :--- |
| **普通用户 / AI 用户（90%）** | `git clone` → 直接使用 | 仓库自带 R27 预编译的 `dist/catia_api.db`，零配置零编译 |
| **老版本用户（如 R21）** | 覆盖 `data/V5Automation.chm` → `python build.py` | 自动解包、解析、重建 `dist/` 下全部产物 |
| **多版本存档（可选高级用法）** | `python build.py --input path/to/V5R21.chm --output dist/v5r21/` | 按需生成独立版本产物到指定目录 |

---

## 3. 开源工程目录结构

```text
CATalyst/
├── .github/
│   └── workflows/                # CI 测试与自动化构建
├── data/
│   ├── V5Automation.chm          # 固定单槽位：默认内置 R27 版本 CHM (受版本控制)
│   └── raw/                      # 解包后的 HTML 原始目录 (.gitignore 严格忽略)
│       └── .gitkeep
├── dist/                         # 编译产物 (默认内置 R27 预编译结果，受版本控制)
│   ├── catia_api.db              # SQLite 单文件数据库 (带 FTS5 全文索引)
│   ├── catia_api.json            # 结构化精简 JSON
│   ├── index.json                # L0 超轻量级框架-类速查索引 (~5KB)
│   └── types/                    # (扩展) 自动生成的 .pyi / .d.ts 类型定义文件
├── src/                          # 核心解析与查询引擎 (Python 3.10+)
│   ├── parser/                   # ETL 提取与脱水流水线
│   │   ├── __init__.py
│   │   ├── chm_unpacker.py       # CHM 解包适配器 (7z / hh.exe)
│   │   ├── html_parser.py        # BeautifulSoup 核心抽取器
│   │   ├── inheritance.py        # 继承树解析与父类方法自动合并引擎
│   │   ├── usecase_parser.py     # 官方 VBScript 用例清洗器
│   │   └── builder.py            # 数据库生成与完整性校验器
│   ├── engine/                   # 本地轻量化检索核心
│   │   ├── __init__.py
│   │   └── query_engine.py       # 精准类检索、继承链展开、全文搜索
│   ├── cli/                      # 命令行交互工具
│   │   └── catalyst_cli.py       # 面向开发者与 AI Agent 的极简 CLI
│   └── mcp/                      # Model Context Protocol 服务端
│       └── server.py             # 适配 Antigravity / Claude / Cursor
├── skills/                       # 开箱即用的 AI Agent 技能定义
│   └── catia-v5-automation/
│       ├── SKILL.md              # 零预载 Token 技能规范
│       └── resources/
├── docs/                         # 技术文档与复刻指南
│   ├── chm_extraction_guide.md   # 本地 CATIA 安装路径提取 CHM 指引
│   ├── reproduction_guide.md     # 复刻其他版本的完整 SOP
│   ├── architecture.md           # 架构设计与 Schema 规范
│   └── ai_integration.md         # AI 工具接入指南
├── tests/
│   ├── test_parser.py
│   └── test_query.py
├── build.py                      # 一键构建入口脚本
├── .gitignore                    # 忽略 data/raw/*, *.pyc 等
├── pyproject.toml
├── requirements.txt
├── LICENSE                       # MIT License
└── README.md                     # 中英双语开源自述文件
```

---

## 4. 统一核心数据模型 (Unified Schema)

```json
{
  "framework": "PartInterfaces",
  "name": "Pad",
  "type": "interface",
  "inherits": ["Prism", "SketchBasedShape", "Shape", "AnyObject"],
  "description": "Represents the pad shape created by extruding a sketch.",
  "properties": [
    {
      "name": "FirstLimit",
      "type": "Limit",
      "readonly": true,
      "declared_in": "Prism",
      "description": "Returns the first prism limit."
    }
  ],
  "methods": [
    {
      "name": "GetDirection",
      "declared_in": "Prism",
      "return_type": "void",
      "params": [
        { "name": "ioDirection", "type": "CATSafeArrayVariant", "direction": "inout" }
      ],
      "description": "Returns the prism direction with absolute coordinates.",
      "sample": "Dim dirArray(2)\nCall firstPrism.GetDirection(dirArray)"
    }
  ]
}
```

---

## 5. 实施阶段规划

### 阶段一：仓库基础设施
1. 初始化 `.gitignore`（排除 `data/raw/*`）、`MIT LICENSE`。
2. 存放 R27 版本 `V5Automation.chm` 至 `data/V5Automation.chm`。
3. 建立 `requirements.txt`（`beautifulsoup4`, `lxml`）与目录骨架。
4. 创建 `build.py` 顶层入口脚本框架。

### 阶段二：ETL 解析与脱水流水线 (`src/parser/`)
1. **`chm_unpacker.py`**：调用 7z / `hh.exe` 解包 CHM 到 `data/raw/`。
2. **`html_parser.py`**：精准抓取 `interface_*.htm` 和 `enum_*.htm` 中的类定义、方法签名、参数方向、属性与说明。
3. **`inheritance.py`**：递归分析 `generatedFatherClass` 与 `CAAMain.xml`，合并父类成员并标注 `declared_in`。
4. **`usecase_parser.py`**：提取 `online/CAAScd*UseCases` 下的 VBScript 实战代码块。
5. **`builder.py`**：一键生成 `dist/` 下的 SQLite（FTS5）+ JSON + `index.json`。

### 阶段三：Token 极速检索工具与 Agent 技能
1. **CLI (`catalyst_cli.py`)**：
   - `python catalyst_cli.py get Pad` → 紧凑 Markdown 签名（< 300 Tokens）
   - `python catalyst_cli.py search "fillet"` → 匹配的方法与所属类
   - `python catalyst_cli.py enum CatHoleType` → 枚举值速查
2. **MCP Server (`src/mcp/server.py`)**：标准 MCP 工具（`get_class_doc`, `search_api`, `get_enum`, `get_use_case`）。
3. **Agent Skill (`skills/catia-v5-automation/`)**：Antigravity 原生 Skill，支持 0 预载、按需查询。

### 阶段四：文档、测试与开源发布
1. 编写单元测试，验证 Part/GSM/Assembly/Drafting 核心模块提取完整性。
2. 撰写中英双语 `README.md`、`chm_extraction_guide.md`、`reproduction_guide.md`。
3. 提交 R27 预编译产物到 `dist/`，确保克隆即用。

---

## 6. 验证与质量保证

* **解析完整性**：针对 `Pad`、`HybridShapeLoft`、`DrawingView`、`Product` 验证属性/方法提取率 100%，继承链合并正确。
* **Token 基准测试**：单类卡片 < 300 Tokens，L0 索引 < 200 Tokens。
* **端到端冒烟测试**：`build.py` 从 CHM 到 `dist/` 全流程无报错。
