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
