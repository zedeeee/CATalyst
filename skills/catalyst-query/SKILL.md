---
name: catalyst-query
description: Queries the local CATalyst knowledge base (10 MCP tools + symmetric CLI) for exact CATIA V5 COM Automation interfaces, inherited members, enums, Selection.Search syntax, Python win32com recipes, offline User's Guide docs, Tools > Options CATNls keys, and official samples. Use whenever writing CATIA V5 automation scripts or resolving CATIA configuration/batch workflows.
---

# CATalyst CATIA V5 Knowledge Skill

Use CATalyst as the ground-truth source before writing any CATIA V5 macro, Python `win32com` script, batch pipeline, or `Tools > Options` guide.

## Prerequisites & Quick Setup

- Core API database (`dist/catalyst.db`) must be built locally.
- If missing, run the one-click installer at the repository root:
  - Windows: `.\install.ps1` (or `uv run python install.py`)
  - macOS / Linux: `./install.sh` (requires `7z`/`p7zip` to unpack `.chm`, or copy a pre-built `dist/catalyst.db`)
- Optional offline docs extension (`dist/local/catalyst_docs.db`) enables 4 extra tools for User's Guide, `CATNls` settings, and official samples (`uv run python build_docs.py`).

## Tool Selection Priority

1. **Prefer MCP Tools (if `catalyst` MCP server is connected)**:
   - **Core COM API & Recipes (6 tools, always active with `dist/catalyst.db`)**:
     - `get_catia_interface(name, member_name="", include_usecases=True, max_usecases=3)` — full interface + inherited members (`declared_in`) + `pywin32` `[out]` hints
     - `search_catia_api(keyword, item_type="", limit=15)` — BM25 search across interfaces, enums, properties, methods (with reverse host lookup)
     - `get_catia_enum(name="", value=None, member_name="")` — bidirectional enum lookup
     - `get_catia_usecases(interface="", member="", source="", limit=5)` — official VBScript + community Python examples
     - `search_catia_recipes(query, workbench="", limit=5)` — industrial `win32com` automation recipes
     - `get_catia_search_syntax(workbench="")` — exact `Selection.Search` prefixes and grammar
   - **Offline Docs, Settings & Samples (4 tools, active when `dist/local/catalyst_docs.db` exists)**:
     - `search_catia_docs(query, category="", module="", solution="", limit=10)` — User's Guide & `Tools > Options` pages
     - `get_catia_doc_page(doc_id, section="", max_chars=6000)` — clean Markdown body, warnings, `linked_docs`, `linked_files`, resolved screenshot `abs_path`
     - `search_catia_settings(query, limit=10)` — `*.CATNls` UI labels/option keys + cross-linked `Tools > Options` pages
     - `search_catia_samples(query, ext="", include_content=False, limit=10)` — text samples (`.csv`, `.CATScript`, `.xml`) & binary CAD templates (`.CATPart`, `.catalog`)

2. **CLI Fallback (if MCP is unavailable)**:
   Run from the CATalyst repository root via `uv run python catalyst_cli.py <command>`:

   ```bash
   # Core COM API & Recipes
   uv run python catalyst_cli.py search "PartNumber" --type property
   uv run python catalyst_cli.py get Pad --member GetDirection
   uv run python catalyst_cli.py enum CatProductSource --value 1
   uv run python catalyst_cli.py recipe "export step"
   uv run python catalyst_cli.py usecase Pad --source official
   uv run python catalyst_cli.py syntax --workbench PartDesign

   # Offline Docs, CATNls Settings & Official Samples (requires catalyst_docs.db)
   uv run python catalyst_cli.py docs "Catalog Batch Mode" --category user_guide
   uv run python catalyst_cli.py doc-page "cceug_C2/cceugbt0102.htm" --section "Batch Mode"
   uv run python catalyst_cli.py settings "FavoriteCatalog"
   uv run python catalyst_cli.py samples "BatchCatalog" --ext .csv --content
   ```

## Rules for CATIA V5 Automation Generation

- **Never Guess APIs**: Do not invent interfaces, properties, methods, or enum values. Always verify exact spelling, parameter count/direction, and return type first.
- **Respect Inheritance**: `get_catia_interface` / `get` fuses parent chains (`Pad -> Prism -> SketchBasedShape -> Shape -> AnyObject`). Any inherited member listed is valid to call directly.
- **Target Clean Python `win32com`**: Generate pure `win32com.client` Python code unless the user explicitly asks for VBScript/VBA.
- **Check `pywin32` Type Hints**: Watch `[out]` / `[inout]` tuple return hints and pass `CATSafeArrayVariant` as Python `list`/`tuple`.
- **Use Non-COM Tools When COM Returns 0 Hits**: If an action is GUI/batch/settings-only (no COM API), query `search_catia_docs`, `search_catia_settings`, or `search_catia_recipes` instead of guessing.
