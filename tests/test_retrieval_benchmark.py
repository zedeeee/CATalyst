"""
Retrieval Quality Benchmark Suite (Recall@K, MRR, anti-starvation, and hallucination guard)
for CATalyst search endpoints using Golden Queries.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from src.engine.db import CatalystDB

GOLDEN_FILE = Path(__file__).resolve().parent / "golden_queries.json"


def evaluate_golden_queries(db: CatalystDB, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute Recall@K and Mean Reciprocal Rank (MRR) over golden query expectations."""
    total_positive = 0
    hits = 0
    rr_sum = 0.0
    failures: List[str] = []

    for case in cases:
        cid = case["id"]
        tool = case["tool"]
        q = case["query"]
        top_k = int(case.get("top_k", 5))

        if tool == "search_api":
            res = db.search(q, item_type=case.get("item_type", "all"), limit=max(top_k, 10))
            names = [r["name"] for r in res[:top_k]]
        elif tool == "search_recipes":
            res = db.search_recipes(q, source="all", limit=max(top_k, 5))
            names = [r["interface"] for r in res[:top_k]]
        else:
            raise ValueError(f"Unsupported golden tool: {tool}")

        if case.get("expected_empty"):
            if res:
                failures.append(f"{cid}: expected empty, got {[r['name'] for r in res]}")
            continue

        total_positive += 1
        expected = set(case["expected_any"])
        rank_pos = None
        for idx, cand in enumerate(names, start=1):
            if cand in expected:
                if case.get("require_community") and res[idx - 1].get("source") != "community":
                    continue
                rank_pos = idx
                break

        if rank_pos is not None:
            hits += 1
            rr_sum += 1.0 / rank_pos
        else:
            failures.append(f"{cid} (q='{q}'): expected any of {sorted(expected)} in top-{top_k}, got {names}")

    recall = hits / total_positive if total_positive else 1.0
    mrr = rr_sum / total_positive if total_positive else 1.0
    return {"recall": recall, "mrr": mrr, "hits": hits, "total": total_positive, "failures": failures}


def test_p0_golden_retrieval_quality():
    db = CatalystDB()
    cases = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    metrics = evaluate_golden_queries(db, cases)
    assert not metrics["failures"], f"Golden benchmark failures:\n" + "\n".join(metrics["failures"])
    assert metrics["recall"] >= 0.90, f"Recall too low: {metrics['recall']}"
    assert metrics["mrr"] >= 0.70, f"MRR too low: {metrics['mrr']}"


def test_search_syntax_uses_canonical_search_grammar():
    db = CatalystDB()
    gsd = db.get_search_syntax(workbench="GenerativeShapeDesign")
    assert gsd["prefix"] == "CATGspSearch", f"Stale CATGsdSearch bug returned: {gsd['prefix']}"
    combined = db.get_search_syntax(workbench="PartDesign", query_type="Hole")
    assert combined["prefix"] == "CATPrtSearch"
    assert any(m["type"] == "Hole" for m in combined.get("matched_types", []))
