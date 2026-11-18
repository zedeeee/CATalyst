#!/usr/bin/env python
"""
Local Offline Documentation Extension Builder for CATalyst.
Compiles version-aligned CATIA V5 User's Guide HTML (Bxxdoc), msgcatalog (*.CATNls),
and official plain-text samples into dist/local/catalyst_docs.db.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from src.parser.docs_builder import CatalystDocsBuilder

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent


def _auto_detect_doc_root() -> Optional[Path]:
    env_val = os.environ.get("CATALYST_DOC_ROOT", "").strip()
    if env_val and Path(env_val).exists():
        return Path(env_val)
    base = Path(r"C:\Program Files\Dassault Systemes")
    if base.exists():
        for cand in sorted(base.glob("B*doc"), reverse=True):
            online = cand / "English" / "online"
            if online.exists():
                return online
    return None


def _auto_detect_install_root(release_hint: str = "") -> Optional[Path]:
    env_val = os.environ.get("CATALYST_INSTALL_ROOT", "").strip()
    if env_val and Path(env_val).exists():
        return Path(env_val)
    base = Path(r"C:\Program Files\Dassault Systemes")
    if not base.exists():
        return None
    if release_hint:
        exact = base / release_hint / "win_b64"
        if exact.exists():
            return exact
    for cand in sorted(base.glob("B*"), reverse=True):
        if cand.name.lower().endswith("doc"):
            continue
        win64 = cand / "win_b64"
        if (win64 / "resources" / "msgcatalog").exists():
            return win64
    return None


def run_docs_smoke_test(db_path: Path) -> None:
    from src.engine.docs_db import CatalystDocsDB

    logger.info("\n--- Starting Offline Docs Smoke Tests ---")
    db = CatalystDocsDB(db_path)
    meta = db.get_meta()
    logger.info(f"  [1/4] Loaded catalyst_docs.db (release={meta.get('catia_release')}, pages={meta.get('page_count')})")
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
        logger.info(f"  [4/4] Official text samples search verified ({smp['results'][0]['sample_id']})")

    logger.info("--- Offline Docs Smoke Tests Passed ---\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build local version-aligned CATalyst offline documentation DB (dist/local/catalyst_docs.db)."
    )
    parser.add_argument(
        "--doc-root",
        default="",
        help="Path to CATIA offline docs online directory (e.g. <Install>/B27doc/English/online)",
    )
    parser.add_argument(
        "--install-root",
        default="",
        help="Path to CATIA win_b64 install root containing resources/msgcatalog and startup/",
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
        help="Optional comma-separated module dirs to index (e.g. cceug_C2,bascuctg_C2,cfyugpkt_C2). Omit for full build.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Worker processes for HTML parsing (0 = auto, up to 8).",
    )
    parser.add_argument(
        "--skip-smoke-test",
        action="store_true",
        help="Skip post-build smoke tests.",
    )
    args = parser.parse_args()

    doc_root = Path(args.doc_root) if args.doc_root else _auto_detect_doc_root()
    from src.parser.docs_parser import detect_release_from_path

    rel_hint = args.release.strip() or detect_release_from_path(doc_root)
    install_root = Path(args.install_root) if args.install_root else _auto_detect_install_root(rel_hint)

    if not doc_root and not install_root:
        logger.error(
            "Could not locate CATIA offline docs or install directory. "
            "Pass --doc-root / --install-root or set CATALYST_DOC_ROOT / CATALYST_INSTALL_ROOT."
        )
        sys.exit(1)

    only_modules = [m.strip() for m in args.modules.split(",") if m.strip()] if args.modules else None

    logger.info("====================================================")
    logger.info("  CATalyst Offline Documentation Extension Builder  ")
    logger.info("====================================================")
    logger.info(f"  Doc Root     : {doc_root or '(none)'}")
    logger.info(f"  Install Root : {install_root or '(none)'}")
    logger.info(f"  Release Tag  : {rel_hint}")
    logger.info(f"  Output DB    : {args.output}")
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
