<div align="center">

# CATalyst

**CATIA V5 Automation API Knowledge Base & AI Agent Toolkit**

将 CATIA V5 官方 Automation 文档转化为结构化、可检索、Token 极致优化的 AI 知识库

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://python.org)

[English](#english) · [简体中文](#简体中文)

</div>

---

## 简体中文

### 痛点

CATIA V5 Automation 拥有 **80+ Framework、数千个 COM 接口**，官方文档以 CHM 格式封装，存在以下致命问题：

- **AI 不可用**：CHM 是编译后的二进制格式，LLM 无法直接读取，只能依赖不可靠的世界知识"猜" API 签名。
- **继承链断裂**：`Pad` 页面里看不到从 `Prism` 继承来的 `FirstLimit`、`DirectionOrientation` 等关键属性，导致 AI 产生幻觉。
- **Token 爆炸**：原始 HTML 充斥大量 JS/CSS 模板噪音，单个简单类占用数千 Token，根本无法批量加载上下文。

### CATalyst 做了什么

```
V5Automation.chm ──▶ 解包 ──▶ 结构化解析 ──▶ 继承链融合 ──▶ 紧凑数据库
                                                              │
                                          ┌───────────────────┼───────────────────┐
                                          ▼                   ▼                   ▼
                                     CLI 查询            MCP Server          Agent Skill
                                   (< 300 Tokens)     (IDE 原生集成)      (零预载按需召回)
```

1. **ETL 解析引擎**：从官方 CHM 中精准提取全部接口、方法签名、参数类型/方向、枚举常量和官方 VBScript 示例。
2. **继承链智能融合**：自动递归合并父类（如 `Prism` → `SketchBasedShape` → `Shape` → `AnyObject`）的属性与方法，标注 `declared_in` 来源，彻底消除遗漏。
3. **多形态 Token 零浪费检索**：
   - **CLI**：`python catalyst_cli.py get Pad` → 紧凑 Markdown 签名卡片（< 300 Tokens）
   - **MCP Server**：适配 Antigravity / Claude Desktop / Cursor 等 IDE 的原生 Model Context Protocol
   - **Agent Skill**：零预载、按需召回的 AI Agent 技能

### 单槽位即插即用架构

CATIA V5 Automation 接口**严格向后兼容**，跨版本重复度 > 95%。仓库采用**单槽位设计**，不搞多版本子文件夹的过度设计：

| 场景 | 操作 | 结果 |
| :--- | :--- | :--- |
| 普通用户 / AI 用户 | `git clone` → 直接使用 | 仓库自带 R27 预编译数据库，零配置 |
| 其他版本用户（如 R21） | 覆盖 `data/V5Automation.chm` → `python build.py` | 一行命令重建专属数据库 |

### 项目结构

```
CATalyst/
├── data/
│   ├── V5Automation.chm          # 官方 CHM 源文件 (默认 R27)
│   └── raw/                      # 解包后的 HTML (.gitignore 忽略)
├── dist/                         # 编译产物：SQLite DB + JSON + 索引
├── src/
│   ├── parser/                   # ETL 解析与脱水流水线
│   ├── engine/                   # 本地检索引擎
│   ├── cli/                      # 命令行工具
│   └── mcp/                      # MCP Server
├── skills/                       # AI Agent 技能定义
├── docs/                         # 技术文档与复刻指南
├── tests/                        # 单元测试
├── build.py                      # 一键构建入口
└── README.md
```

### 快速开始

#### 环境要求

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (极速 Python 包管理器，推荐)
- Windows（CHM 解包依赖 7z 或 `hh.exe`）

#### 安装与构建

```bash
git clone https://github.com/zedeeee/CATalyst.git
cd CATalyst
uv venv
uv pip install -r requirements.txt

# 使用默认 R27 版本构建数据库
uv run build.py
```

#### 适配你自己的 CATIA 版本

1. 从本地 CATIA 安装目录提取 CHM 文件（详见 [CHM 提取指南](docs/chm_extraction_guide.md)）：
   ```
   典型路径：C:\Program Files\Dassault Systemes\B<Release>\win_b64\code\bin\V5Automation.chm
   ```
2. 覆盖仓库中的 CHM：
   ```bash
   cp /path/to/your/V5Automation.chm data/V5Automation.chm
   ```
3. 重新构建：
   ```bash
   python build.py
   ```

#### CLI 使用

```bash
# 查询类的完整签名（含继承链合并）
python catalyst_cli.py get Pad

# 全文搜索 API
python catalyst_cli.py search "fillet"

# 查询枚举值
python catalyst_cli.py enum CatHoleType
```

### 贡献

欢迎提交 Issue 和 Pull Request。开发前请阅读 [docs/implementation_plan.md](docs/implementation_plan.md)。

### 许可证

[MIT License](LICENSE)

---

## English

### The Problem

CATIA V5 Automation ships with **80+ Frameworks and thousands of COM interfaces**, all locked inside a compiled CHM file:

- **AI-Inaccessible**: LLMs cannot read CHM binaries and must guess API signatures from unreliable world knowledge.
- **Broken Inheritance**: The `Pad` page doesn't show `FirstLimit` or `DirectionOrientation` inherited from `Prism`, causing LLM hallucinations.
- **Token Explosion**: Raw HTML is bloated with JS/CSS boilerplate — a single simple class wastes thousands of tokens.

### What CATalyst Does

1. **ETL Parser**: Extracts all interfaces, method signatures, parameter types/directions, enum constants, and official VBScript samples from the CHM.
2. **Inheritance Chain Fusion**: Recursively merges parent class members (e.g., `Prism` → `SketchBasedShape` → `Shape` → `AnyObject`), tagged with `declared_in` origin.
3. **Multi-Modal Zero-Waste Retrieval**:
   - **CLI**: `python catalyst_cli.py get Pad` → compact Markdown signature card (< 300 tokens)
   - **MCP Server**: Native Model Context Protocol for Antigravity / Claude Desktop / Cursor
   - **Agent Skill**: Zero-preload, on-demand recall

### Single-Slot Plug-and-Play Architecture

CATIA V5 Automation interfaces are **strictly backward-compatible** with > 95% overlap across releases. The repo uses a **single-slot design** — no multi-version subdirectory over-engineering:

| Scenario | Action | Result |
| :--- | :--- | :--- |
| General / AI users | `git clone` → use directly | Ships with R27 pre-built database, zero config |
| Other versions (e.g., R21) | Replace `data/V5Automation.chm` → `python build.py` | One command rebuilds everything |

### Quick Start

```bash
git clone https://github.com/zedeeee/CATalyst.git
cd CATalyst
uv venv
uv pip install -r requirements.txt
uv run build.py
```

To use your own CATIA version, copy your `V5Automation.chm` from:
```
C:\Program Files\Dassault Systemes\B<Release>\win_b64\code\bin\V5Automation.chm
```
into `data/V5Automation.chm`, then run `python build.py`.

### License

[MIT License](LICENSE)