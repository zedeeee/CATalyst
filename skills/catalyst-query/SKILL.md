---
name: catalyst-query
description: Queries the local CATalyst knowledge base (10 MCP tools + symmetric CLI) for exact CATIA V5 COM Automation interfaces, shortest object navigation chains (from_interface), known implementation caveats (pitfall_warning), enums, Selection.Search syntax, Python win32com recipes, offline User's Guide docs, Tools > Options CATNls keys, GUI Command Header IDs, CATRsc keyboard shortcuts, and official samples. Use whenever writing CATIA V5 automation scripts or resolving CATIA GUI/batch/configuration workflows.
---

# CATalyst CATIA V5 Knowledge Skill

Use CATalyst as the ground-truth source before writing any CATIA V5 macro, Python `win32com` script, batch pipeline, or `Tools > Options` guide.

## Prerequisites & Quick Setup

- Core API database (`dist/catalyst.db`) must be built locally (drives 6 core tools).
- If missing, run the one-click installer at the repository root:
  - Windows: `.\install.ps1` (or `uv run python install.py`)
  - macOS / Linux: `./install.sh` (requires `7z`/`p7zip` to unpack `.chm`, or reuse a pre-built `dist/catalyst.db`)
- Optional offline docs extension (`dist/local/catalyst_docs.db`, `uv run python build_docs.py`) enables 4 extra tools for User's Guide, `CATNls`/`CATRsc` settings/headers/shortcuts, and official samples. Legacy `v0.3.0+` DBs auto-migrate `doc_api_links` and `*.CATRsc` shortcuts on first query without rebuilding.

## Tool Selection Priority

### 1. Prefer MCP Tools (if `catalyst` MCP server is connected)

Use compact options (`output_format="card"`, `detail="compact"`, wildcard `member_name`, `include_snippet=False`, `scope`) to save context tokens.

- **Core COM API & Recipes (6 tools, always active with `dist/catalyst.db`)**:
  - `get_catia_interface(name, member_name="", from_interface="", include_usecases=True, max_usecases=3, detail="auto", include_base_members=False, output_format="json")`
    - Supports exact, comma-separated, and wildcard `member_name` filters (e.g. `"*Fillet*"`).
    - `from_interface="Application"` returns `navigation_path` with the shortest access chain, terminal constructor signature, and `terminal_pitfall`.
    - `detail="auto"` yields a compact overview (folding `AnyObject` boilerplate into `omitted_base_members`) and expands to full details when `member_name` is specified; automatically attaches `pitfall_warning`, inline `referenced_enums`, and `linked_official_docs`/`linked_sample_scripts` when `catalyst_docs.db` exists.
    - Pass `output_format="card"` for dense IDL text cards (~80–90% smaller).
  - `search_catia_api(query, item_type="all", include_catnls=False, include_cross_links=True, detail="full", limit=15)`
    - Weighted BM25 + CamelCase + bilingual CN/EN CAD synonym fallback (`"凸台"`, `"缩略图"`, `"几何图形集"`), reverse host lookup, and `related_recipes`/`related_docs`.
    - Set `detail="compact"` / `include_cross_links=False` to save tokens, or `include_catnls=True` on 0 COM hits to auto-probe `*.CATNls`/`*.CATRsc`.
  - `get_catia_enum(name="", value=None, member_name="")` — bidirectional enum lookup.
  - `get_catia_usecases(interface="", member="", source="all", query="", limit=5)` — official VBScript + curated Python `win32com` examples.
  - `search_catia_recipes(query, workbench="", source="all", limit=5)` — industrial `win32com` automation recipes.
  - `get_catia_search_syntax(workbench="", query_type="")` — exact `Selection.Search` workbench prefixes (e.g. `CATPrtSearch`, `CATGspSearch`) and query grammar.

