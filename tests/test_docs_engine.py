import json
from pathlib import Path

from src.engine.docs_db import CatalystDocsDB
from src.mcp import server as mcp_server
from src.parser.docs_builder import CatalystDocsBuilder
from src.parser.docs_parser import parse_catnls_file, parse_toc_xml


def _create_synthetic_catia_env(tmp_path: Path):
    doc_root = tmp_path / "B27doc" / "English" / "online"
    install_root = tmp_path / "B27" / "win_b64"

    # 1. TOC XML
    doc_root.mkdir(parents=True)
    (doc_root / "CATIA_P3_TOC.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<Root>
  <ITEM name="CATIA P3">
    <ITEM name="Infrastructure" searchFilter="Solution">
      <DITEM dir="cceug_C2" name="Component Catalog Editor" searchFilter="Product"/>
    </ITEM>
  </ITEM>
</Root>""",
        encoding="utf-8",
    )

    # 2. cceug_C2 batch catalog doc + image + sample CSV
    cce = doc_root / "cceug_C2"
    (cce / "images").mkdir(parents=True)
    (cce / "images" / "batch_layout.gif").write_bytes(b"GIF89a")
    (cce / "samples").mkdir(parents=True)
    (cce / "samples" / "BatchCatalog.csv").write_text(
        "CHAPTER;FirstChapter\nKeywords;Name\nTypes;String\nSubChapter1;SubChapter1\nEND\n",
        encoding="utf-8",
    )
    (cce / "cceugbt0102.htm").write_text(
        """<html><head><title>Creating a Catalog in Batch Mode</title></head><body>
        <h1>Creating a Catalog in Batch Mode
          <a name="ix-creating::catalog in batch mode;catalog::creating in batch mode"></a>
        </h1>
        <table>
          <tr><td><img src="../icons_C2/common/atarget.gif"></td>
              <td>This task explains how to create a catalog in Batch mode.</td></tr>
          <tr><td><img src="../icons_C2/common/awarning.gif"></td>
              <td>Keyword Name is not automatically added in Batch mode.</td></tr>
        </table>
        <h2>CSV Structure</h2>
        <p>Use BatchCatalog.csv with CHAPTER and ENDCHAPTER markers.</p>
        <img src="images/batch_layout.gif">
        </body></html>""",
        encoding="utf-8",
    )

    # 3. bascuctg_C2 options page
    opt_dir = doc_root / "bascuctg_C2"
    opt_dir.mkdir(parents=True)
    (opt_dir / "bascuctg0000.htm").write_text(
        """<html><head><title>Catalogs</title></head><body>
        <h1>Catalogs <a name="ToolsOptions.Infrastructure.Catalogs"></a></h1>
        <h2>Resolved Family Components</h2>
        <h3>Standard Behavior</h3>
        <p>Generates independent .CATPart using New from behavior.</p>
        <h3>Allow family component dynamic resolution in catalog</h3>
        <p>Dynamically resolves family components into the specified folder.</p>
        </body></html>""",
        encoding="utf-8",
    )

    # 4. msgcatalog CATNls
    msg_dir = install_root / "resources" / "msgcatalog"
    msg_dir.mkdir(parents=True)
    (msg_dir / "CATCuiOptionEditor.CATNls").write_text(
        """// Sample CATNls
TabPage.Title = "Catalogs";
Cancel.Title = "Cancel";
CATCuiOptionEditor.ResolvedComponents.AllowComponentResolution.Title = "Allow family component dynamic resolution in catalog";
CATCuiOptionEditor.ResolvedComponents.AllowComponentResolution.LongHelp = "Allows dynamic resolution and storage of non resolved family components.";
""",
        encoding="utf-8",
    )

    return doc_root, install_root


def test_toc_and_catnls_parsers(tmp_path: Path):
    doc_root, install_root = _create_synthetic_catia_env(tmp_path)
    toc = parse_toc_xml(doc_root)
    assert toc["cceug_C2"] == ("Infrastructure", "Component Catalog Editor")

    rows = parse_catnls_file(install_root / "resources" / "msgcatalog" / "CATCuiOptionEditor.CATNls")
    keys = {r[1] for r in rows}
    assert "Cancel.Title" not in keys  # Generic UI noise filtered out
    assert "CATCuiOptionEditor.ResolvedComponents.AllowComponentResolution.LongHelp" in keys


def test_docs_builder_engine_and_mcp_endpoints(tmp_path: Path, monkeypatch):
    doc_root, install_root = _create_synthetic_catia_env(tmp_path)
    out_db = tmp_path / "catalyst_docs.db"

    builder = CatalystDocsBuilder(
        output_db=out_db,
        doc_root=doc_root,
        install_root=install_root,
        release="B27",
        workers=1,
    )
    summary = builder.build()
    assert summary["page_count"] == 2
    assert summary["nls_count"] >= 2
    assert summary["sample_count"] == 1

    db = CatalystDocsDB(out_db)
    assert db.get_meta()["catia_release"] == "B27"

    # Search docs
    res = db.search_docs("Catalog Batch Mode", category="user_guide")
    assert res["total_matches"] == 1
    assert res["results"][0]["doc_id"] == "cceug_C2/cceugbt0102.htm"
    assert "Keyword Name" in res["results"][0]["warnings_preview"]
    assert res["results"][0]["image_count"] == 1

    # Get page + section slicing + resolved image path
    page = db.get_doc_page("cceug_C2/cceugbt0102.htm", section="CSV Structure")
    assert page is not None
    assert page["section_matched"] is True
    assert "BatchCatalog.csv" in page["body_text"]
    assert page["images"][0]["rel_path"] == "cceug_C2/images/batch_layout.gif"
    assert Path(page["images"][0]["abs_path"]).exists()

    # Settings cross-search (CATNls + Tools>Options doc page)
    st = db.search_settings(query="dynamic resolution")
    assert st["total_nls_matches"] >= 1
    assert st["nls_entries"][0]["file_stem"] == "CATCuiOptionEditor"
    assert any(d["doc_id"] == "bascuctg_C2/bascuctg0000.htm" for d in st["related_option_docs"])

    # Samples search with full content
    smp = db.search_samples(query="BatchCatalog", ext=".csv", include_content=True)
    assert smp["total_matches"] == 1
    assert "FirstChapter" in smp["results"][0]["content"]

    # MCP endpoints with CATALYST_DOCS_DB_PATH
    monkeypatch.setenv("CATALYST_DOCS_DB_PATH", str(out_db))
    monkeypatch.setattr(mcp_server, "_docs_db_instance", None)

    mcp_docs = json.loads(mcp_server.search_catia_docs(query="Batch Mode"))
    assert not mcp_docs.get("isError") and mcp_docs["total_matches"] == 1

    mcp_page = json.loads(mcp_server.get_catia_doc_page(doc_id="bascuctg0000.htm"))
    assert not mcp_page.get("isError") and "ToolsOptions.Infrastructure.Catalogs" in mcp_page["options_anchors"]

    mcp_set = json.loads(mcp_server.search_catia_settings(nls_file="CATCuiOptionEditor"))
    assert not mcp_set.get("isError") and mcp_set["total_nls_matches"] >= 2

    mcp_smp = json.loads(mcp_server.search_catia_samples(query="BatchCatalog", include_content=True))
    assert not mcp_smp.get("isError") and mcp_smp["total_matches"] == 1

    # Graceful error when docs DB does not exist
    monkeypatch.setenv("CATALYST_DOCS_DB_PATH", str(tmp_path / "missing.db"))
    monkeypatch.setattr(mcp_server, "_docs_db_instance", None)
    # Also ensure default resolution doesn't pick up repo's local DB during this test
    monkeypatch.setattr(mcp_server, "resolve_docs_db_path", lambda: None)
    missing_res = json.loads(mcp_server.search_catia_docs(query="Catalog"))
    assert missing_res.get("isError") is True
