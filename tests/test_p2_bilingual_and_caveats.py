"""
Unit tests for P2 Bilingual CAD Synonyms, CaveatMiner automatic extraction,
externalized data/pitfalls.json loading, and cross-DB hints.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.engine.caveat_miner import CaveatMiner
from src.engine.db import CatalystDB
from src.engine.pitfalls import get_interface_pitfalls, get_method_pitfall
from src.engine.synonyms import expand_bilingual_queries
from src.mcp import server as mcp_server


def test_bilingual_synonym_expansion():
    exp_thumb = expand_bilingual_queries("缩略图")
    assert any("Icon" in x or "PutIcon" in x for x in exp_thumb)

    exp_pad_dir = expand_bilingual_queries("凸台 方向")
    assert "Pad Direction" in exp_pad_dir

    # Unknown pure-ASCII tokens must NOT be falsely expanded
    assert expand_bilingual_queries("NonExistentCatalystApiXYZ999") == []


def test_bilingual_api_and_recipe_search_ci():
    db = CatalystDB()

    # Chinese query for thumbnail -> Material.PutIcon / GetIcon
    res_thumb = db.search("缩略图", limit=5)
    assert any(r["name"] in ("Material.PutIcon", "Material.GetIcon") for r in res_thumb), res_thumb

    # English alias 'thumbnail' -> Material.PutIcon / GetIcon
    res_en_thumb = db.search("thumbnail", limit=5)
    assert any(r["name"] in ("Material.PutIcon", "Material.GetIcon") for r in res_en_thumb), res_en_thumb

    # Combined Chinese query "凸台 方向" -> Pad.GetDirection
    res_pad = db.search("凸台 方向", item_type="method", limit=5)
    assert any(r["name"] == "Pad.GetDirection" for r in res_pad), res_pad

    # Chinese recipe search "批量 导出 step" -> Product STEP export recipe
    res_recipe = db.search_recipes("批量 导出 step", limit=5)
    assert any(r["interface"] == "Product" for r in res_recipe), res_recipe


def test_external_pitfalls_json_hotload():
    p = get_method_pitfall("Material", "PutIcon")
    assert p is not None
    assert p["severity"] == "CRITICAL"
    iface_pitfalls = get_interface_pitfalls("Material")
    assert "puticon" in iface_pitfalls


def test_caveat_miner_discovers_folder_and_inline_comment(tmp_path):
    from tests.conftest import build_synthetic_core_db

    core_db = build_synthetic_core_db(tmp_path / "core.db")
    docs_db = tmp_path / "docs.db"
    conn = sqlite3.connect(docs_db)
    conn.executescript("""
        CREATE TABLE doc_api_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            interface_name TEXT NOT NULL,
            member_name TEXT NOT NULL,
            target_type TEXT NOT NULL,
            ref_id TEXT NOT NULL,
            rel_path TEXT NOT NULL,
            title TEXT,
            line_no INTEGER DEFAULT 0,
            code_snippet TEXT NOT NULL,
            official_note TEXT
        );
    """)
    conn.execute(
        "INSERT INTO doc_api_links (interface_name, member_name, target_type, ref_id, rel_path, title, line_no, code_snippet, official_note) "
        "VALUES ('Material', 'PutIcon', 'sample', 's1', 'startup/importMaterialLibrary.CATScript', 'importMaterialLibrary', 147, "
        "'oMaterial.PutIcon(sFolderIcon & sSep & oFamily.Name & sSep) '' & oMaterial.Name & \".jpg\")', NULL)"
    )
    conn.commit()
    conn.close()

    out_json = tmp_path / "candidates.json"
    cands = CaveatMiner(core_db_path=core_db, docs_db_path=docs_db).mine_caveats(output_path=out_json)
    assert out_json.exists()

    cats = {(c["interface"], c["member"], c["category"]) for c in cands}
    assert ("Material", "PutIcon", "FOLDER_PATH_CONTRACT") in cats
    assert ("Material", "PutIcon", "INLINE_WORKAROUND_COMMENT") in cats
    assert ("Material", "PutIcon", "SAMPLE_TRAILING_SEP") in cats


def test_mcp_search_api_surfaces_cross_db_recipes():
    raw = mcp_server.search_catia_api(query="export step")
    data = json.loads(raw)
    assert not data.get("isError")
    assert "related_recipes" in data
    assert any(r["interface"] == "Product" for r in data["related_recipes"])
