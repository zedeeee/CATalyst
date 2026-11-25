"""
Opt-in Local Real-DB Watchdog & Live CATIA Verification Gates.
Runs automatically against real dist/catalyst.db & dist/local/catalyst_docs.db when present
(and skipped cleanly in clean BYOD CI clones without local Dassault binaries).
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from src.engine.caveat_miner import CaveatMiner
from src.engine.db import CatalystDB
from src.engine.docs_db import CatalystDocsDB, resolve_docs_db_path
from tests.test_retrieval_benchmark import GOLDEN_FILE, evaluate_golden_queries

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _get_real_core_db_or_skip() -> Path:
    env_override = os.environ.get("CATALYST_DB_PATH")
    real_db = PROJECT_ROOT / "dist" / "catalyst.db"
    if env_override and Path(env_override).resolve() != real_db.resolve():
        pytest.skip("Synthetic CI override active; skipping real_db gate.")
    if not real_db.exists():
        pytest.skip("Local dist/catalyst.db not built; skipping real_db gate.")
    return real_db


@pytest.mark.real_db
def test_real_db_coverage_and_ranking_watchdog():
    real_db = _get_real_core_db_or_skip()
    conn = sqlite3.connect(real_db)
    total_methods = conn.execute("SELECT COUNT(*) FROM methods").fetchone()[0]
    desc_methods = conn.execute("SELECT COUNT(*) FROM methods WHERE length(description) > 0").fetchone()[0]
    total_edges = conn.execute("SELECT COUNT(*) FROM object_edges").fetchone()[0]
    conn.close()

    assert total_methods >= 9000
    assert desc_methods / total_methods >= 0.85, f"Member doc coverage regressed: {desc_methods}/{total_methods}"
    assert total_edges >= 6000

    db = CatalystDB(real_db)
    cases = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    metrics = evaluate_golden_queries(db, cases)
    assert not metrics["failures"], f"Real DB Golden failures: {metrics['failures']}"
    assert metrics["recall"] == 1.0
    assert metrics["mrr"] >= 0.80

    # Bilingual search on real DB
    assert any(r["name"] == "Material.PutIcon" for r in db.search("缩略图", limit=5))
    assert any(r["name"] == "Pad.GetDirection" for r in db.search("凸台 方向", item_type="method", limit=5))
    assert any(r["name"] == "HybridBody" for r in db.search("几何图形集", item_type="interface", limit=5))


@pytest.mark.real_db
def test_real_docs_db_linkage_and_caveat_miner_watchdog():
    _get_real_core_db_or_skip()
    docs_path = resolve_docs_db_path()
    if not docs_path or not docs_path.exists():
        pytest.skip("Local catalyst_docs.db not built; skipping docs watchdog.")

    conn = sqlite3.connect(docs_path)
    total_links = conn.execute("SELECT COUNT(*) FROM doc_api_links").fetchone()[0]
    linked_ifaces = conn.execute("SELECT COUNT(DISTINCT interface_name) FROM doc_api_links").fetchone()[0]
    conn.close()

    assert total_links >= 12000
    assert linked_ifaces >= 330

    docs_db = CatalystDocsDB(docs_path)
    bilingual_docs = docs_db.search_docs("缩略图 材质", limit=5)
    assert bilingual_docs["total_matches"] > 0

    cands = CaveatMiner(docs_db_path=docs_path).mine_caveats()
    assert any(c["interface"] == "Material" and c["member"] == "PutIcon" for c in cands)


@pytest.mark.live_catia
def test_live_catia_com_session_diagnostic():
    if os.environ.get("CATALYST_RUN_LIVE_CATIA") != "1":
        pytest.skip("Set CATALYST_RUN_LIVE_CATIA=1 to run live CATIA ROT smoke test.")
    from src.client import CatiaClient

    client = CatiaClient()
    if not client.is_running():
        pytest.skip("No active CATIA V5 instance in ROT.")
    report = client.get_diagnostic_report()
    assert "Connected" in report
