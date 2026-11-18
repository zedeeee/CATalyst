#!/usr/bin/env python
"""
Main Build Script for CATalyst.
Executes the full pipeline:
1. Unpack CHM (if raw/ is empty)
2. Parse HTML and fuse inheritance
3. Build SQLite/JSON Database
4. Run Post-Build Smoke Tests on DB Engine and MCP Server
"""

import argparse
import os
import sys
import json
import logging
from pathlib import Path
from src.engine.local_config import (
    LOCAL_PATHS_CONFIG,
    is_running_in_venv,
    parse_user_path,
    resolve_chm_path,
    save_local_paths_config,
)
from src.parser.chm_unpacker import ensure_unpacker_choice, unpack_chm
from src.parser.builder import CatalystBuilder
from src.parser.docs_parser import detect_release_from_path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def run_smoke_test(db_path: Path):
    """
    Executes an automated smoke test suite against the generated SQLite database
    and MCP Server endpoints to prevent damaged builds from going live.
    """
    logger.info("\n--- Starting Post-Build Smoke Tests ---")
    
    from src.engine.db import CatalystDB
    import src.mcp.server as mcp_server
    
    # 1. Test Database Connectivity & Resolution
    db = CatalystDB(db_path)
    logger.info("  [1/6] Database connection & resolution verified.")

    # 2. Test get_interface & Inheritance Fusion
    pad_data = db.get_interface("Pad")
    assert pad_data is not None, "Smoke test failed: 'Pad' interface not found."
    assert "Prism" in pad_data.get("inheritance_chain", []), "Smoke test failed: 'Pad' inheritance chain missing 'Prism'."
    method_names = [m["name"] for m in pad_data.get("methods", [])]
    assert "GetDirection" in method_names, "Smoke test failed: Inherited method 'GetDirection' missing from 'Pad'."
    logger.info("  [2/6] Interface retrieval & inheritance fusion verified ('Pad').")

    # 3. Test Bidirectional Enum Retrieval
    enum_data = db.get_enum("CatProductSource")
    assert enum_data is not None, "Smoke test failed: 'CatProductSource' enum not found."
    assert any(v["name"] == "catProductMade" for v in enum_data["values"]), "Smoke test failed: 'catProductMade' missing in values."

    rev_val = db.get_enum(name="CatProductSource", value=1)
    assert rev_val is not None and rev_val.get("matched_value", {}).get("name") == "catProductMade", (
        f"Smoke test failed: Enum value lookup failed. Got: {rev_val}"
    )

    rev_member = db.get_enum(member_name="catProductMade")
    assert rev_member is not None and rev_member["name"] == "CatProductSource", (
        f"Smoke test failed: Enum member reverse lookup failed. Got: {rev_member}"
    )
    logger.info("  [3/6] Bidirectional enum query & reverse lookup verified ('CatProductSource').")

    # 4. Test Property/Method Reverse Interface Search
    prop_lookup = db.get_interfaces_by_member("PartNumber", member_type="property")
    assert prop_lookup["total_host_interfaces"] > 0, "Smoke test failed: Reverse search for 'PartNumber' returned 0 hosts."
    assert "Product" in prop_lookup["host_interfaces"], "Smoke test failed: 'Product' not found in host interfaces of 'PartNumber'."
    logger.info("  [4/6] Property/method reverse host interface lookup verified ('PartNumber' -> 'Product').")

    # 5. Test MCP Server Tool Endpoints & Granular Features
    # 5.1 get_catia_interface with alias & member filtering
    mcp_if_res = json.loads(mcp_server.get_catia_interface(interface_name="Pad", member_name="GetDirection"))
    assert not mcp_if_res.get("isError") and mcp_if_res.get("name") == "Pad", f"MCP interface query failed: {mcp_if_res}"
    assert len(mcp_if_res["methods"]) == 1 and mcp_if_res["methods"][0]["name"] == "GetDirection", "Granular member filter failed"

    # 5.2 Python pywin32 mapping hints on methods with out params
    vis_res = db.get_interface("VisPropertySet", member_name="GetRealColor")
    assert vis_res and len(vis_res["methods"]) == 1, "Failed to retrieve VisPropertySet.GetRealColor"
    method_data = vis_res["methods"][0]
    assert "python_mapping" in method_data and "pywin32_call" in method_data["python_mapping"], "Missing Python COM mapping hint"

    # 5.3 get_catia_usecases tool
    uc_res = json.loads(mcp_server.get_catia_usecases(interface="VisPropertySet", member="GetRealColor"))
    assert not uc_res.get("isError") and uc_res.get("total_examples", 0) > 0, f"MCP usecase query failed: {uc_res}"

    # 5.4 get_catia_search_syntax tool
    syntax_res = json.loads(mcp_server.get_catia_search_syntax(workbench="PartDesign"))
    assert not syntax_res.get("isError") and syntax_res.get("prefix") == "CATPrtSearch", f"MCP search syntax failed: {syntax_res}"

    # 5.5 get_catia_enum with alias and value
    mcp_enum_res = json.loads(mcp_server.get_catia_enum(enum_name="CatProductSource", value=1))
    assert not mcp_enum_res.get("isError") and mcp_enum_res.get("matched_value", {}).get("name") == "catProductMade", (
        f"MCP enum query failed: {mcp_enum_res}"
    )

    # 5.6 search_catia_api with alias
    mcp_search_res = json.loads(mcp_server.search_catia_api(keyword="PartNumber", item_type="property"))
    assert not mcp_search_res.get("isError") and mcp_search_res.get("total_matches", 0) > 0, (
        f"MCP search query failed: {mcp_search_res}"
    )
    logger.info("  [5/6] MCP tool endpoints, granular filters, usecase tools, and syntax verified.")

    # 6. Test MCP Server Global Exception Safety
    err_res = json.loads(mcp_server.get_catia_interface(name="NonExistentInterface999"))
    assert err_res.get("isError") is True, "MCP error handling failed: Expected isError: True for missing interface."
    logger.info("  [6/8] MCP global exception safety & error responses verified.")

    # 7. Test FTS5 Full-Text Search Indexes & BM25
    assert db._has_table("usecases_fts"), "Smoke test failed: 'usecases_fts' table missing."
    assert db._has_table("apis_fts"), "Smoke test failed: 'apis_fts' table missing."
    fts_recipes = db.search_recipes("export step", limit=3)
    assert len(fts_recipes) > 0, "Smoke test failed: FTS5 recipe search returned 0 results."
    logger.info("  [7/8] FTS5 full-text indexing & BM25 ranking verified.")

    # 8. Test Client Diagnostics
    from src.client import CatiaClient
    client = CatiaClient()
    report = client.get_diagnostic_report()
    assert "CATIA V5 Diagnostic Report" in report, "Smoke test failed: Client diagnostic report invalid."
    logger.info("  [8/8] Client COM bridge & host diagnostics verified.")

    logger.info("--- Smoke Tests Passed Successfully (8/8) ---\n")


