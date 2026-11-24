<div align="center">

# CATalyst

**面向 AI Agent 的 CATIA V5 全栈离线知识引擎与 MCP Server**

将 CATIA V5 封闭的 CHM Automation 文档、GB 级离线 HTML User's Guide、`CATNls` 选项词典与官方 CAD/脚本样板，转化为亚 10ms 响应、版本严格对齐、零幻觉的本地 SQLite FTS5 真理库。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://python.org)
[![MCP Ready](https://img.shields.io/badge/MCP-10%20Tools-blueviolet.svg)](#mcp-server-工具清单)

[English](README.md) · **简体中文**

</div>

---

## 为什么需要 CATalyst（核心意义）

用 AI Agent 做 CATIA V5 工程自动化，长期卡死在 4 个底层断层上：

1. **COM API 幻觉与继承链断裂**：CATIA V5 拥有 **80+ Framework、1,100+ COM 接口**，全部封死在二进制 `V5Automation.chm` 中。原始页面不展示父类成员（例如 `Pad` 页面看不到继承自 `Prism` 的 `FirstLimit`、`DirectionOrientation`），导致模型频繁捏造接口或在 `pywin32` `[out]` 参数解包上踩坑。
2. **非 COM 工程盲区**：大量决定 CATIA 落地成败的能力并不在 COM Automation 里——例如无 `SettingController` 的 `Tools > Options` 选项（`CatalogOption.CATSettings`）、批处理协议（`CreateCatalogFromcsv` CSV 硬语法、`CNEXT -batch`）、以及 GUI-only 架构边界（如 PKT `Document Template` 与 Unresolved `Part Family` 的选型差异）。
3. **GB 级离线帮助不可直用**：完整版达索 `Bxxdoc` 体积超过 **2.2 GB（78,000+ 文件）**，其中 93% 是二进制 `.CATPart`/`.cgr`/`.model` 和图片。全盘遍历直接超时，原始 FrontPage HTML 塞满噪音标签，瞬间撑爆上下文 Token。
4. **跨版本漂移与路径强耦合**：混读 R21/R27/R32 文档会静默破坏脚本，而把本机绝对路径写死进索引库会导致知识库无法跨机器复现或团队共享。

### CATalyst 的架构解法

CATalyst 严格坚守**纯只读知识大脑定位**（不耦合任何活体 `win32com` 建模副作用，CATIA 崩溃绝不连坐字典服务），采用 **双库解耦 + 纯相对路径可移植架构**：

```text
  [核心开源库: dist/catalyst.db (~9 MB)]
  ├── 官方 V5Automation.chm    ──▶ 继承链融合 + IDL 精准签名 + 3,700+ 官方示例
  └── 精选工业实战 Recipe       ──▶ AST 语法校验、安全脱敏的纯 Python win32com 配方
                                             │
  [可选本地扩展库: dist/local/catalyst_docs.db (~120 MB, .gitignore 隔离)]
  ├── Bxxdoc/English/online/   ──▶ 12,000+ User's Guide 与 Tools>Options 页面 (TOC + ix-* + 官方警告)
  ├── Bxx/win_b64/msgcatalog/  ──▶ 237,000+ 清洗后的 CATNls 界面文案 <-> 底层选项键映射
  └── samples/ 与 startup/      ──▶ 文本样板 (全文入库) + 二进制 CAD 模板 (仅存相对路径元数据)
                                             │
                                             ▼
            ┌────────────────────────────────┼────────────────────────────────┐
            ▼                                ▼                                ▼
     MCP Server (10 Tools)            CLI (catalyst_cli.py)             Agent Skill
(Antigravity / Claude / Codex 等)      (< 300 Token 卡片)              (零预载按需召回)
```

### 核心能力与突破

- **零幻觉 COM API 真理源**：自动递归融合继承链（`Pad -> Prism -> SketchBasedShape -> Shape -> AnyObject`）并标注 `declared_in`；支持 Enum 双向反查、属性/方法反向查宿主接口、`Selection.Search` 精确语法，以及 `pywin32` `[out]` / `CATSafeArrayVariant` 调用提示。
- **方法级调用约束与已知实现差异 (Known Implementation Caveats)**：针对达索底层实现与 IDL 声明存在契约背离的高危接口（如 `Material.PutIcon` 声明为 `iPath` 却强求以反斜杠结尾的目录路径导致 `E_FAIL`、批处理无头环境限制、文件独占锁死等），自动在接口卡片中挂载结构化 `pitfall_warning`、底层根因剖析与安全调用范式。
- **官方源码与用例双向穿透引擎 (Doc & Sample Code Linkage)**：建立 2,415 个官方样板宏与 12,179 篇 HTML 的反向索引表，精准定位 14,473 处实战调用行号，解冻 82 个原零用例接口；`get_catia_interface` 自动输出关联的官方文档切片与带行号的脚本调用上下文。
- **2.24 GB 官方离线手册秒级建库、亚 10ms 检索**：多进程 `lxml` 流水线数秒解析 12,500+ 页 HTML，原生榨干达索 `CATIA_P3_TOC.xml` 产品分类树、`<a name="ix-...">` 官方索引词、`<a name="ToolsOptions...">` 选项锚点、`awarning.gif` 官方避坑警告、页面间 `linked_docs` 跳转、`linked_files` 关联样板及有效截图；基于 SQLite FTS5 External Content Table（正文零双份冗余）+ BM25 列权重倾斜 + CamelCase 自动切词回退（搜 `FavoriteCatalog` 自动命中 `Favorite Catalog`）。
- **100% 纯相对路径可移植库**：`catalyst_docs.db` **不写入任何机器绝对路径**（`portable_relative_paths: true`），内置 `catia_release` 版本水印（如 `B27`）。在任意机器只需于 MCP `env` 配置 `CATALYST_DOC_ROOT` / `CATALYST_INSTALL_ROOT`，运行时自动展开本机 `abs_path`——HTML 原页、有效截图（供多模态 Agent 按需 `read_file` 看图）、文本样板（`.csv`/`.CATScript`/`.xml`）及二进制 CAD 样板（`.CATPart`/`.CATProduct`/`.catalog`）全链路直达。
- **真机实锤工业 Recipe 库**：内置多条经过 CATIA 内核实测验证的避坑配方（无头 `CNEXT -batch` 建 Catalog 避开空 `章节.1` 根坑、`CATBatGenXMLSet`/`CATBatImpXMLSet` `.CATSettings` XML 往返、`.txt` DesignTable 强制 CRLF 防静默失步、`Relation.Hidden` 封装与 `Product.Source`、Catalog 三模入库与 PKT `Document Template` 边界、STEP 批量导出、BOM/Inertia、Bounding Box、工程图 Title Block）。
- **优雅降级即插即用**：未构建 `catalyst_docs.db` 时，核心 6 个 API/Recipe 工具零配置开箱即用；本地建好扩展库后，新增 4 个离线文档/配置/样板工具自动激活。

---

## 本地构建与环境隔离

- **本地按需构建**：核心库（`dist/catalyst.db`）与可选离线文档库（`dist/local/catalyst_docs.db`）均在本地由本机 CATIA V5 文档生成，并由 `.gitignore` 忽略。
- **默认虚拟环境隔离**：全流程推荐通过 `uv sync` / `uv run` 在项目专属 `.venv/` 中运行；`build.py` 与 `build_docs.py` 若检测到运行在全局 Python 下会显式发出告警。
- **零系统侵入**：读取本机 CATIA 路径或写入本机私有配置（`dist/local/paths.json`）前先打印读写清单；**绝不修改系统 `PATH`、Windows 注册表或 CATIA 安装目录**。

---

## 快速开始

### 环境要求

| 依赖项 | 级别 | 说明 |
| :--- | :--- | :--- |
| **Python 3.10+** 与 **[uv](https://docs.astral.sh/uv/)** | 必需 | 自动管理项目隔离 `.venv/`（全部依赖均提供预编译 wheel，无需 C++ 编译环境）。 |
| **[7-Zip (`7z`)](https://www.7-zip.org/)** | **强烈推荐**（Linux/macOS 原地解包 `.chm` 时必需） | 极速且完全免疫含空格路径（Windows：`winget install 7zip.7zip`；macOS：`brew install p7zip`；Ubuntu：`sudo apt install p7zip-full`）。Windows 未装 7-Zip 时，安装脚本会让你明确选择「中断去装 7-Zip / 手动指定 `7z.exe` / 显式使用 `hh.exe`（`--use-hh`）」。 |
| **本机 CATIA V5 文档** | `V5Automation.chm` 必需 / `Bxxdoc` 可选 | Windows 下通过 `CATEnv` 自动发现（强制版本对齐）；若未找到，安装脚本会交互提示输入或直接拖入路径（兼容空格及 `/`、`\`）。 |

### 一键安装（推荐）

一条命令自动完成「同步 `.venv` → 检查 7-Zip（缺失时交互选择）→ 探测或指定 `V5Automation.chm` 与同版本 `Bxxdoc` → 构建本地 SQLite 知识库 → 安全合并写入 MCP 配置（自动备份 `.bak`）→ 端到端验收」：

```powershell
# Windows (PowerShell)
git clone https://github.com/zedeeee/CATalyst.git
cd CATalyst
.\install.ps1
# 若新机器默认策略阻止运行本地脚本：
# powershell -ExecutionPolicy Bypass -File .\install.ps1

# 常用参数示例：
# .\install.ps1 --chm "D:\Dassault\B27\win_b64\code\bin\V5Automation.chm"
# .\install.ps1 --client claude     # 内置 antigravity（默认）、claude、cursor，或用 --config <路径> 适配 Codex 等其他 MCP Agent / 编辑器
# .\install.ps1 --yes               # 非交互模式（Windows 无 7-Zip 时需显式追加 --use-hh）
```

```bash
# macOS / Linux（需安装 p7zip/7z 原地解包 CHM，或直接复用已构建好的 dist/catalyst.db）
./install.sh
```

### 分步手动安装

#### 1. 初始化项目隔离虚拟环境

```bash
git clone https://github.com/zedeeee/CATalyst.git
cd CATalyst
uv sync --extra dev
```

#### 2. 初始化核心 API 数据库（`dist/catalyst.db`）

`build.py` 会通过 `CATEnv` 自动定位本机 `<CATInstallPath>/code/bin/V5Automation.chm`，确认后本地生成 `dist/catalyst.db`（支持 `--chm` 手动指定、Windows 无 7-Zip 时 `--use-hh`、或 `--with-docs` 一步同时构建离线文档库）：

```bash
# 通过 CATEnv 自动发现本机 V5Automation.chm（交互确认后本地构建）
uv run python build.py

# 手动指定 CHM 路径，或一步同时构建核心库 + 离线文档扩展库：
uv run python build.py --chm "D:/Dassault/B27/win_b64/code/bin/V5Automation.chm"
uv run python build.py --with-docs
```

#### 3. 一键构建本地版本对齐离线文档库（`dist/local/catalyst_docs.db`）

直接指向本机顶级 `Bxxdoc` 与 `Bxx` 目录（自动归一化子目录，且绝不向数据库写入任何本机绝对路径）：

```bash
uv run python build_docs.py \
  --doc-root "C:/Program Files/Dassault Systemes/B27doc" \
  --install-root "C:/Program Files/Dassault Systemes/B27" \
  --release B27
```

- 默认产物落盘在 `dist/local/catalyst_docs.db`（已在 `.gitignore` 中忽略）。
- 支持 `--modules cceug_C2,bascuctg_C2` 做定向增量调试，支持 `--workers N` 调节并发进程数。

#### 全新电脑 5 级路径自动发现与绑定机制

在新机器上，CATalyst 按严格优先级解析本机 CATIA 文档与安装根目录：
1. **显式 CLI / MCP `env`（最高优先级）**：`CATALYST_DOC_ROOT` 与 `CATALYST_INSTALL_ROOT`（直接填顶级 `Bxxdoc` / `Bxx` 即可）。
2. **本机私有配置**：`dist/local/paths.json`（已被 `.gitignore` 忽略；跑 `build_docs.py` 自动写入；若是直接拷贝团队预编译的 `catalyst_docs.db`，执行 `uv run python build_docs.py --set-paths` 即可一步绑定本机目录无需重建）。
3. **达索官方 `CATEnv` 自动嗅探**：自动读取 `%ProgramData%\DassaultSystemes\CATEnv\*.txt` 里的 `CATDocView` 与 `CATInstallPath`——无论装在 `C:`/`D:`/`E:` 哪个盘都零配置直出。
4. **标准默认目录兜底**：扫描 `C:\Program Files\Dassault Systemes\B*doc` 与 `B*\win_b64`。
5. **交互引导 / MCP 提示兜底**：全都没找到时，CLI 在交互终端直接提示输入路径；MCP 运行时在保持全文搜索可用的前提下返回 `path_setup_hint`，提示 Agent 询问用户配置根目录。

---

## MCP Server 配置

运行 `.\install.ps1` / `./install.sh` 会自动将 `catalyst` 合并写入目标 MCP 客户端配置（支持 Antigravity `~/.gemini/config/mcp_config.json`、Claude `claude_desktop_config.json`、Cursor `~/.cursor/mcp.json`，以及通过 `--config <路径>` 适配 Codex、Claude Code 等其他支持 MCP 的 AI Agent 与代码编辑器）。如需手动配置，可参考：

```json
{
  "mcpServers": {
    "catalyst": {
      "command": "uv",
      "args": [
        "--directory",
        "<path-to-CATalyst>",
        "run",
        "python",
        "-m",
        "src.mcp.server"
      ],
      "env": {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "CATALYST_INSTALL_ROOT": "C:\\Program Files\\Dassault Systemes\\B27",
        "CATALYST_DOC_ROOT": "C:\\Program Files\\Dassault Systemes\\B27doc"
      }
    }
  }
}
```

> 请使用当前系统的原生路径分隔符（Windows 在 JSON 中写 `\\`，macOS/Linux 写 `/`）。`CATALYST_DOC_ROOT` 默认优先使用本机 `Bxxdoc` 目录（若仅使用 6 个核心 COM API / Recipe 工具可省略）。将已构建好的 `catalyst_docs.db` 拷贝到另一台电脑复用时，无需重建库，直接通过 `CATALYST_DOC_ROOT` 或 `uv run python build_docs.py --set-paths --doc-root <前缀>` 即可更换运行时前缀（优先本地路径，亦可选 Samba UNC 或 `http(s)://` 在线地址）。

可选环境变量：
- `CATALYST_DB_PATH`：覆写核心 `catalyst.db` 路径。
- `CATALYST_DOCS_DB_PATH`：覆写或指向团队共享的 `catalyst_docs.db` 路径。
- `CATALYST_7Z_PATH`：手动指定 `7z`/`7za` 可执行文件路径。

---

## MCP Server 工具清单

| 分类 | Tool | 职责 |
| :--- | :--- | :--- |
| **COM API** | `get_catia_interface` | 获取接口完整签名（含继承成员 `declared_in`）、`pywin32` `[out]` 解包提示、方法级实现约束 (`pitfall_warning`)，以及关联的官方文档与样板宏源码 (`linked_official_docs`, `linked_sample_scripts`) |
| **COM API** | `search_catia_api` | FTS5 BM25 检索接口/枚举/属性/方法（附宿主接口反查与 0 命中文档引导） |
| **COM API** | `get_catia_enum` | 枚举双向查询（按名称、数值索引或成员名反查） |
| **COM API** | `get_catia_usecases` | 双轨查询官方 VBScript 示例与社区 Python `win32com` 实例 |
| **COM API** | `search_catia_recipes` | 按自然语言意图 BM25 检索工业实战避坑 Recipe |
| **COM API** | `get_catia_search_syntax` | 查询 `Selection.Search` 精确工作台前缀与语法 |
| **离线文档** | `search_catia_docs` | BM25 检索 User's Guide、`Tools > Options` 与 Automation 技术文章（支持 `category`/`module`/`solution` 过滤） |
| **离线文档** | `get_catia_doc_page` | 读取清洗后的页面正文、按章节切片、官方警告、`linked_docs`、`linked_files` 与解析后的截图 `abs_path` |
| **配置映射** | `search_catia_settings` | 检索 `*.CATNls` UI 文案与选项键（支持 CamelCase 切词回退），自动关联 `Tools > Options` 文档页与 `CATBatGen/ImpXMLSet` 提示 |
| **官方样板** | `search_catia_samples` | 检索官方纯文本样板（`.csv`/`.CATScript`/`.txt`/`.xml`，支持吐出全文）及二进制 CAD 样板（`.CATPart`/`.catalog` 等，返回相对路径与运行时 `abs_path`） |

---

## CLI 命令行速查

全部 MCP 能力均在 `catalyst_cli.py` 提供对称子命令：

```bash
# 核心 COM API 与实战 Recipe
uv run python catalyst_cli.py get Pad --member GetDirection
uv run python catalyst_cli.py search "PartNumber" --type property
uv run python catalyst_cli.py enum CatProductSource --value 1
uv run python catalyst_cli.py recipe "CreateCatalogFromcsv"
uv run python catalyst_cli.py syntax --workbench PartDesign

# 离线手册、CATNls 配置与官方样板
uv run python catalyst_cli.py docs "Catalog Batch Mode" --category user_guide
uv run python catalyst_cli.py doc-page "cceug_C2/cceugbt0102.htm" --section "Batch Mode"
uv run python catalyst_cli.py settings "FavoriteCatalog"
uv run python catalyst_cli.py samples "BatchCatalog" --ext .csv --content
uv run python catalyst_cli.py samples "AISC_C" --ext .catpart
```

---

## 项目结构

```text
CATalyst/
├── data/
│   ├── recipes/                    # 经 AST 校验的社区工业 Recipe 库 (JSON)
│   └── raw/                        # 本地解包的 CHM HTML (.gitignore 忽略)
├── dist/
│   ├── catalyst.db                 # 本地构建的核心 COM API + Recipe 数据库 (.gitignore 忽略)
│   └── local/                      # 本地可移植 catalyst_docs.db 与 paths.json (.gitignore 忽略)
├── docs/
│   ├── architecture.md             # 系统架构、Schema、路径发现与排错参考
│   └── tutorial.md                 # CLI 与 MCP 实战使用手册
├── src/
│   ├── parser/                     # CHM 解包器 (7z/hh)、HTML 解析、继承链融合、离线文档 ETL
│   ├── engine/                     # 线程安全 SQLite FTS5 检索引擎 (db.py, docs_db.py, local_config.py)
│   ├── mcp/                        # FastMCP / MCPServer 服务端，暴露 10 个工具 (server.py)
│   └── client/                     # 可选宿主机诊断工具
├── skills/catalyst-query/          # Agent Skill 定义 (SKILL.md)
├── tests/                          # 自动化测试套件（引擎、FTS5、Schema、跨机移植、安装器、MCP）
├── install.ps1 / install.sh        # 一键安装入口（Windows / macOS / Linux）
├── install.py                      # 跨平台安装与 MCP 配置注册核心脚本
├── build.py                        # 核心 API 库构建入口 + 8 项冒烟测试
├── build_docs.py                   # 离线文档/CATNls/样板扩展库构建入口 + 冒烟测试
├── catalyst_cli.py                 # 对称 CLI 入口
├── AGENTS.md                       # AI Agent 防幻觉规范与快速部署 SOP
├── README.md                       # 英文主文档（默认）
└── README_CN.md                    # 简体中文文档
```

## 延伸文档

- [系统架构与部署排错手册](docs/architecture.md)
- [CLI 与 MCP 实战使用手册](docs/tutorial.md)
- [社区实战配方贡献指南](data/recipes/README.md)
- [AI Agent 规范与快速部署 SOP](AGENTS.md)

---

## 测试验证

```bash
uv run pytest
```

## 致谢与许可证

- 由 **Google Antigravity & Gemini** 协助架构设计与构建。
- 基于 [MIT License](LICENSE) 开源。
