# CATalyst 架构与部署参考手册

本文档描述 CATalyst 当前版本的真实系统架构、数据库结构、路径解析规范与部署排错指南，供开发者与 AI Agent 快速理解与部署。

---

## 1. 整体架构（只读双库 + 相对路径可移植）

CATalyst 采用**纯只读知识平面**设计（不耦合实时 `win32com` 会话），通过两个解耦的本地 SQLite FTS5 数据库向 MCP Server（10 工具）和 CLI（`catalyst_cli.py`）提供毫秒级查询：

```text
本地 CATIA 资产（只读读取，绝不修改安装目录）
├── V5Automation.chm ──▶ chm_unpacker (7z 优先 / hh.exe 显式可选)
│                    ──▶ html_parser + inheritance + usecase_parser + builder
│                    ──▶ dist/catalyst.db (~9 MB，必选，驱动 6 个核心 MCP 工具)
│                            ▲
│                            │ 热加载
│                    data/recipes/*.json (纯文本社区实战配方，Git 托管)
│
└── Bxxdoc + Bxx/win_b64 (可选，版本对齐)
                     ──▶ docs_parser + docs_builder (多进程 lxml ETL)
                     ──▶ dist/local/catalyst_docs.db (~120 MB，驱动 4 个扩展 MCP 工具)
                     ──▶ dist/local/paths.json (本机路径缓存)
```

### 目录结构映射

| 路径 | 职责 |
| :--- | :--- |
| `install.ps1` / `install.sh` / `install.py` | 一键安装入口（同步 `.venv`、检查 7z、探测/交互指定路径、建库、安全写入 MCP 配置、端到端自检） |
| `build.py` | 核心 COM API 数据库构建器（生成 `dist/catalyst.db` + 8 项冒烟测试） |
| `build_docs.py` | 可选离线文档/设置/样板构建器与路径绑定工具（生成 `dist/local/catalyst_docs.db`） |
| `catalyst_cli.py` | 与 MCP 10 工具完全对称的本地 CLI 入口（含 `path` 对象导航子命令） |
| `src/parser/` | `chm_unpacker.py`、`html_parser.py`（提取完整成员 `<dl><dd>` / `Parameters` / `Returns`）、`inheritance.py`、`usecase_parser.py`、`builder.py`、`docs_parser.py`、`docs_builder.py` |
| `src/engine/` | `db.py`（核心库查询 + 自适应粒度 + FTS5 检索 + 配方热加载）、`docs_db.py`、`formatter.py`（紧凑 JSON 序列化 + CHM 截断文本清洗 + IDL 极简签名卡渲染）、`object_graph.py`（COM 对象模型有向图与最短路径寻路）、`pitfalls.py`（热加载 `data/pitfalls.json`）、`caveat_miner.py`（静态约束挖掘）、`linkage_builder.py`（返回类型传播反向索引）、`synonyms.py`、`text_utils.py`、`local_config.py`、`search_grammar.py` |
| `src/tools/` | `linkage_diff_reporter.py`（官方文档/样板源码穿透覆盖率对比看板生成器） |
| `src/mcp/server.py` | FastMCP / MCP Server，暴露 10 个只读工具 |
| `skills/catalyst-query/SKILL.md` | 跨项目 Agent Skill 定义 |
| `data/` | `data/pitfalls.json`（方法级调用约束规则）与 `data/recipes/*.json`（社区 `win32com` 配方） |
| `tests/` | 单元测试、Golden Query `Recall@K`/`MRR` 基准、`real_db` 本地体检门禁与可选 `live_catia` 沙盒冒烟 |

---

## 2. 数据库核心 Schema

