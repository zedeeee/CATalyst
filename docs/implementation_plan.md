# CATalyst: 开源 CATIA V5 Automation 知识库与 AI Agent 工具链架构规划

## 1. 项目定位与核心目标

面向 **CATIA V5 全系列（R20–R30+）** 的 Automation COM 接口知识库转换与 AI 极速调用引擎。

* **专注 CATIA V5 体系**：精准适配 V5 Automation COM/IDL 接口规范，纯 `win32com` 原生开发，不引入任何第三方非标依赖。
* **单槽位即插即用（Single-Slot Design）**：仓库固定一个 CHM 槽位和一套产物路径，默认内置 R27 版本的 CHM 及预编译数据库，克隆即用。用户如需适配其他版本，覆盖 CHM 后一行命令重建。
* **继承链与签名无损修复**：自动解构并合并 `generatedFatherClass` 继承树，消除 API 遗漏与参数缺失。
* **双轨分离架构 (Dual-Track Architecture)**：
  * **官方真理库**：编译存储于 `dist/catalyst.db`，收录 1,137 个接口、9,576 个属性、9,908 个方法、335 个枚举及 3,766 条官方示例；
  * **社区实战配方库**：纯文本存储于 `data/recipes/*.json`，免编译、热重载、Git 友好，支持精准出处追溯（Provenance）。
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
| **普通用户 / AI 用户（90%）** | `git clone` → 直接使用 | 仓库自带 R27 预编译的 `dist/catalyst.db`，零配置零编译 |
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
│   ├── recipes/                  # 社区实战配方库 (纯文本 JSON，免编译热重载)
│   │   ├── README.md             # 社区贡献与 Provenance 追溯规范
│   │   └── community_recipes.json # 首批工业级实战配方种子
│   └── raw/                      # 解包后的 HTML 原始目录 (.gitignore 严格忽略)
│       └── .gitkeep
├── dist/                         # 编译产物 (默认内置 R27 预编译官方真理库)
│   └── catalyst.db               # 100% 官方 SQLite 单文件数据库 (带 FTS5 与索引)
├── src/                          # 核心解析与查询引擎 (Python 3.10+)
│   ├── parser/                   # ETL 提取与脱水流水线
│   │   ├── chm_unpacker.py       # CHM 解包适配器 (7z / hh.exe)
│   │   ├── html_parser.py        # BeautifulSoup 核心抽取器
│   │   ├── inheritance.py        # 继承树解析与父类方法自动合并引擎
│   │   ├── usecase_parser.py     # 官方 VBScript 用例清洗器
│   │   └── builder.py            # 数据库生成与完整性校验器
│   ├── engine/                   # 本地轻量化双轨检索引擎
│   │   └── db.py                 # 线程安全 SQLite 连接池 + 动态配方加载 + 官方优先排序
│   ├── cli/                      # 命令行交互工具
│   │   └── catalyst_cli.py       # 面向开发者与 AI Agent 的极简 CLI
│   └── mcp/                      # Model Context Protocol 服务端
│       └── server.py             # 适配 Antigravity / Claude / Cursor
├── skills/                       # 开箱即用的 AI Agent 技能定义
│   └── catalyst-query/
│       └── SKILL.md              # 零预载 Token 技能规范
├── docs/                         # 技术文档与复刻指南
│   ├── tutorial.md               # 开发者实战指南 (4 大实战场景 + MCP)
│   ├── chm_extraction_guide.md   # 本地 CATIA 安装路径提取 CHM 指引
│   └── implementation_plan.md    # 架构规划与实施交付全景 (本文件)
├── tests/
│   ├── test_engine.py            # 检索引擎双轨与枚举逆向测试
│   ├── test_mcp.py               # MCP Server 工具测试
│   └── test_recipes_schema.py    # 社区配方 Schema、URL 与 AST 校验测试
├── build.py                      # 一键构建入口脚本
├── catalyst_cli.py               # 根目录快速入口
├── AGENTS.md                     # Agent 防幻觉 API 检索准则
├── .gitignore                    # 忽略 data/raw/*, *.pyc 等
├── pyproject.toml
├── LICENSE                       # MIT License
└── README.md                     # 中英双语开源自述文件
```

---

## 4. 统一核心数据模型 (Unified Schema)

### 4.1 官方接口模型 (`interfaces`)
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

### 4.2 社区实战配方模型 (`data/recipes/*.json`)
```json
{
  "interface_name": "Product",
  "title": "遍历装配体树并批量导出各零件为 STEP 格式",
  "workbench": "Assembly",
  "tags": "batch-export,step,assembly,product,export",
  "provenance": {
    "source_type": "forum_archive",
    "source_url": "https://www.coe.org/p/fo/et/thread=26500",
    "source_ref": "COE Forum Topic: Batch Export Assembly Components to STEP",
    "author": "COE Community",
    "license": "MIT / Public Domain",
    "original_language": "VBScript",
    "verified_date": "2026-08-29"
  },
  "description": "遍历当前激活 Product 文档下的所有子部件，获取对应 PartDocument 并批量导出为 .stp 文件。",
  "code": "import win32com.client\n..."
}
```

---

## 5. 实施阶段规划与交付状态

### 阶段一：仓库基础设施 (已交付 ✅)
1. 初始化 `.gitignore`（排除 `data/raw/*`）、`MIT LICENSE`。
2. 存放 R27 版本 `V5Automation.chm` 至 `data/V5Automation.chm`。
3. 建立单槽位目录骨架与 `build.py` 顶层入口脚本。

### 阶段二：ETL 解析与脱水流水线 (已交付 ✅)
1. **`chm_unpacker.py`**：调用 7z / `hh.exe` 解包 CHM 到 `data/raw/`。
2. **`html_parser.py`**：精准抓取 `interface_*.htm` 和 `enum_*.htm` 中的类定义、方法签名、参数方向、属性与说明。
3. **`inheritance.py`**：递归分析 `generatedFatherClass` 与 `CAAMain.xml`，合并父类成员并标注 `declared_in`。
4. **`usecase_parser.py`**：提取 `online/CAAScd*UseCases` 下 3,766 条官方 VBScript 实战代码块。
5. **`builder.py`**：一键生成 `dist/catalyst.db` SQLite（带 FTS5）与索引。

### 阶段三：Token 极速检索工具与 Agent 技能 (已交付 ✅)
1. **CLI (`catalyst_cli.py`)**：
   - `python catalyst_cli.py get Pad` → 紧凑 Markdown 签名（< 300 Tokens）
   - `python catalyst_cli.py search "fillet"` → 匹配的方法、属性与所属类
   - `python catalyst_cli.py enum CatHoleType` → 枚举值与反向索引速查
   - `python catalyst_cli.py recipe "export step"` → 自然语言意图实战配方检索
   - `python catalyst_cli.py usecase Pad --source official|community` → 双轨用例检索
2. **MCP Server (`src/mcp/server.py`)**：标准 MCP 工具（`get_catia_interface`, `get_catia_enum`, `get_catia_usecases`, `search_catia_recipes`, `get_catia_search_syntax`）。
3. **Agent Skill (`skills/catalyst-query/`)**：Antigravity / Cursor 原生 Skill，支持 0 预载、按需查询。

### 阶段四：双轨分离与社区配方体系 (已交付 ✅)
1. 物理分离官方真理库（`dist/catalyst.db`）与社区配方库（`data/recipes/`）。
2. 构建首批 6 条经过脱敏与 AST 语法校验的工业级实战配方。
3. 建立 Provenance 可追溯链接与开源协议规范。
4. 编写 `tests/test_recipes_schema.py` 自动化合规测试套件。

### 阶段五：文档、测试与开源发布 (已交付 ✅)
1. 编写 32 项单元测试，验证 Part/GSM/Assembly/Drafting 核心模块提取完整性与 MCP 稳定性。
2. 撰写中英双语 `README.md`、`docs/tutorial.md`、`docs/chm_extraction_guide.md`。
3. 固化 AGENTS.md 防幻觉 Ground Truth 准则。

---

## 6. 验证与质量保证

* **解析完整性**：针对 `Pad`、`HybridShapeLoft`、`DrawingView`、`Product` 验证属性/方法提取率 100%，继承链合并正确。
* **Token 基准测试**：单类卡片 < 300 Tokens，极速按需加载。
* **端到端冒烟测试**：`build.py` 从 CHM 到 `dist/` 全流程无报错，32 项自动化测试全部通过。
