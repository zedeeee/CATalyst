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
    is_http_url,
    is_running_in_venv,
    is_unc_path,
    normalize_http_doc_root,
    normalize_http_install_root,
    parse_user_path,
    resolve_doc_root,
    resolve_doc_root_location,
    resolve_install_root,
    resolve_install_root_location,
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


def _prompt_path_interactive(label: str, normalizer, allow_http: bool = False):
    if not sys.stdin or not sys.stdin.isatty():
        return None
    try:
        raw = input(f"Enter {label} (leave blank to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not raw:
        return None
    if allow_http and is_http_url(raw):
        norm_url = normalize_http_doc_root(raw) if normalizer is normalize_doc_root else normalize_http_install_root(raw)
        if norm_url:
            return norm_url
        logger.warning(f"Invalid HTTP(S) URL: {raw}")
        return None
    parsed = parse_user_path(raw)
    norm = normalizer(parsed) if parsed else None
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
        help="Only bind/switch doc/install prefix in dist/local/paths.json (local path, SMB UNC, or HTTP(S) URL) without rebuilding DB.",
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

    if not args.set_paths and (is_http_url(args.doc_root) or is_http_url(args.install_root)):
        logger.error(
            "Building catalyst_docs.db requires a local directory or mounted/SMB filesystem path "
            "(HTTP(S) URLs cannot be crawled for extraction).\n"
            "If you already have a pre-built dist/local/catalyst_docs.db and only want to bind an HTTP(S) prefix, "
            "run with `--set-paths`: `uv run python build_docs.py --set-paths --doc-root <https://...>`."
        )
        sys.exit(1)

    if args.set_paths:
        doc_root = resolve_doc_root_location(explicit=args.doc_root or None, release_hint=args.release)
        rel_hint = args.release.strip() or detect_release_from_path(doc_root)
        install_root = resolve_install_root_location(explicit=args.install_root or None, release_hint=rel_hint)
        if rel_hint == "unknown":
            rel_hint = detect_release_from_path(install_root)
    else:
        doc_root = resolve_doc_root(explicit=args.doc_root or None, release_hint=args.release)
        rel_hint = args.release.strip() or detect_release_from_path(doc_root)
        install_root = resolve_install_root(explicit=args.install_root or None, release_hint=rel_hint)
        if rel_hint == "unknown":
            rel_hint = detect_release_from_path(install_root)

    # Interactive prompt on fresh machines when auto-discovery finds nothing (local path preferred by default)
    if not doc_root and (args.set_paths or not install_root):
        prompt_label = (
            "CATIA doc root (local path preferred, e.g. D:\\Dassault\\B27doc; optional SMB or HTTP URL)"
            if args.set_paths
            else "CATIA offline doc root (local or SMB path, e.g. D:\\Dassault\\B27doc)"
        )
        doc_root = _prompt_path_interactive(prompt_label, normalize_doc_root, allow_http=args.set_paths)
    if not install_root and (args.set_paths or not doc_root):
        install_root = _prompt_path_interactive(
            "CATIA install root (local path, e.g. D:\\Dassault\\B27)",
            normalize_install_root,
            allow_http=args.set_paths,
        )

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

    # Cap default worker count on SMB/UNC shares to avoid thrashing remote HDD I/O
    effective_workers: Optional[int] = args.workers if args.workers > 0 else (4 if is_unc_path(doc_root) else None)
    if args.workers <= 0 and is_unc_path(doc_root):
        logger.info("  SMB/UNC Share: Auto-throttling HTML parser workers to 4 for stable network I/O.")

    builder = CatalystDocsBuilder(
        output_db=args.output,
        doc_root=doc_root,
        install_root=install_root,
        release=rel_hint,
        only_modules=only_modules,
        workers=effective_workers,
    )
    summary = builder.build()

    try:
        from src.engine.linkage_builder import LinkageBuilder
        linkage_res = LinkageBuilder(docs_db_path=summary["output_db"]).build_linkages()
        logger.info(
            f"Built {linkage_res['total_links']} official API code linkages "
            f"({linkage_res['linked_interfaces']} interfaces, {linkage_res['linked_members']} members) "
            f"in {linkage_res['elapsed_seconds']}s."
        )
    except Exception as e:
        logger.warning(f"Linkage build step skipped or failed: {e}")

    if not args.skip_smoke_test and not only_modules:
        run_docs_smoke_test(Path(summary["output_db"]))


if __name__ == "__main__":
    main()
