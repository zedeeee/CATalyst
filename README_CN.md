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
   (Antigravity / Cursor / Claude)      (< 300 Token 卡片)              (零预载按需召回)
```

### 核心能力与突破

- **零幻觉 COM API 真理源**：自动递归融合继承链（`Pad -> Prism -> SketchBasedShape -> Shape -> AnyObject`）并标注 `declared_in`；支持 Enum 双向反查、属性/方法反向查宿主接口、`Selection.Search` 精确语法，以及 `pywin32` `[out]` / `CATSafeArrayVariant` 调用提示。
- **2.24 GB 官方离线手册秒级建库、亚 10ms 检索**：多进程 `lxml` 流水线数秒解析 12,500+ 页 HTML，原生榨干达索 `CATIA_P3_TOC.xml` 产品分类树、`<a name="ix-...">` 官方索引词、`<a name="ToolsOptions...">` 选项锚点、`awarning.gif` 官方避坑警告、页面间 `linked_docs` 跳转、`linked_files` 关联样板及有效截图；基于 SQLite FTS5 External Content Table（正文零双份冗余）+ BM25 列权重倾斜 + CamelCase 自动切词回退（搜 `FavoriteCatalog` 自动命中 `Favorite Catalog`）。
- **100% 纯相对路径可移植库**：`catalyst_docs.db` **不写入任何机器绝对路径**（`portable_relative_paths: true`），内置 `catia_release` 版本水印（如 `B27`）。在任意机器只需于 MCP `env` 配置 `CATALYST_DOC_ROOT` / `CATALYST_INSTALL_ROOT`，运行时自动展开本机 `abs_path`——HTML 原页、有效截图（供多模态 Agent 按需 `read_file` 看图）、文本样板（`.csv`/`.CATScript`/`.xml`）及二进制 CAD 样板（`.CATPart`/`.CATProduct`/`.catalog`）全链路直达。
- **真机实锤工业 Recipe 库**：内置多条经过 CATIA 内核实测验证的避坑配方（无头 `CNEXT -batch` 建 Catalog 避开空 `章节.1` 根坑、`CATBatGenXMLSet`/`CATBatImpXMLSet` `.CATSettings` XML 往返、`.txt` DesignTable 强制 CRLF 防静默失步、`Relation.Hidden` 封装与 `Product.Source`、Catalog 三模入库与 PKT `Document Template` 边界、STEP 批量导出、BOM/Inertia、Bounding Box、工程图 Title Block）。
- **优雅降级即插即用**：未构建 `catalyst_docs.db` 时，核心 6 个 API/Recipe 工具零配置开箱即用；本地建好扩展库后，新增 4 个离线文档/配置/样板工具自动激活。

---

## 快速开始

### 环境要求

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)（推荐）
- 可选（启用离线文档扩展库）：与目标版本一致的本机 CATIA V5 离线帮助目录（`Bxxdoc`）及安装目录（`Bxx/win_b64`）。

### 1. 安装依赖

```bash
git clone https://github.com/zedeeee/CATalyst.git
cd CATalyst
uv sync --extra dev
```

### 2. 核心 API 数据库（`dist/catalyst.db`）

仓库默认自带 R27 预编译核心库，克隆即可使用。如需适配本机其他版本，提取本机 `V5Automation.chm`（典型路径 `<CATInstall>/win_b64/code/bin/V5Automation.chm`，详见 [docs/chm_extraction_guide.md](docs/chm_extraction_guide.md)）覆盖后重建：

```bash
cp /path/to/V5Automation.chm data/V5Automation.chm
uv run python build.py
```

### 3. 一键构建本地版本对齐离线文档库（`dist/local/catalyst_docs.db`）

直接指向本机顶级 `Bxxdoc` 与 `Bxx` 目录（自动归一化子目录，且绝不向数据库写入任何本机绝对路径）：

```bash
uv run python build_docs.py \
  --doc-root "C:/Program Files/Dassault Systemes/B27doc" \
  --install-root "C:/Program Files/Dassault Systemes/B27" \
  --release B27
```

- 默认产物落盘在 `dist/local/catalyst_docs.db`（已在 `.gitignore` 中排除，避免商业文档资产污染 Git）。
- 支持 `--modules cceug_C2,bascuctg_C2` 做定向增量调试，支持 `--workers N` 调节并发进程数。

---

## MCP Server 配置

将 CATalyst 注册到 MCP 客户端配置（如 Antigravity 的 `~/.gemini/config/mcp_config.json`，或 Claude Desktop / Cursor）。在 `env` 中配置两个根目录，即可让所有可移植相对路径在运行时动态解析为本机真实路径：

```json
{
  "mcpServers": {
    "catalyst": {
      "command": "uv",
      "args": ["run", "python", "-m", "src.mcp.server"],
      "cwd": "<path-to-CATalyst>",
      "env": {
        "CATALYST_DOC_ROOT": "C:/Program Files/Dassault Systemes/B27doc",
        "CATALYST_INSTALL_ROOT": "C:/Program Files/Dassault Systemes/B27"
      }
    }
  }
}
```

可选环境变量：
- `CATALYST_DB_PATH`：覆写核心 `catalyst.db` 路径。
- `CATALYST_DOCS_DB_PATH`：覆写或指向团队共享的 `catalyst_docs.db` 路径。

---

## MCP Server 工具清单

| 分类 | Tool | 职责 |
| :--- | :--- | :--- |
| **COM API** | `get_catia_interface` | 获取接口完整签名（含继承成员 `declared_in`）、`pywin32` `[out]` 解包提示与按成员过滤 |
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
│   ├── V5Automation.chm            # 官方 Automation CHM 源文件
│   └── recipes/                    # 经 AST 校验的社区工业 Recipe 库 (JSON)
├── dist/
│   ├── catalyst.db                 # 预编译核心 COM API + Recipe 数据库
│   └── local/                      # 本地版本对齐 catalyst_docs.db (.gitignore 隔离)
├── src/
│   ├── parser/                     # CHM 解析、继承链融合、离线文档/CATNls/样板 ETL 流水线
│   ├── engine/                     # 线程安全 SQLite FTS5 检索引擎 (db.py, docs_db.py, search_grammar.py)
│   ├── mcp/                        # FastMCP / MCPServer 服务端，暴露 10 个工具 (server.py)
│   └── client/                     # 可选宿主机诊断工具
├── skills/                         # Agent Skill 定义
├── tests/                          # Pytest 测试套件（单元、FTS5、Schema、跨机移植、MCP 测试）
├── build.py                        # 核心 API 库构建入口 + 8 项冒烟测试
├── build_docs.py                   # 离线文档/CATNls/样板扩展库构建入口 + 冒烟测试
├── catalyst_cli.py                 # 对称 CLI 入口
├── README.md                       # 英文主文档（默认）
└── README_CN.md                    # 简体中文文档
```

---

## 测试验证

```bash
uv run pytest
```

## 许可证

[MIT License](LICENSE)
