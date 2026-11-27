# CATalyst CLI Fallback & Database Setup

Load this file only when the `catalyst` MCP server is unavailable or local databases are not initialized.

## Database Prerequisites

- **Core COM API DB (`dist/catalyst.db`)**: Required for the 6 core API/Recipe commands.
  - Windows one-click install: `.\install.ps1` (or `uv run python install.py`)
  - macOS / Linux: `./install.sh` (requires `7z`/`p7zip` to unpack `.chm`, or reuse a pre-built `dist/catalyst.db`)
- **Offline Docs DB (`dist/local/catalyst_docs.db`, optional)**: Enables `docs`, `doc-page`, `settings`, and `samples` (`uv run python build_docs.py`).
  - `v0.3.0+` databases auto-migrate `doc_api_links` and `*.CATRsc` shortcuts on first query without rebuilding.

## CLI Fallback (`catalyst_cli.py`)

Run from the CATalyst repository root via `uv run python catalyst_cli.py --help` (or `<subcommand> --help`) to inspect current flags. Common patterns:

```bash
# COM API & Object Graph Navigation
uv run python catalyst_cli.py get Pad --from Application --format card --no-usecases
uv run python catalyst_cli.py get HybridShapeFactory --member "*Fillet*" --format card
uv run python catalyst_cli.py path RenderingMaterial --from Application
uv run python catalyst_cli.py search AddNewPad --detail compact --no-cross-links
uv run python catalyst_cli.py search OpenInNewWnd --include-catnls
uv run python catalyst_cli.py enum CatProductSource --value 1
uv run python catalyst_cli.py recipe "CreateCatalogFromcsv"
uv run python catalyst_cli.py syntax --workbench PartDesign

# Offline Docs, Options, Command Headers, Shortcuts & Samples
uv run python catalyst_cli.py docs "Catalog Batch Mode" --category user_guide --no-snippet
uv run python catalyst_cli.py doc-page "cceug_C2/cceugbt0102.htm" --section "Batch Mode"
uv run python catalyst_cli.py settings FavoriteCatalog --scope options
uv run python catalyst_cli.py settings OpenInNewWnd --scope headers
uv run python catalyst_cli.py settings "Ctrl+N" --scope accelerators
uv run python catalyst_cli.py samples AISC_C --ext .catpart --source startup
```