- **Offline Docs, Settings, Command Headers & Samples (4 tools, active with `dist/local/catalyst_docs.db`)**:
  - `search_catia_docs(query, category="all", module="", solution="", include_snippet=True, limit=10)` — User's Guide, `Tools > Options`, Automation articles (set `include_snippet=False` for ultra-compact `doc_id` index).
  - `get_catia_doc_page(doc_id, section="", include_images=True, max_chars=12000, start_line=0, end_line=0)` — cleaned Markdown body, section or line-range slicing (`start_line`/`end_line`), warnings, `linked_docs`/`linked_files`, and resolved screenshot `abs_path`.
  - `search_catia_settings(query="", nls_file="", options_only=True, scope="all", include_related_docs=None, limit=15)` — scoped lookup across `*.CATNls` & `*.CATRsc`:
    - `scope="options"`: `Tools > Options` & `.CATSettings` keys (+ `related_option_docs` & `xml_roundtrip_hint`).
    - `scope="headers"`: GUI Command Header IDs for `CATIA.StartCommand(...)` (e.g. `OpenInNewWnd`).
    - `scope="accelerators"`: keyboard shortcuts from `*.CATRsc` (e.g. `Ctrl+N`).
    - `headers`/`accelerators` default `include_related_docs=False` to avoid Options doc noise.
  - `search_catia_samples(query="", ext="", module="", source="all", include_content=False, include_binary=True, max_chars=6000, limit=10)` — filter `source="doc_samples"` or `"startup"` (`win_b64/startup/`); covers text samples (`.csv`, `.CATScript`, `.xml`) and binary CAD templates (`.CATPart`, `.catalog`).

### 2. CLI Fallback (if MCP is unavailable)

Run from the CATalyst repository root via `uv run python catalyst_cli.py <command>` (`--help` shows all flags):

```bash
# Core COM API, Object Graph Navigation & Recipes
uv run python catalyst_cli.py get Pad --from Application --format card --no-usecases
uv run python catalyst_cli.py get HybridShapeFactory --member "*Fillet*" --format card
uv run python catalyst_cli.py path RenderingMaterial --from Application
uv run python catalyst_cli.py search AddNewPad --detail compact --no-cross-links
uv run python catalyst_cli.py search OpenInNewWnd --include-catnls
uv run python catalyst_cli.py enum CatProductSource --value 1
uv run python catalyst_cli.py recipe "CreateCatalogFromcsv"
uv run python catalyst_cli.py usecase Pad --source official
uv run python catalyst_cli.py syntax --workbench PartDesign

# Offline Docs, Options, Command Headers, Shortcuts & Samples (requires catalyst_docs.db)
uv run python catalyst_cli.py docs "Catalog Batch Mode" --category user_guide --no-snippet
uv run python catalyst_cli.py doc-page "cceug_C2/cceugbt0102.htm" --section "Batch Mode"
uv run python catalyst_cli.py settings FavoriteCatalog --scope options
uv run python catalyst_cli.py settings OpenInNewWnd --scope headers
uv run python catalyst_cli.py settings "Ctrl+N" --scope accelerators
uv run python catalyst_cli.py samples AISC_C --ext .catpart --source startup
```

## Rules for CATIA V5 Automation Generation

- **Never Guess APIs**: Do not invent interfaces, properties, methods, or enum values. Always verify exact spelling, parameter count/direction, and return type first.
- **Verify Reachability (`from_interface`)**: When creating or traversing objects, pass `from_interface="Application"` (or run `catalyst_cli.py path`) to verify the exact chain and terminal constructor signature.
- **Respect Implementation Caveats (`pitfall_warning`)**: Whenever `get_catia_interface` returns a `pitfall_warning`, strictly follow its `safe_pattern` and contract constraints (e.g. `Material.PutIcon` requires a directory path ending with `\`, `CatalogDocument.CreateCatalogFromcsv` requires headless batch mode + ANSI CSV without BOM, `DesignTable.Synchronize` requires CRLF text files).
- **Respect Inheritance & `pywin32` Types**: Any inherited member shown by `get_catia_interface` is valid to call directly. Unpack `[out]`/`[inout]` tuple returns per `python_mapping`, pass `CATSafeArrayVariant` as Python `list`/`tuple`, and use inline `referenced_enums` values.
- **Route Non-COM Queries Precisely**: For `CATIA.StartCommand(...)` IDs or shortcuts query `search_catia_settings(scope="headers"|"accelerators")` (or `search_catia_api(..., include_catnls=True)`); for `Tools > Options` / `.CATSettings` use `scope="options"`; for GUI-only/batch workflows use `search_catia_docs`, `search_catia_samples`, or `search_catia_recipes`.
