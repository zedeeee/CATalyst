# CATalyst Project Agent Guidelines

## 1. CATIA API 调用铁律 (Ground Truth Policy)
- **严禁凭空脑补 (Zero Hallucination)**：严禁凭 LLM 记忆捏造 CATIA V5 的 COM 接口名、属性名、方法名、参数或枚举常量（例如杜绝 `ServicePackNumber`、`BuildNumber` 这类伪属性）。
- **唯一可信数据源**：
  - **COM API / 枚举 / 社区配方**：必须通过本地 `dist/catalyst.db` 检索验证（MCP 工具：`get_catia_interface`、`search_catia_api`、`get_catia_enum`、`get_catia_usecases`、`search_catia_recipes`、`get_catia_search_syntax`；或 CLI `uv run python catalyst_cli.py ...`；或 `src/engine/db.py`）。
  - **非 COM 工程知识（`Tools > Options`、批处理参数、`CATNls`、官方样板）**：当 `dist/local/catalyst_docs.db` 已构建时，通过 `search_catia_docs`、`get_catia_doc_page`、`search_catia_settings`、`search_catia_samples` 检索验证。
- **签名一致性**：属性/方法大小写、参数数量与方向（`in`/`out`/`inout`）、类型（如 `long`、`CATBSTR`、`CATSafeArrayVariant`）必须 100% 符合 `catalyst.db` 中的 IDL 规范；若库中查不到，直接说明该能力未在 CATIA V5 Automation 中暴露。

## 2. AI 快速部署 SOP (Deployment Runbook)
当用户要求安装或部署本项目的 MCP 时，按最短路径执行：
1. **检查现有状态**：确认 `dist/catalyst.db` 是否存在，以及目标客户端配置文件（Antigravity：`~/.gemini/config/mcp_config.json`；Cursor：`~/.cursor/mcp.json`；Claude：`claude_desktop_config.json`）是否已注册 `catalyst`。
2. **依赖与环境要求**：必需 Python 3.10+ 与 `uv`；解包 `.chm` 时**强烈推荐 7-Zip (`7z`)**。
   - 若缺失 `7z` 且需要解包 `.chm`，**严禁静默切换方案**——询问用户选择「先安装 7-Zip（推荐） / 手动指定 `7z` 路径 / 显式加 `--use-hh` 使用 Windows `hh.exe`」。
3. **执行一键安装**：
   - Windows：`.\install.ps1`（若策略受限用 `powershell -ExecutionPolicy Bypass -File .\install.ps1`；自动化带参：`--chm "<path>" --yes`，无 7z 且获用户同意时加 `--use-hh`）。
   - macOS / Linux：`./install.sh`（需装 `p7zip`/`7z` 或直接复用已构建好的 `dist/catalyst.db`）。
   - **缺失路径必须主动询问用户**：
     - 若未自动探测到 `V5Automation.chm`，必须向用户询问路径并通过 `--chm "<path>"` 传入。
     - 若未自动探测到同版本 `Bxxdoc`（即使只先跑了 `--yes` 激活 6/10 核心工具），**必须主动向用户确认**本机其他盘符/目录是否装有 `Bxxdoc`；若用户提供路径，使用 `--doc-root "<path>"` 补建以激活全部 10/10 个 MCP 工具。
4. **验收**：确认 `install.py` 输出 `[PASS]`（已激活 6/10 或 10/10 个 MCP 工具），并验证 `get_catia_interface("Pad", member_name="GetDirection")` 返回有效结果。

## 3. 仓库卫生约束
- 严禁向 Git 提交任何本地解包目录或生成的二进制/数据库文件（`data/raw/`、`data/V5Automation.chm`、`dist/catalyst.db`、`dist/local/` 均保持由 `.gitignore` 忽略）。
