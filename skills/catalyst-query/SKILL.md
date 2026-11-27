---
name: catalyst-query
description: >-
  Queries CATalyst for verified CATIA V5 COM APIs, object paths, caveats, docs,
  Command Headers, shortcuts, and samples. Use before writing CATIA V5 macros,
  Python win32com scripts, or CATIA configuration/batch workflows.
---

# CATalyst Query Workflow

Query CATalyst as ground truth before writing any CATIA V5 macro, Python `win32com` script, or configuration/batch workflow.

## Query Routing

1. **COM API & Object Path**:
   - Unknown symbol -> `search_catia_api` (supports CN/EN CAD terms).
   - Inspect/instantiate interface -> `get_catia_interface(name, from_interface="Application", output_format="card")` for shortest path, terminal constructor signature, caveats, and inline enums.
   - Big factories (`ShapeFactory`, `HybridShapeFactory`) -> filter via wildcard `member_name="*Fillet*"`.
2. **Non-COM / GUI / Config / Samples**:
   - `CATIA.StartCommand` IDs or shortcuts -> `search_catia_settings(scope="headers"|"accelerators")`.
   - `Tools > Options` / `.CATSettings` -> `search_catia_settings(scope="options")` + `search_catia_docs`.
   - Batch protocols / sample files -> `search_catia_recipes` / `search_catia_samples`.
3. **No MCP Available**: Read [CLI & Setup](./references/cli_and_setup.md) or run `uv run python catalyst_cli.py --help`.

## Rules & Validation

- **Zero Hallucination**: Verify exact spelling, parameter count/direction, and return type against CATalyst output; never invent APIs.
- **Obey Caveats**: When `pitfall_warning` is returned (e.g., `Material.PutIcon` trailing `\`), strictly apply its `safe_pattern`.
- **Verify Before Finalizing**: Confirm `[out]` tuple unpacking from `python_mapping`, pass `CATSafeArrayVariant` as Python `list`/`tuple`, and verify object reachability via `navigation_path`.

## References (Load On Demand)

- Token-saving options & edge-case patterns: [MCP Tips](./references/mcp_tips.md)
- CLI commands & DB setup: [CLI & Setup](./references/cli_and_setup.md)
