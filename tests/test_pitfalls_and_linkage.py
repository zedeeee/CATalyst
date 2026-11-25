import json
import pytest
from pathlib import Path

from src.engine.db import CatalystDB
from src.engine.docs_db import CatalystDocsDB, resolve_docs_db_path
from src.engine.pitfalls import get_method_pitfall, get_interface_pitfalls
from src.mcp.server import get_catia_interface
from src.tools.linkage_diff_reporter import generate_linkage_report


def test_pitfalls_module_direct_lookup():
    # 1. Known critical pitfall
    p = get_method_pitfall("Material", "PutIcon")
    assert p is not None
    assert p["severity"] == "CRITICAL"
    assert p["category"] == "CONTRACT_VIOLATION"
    assert "文件夹路径" in p["summary"]
    assert "oMaterial.PutIcon" in p["safe_pattern"]

    # Case insensitivity
    p2 = get_method_pitfall("material", "puticon")
    assert p2 == p

    # Other registered pitfalls
    p_cat = get_method_pitfall("CatalogDocument", "CreateCatalogFromcsv")
    assert p_cat is not None
    assert "ANSI" in p_cat["summary"]

    p_dt = get_method_pitfall("DesignTable", "Synchronize")
    assert p_dt is not None
    assert "CRLF" in p_dt["summary"]

    # Unknown member
    assert get_method_pitfall("Material", "GetIcon") is None
    assert get_method_pitfall("NonExistent", "Foo") is None


def test_core_db_injects_pitfall_warning():
    db = CatalystDB()
    res = db.get_interface("Material", member_name="PutIcon")
    assert res is not None
    assert len(res["methods"]) == 1
    m = res["methods"][0]
    assert m["name"] == "PutIcon"
    assert "pitfall_warning" in m
    assert m["pitfall_warning"]["severity"] == "CRITICAL"

    # Non-pitfall method
    res_normal = db.get_interface("Material", member_name="GetIcon")
    assert res_normal is not None
    assert len(res_normal["methods"]) == 1
    assert "pitfall_warning" not in res_normal["methods"][0]


def test_docs_db_api_linkages():
    docs_path = resolve_docs_db_path()
    if not docs_path or not docs_path.exists():
        pytest.skip("catalyst_docs.db not available on this machine")

    docs_db = CatalystDocsDB(docs_path)
    links = docs_db.get_api_linkages("Material", "PutIcon")
    assert "linked_official_docs" in links
    assert "linked_sample_scripts" in links
    assert len(links["linked_official_docs"]) > 0
    assert len(links["linked_sample_scripts"]) > 0

    # Verify official use case is present
    doc_ids = [d["doc_id"] for d in links["linked_official_docs"]]
    assert any("importMaterialLibrarySource.htm" in did for did in doc_ids)

    # Verify the code context contains the workaround
    snippets = [s["code_context"] for s in links["linked_sample_scripts"]]
    assert any("PutIcon" in snip for snip in snippets)


def test_mcp_get_catia_interface_enrichment():
    raw_json = get_catia_interface("Material", member_name="PutIcon")
    data = json.loads(raw_json)
    assert not data.get("isError")
    assert data["name"] == "Material"
    assert len(data["methods"]) == 1
    assert "pitfall_warning" in data["methods"][0]

    docs_path = resolve_docs_db_path()
    if docs_path and docs_path.exists():
        assert "linked_official_docs" in data
        assert "linked_sample_scripts" in data
        assert len(data["linked_official_docs"]) > 0


def test_linkage_diff_reporter_runs(tmp_path):
    docs_path = resolve_docs_db_path()
    if not docs_path or not docs_path.exists():
        pytest.skip("catalyst_docs.db not available on this machine")

    out_md = tmp_path / "test_diff.md"
    metrics = generate_linkage_report(output_md_path=out_md)
    assert metrics["total_links"] > 0
    assert metrics["combined_iface_count"] >= metrics["baseline_iface_count"]
    assert out_md.exists()
    content = out_md.read_text(encoding="utf-8")
    assert "# CATalyst 官方文档与样板源码穿透增量看板" in content
    assert "Material.PutIcon" in content


