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
   (Antigravity / Cursor / Claude)      (< 300 Token Cards)         (On-Demand Recall)
```

### Key Architectural Breakthroughs

- **Zero-Hallucination API Ground Truth**: Recursively fuses parent inheritance chains (`Pad -> Prism -> SketchBasedShape -> Shape -> AnyObject`), provides bidirectional enum lookup, reverse member-to-interface lookup, `Selection.Search` grammar, and `pywin32` `[out]` / `CATSafeArrayVariant` calling hints.
- **2.24 GB Offline Docs Compressed to Sub-10ms FTS5**: Multiprocess `lxml` ETL parses 12,500+ HTML pages in seconds, extracts Dassault's native `CATIA_P3_TOC.xml` hierarchy, `<a name="ix-...">` index tags, `<a name="ToolsOptions...">` anchors, `awarning.gif` official pitfalls, `linked_docs` cross-references, `linked_files`, and content screenshots — stored via SQLite FTS5 External Content Tables (no duplicate text storage) with BM25 column weighting and CamelCase fallback (`FavoriteCatalog` -> `Favorite Catalog`).
- **100% Portable Relative-Path Index**: `catalyst_docs.db` stores **zero machine-specific absolute paths** (`portable_relative_paths: true`) and carries a `catia_release` watermark (e.g., `B27`). Configure `CATALYST_DOC_ROOT` / `CATALYST_INSTALL_ROOT` in MCP `env` on any machine and CATalyst dynamically resolves local `abs_path` for HTML pages, embedded screenshots (for multimodal `read_file` inspection), text `.csv`/`.CATScript`/`.xml` samples, and binary `.CATPart`/`.CATProduct`/`.catalog` templates.
- **Dual-Track Industrial Recipes**: Bundles kernel-verified `win32com` engineering recipes (headless `CNEXT -batch` Catalog creation, `CATBatGenXMLSet`/`CATBatImpXMLSet` `.CATSettings` XML round-trip, `.txt` DesignTable CRLF guard, `Relation.Hidden` encapsulation, Catalog 3-mode architecture, STEP batch export, BOM/Inertia, Bounding Box, Drafting Title Block).
- **Graceful Plug-and-Play**: Without `catalyst_docs.db`, the 6 core API/Recipe tools work out of the box with zero configuration; once built locally, all 4 offline doc/settings/sample tools activate seamlessly.

---

## Quick Start

### Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended)
- Optional (for offline docs extension): Local CATIA V5 documentation (`Bxxdoc`) and/or installation (`Bxx/win_b64`) matching your target CATIA release.

### 1. Install Dependencies

```bash
git clone https://github.com/zedeeee/CATalyst.git
cd CATalyst
uv sync --extra dev
```

### 2. Core API Database (`dist/catalyst.db`)

CATalyst ships with a pre-built R27 core API database ready to use immediately. To rebuild from your own CATIA release's `V5Automation.chm` (typically under `<CATInstall>/win_b64/code/bin/V5Automation.chm`, see [docs/chm_extraction_guide.md](docs/chm_extraction_guide.md)):

```bash
cp /path/to/V5Automation.chm data/V5Automation.chm
uv run python build.py
```

### 3. Build Local Offline Docs Extension (`dist/local/catalyst_docs.db`)

Run once against your version-aligned local CATIA documentation and install directory (pass top-level `Bxxdoc` / `Bxx` folders; paths are normalized automatically and never hardcoded into the resulting DB):

```bash
uv run python build_docs.py \
  --doc-root "C:/Program Files/Dassault Systemes/B27doc" \
  --install-root "C:/Program Files/Dassault Systemes/B27" \
  --release B27
```

- Output defaults to `dist/local/catalyst_docs.db` (ignored by `.gitignore` to prevent committing commercial Dassault assets).
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

Add CATalyst to your MCP client configuration (e.g., `~/.gemini/config/mcp_config.json` for Antigravity, or Claude Desktop / Cursor). Configure `CATALYST_DOC_ROOT` and `CATALYST_INSTALL_ROOT` once so all portable relative paths resolve to your machine's local files at runtime:

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

Optional environment overrides:
- `CATALYST_DB_PATH`: Custom path to `catalyst.db`.
- `CATALYST_DOCS_DB_PATH`: Custom path to a shared/relocated `catalyst_docs.db`.

---

## MCP Server Tools

| Category | Tool | Purpose |
| :--- | :--- | :--- |
| **COM API** | `get_catia_interface` | Full interface signatures with inherited members (`declared_in`), `pywin32` `[out]` hints, and member-level filtering |
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
│   ├── V5Automation.chm            # Official Automation CHM source
│   └── recipes/                    # Curated, AST-verified community recipes (JSON)
├── dist/
│   ├── catalyst.db                 # Pre-built core COM API + Recipes SQLite DB
│   └── local/                      # Local version-aligned catalyst_docs.db (.gitignore)
├── src/
│   ├── parser/                     # CHM HTML parser, inheritance tree, offline docs/CATNls/samples ETL
│   ├── engine/                     # Thread-safe SQLite FTS5 engines (db.py, docs_db.py, search_grammar.py)
│   ├── mcp/                        # FastMCP / MCPServer exposing 10 tools (server.py)
│   └── client/                     # Optional host diagnostics
├── skills/                         # Agent Skill definitions
├── tests/                          # Pytest suite (unit, FTS5, schema, portable relocation, MCP tests)
├── build.py                        # Core API DB builder + 8 smoke tests
├── build_docs.py                   # Offline docs/CATNls/samples extension builder + smoke tests
├── catalyst_cli.py                 # Symmetric CLI entrypoint
├── README.md                       # English documentation (default)
└── README_CN.md                    # 简体中文文档
```

---

## Verification & Testing

```bash
uv run pytest
```

## Credits & License

- Co-architected and built with **Google Antigravity & Gemini**.
- Released under the [MIT License](LICENSE).
