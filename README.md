<div align="center">

# CATalyst

**Full-Stack Offline CATIA V5 Knowledge Engine & MCP Server for AI Agents**

Turn CATIA V5's closed CHM Automation reference, multi-gigabyte offline HTML User's Guide, `CATNls` message catalogs, and official CAD/script samples into a sub-10ms, version-aligned, zero-hallucination local SQLite FTS5 knowledge base.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://python.org)
[![MCP Ready](https://img.shields.io/badge/MCP-10%20Tools-blueviolet.svg)](#mcp-server-tools)

**English** · [简体中文](README_CN.md)

</div>

---

## Why CATalyst Matters

Building reliable CATIA V5 automation with AI Agents has historically failed for four structural reasons:

1. **COM API Hallucination & Broken Inheritance**: CATIA V5 ships with **80+ Frameworks and 1,100+ COM interfaces** locked inside `V5Automation.chm`. Raw HTML omits inherited members (e.g., `Pad` does not display `FirstLimit` or `DirectionOrientation` inherited from `Prism`), causing LLMs to invent methods or break `pywin32` `[out]` tuple unpacking.
2. **The Non-COM Blind Spot**: A huge portion of real CATIA engineering lives *outside* COM Automation — `Tools > Options` settings without a `SettingController` (e.g., `CatalogOption.CATSettings`), batch protocols (`CreateCatalogFromcsv` CSV grammar, `CNEXT -batch`), and GUI-only architecture boundaries (e.g., PKT `Document Template` vs. Unresolved `Part Family`).
3. **Unusable Multi-Gigabyte Offline Docs**: A full Dassault `Bxxdoc` installation exceeds **2.2 GB (78,000+ files)** — 93% of which are binary `.CATPart`/`.cgr`/`.model` assets and images. Naive recursive search times out, and raw FrontPage HTML explodes context windows.
4. **Cross-Version Drift & Machine Coupling**: Mixing documentation from R21/R27/R32 silently breaks scripts, while hardcoding local paths makes knowledge bases impossible to share across a team.

### How CATalyst Solves It

CATalyst enforces a **strict read-only knowledge plane** (zero live `win32com` coupling, zero CATIA crash blast radius) built on a **Decoupled Dual-DB + Portable Relative-Path Architecture**:

```text
  [Core Open-Source DB: dist/catalyst.db (~9 MB)]
  ├── Official V5Automation.chm ──▶ Inheritance Fusion + IDL Signatures + 3,700+ Official Examples
  └── Curated Community Recipes ──▶ AST-Verified, Sanitized Python win32com Industrial Patterns
                                             │
  [Optional Local Extension DB: dist/local/catalyst_docs.db (~120 MB, .gitignore)]
  ├── Bxxdoc/English/online/    ──▶ 12,000+ User's Guide & Tools>Options Pages (TOC + ix-* + Warnings)
  ├── Bxx/win_b64/msgcatalog/   ──▶ 237,000+ Cleaned CATNls UI Labels <-> Option Keys
  └── samples/ & startup/       ──▶ Text Samples (Full Content) + Binary CAD Models (Relative Paths Only)
                                             │
                                             ▼
            ┌────────────────────────────────┼────────────────────────────────┐
            ▼                                ▼                                ▼
     MCP Server (10 Tools)            CLI (catalyst_cli.py)             Agent Skill
(Antigravity / Claude / Codex / IDEs)  (< 300 Token Cards)         (On-Demand Recall)
```

### Key Architectural Breakthroughs

- **Zero-Hallucination API Ground Truth**: Recursively fuses parent inheritance chains (`Pad -> Prism -> SketchBasedShape -> Shape -> AnyObject`), extracts full CHM member `<dl><dd>` descriptions / `Parameters:` / `Returns:` / `Role:`, builds a 6,871-edge **COM Object Model Graph** (`from_interface` shortest access chain), and supports CamelCase + bilingual CAD synonyms, bidirectional enum lookup, `Selection.Search` grammar, and `pywin32` `[out]` / `CATSafeArrayVariant` calling hints.
- **Token-Efficient Adaptive Output & Round-Trip Elimination**: Cuts MCP output size by **58%–88%** without losing signature precision — strips JSON whitespace/empty keys, folds `AnyObject` boilerplate in overview mode (`omitted_base_members`), renders typed single-line signatures (`detail="auto|summary|compact|full"` + optional `output_format="card"` IDL cards), supports wildcard/comma member filtering (`*Fillet*`), inlines Enum definitions (`referenced_enums`), and fuses terminal creator signatures directly into `navigation_path` (`AddNewPad(iSketch: Sketch, iHeight: double) -> Pad`) to eliminate extra tool round-trips.
- **Method-Level Calling Constraints & Caveats**: Hot-loads verified calling caveats (`data/pitfalls.json` + static `CaveatMiner`) for APIs where Dassault's underlying C++ implementation diverges from IDL declarations (e.g., `Material.PutIcon` requiring a directory path ending with `\` to prevent `E_FAIL`). Emits structured `pitfall_warning` blocks with root-cause analysis and verified safe calling patterns.
- **Official Sample Code & Doc Linkage Reverse Index**: Direct call-site mapping with return-type propagation across 2,415 sample scripts and 12,179 doc pages, uncovering 14,508 verified call sites and unfreezing 78+ previously unreferenced interfaces with exact line-number context.
- **2.24 GB Offline Docs Compressed to Sub-10ms FTS5**: Multiprocess `lxml` ETL parses 12,500+ HTML pages in seconds, extracts Dassault's native `CATIA_P3_TOC.xml` hierarchy, `<a name="ix-...">` index tags, `<a name="ToolsOptions...">` anchors, `awarning.gif` official pitfalls, `linked_docs` cross-references, `linked_files`, and content screenshots — stored via SQLite FTS5 External Content Tables (no duplicate text storage) with BM25 column weighting and CamelCase fallback (`FavoriteCatalog` -> `Favorite Catalog`).
- **100% Portable Relative-Path Index**: `catalyst_docs.db` stores **zero machine-specific absolute paths** (`portable_relative_paths: true`) and carries a `catia_release` watermark (e.g., `B27`). Configure `CATALYST_DOC_ROOT` / `CATALYST_INSTALL_ROOT` in MCP `env` on any machine and CATalyst dynamically resolves local `abs_path` for HTML pages, embedded screenshots (for multimodal `read_file` inspection), text `.csv`/`.CATScript`/`.xml` samples, and binary `.CATPart`/`.CATProduct`/`.catalog` templates.
- **Dual-Track Industrial Recipes**: Bundles kernel-verified `win32com` engineering recipes (headless `CNEXT -batch` Catalog creation, `CATBatGenXMLSet`/`CATBatImpXMLSet` `.CATSettings` XML round-trip, `.txt` DesignTable CRLF guard, `Relation.Hidden` encapsulation, Catalog 3-mode architecture, STEP batch export, BOM/Inertia, Bounding Box, Drafting Title Block).
- **Graceful Plug-and-Play**: Without `catalyst_docs.db`, the 6 core API/Recipe tools work out of the box with zero configuration; once built locally, all 4 offline doc/settings/sample tools activate seamlessly.

---

## Local Setup & Environment Isolation

- **Local Database Initialization**: Core (`dist/catalyst.db`) and optional offline docs (`dist/local/catalyst_docs.db`) databases are built locally from your machine's CATIA V5 documentation and kept out of Git via `.gitignore`.
- **Upgrading Existing Databases**:
  - `v0.3.0` → `v0.3.1`: **No database rebuild required** (zero schema changes — simply refresh/restart your MCP server).
  - `v0.2.x` → `v0.3.x`: **Rebuild `dist/catalyst.db`** via `uv run python build.py` to populate `object_edges` and member descriptions (`catalyst_docs.db` auto-heals `doc_api_links` on first query without re-unpacking `Bxxdoc`).
- **Isolated Virtual Environment by Default**: Always use `uv sync` / `uv run` (project-local `.venv/`). `build.py` and `build_docs.py` warn if invoked under global Python.
- **Zero System Side-Effects**: Builders print resolved paths before reading local CATIA folders and never modify system `PATH`, Windows Registry, or CATIA installation directories.

---

## Quick Start

### Requirements

| Dependency | Requirement | Notes |
| :--- | :--- | :--- |
| **Python 3.10+** & **[uv](https://docs.astral.sh/uv/)** | Required | Manages the project-local `.venv/` automatically (all dependencies ship pre-built wheels; no C++ compiler needed). |
| **[7-Zip (`7z`)](https://www.7-zip.org/)** | **Strongly Recommended** (Required on Linux/macOS to unpack `.chm`) | Fastest, space-in-path safe CHM unpacker (`winget install 7zip.7zip` / `brew install p7zip` / `sudo apt install p7zip-full`). If missing on Windows, the installer asks you whether to exit and install 7-Zip, specify a local `7z.exe`, or explicitly continue with Windows `hh.exe` (`--use-hh`). |
| **Local CATIA V5 Docs** | Required (`V5Automation.chm`) / Optional (`Bxxdoc`) | Auto-detected via `CATEnv` on Windows (release-aligned); if not found, the installer prompts you to enter or drag-and-drop the path (supports spaces and `/` or `\`). |

### One-Click Installation (Recommended)

A single command syncs `.venv`, verifies 7-Zip (or asks your choice), auto-discovers or prompts for `V5Automation.chm` and optional release-aligned `Bxxdoc`, builds the local SQLite database(s), safely merges `mcpServers.catalyst` into your MCP client config (with `.bak` backup), and runs end-to-end verification:

```powershell
# Windows (PowerShell)
git clone https://github.com/zedeeee/CATalyst.git
cd CATalyst
.\install.ps1
# If PowerShell blocks local scripts (Restricted ExecutionPolicy):
# powershell -ExecutionPolicy Bypass -File .\install.ps1

# Common options:
# .\install.ps1 --chm "D:\Dassault\B27\win_b64\code\bin\V5Automation.chm"
# .\install.ps1 --client claude     # Built-in presets: antigravity (default), claude, cursor; or --config <path> for Codex / other MCP agents & IDEs
# .\install.ps1 --yes               # Non-interactive (add --use-hh on Windows if 7-Zip is not installed)
```

```bash
# macOS / Linux (requires p7zip/7z to unpack CHM, or reuse a pre-built dist/catalyst.db)
./install.sh
```

### Manual Step-by-Step Setup

#### 1. Create Isolated Virtual Environment

```bash
git clone https://github.com/zedeeee/CATalyst.git
cd CATalyst
uv sync --extra dev
```

#### 2. Initialize Core API Database (`dist/catalyst.db`, Required)

`build.py` automatically discovers local `V5Automation.chm` via `CATEnv` (`<CATInstallPath>/code/bin/V5Automation.chm`), displays detected paths for confirmation, and builds `dist/catalyst.db` locally (pass `--chm` for custom locations, `--use-hh` on Windows without 7-Zip, or `--with-docs` to build both databases together):

```bash
# Auto-detect V5Automation.chm via CATEnv (interactive confirmation before build)
uv run python build.py

# Or specify CHM explicitly, or build Core API + Offline Docs together:
uv run python build.py --chm "D:/Dassault/B27/win_b64/code/bin/V5Automation.chm"
uv run python build.py --with-docs
```

#### 3. Build Local Offline Docs Extension (`dist/local/catalyst_docs.db`, Optional)

Run once against your version-aligned local CATIA documentation and install directory (pass top-level `Bxxdoc` / `Bxx` folders; paths are normalized automatically and never hardcoded into the resulting DB):

```bash
uv run python build_docs.py \
  --doc-root "C:/Program Files/Dassault Systemes/B27doc" \
  --install-root "C:/Program Files/Dassault Systemes/B27" \
  --release B27
```

- Output defaults to `dist/local/catalyst_docs.db` (ignored by `.gitignore`).
- Supports `--modules cceug_C2,bascuctg_C2` for targeted testing and `--workers N` for parallel tuning.

#### Fresh Machine Path Auto-Discovery (5-Tier Precedence)

On a fresh machine, CATalyst resolves local CATIA doc/install roots in strict priority order:
1. **Explicit CLI / MCP `env`**: `CATALYST_DOC_ROOT` & `CATALYST_INSTALL_ROOT` (accepts top-level `Bxxdoc` / `Bxx` folders).
2. **Machine-Local Config**: `dist/local/paths.json` (gitignored; saved automatically when running `build_docs.py`, or set standalone via `uv run python build_docs.py --set-paths` when reusing a pre-built `catalyst_docs.db`).
3. **Dassault Official `CATEnv`**: Auto-parses `%ProgramData%\DassaultSystemes\CATEnv\*.txt` (`CATDocView` & `CATInstallPath`) — works regardless of install drive (`C:`, `D:`, `E:`, etc.).
4. **Standard Default Path**: `C:\Program Files\Dassault Systemes\B*doc` and `B*\win_b64`.
5. **Interactive Prompt / MCP Setup Hint**: In an interactive terminal `build_docs.py` prompts for the directory; at MCP runtime, missing roots emit `path_setup_hint` while keeping text search fully operational.

---

## MCP Server Configuration

Running `.\install.ps1` / `./install.sh` automatically registers `catalyst` in your MCP client config (Antigravity `~/.gemini/config/mcp_config.json`, Claude `claude_desktop_config.json`, Cursor `~/.cursor/mcp.json`, or any other MCP-compatible Agent / AI IDE such as Claude Code & Codex via `--config <path>`). For manual setup, use:

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

> Use native path separators for your OS (e.g. `\\` in JSON on Windows, `/` on macOS/Linux). `CATALYST_DOC_ROOT` defaults to a local `Bxxdoc` directory (and is optional if you only use the 6 core COM API/Recipe tools). When reusing a pre-built `catalyst_docs.db` on another machine, you can swap the runtime prefix without rebuilding via `CATALYST_DOC_ROOT` or `uv run python build_docs.py --set-paths --doc-root <prefix>` (local directory preferred; optional SMB UNC or `http(s)://` base URL also supported).

Optional environment overrides:
- `CATALYST_DB_PATH`: Custom path to `catalyst.db`.
- `CATALYST_DOCS_DB_PATH`: Custom path to a shared/relocated `catalyst_docs.db`.
- `CATALYST_7Z_PATH`: Custom path to `7z`/`7za` executable.
- `CATALYST_OUTPUT_FORMAT`: Default format for `get_catia_interface` (`json` default compact JSON, or `card` for ultra-dense IDL text cards).
- `CATALYST_PRETTY_JSON`: Set to `1` to re-enable `indent=2` JSON formatting for human debugging.

---

## MCP Server Tools

| Category | Tool | Purpose |
| :--- | :--- | :--- |
| **COM API** | `get_catia_interface` | Adaptive interface lookup (`detail`: `auto`/`summary`/`compact`/`full`; `output_format`: `json`/`card`): supports exact/comma/wildcard `member_name` filtering (`*Fillet*`), base-member folding, `from_interface` navigation with terminal constructor signature, inline `referenced_enums`, implementation caveats (`pitfall_warning`), and linked official docs/samples |
| **COM API** | `search_catia_api` | FTS5 BM25 search across interfaces, enums, properties, and methods (with reverse host lookup & 0-hit doc hint) |
| **COM API** | `get_catia_enum` | Bidirectional enum lookup by enum name, integer value, or member name |
| **COM API** | `get_catia_usecases` | Dual-track official VBScript tutorials + community Python `win32com` examples |
| **COM API** | `search_catia_recipes` | Natural-language BM25 search over curated industrial automation recipes |
| **COM API** | `get_catia_search_syntax` | Exact `Selection.Search` workbench prefixes and query grammar |
| **Offline Docs** | `search_catia_docs` | BM25 search over User's Guide, `Tools > Options`, and Automation articles (`category` / `module` / `solution` filters) |
| **Offline Docs** | `get_catia_doc_page` | Clean Markdown page body, section slicing, official warnings, `linked_docs`, `linked_files`, and resolved screenshot `abs_path` |
| **Settings** | `search_catia_settings` | Search `*.CATNls` UI labels/keys with CamelCase fallback, cross-linked `Tools > Options` pages, and `CATBatGen/ImpXMLSet` hints |
| **Samples** | `search_catia_samples` | Search official text samples (`.csv`, `.CATScript`, `.txt`, `.xml`) with full content + binary CAD templates (`.CATPart`, `.catalog`, etc.) with resolved `abs_path` |

---

## CLI Usage

Every MCP capability has a symmetric command in `catalyst_cli.py`:

```bash
# Core COM API & Recipes
uv run python catalyst_cli.py get Pad --member GetDirection
uv run python catalyst_cli.py get Pad --from Application --format card --no-usecases
uv run python catalyst_cli.py get HybridShapeFactory --member "*Fillet*" --format card
uv run python catalyst_cli.py path Pad --from Application
uv run python catalyst_cli.py search "PartNumber" --type property
uv run python catalyst_cli.py enum CatProductSource --value 1
uv run python catalyst_cli.py recipe "CreateCatalogFromcsv"
uv run python catalyst_cli.py syntax --workbench PartDesign

# Offline Docs, CATNls Settings & Official Samples
uv run python catalyst_cli.py docs "Catalog Batch Mode" --category user_guide
uv run python catalyst_cli.py doc-page "cceug_C2/cceugbt0102.htm" --section "Batch Mode"
uv run python catalyst_cli.py settings "FavoriteCatalog"
uv run python catalyst_cli.py samples "BatchCatalog" --ext .csv --content
uv run python catalyst_cli.py samples "AISC_C" --ext .catpart
```

---

## Project Structure

```text
CATalyst/
├── data/
│   ├── recipes/                    # Curated, AST-verified community recipes (JSON)
│   └── raw/                        # Local extracted CHM HTML (.gitignore)
├── dist/
│   ├── catalyst.db                 # Locally built core COM API + Recipes SQLite DB (.gitignore)
│   └── local/                      # Local portable catalyst_docs.db & paths.json (.gitignore)
├── docs/
│   ├── architecture.md             # System architecture, schema, path discovery & troubleshooting
│   └── tutorial.md                 # Hands-on CLI & MCP usage guide
├── src/
│   ├── parser/                     # CHM unpacker (7z/hh), HTML parser, inheritance tree, offline docs ETL
│   ├── engine/                     # Thread-safe SQLite FTS5 engines (db.py, docs_db.py, local_config.py)
│   ├── mcp/                        # FastMCP / MCPServer exposing 10 tools (server.py)
│   └── client/                     # Optional host diagnostics
├── skills/catalyst-query/          # Agent Skill definition (SKILL.md)
├── tests/                          # Automated tests (engine, FTS5, schema, portability, installer, MCP)
├── install.ps1 / install.sh        # One-click installers (Windows / macOS / Linux)
├── install.py                      # Cross-platform installer & MCP registration engine
├── build.py                        # Core API DB builder + 8 smoke tests
├── build_docs.py                   # Offline docs/CATNls/samples extension builder + smoke tests
├── catalyst_cli.py                 # Symmetric CLI entrypoint
├── AGENTS.md                       # AI agent ground-truth policy & deployment runbook
├── README.md                       # English documentation (default)
└── README_CN.md                    # 简体中文文档
```

## Documentation

- [Architecture & Deployment Reference](docs/architecture.md)
- [Hands-on Tutorial (CLI & MCP)](docs/tutorial.md)
- [Community Recipes Contribution Guide](data/recipes/README.md)
- [Agent Guidelines & Deployment Runbook](AGENTS.md)

---

## Verification & Testing

```bash
uv run pytest
```

## Credits & License

- Co-architected and built with **Google Antigravity & Gemini**.
- Released under the [MIT License](LICENSE).
