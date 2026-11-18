import json
import shutil
from pathlib import Path

from src.engine.docs_db import CatalystDocsDB
from src.mcp import server as mcp_server
from src.parser.docs_builder import CatalystDocsBuilder
from src.parser.docs_parser import parse_catnls_file, parse_toc_xml


def _create_synthetic_catia_env(root_dir: Path):
    doc_root = root_dir / "B27doc" / "English" / "online"
    install_root = root_dir / "B27" / "win_b64"

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

    # 2. cceug_C2 batch catalog doc + image + text CSV + binary CATPart sample
    cce = doc_root / "cceug_C2"
    (cce / "images").mkdir(parents=True)
    (cce / "images" / "batch_layout.gif").write_bytes(b"GIF89a")
    (cce / "samples").mkdir(parents=True)
    (cce / "samples" / "BatchCatalog.csv").write_text(
        "CHAPTER;FirstChapter\nKeywords;Name\nTypes;String\nSubChapter1;SubChapter1\nEND\n",
        encoding="utf-8",
    )
    (cce / "samples" / "FHC_M03-05.CATPart").write_bytes(b"\x00\x01FAKE_CATPART_BINARY")
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
        <p>Use BatchCatalog.csv and FHC_M03-05.CATPart with CHAPTER and ENDCHAPTER markers.
           See also <a href="../bascuctg_C2/bascuctg0000.htm">Catalog Options</a>.</p>
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
    assert "Cancel.Title" not in keys
    assert "CATCuiOptionEditor.ResolvedComponents.AllowComponentResolution.LongHelp" in keys


def test_portable_relative_db_relocation_and_linked_assets(tmp_path: Path, monkeypatch):
    build_env = tmp_path / "machine_a"
    doc_root, install_root = _create_synthetic_catia_env(build_env)
    out_db = tmp_path / "catalyst_docs.db"

    # Build on "machine A" (accepting top-level B27doc root as well)
    builder = CatalystDocsBuilder(
        output_db=out_db,
        doc_root=build_env / "B27doc",
        install_root=build_env / "B27",
        release="B27",
        workers=1,
    )
    summary = builder.build()
    assert summary["page_count"] == 2
    assert summary["text_sample_count"] == 1
    assert summary["binary_sample_count"] == 1

    # Simulate relocating docs to a completely different root on "machine B" and deleting machine A
    relocated = tmp_path / "machine_b" / "custom_docs_dir"
    shutil.copytree(build_env / "B27doc", relocated)
    shutil.rmtree(build_env)

    # Configure only CATALYST_DOC_ROOT at runtime (pointing to top-level B27doc folder)
    monkeypatch.setenv("CATALYST_DOC_ROOT", str(relocated))
    monkeypatch.setenv("CATALYST_DOCS_DB_PATH", str(out_db))
    monkeypatch.setattr(mcp_server, "_docs_db_instance", None)

    db = CatalystDocsDB(out_db)
    meta = db.get_meta()
    assert meta["portable_relative_paths"] == "true"
    assert "doc_root" not in meta  # Zero machine-specific absolute paths stored in DB

    # get_doc_page dynamically resolves HTML, images, linked_docs, and linked_files (text + binary!)
    page = db.get_doc_page("cceug_C2/cceugbt0102.htm", section="CSV Structure")
    assert page is not None
    assert page["section_matched"] is True
    assert Path(page["abs_path"]).exists()
    assert str(relocated) in page["abs_path"]
    assert page["images"][0]["rel_path"] == "cceug_C2/images/batch_layout.gif"
    assert Path(page["images"][0]["abs_path"]).exists()
    assert "bascuctg_C2/bascuctg0000.htm" in page["linked_docs"]

    linked_rel_paths = {f["rel_path"]: f for f in page["linked_files"]}
    assert "cceug_C2/samples/BatchCatalog.csv" in linked_rel_paths
    assert "cceug_C2/samples/FHC_M03-05.CATPart" in linked_rel_paths
    assert linked_rel_paths["cceug_C2/samples/FHC_M03-05.CATPart"]["is_binary"] is True
    assert Path(linked_rel_paths["cceug_C2/samples/FHC_M03-05.CATPart"]["abs_path"]).exists()

    # Search binary CAD sample by filename + dynamically resolved abs_path
    bin_smp = json.loads(mcp_server.search_catia_samples(query="FHC_M03", ext=".catpart"))
    assert bin_smp["total_matches"] == 1
    assert bin_smp["results"][0]["is_binary"] is True
    assert bin_smp["results"][0]["rel_path"] == "cceug_C2/samples/FHC_M03-05.CATPart"
    assert Path(bin_smp["results"][0]["abs_path"]).exists()

    # Text-only filter excludes binary CAD samples
    txt_only = json.loads(mcp_server.search_catia_samples(query="FHC_M03", include_binary=False))
    assert txt_only["total_matches"] == 0

    # Settings cross-search works seamlessly
    mcp_set = json.loads(mcp_server.search_catia_settings(query="dynamic resolution"))
    assert not mcp_set.get("isError") and mcp_set["total_nls_matches"] >= 1
    assert any(d["doc_id"] == "bascuctg_C2/bascuctg0000.htm" for d in mcp_set["related_option_docs"])

    # Graceful error when docs DB is missing
    monkeypatch.setattr(mcp_server, "_docs_db_instance", None)
    monkeypatch.setattr(mcp_server, "resolve_docs_db_path", lambda: None)
    missing_res = json.loads(mcp_server.search_catia_docs(query="Catalog"))
    assert missing_res.get("isError") is True


