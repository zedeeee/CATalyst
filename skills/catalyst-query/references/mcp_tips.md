# CATalyst MCP Token-Saving Tips & Patterns

Load this file only when optimizing large queries or handling tricky CATIA COM edge cases.

## Token-Saving Parameters

- **`get_catia_interface`**:
  - `output_format="card"` (or env `CATALYST_OUTPUT_FORMAT=card`): compact IDL text card (~80–90% smaller than JSON).
  - `detail="auto"` (default): compact overview folding `AnyObject` boilerplate (`Application`, `Name`, `Parent`, `GetItem`) into `omitted_base_members`; automatically switches to `full` when `member_name` is provided. Use `detail="summary"` for huge interfaces.
  - `member_name`: accepts exact name, comma list (`"FirstLimit,GetDirection"`), or `*`/`?` wildcards (`"*Fillet*"`).
  - `include_usecases=False`: skip code snippets when only signatures are needed.
- **`search_catia_api`**:
  - Pass `detail="compact"` and `include_cross_links=False` to suppress descriptions, host summaries, and cross-DB links.
  - Supports bilingual CN/EN queries (e.g., `"凸台"`, `"缩略图"`, `"几何图形集"`).
  - Pass `include_catnls=True` if a single identifier returns 0 COM hits (probes `*.CATNls`/`*.CATRsc`).
- **`search_catia_settings`**:
  - Always pass `scope="headers"` (for `CATIA.StartCommand` IDs like `OpenInNewWnd`) or `scope="accelerators"` (for shortcuts like `Ctrl+N`) to automatically omit unrelated `Tools > Options` docs and XML hints.
- **`search_catia_docs` & `get_catia_doc_page`**:
  - Pass `include_snippet=False` in `search_catia_docs` for a pure `doc_id` index.
  - Use `section="..."` or `start_line`/`end_line` on `get_catia_doc_page` when slicing long `*Source.htm` script pages.
- **`search_catia_samples`**:
  - Narrow via `source="startup"` (`win_b64/startup/`) or `source="doc_samples"`.

## Common Pitfalls & Conventions

- `Material.PutIcon(iPath)`: must pass directory path ending with `\` (CATIA appends `<Material.Name>.jpg`); passing a file path raises `E_FAIL`.
- `CatalogDocument.CreateCatalogFromcsv`: run headless (`CNEXT -batch`) with ANSI CSV (no UTF-8 BOM).
- `DesignTable.Synchronize`: external `.txt` requires Windows CRLF (`\r\n`).
- Python `win32com`: generate pure Python `win32com.client` code unless VBScript/VBA is explicitly requested.
