"""
Unit tests for FTS5 full-text indexing, query sanitization, and BM25 ranking.
"""

import pytest
from src.engine.db import CatalystDB, _format_fts_query


@pytest.fixture
def db():
    return CatalystDB()


def test_format_fts_query():
    # Empty query
    assert _format_fts_query("") == ""
    assert _format_fts_query("   ") == ""

    # Normal multi-word
    res = _format_fts_query("export step")
    assert res == '"export"* AND "step"*'

    # Query with syntax punctuation
    res_punct = _format_fts_query('export: (step) + [stl]* "iges"')
    assert '"export"*' in res_punct
    assert '"step"*' in res_punct
    assert '"stl"*' in res_punct
    assert '"iges"*' in res_punct
    assert "(" not in res_punct and ")" not in res_punct


def test_fts_tables_exist(db):
    assert db._has_table("usecases_fts")
    assert db._has_table("apis_fts")


def test_fts_search_recipes_bm25(db):
    recipes = db.search_recipes("export step", limit=5)
    assert len(recipes) > 0
    # Recipe titles or context should match
    assert any("step" in r["title"].lower() or "step" in r["code"].lower() for r in recipes)


def test_fts_search_api_bm25(db):
    # Searching 'Pad' should put interface Pad at or near the top
    results = db.search("Pad", item_type="interface", limit=5)
    assert len(results) > 0
    assert results[0]["name"] == "Pad"
    assert results[0]["type"] == "interface"


def test_fts_fallback_on_empty_match(db):
    # Searching non-existent query should cleanly return empty list without crashing
    results = db.search("NonExistentXYZWord123456", limit=5)
    assert results == []