def test_linkage_builder_return_type_propagation_and_prose_noise_filter(tmp_path):
    """
    Verify chained return-type inference without Dim annotations, and ensure
    English prose dots (e.g., file.txt, .htm) do not pollute doc_api_links.
    """
    import sqlite3
    from src.engine.linkage_builder import LinkageBuilder
    from tests.conftest import build_synthetic_core_db

    core_db = build_synthetic_core_db(tmp_path / "core.db")
    docs_db = tmp_path / "docs.db"
    conn = sqlite3.connect(docs_db)
    conn.executescript("""
        CREATE TABLE doc_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT UNIQUE NOT NULL,
            module TEXT NOT NULL,
            solution TEXT,
            product_name TEXT,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            ix_keywords TEXT,
            options_anchors TEXT,
            headings TEXT,
            summary TEXT,
            warnings TEXT,
            body_text TEXT,
            images_json TEXT,
            linked_docs_json TEXT,
            linked_files_json TEXT
        );
        CREATE TABLE doc_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            module TEXT,
            filename TEXT NOT NULL,
            ext TEXT NOT NULL,
            rel_path TEXT NOT NULL,
            size_bytes INTEGER,
            is_binary INTEGER DEFAULT 0,
            content TEXT NOT NULL
        );
    """)
    # Script WITHOUT any Dim statements, using chained return types:
    # Application.ActiveDocument -> Document (.CATMaterial hint) -> MaterialDocument.Families -> MaterialFamilies.Add -> MaterialFamily.Materials -> Materials.Add -> Material.PutIcon
    chained_script = """
    Set doc = CATIA.ActiveDocument
    Set fams = materialDoc.Families
    Set fam = fams.Add()
    Set mat = fam.Materials.Add()
    mat.CreateRenderingData().Transparency = 0.5
    mat.GetIcon("C:\\out\\")
    """
    conn.execute(
        "INSERT INTO doc_samples (sample_id, source, module, filename, ext, rel_path, size_bytes, is_binary, content) "
        "VALUES ('s1', 'startup', 'materials', 'chained.CATScript', '.catscript', 'startup/chained.CATScript', 200, 0, ?)",
        (chained_script,),
    )
    # Prose document with non-code periods & ambiguous English text
    prose_doc = """
    This guide explains e.g. how CATPart.CATMaterial files work.
    Open index.htm and check file.Name or doc.Add in your browser.
    No real automation statements exist in this paragraph.
    """
    conn.execute(
        "INSERT INTO doc_pages (doc_id, module, solution, product_name, category, title, summary, warnings, body_text) "
        "VALUES ('ug/prose.htm', 'ug', 'Infra', 'Infra', 'user_guide', 'Prose Page', '', '', ?)",
        (prose_doc,),
    )
    conn.commit()
    conn.close()

    metrics = LinkageBuilder(core_db_path=core_db, docs_db_path=docs_db).build_linkages()
    assert metrics["sample_links"] >= 4

    check_conn = sqlite3.connect(docs_db)
    sample_hits = check_conn.execute(
        "SELECT interface_name, member_name FROM doc_api_links WHERE target_type='sample'"
    ).fetchall()
    prose_hits = check_conn.execute(
        "SELECT interface_name, member_name FROM doc_api_links WHERE target_type='doc'"
    ).fetchall()
    check_conn.close()

    assert ("MaterialFamilies", "Add") in sample_hits
    assert ("Materials", "Add") in sample_hits
    assert ("Material", "CreateRenderingData") in sample_hits
    assert ("Material", "GetIcon") in sample_hits
    assert prose_hits == [], f"Unexpected prose noise false positives: {prose_hits}"