def test_5tier_catenv_and_local_paths_config_discovery(tmp_path: Path, monkeypatch):
    from src.engine import local_config

    custom_root = tmp_path / "D_drive"
    doc_root, install_root = _create_synthetic_catia_env(custom_root)

    # Create synthetic CATEnv file pointing to non-default D_drive path
    catenv_dir = tmp_path / "CATEnv"
    catenv_dir.mkdir()
    (catenv_dir / "CATIA_P3.V5-6R2017.B27.txt").write_text(
        f"CATInstallPath={install_root}\nCATDocView={custom_root / 'B27doc'}\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("CATALYST_DOC_ROOT", raising=False)
    monkeypatch.delenv("CATALYST_INSTALL_ROOT", raising=False)
    missing_cfg = tmp_path / "no_paths.json"

    # Tier 3: CATEnv auto-discovery works for arbitrary custom drives
    found_doc = local_config.resolve_doc_root(
        release_hint="B27", config_path=missing_cfg, catenv_dirs=[catenv_dir]
    )
    found_inst = local_config.resolve_install_root(
        release_hint="B27", config_path=missing_cfg, catenv_dirs=[catenv_dir]
    )
    assert found_doc == doc_root.resolve()
    assert found_inst == install_root.resolve()

    # Tier 2: dist/local/paths.json persistence overrides CATEnv
    cfg_file = tmp_path / "paths.json"
    local_config.save_local_paths_config(
        doc_root=custom_root / "B27doc",
        install_root=custom_root / "B27",
        release="B27",
        config_path=cfg_file,
    )
    assert local_config.resolve_doc_root(config_path=cfg_file, catenv_dirs=[]) == doc_root.resolve()
    assert local_config.resolve_install_root(config_path=cfg_file, catenv_dirs=[]) == install_root.resolve()

    # Unconfigured machine emits clear path_setup_hint without failing
    out_db = tmp_path / "portable.db"
    CatalystDocsBuilder(output_db=out_db, doc_root=doc_root, install_root=install_root, release="B27", workers=1).build()
    monkeypatch.setattr("src.engine.docs_db.resolve_runtime_doc_root", lambda meta: None)
    monkeypatch.setattr("src.engine.docs_db.resolve_runtime_install_root", lambda meta: None)
    db = CatalystDocsDB(out_db)
    page = db.get_doc_page("cceug_C2/cceugbt0102.htm")
    assert page is not None and "path_setup_hint" in page
    smp = db.search_samples("BatchCatalog")
    assert "path_setup_hint" in smp


def test_byod_chm_discovery_and_synthetic_ci_db(tmp_path: Path, monkeypatch):
    from src.engine import local_config
    from src.engine.db import CatalystDB
    from tests.conftest import build_synthetic_core_db

    # 1. CATEnv auto-discovers licensed V5Automation.chm from <CATInstallPath>/code/bin/
    fake_inst = tmp_path / "E_drive" / "B27" / "win_b64"
    (fake_inst / "resources" / "msgcatalog").mkdir(parents=True)
    chm_file = fake_inst / "code" / "bin" / "V5Automation.chm"
    chm_file.parent.mkdir(parents=True)
    chm_file.write_bytes(b"ITSF_SYNTHETIC")

    catenv_dir = tmp_path / "CATEnv"
    catenv_dir.mkdir()
    (catenv_dir / "CATIA_P3.B27.txt").write_text(f"CATInstallPath={fake_inst}\n", encoding="utf-8")

    monkeypatch.delenv("CATALYST_CHM_PATH", raising=False)
    monkeypatch.delenv("CATALYST_INSTALL_ROOT", raising=False)
    found_chm = local_config.resolve_chm_path(
        release_hint="B27", config_path=tmp_path / "missing.json", catenv_dirs=[catenv_dir]
    )
    assert found_chm == chm_file.resolve()

    # 2. Synthetic core DB supports all core CatalystDB queries with zero proprietary binaries
    synth_db = build_synthetic_core_db(tmp_path / "catalyst.db")
    db = CatalystDB(synth_db)
    pad = db.get_interface("Pad")
    assert pad is not None and "Prism" in pad["inheritance_chain"]
    assert db.get_enum("CatProductSource", value=1)["matched_value"]["name"] == "catProductMade"
    assert len(db.search_recipes("CreateCatalogFromcsv")) > 0
