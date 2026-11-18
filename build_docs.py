#!/usr/bin/env python
"""
Local Offline Documentation Extension Builder & Path Setup Tool for CATalyst.
Compiles version-aligned CATIA V5 User's Guide HTML (Bxxdoc), msgcatalog (*.CATNls),
and official samples into portable dist/local/catalyst_docs.db.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from src.engine.local_config import (
    LOCAL_PATHS_CONFIG,
    is_running_in_venv,
    resolve_doc_root,
    resolve_install_root,
    save_local_paths_config,
)
from src.parser.docs_builder import CatalystDocsBuilder
from src.parser.docs_parser import (
    detect_release_from_path,
    normalize_doc_root,
    normalize_install_root,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent


def _prompt_path_interactive(label: str, normalizer) -> Optional[Path]:
    if not sys.stdin or not sys.stdin.isatty():
        return None
    try:
        raw = input(f"Enter {label} (leave blank to skip): ").strip().strip('"').strip("'")
    except (EOFError, KeyboardInterrupt):
        return None
    if not raw:
        return None
    norm = normalizer(Path(raw))
    if not norm:
        logger.warning(f"Path not found or invalid: {raw}")
        return None
    return norm


def run_docs_smoke_test(db_path: Path) -> None:
    from src.engine.docs_db import CatalystDocsDB

    logger.info("\n--- Starting Offline Docs Smoke Tests ---")
    db = CatalystDocsDB(db_path)
    meta = db.get_meta()
    logger.info(
        f"  [1/4] Loaded catalyst_docs.db (release={meta.get('catia_release')}, "
        f"pages={meta.get('page_count')}, samples={meta.get('sample_count')})"
    )
    assert int(meta.get("page_count", 0)) > 0 or int(meta.get("nls_count", 0)) > 0, "Empty docs database"

    if int(meta.get("page_count", 0)) > 0:
        res = db.search_docs("Catalog Batch Mode", limit=5)
        assert res["total_matches"] > 0, "Smoke test failed: 'Catalog Batch Mode' returned 0 matches"
        first_id = res["results"][0]["doc_id"]
        page = db.get_doc_page(first_id, max_chars=2000)
        assert page and not page.get("isError"), f"Smoke test failed: get_doc_page({first_id})"
        logger.info(f"  [2/4] Docs FTS5 search & page read verified (top hit: {first_id})")

    if int(meta.get("nls_count", 0)) > 0:
        nls = db.search_settings("ResolvedComponents", limit=5)
        assert nls["total_nls_matches"] > 0, "Smoke test failed: 'ResolvedComponents' returned 0 CATNls hits"
        logger.info(f"  [3/4] CATNls & Tools>Options cross-search verified ({nls['total_nls_matches']} hits)")

    if int(meta.get("sample_count", 0)) > 0:
        smp = db.search_samples("BatchCatalog", include_content=True, limit=5)
        assert smp["total_matches"] > 0, "Smoke test failed: 'BatchCatalog' sample not found"
        logger.info(f"  [4/4] Official sample search verified ({smp['results'][0]['sample_id']})")

    logger.info("--- Offline Docs Smoke Tests Passed ---\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build or configure local CATalyst offline documentation DB (dist/local/catalyst_docs.db)."
    )
    parser.add_argument(
        "--doc-root",
        default="",
        help="Path to CATIA offline docs root (e.g. D:/Dassault/B27doc or .../English/online)",
    )
    parser.add_argument(
        "--install-root",
        default="",
        help="Path to CATIA installation root (e.g. D:/Dassault/B27 or .../win_b64)",
    )
    parser.add_argument(
        "--release",
        default="",
        help="Explicit CATIA release tag (e.g. B27). Auto-detected from paths if omitted.",
    )
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / "dist" / "local" / "catalyst_docs.db"),
        help="Output SQLite DB path (default: dist/local/catalyst_docs.db)",
    )
    parser.add_argument(
        "--modules",
        default="",
        help="Optional comma-separated module dirs to index (e.g. cceug_C2,bascuctg_C2). Omit for full build.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Worker processes for HTML parsing (0 = auto, up to 8).",
    )
    parser.add_argument(
        "--set-paths",
        action="store_true",
        help="Only configure and persist machine-local doc/install roots to dist/local/paths.json without rebuilding DB.",
    )
    parser.add_argument(
        "--no-save-paths",
        action="store_true",
        help="Do not save resolved doc/install roots into dist/local/paths.json.",
    )
    parser.add_argument(
        "--skip-smoke-test",
        action="store_true",
        help="Skip post-build smoke tests.",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip interactive confirmation prompt for detected local environment paths.",
    )
    args = parser.parse_args()

    if not is_running_in_venv():
        logger.warning(
            "[ENV NOTICE] Running under global Python (%s). "
            "Prefer isolated virtual environment: `uv sync && uv run python build_docs.py`.",
            sys.executable,
        )

    doc_root = resolve_doc_root(explicit=args.doc_root or None, release_hint=args.release)
    rel_hint = args.release.strip() or detect_release_from_path(doc_root)
    install_root = resolve_install_root(explicit=args.install_root or None, release_hint=rel_hint)
    if rel_hint == "unknown":
        rel_hint = detect_release_from_path(install_root)

    # Interactive prompt on fresh machines when auto-discovery finds nothing
    if not doc_root and (args.set_paths or not install_root):
        doc_root = _prompt_path_interactive("CATIA offline doc root (e.g. D:\\Dassault\\B27doc)", normalize_doc_root)
    if not install_root and (args.set_paths or not doc_root):
        install_root = _prompt_path_interactive("CATIA install root (e.g. D:\\Dassault\\B27)", normalize_install_root)

    if rel_hint == "unknown":
        rel_hint = detect_release_from_path(doc_root) or detect_release_from_path(install_root) or "unknown"

    if not doc_root and not install_root:
        logger.error(
            "Could not auto-detect CATIA offline docs or install directory (checked MCP env, "
            "dist/local/paths.json, CATEnv, and default Program Files).\n"
            "Pass --doc-root / --install-root, set CATALYST_DOC_ROOT / CATALYST_INSTALL_ROOT, "
            "or run interactively to configure."
        )
        sys.exit(1)

    logger.info("====================================================")
    logger.info("  CATalyst Offline Documentation Extension Builder  ")
    logger.info("====================================================")
    logger.info(f"  Python Env   : {sys.executable} ({'venv' if is_running_in_venv() else 'GLOBAL - venv recommended'})")
    logger.info(f"  Doc Root     : {doc_root or '(none)'} [read-only]")
    logger.info(f"  Install Root : {install_root or '(none)'} [read-only]")
    logger.info(f"  Release Tag  : {rel_hint}")
    logger.info(f"  Output DB    : {args.output} [project-local, gitignored]")
    logger.info(f"  Local Config : {LOCAL_PATHS_CONFIG} [project-local, gitignored]")
    logger.info("  System Scope : Zero changes to system PATH, registry, or CATIA install directory.")

    if not args.yes and sys.stdin and sys.stdin.isatty():
        try:
            ans = input("Proceed with local configuration/build using these paths? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.exit(1)
        if ans in ("n", "no"):
            logger.info("Cancelled by user.")
            sys.exit(0)

    if not args.no_save_paths:
        cfg_file = save_local_paths_config(doc_root=doc_root, install_root=install_root, release=rel_hint)
        logger.info(f"Saved machine-local paths to {cfg_file} (gitignored).")

    if args.set_paths:
        return

    only_modules = [m.strip() for m in args.modules.split(",") if m.strip()] if args.modules else None
    if only_modules:
        logger.info(f"  Modules Only : {', '.join(only_modules)}")

    builder = CatalystDocsBuilder(
        output_db=args.output,
        doc_root=doc_root,
        install_root=install_root,
        release=rel_hint,
        only_modules=only_modules,
        workers=args.workers if args.workers > 0 else None,
    )
    summary = builder.build()

    if not args.skip_smoke_test and not only_modules:
        run_docs_smoke_test(Path(summary["output_db"]))


if __name__ == "__main__":
    main()