### 2.1 `dist/catalyst.db`（核心 COM API + 配方库）
- `interfaces` / `properties` / `methods` / `enums` / `enum_values`：存储从 `V5Automation.chm` 提取并完成 `generatedFatherClass` 继承链融合的完整 IDL 元数据与成员 `<dl><dd>`/`Parameters:`/`Returns:` 文档（保留 `declared_in`）。
- `object_edges`：由属性/方法返回值及 `Document`/`Factory` 子类下转型派生出的 COM 对象有向图边表（~6,871 条边），驱动最短调用链寻路。
- `usecases`：官方 VBScript 示例与导入的社区 Python 配方。
- `apis_fts` / `usecases_fts`：SQLite FTS5 全文索引表（`apis_fts` 含 `camel_tokens` 拆词与 `is_inherited` 降权，按加权 `BM25` 排序）。
- `data/recipes/*.json` & `data/pitfalls.json`：运行时支持基于 mtime 的热加载与内存 FTS5 索引。

### 2.2 `dist/local/catalyst_docs.db`（可选离线文档扩展库）
- `metadata`：记录 `catia_release`（如 `B27`）、`portable_relative_paths = true`、页数/条目统计；**不存储任何本机绝对路径**。
- `doc_pages` + `doc_pages_fts`（External Content FTS5）：解析 `Bxxdoc/English/online/` HTML 页面、TOC 层级、`<a name="ix-...">` 索引词、警告框、`linked_docs`、`linked_files` 与图片相对路径。
- `catnls_entries` + `catnls_fts`：解析 `win_b64/resources/msgcatalog/*.CATNls` UI 文本与选项键，支持 CamelCase 切词回退。
- `samples` + `samples_fts`：文本样板存正文 + 相对路径；二进制 CAD 样板（`.CATPart`/`.CATProduct`/`.catalog` 等）仅索引元信息与相对路径。
- `doc_api_links`：官方样板宏与 HTML 用例文档的 COM API 反向索引表（存储 `interface_name`, `member_name`, `target_type`, `ref_id`, `rel_path`, `line_no`, `code_snippet`, `official_note`；支持自愈按需构建）。在 `get_catia_interface` 查询时自动挂载，解冻孤儿接口实战代码。

---

## 3. 5 级路径发现与版本对齐规则

`src/engine/local_config.py` 按严格优先级解析 `V5Automation.chm`、`doc_root` 和 `install_root`：

1. **显式参数 / 环境变量**：CLI `--chm` / `--doc-root` / `--install-root` 或环境变量 `CATALYST_CHM_PATH` / `CATALYST_DOC_ROOT` / `CATALYST_INSTALL_ROOT`。
2. **本机缓存配置**：`dist/local/paths.json`（运行 `install.py` / `build.py` / `build_docs.py` 时自动保存，或通过 `uv run python build_docs.py --set-paths` 单独写入）。
3. **达索 `CATEnv`（仅 Windows）**：解析 `%ProgramData%\DassaultSystemes\CATEnv\*.txt` 中的 `CATInstallPath` 与 `CATDocView`。
   - **严格版本对齐**：先以官方 `CATIA*.txt` 确定主安装目录版本号（如 `B27`），扫描 `CATDocView` 时自动过滤版本号冲突的条目（如第三方插件 `B21` 文档），杜绝跨版本混编。
4. **标准安装目录（仅 Windows）**：`C:\Program Files\Dassault Systemes\B*` 与 `B*doc`（或项目内本地放置的 `data/V5Automation.chm`）。
5. **交互提示 / 运行时提示**：安装脚本交互式提示用户输入或拖入路径；MCP 运行时缺少目录仍保留全部文本检索能力，并在结果中附带 `path_setup_hint`。

### 常见 CATIA 版本 `V5Automation.chm` 典型路径参考

| 架构 / 版本 | 典型路径 |
| :--- | :--- |
| 64 位（R22 / B22 及以上，如 B27 / B32） | `C:\Program Files\Dassault Systemes\B27\win_b64\code\bin\V5Automation.chm` |
| 32 位（早期 B20 / B21 等） | `C:\Program Files\Dassault Systemes\B21\intel_a\code\bin\V5Automation.chm` |

---

## 4. 跨平台路径与含空格路径规范