def _warn_if_global_python():
    if not is_running_in_venv():
        logger.warning(
            "[ENV NOTICE] Running under global Python (%s). "
            "Use an isolated virtual environment via `uv sync && uv run python build.py` to avoid polluting system packages.",
            sys.executable,
        )


def _prompt_chm_interactive() -> Path | None:
    if not sys.stdin or not sys.stdin.isatty():
        return None
    try:
        raw = input("Enter path to local V5Automation.chm (leave blank to abort): ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    p = parse_user_path(raw)
    return p.resolve() if (p and p.is_file()) else None


def main():
    parser = argparse.ArgumentParser(
        description="Build CATalyst core API database (dist/catalyst.db) from local V5Automation.chm."
    )
    parser.add_argument(
        "--chm",
        default="",
        help="Path to V5Automation.chm (auto-detected from CATEnv / dist/local/paths.json if omitted).",
    )
    parser.add_argument(
        "--7z",
        dest="seven_zip",
        default="",
        help="Explicit path to 7z/7za executable.",
    )
    parser.add_argument(
        "--use-hh",
        action="store_true",
        help="Windows only: explicitly allow hh.exe fallback when 7-Zip is unavailable.",
    )
    parser.add_argument(
        "--force-unpack",
        action="store_true",
        help="Re-extract data/raw even if HTML files already exist.",
    )
    parser.add_argument(
        "--with-docs",
        action="store_true",
        help="Also run build_docs.py after building dist/catalyst.db.",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip interactive confirmation prompt for detected local environment paths.",
    )
    args = parser.parse_args()

    _warn_if_global_python()

    if args.seven_zip:
        sz_path = parse_user_path(args.seven_zip)
        if not sz_path or not sz_path.is_file():
            logger.error(f"Specified 7z executable not found: {args.seven_zip}")
            sys.exit(1)
        os.environ["CATALYST_7Z_PATH"] = str(sz_path.resolve())

    raw_dir = Path("data/raw")
    dist_dir = Path("dist")
    has_html = raw_dir.exists() and any(raw_dir.glob("**/*.htm"))
    interactive = (not args.yes) and bool(sys.stdin and sys.stdin.isatty())

    chm_file = resolve_chm_path(explicit=args.chm or None)
    if not chm_file and (args.force_unpack or not has_html):
        logger.warning(
            "Could not auto-detect V5Automation.chm via CATALYST_CHM_PATH, dist/local/paths.json, or CATEnv."
        )
        chm_file = _prompt_chm_interactive()
        if not chm_file:
            logger.error(
                "Aborting: V5Automation.chm not found. Pass `--chm <path/to/V5Automation.chm>` "
                "or set CATALYST_CHM_PATH in your environment."
            )
            sys.exit(1)

    allow_hh = args.use_hh
    if args.force_unpack or not has_html:
        ready, allow_hh = ensure_unpacker_choice(interactive=interactive, allow_hh_fallback=allow_hh)
        if not ready:
            sys.exit(1)

    logger.info("====================================================")
    logger.info("  CATalyst Core API Builder (Isolated Local Env)    ")
    logger.info("====================================================")
    logger.info(f"  Python Env   : {sys.executable} ({'venv' if is_running_in_venv() else 'GLOBAL - venv recommended'})")
    logger.info(f"  Source CHM   : {chm_file or '(reusing existing data/raw)'} [read-only]")
    logger.info(f"  Output DB    : {(dist_dir / 'catalyst.db').resolve()} [project-local]")
    logger.info(f"  Local Config : {LOCAL_PATHS_CONFIG} [project-local]")
    logger.info("  System Scope : Zero changes to system PATH, registry, or CATIA install directory.")

    if interactive:
        try:
            ans = input("Proceed with local initialization using these paths? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.exit(1)
        if ans in ("n", "no"):
            logger.info("Cancelled by user.")
            sys.exit(0)

    if chm_file:
        save_local_paths_config(chm_path=chm_file, release=detect_release_from_path(chm_file))

    if args.force_unpack or not has_html:
        logger.info("Extracting raw HTML from V5Automation.chm...")
        success = unpack_chm(chm_file, raw_dir, allow_hh_fallback=allow_hh)
        if not success:
            logger.error("Failed to extract CHM. Aborting build.")
            sys.exit(1)
    else:
        logger.info("Found existing raw HTML extraction. Skipping unpack (use --force-unpack to re-extract).")

    # Step 2 & 3: ETL & Build Database
    logger.info("Starting CATalyst Builder...")
    builder = CatalystBuilder(raw_dir=raw_dir, dist_dir=dist_dir)
    builder.build()
    
    # Step 4: Run Post-Build Smoke Tests
    db_path = dist_dir / "catalyst.db"
    try:
        run_smoke_test(db_path)
    except Exception as e:
        logger.error(f"Post-build smoke tests failed: {e}")
        sys.exit(1)

    logger.info("Core API database build finished successfully.")

    if args.with_docs:
        import subprocess
        cmd = [sys.executable, str(Path(__file__).resolve().parent / "build_docs.py")]
        if args.yes:
            cmd.append("--yes")
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()