1. **数据库内部存储**：所有相对路径统一使用 POSIX `/`（例如 `cceug_C2/cceugbt0102.htm`），确保同一个 `catalyst_docs.db` 可在 Windows / macOS / Linux 间直接拷贝复用。
2. **运行时多协议前缀替换（本地默认优先）**：同一份 `catalyst_docs.db` 拷贝到另一台电脑后无需重建，只需通过 `CATALYST_DOC_ROOT` 或 `uv run python build_docs.py --set-paths --doc-root <prefix>` 即可更换前缀（数据提取建库仍仅支持文件系统路径）：
   - **本地目录（默认推荐）**：如 `D:\CATIA\B27doc` 或 `/mnt/catia/B27doc` → 返回原生 `abs_path`（可直接本地读取文件/截图）。
   - **Samba / UNC 共享（可选）**：如 `\\nas-server\share\B27doc` → 返回 UNC `abs_path`，网络中断时自动捕获 `OSError` 优雅降级，全文检索不受影响。
   - **HTTP(S) 在线文档站（可选高级）**：如 `https://docs.example.com/B27doc`（支持直接粘贴 `.../CATIA_P3_default.htm` 首页，自动归一化至 `/English/online`）→ 零延迟拼接返回 `url` 字段（不填 `abs_path`）。
3. **运行时路径还原**：`docs_db._join_portable_rel()` 将 `/` 或 `\` 统一拆分为路径段后调用 `Path.joinpath(*parts)`，输出当前 OS 原生绝对路径。
3. **用户输入解析**：`local_config.parse_user_path()` 统一处理双引号/单引号、PowerShell 拖放 `& '...'` 前缀、POSIX 拖放 `\ ` 转义空格、`~` 家目录展开以及 `/` 与 `\` 混用。
4. **MCP 配置文件（`mcp_config.json`）**：`command`、`args`、`env` 全部统一使用当前 OS 原生分隔符（Windows 为 `\`，macOS/Linux 为 `/`），通过 JSON 数组传参天然兼容含空格路径。
5. **CHM 解包与空格处理**：
   - **优先 7-Zip**：通过 `subprocess` 参数列表传参（不经过 shell），天然支持源 CHM 与目标输出目录双双含空格。
   - **Windows `hh.exe`（仅用户显式同意或传 `--use-hh` 时启用）**：将 CHM 复制到无空格临时目录并用相对路径 `hh.exe -decompile out source.chm` 解包；若系统默认 `%TEMP%` 含空格则自动切换无空格目录或校验 8.3 短路径，避免 `hh.exe` 静默失败。

---

## 5. 常见部署排错

| 现象 | 原因与解决方法 |
| :--- | :--- |
| 提示未检测到 7-Zip | 推荐安装 7-Zip（Windows: `winget install 7zip.7zip`；macOS: `brew install p7zip`；Ubuntu: `sudo apt install p7zip-full`）；或在交互菜单选 `[2]` 指定便携版 `7z` 路径，Windows 也可显式选 `[3]`（或传 `--use-hh`）使用 `hh.exe`。 |
| 自动探测不到 `V5Automation.chm` | CATIA 装在自定义位置或非 Windows 环境。在 `install.py` 交互提示中直接输入/拖入 `.chm` 或 CATIA 安装目录，或传 `--chm "<path>"`。 |
| 提示未检测到同版本 `Bxxdoc` | 本机未装完整离线 HTML 帮助手册。直接跳过即可，6 个核心 COM API / Recipe MCP 工具完全不受影响；后续安装好 `Bxxdoc` 后运行 `uv run python build_docs.py` 即可无缝激活剩余 4 个工具。 |
| 团队跨机器 / 跨系统共享数据库 | `dist/catalyst.db` 与 `dist/local/catalyst_docs.db` 均 100% 跨平台可移植。直接拷贝至新机器对应目录后执行 `uv run python install.py --yes`（离线文档可额外跑 `uv run python build_docs.py --set-paths` 绑定本机目录）。 |
| MCP 写入 `mcp_config.json` 提示权限不足 | `install.py` 会自动打印可直接复制的 JSON 配置片段，手动合并进目标客户端配置文件后刷新 MCP 即可。 |
