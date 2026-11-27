"""
Tests for scoped search options, *.CATRsc accelerator parsing, entry_kind classification,
include_catnls opt-in behavior, include_cross_links/detail controls, and CLI --help.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.engine.docs_db import CatalystDocsDB, resolve_docs_db_path
from src.mcp.server import search_catia_api, search_catia_docs, search_catia_samples, search_catia_settings
from src.parser.docs_parser import classify_catnls_entry, parse_catrsc_file

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_parse_catrsc_accelerator_and_classify(tmp_path):
    rsc = tmp_path / "CATFileHeader.CATRsc"
    rsc.write_text(
        '// comment\n'
        'CATFileHeader.FileNew.Accelerator = "Ctrl+N";\n'
        'CATFileHeader.FileOpen.Icon.Normal = "I_Open";\n'
        'CATFileHeader.FileOpen.Accelerator = "Ctrl+O";\n',
        encoding="utf-8",
    )
    rows = parse_catrsc_file(rsc)
    assert len(rows) == 2
    assert rows[0] == ("CATFileHeader", "CATFileHeader.FileNew.Accelerator", "Ctrl+N", 0, "accelerator")
    assert rows[1] == ("CATFileHeader", "CATFileHeader.FileOpen.Accelerator", "Ctrl+O", 0, "accelerator")

    assert classify_catnls_entry("CATFileHeader", "CATFileHeader.OpenInNewWnd.Title", 0) == "header"
    assert classify_catnls_entry("CATCuiOptionEditor", "ResolvedComponents", 1) == "option"
    assert classify_catnls_entry("CATFileHeader", "CATFileHeader.FileNew.Accelerator", 0) == "accelerator"
    assert classify_catnls_entry("GenericDialog", "CancelLabel", 0) == "ui"


def test_search_catia_api_opt_in_catnls_and_compact_controls():
    # Default: include_catnls=False does NOT probe CATNls on 0 COM hits
    raw_default = search_catia_api(query="OpenInNewWnd")
    data_default = json.loads(raw_default)
    assert data_default["total_matches"] == 0
    assert "related_catnls_headers" not in data_default

    # Opt-in: include_catnls=True probes *.CATNls/*.CATRsc
    docs_path = resolve_docs_db_path()
    if docs_path and docs_path.exists():
        raw_opt_in = search_catia_api(query="OpenInNewWnd", include_catnls=True)
        data_opt_in = json.loads(raw_opt_in)
        assert "related_catnls_headers" in data_opt_in
        assert any("OpenInNewWnd" in e["nls_key"] for e in data_opt_in["related_catnls_headers"])

    # Compact + no cross links
    raw_compact = search_catia_api(query="Pad", detail="compact", include_cross_links=False, limit=3)
    data_compact = json.loads(raw_compact)
    assert data_compact["total_matches"] > 0
    assert "related_recipes" not in data_compact
    assert "related_docs" not in data_compact
    assert "host_interfaces_summary" not in data_compact
    assert "description" not in data_compact["results"][0]


def test_search_catia_settings_scoped_headers_and_accelerators():
    docs_path = resolve_docs_db_path()
    if not docs_path or not docs_path.exists():
        pytest.skip("catalyst_docs.db not available on this machine")

    # 1. Headers scope omits related_option_docs & xml_roundtrip_hint
    hdr_res = json.loads(search_catia_settings(query="OpenInNewWnd", scope="headers"))
    assert hdr_res["scope"] == "headers"
    assert hdr_res["total_nls_matches"] > 0
    assert "related_option_docs" not in hdr_res
    assert "xml_roundtrip_hint" not in hdr_res
    assert all(e["entry_kind"] == "header" for e in hdr_res["nls_entries"])

    # 2. Accelerators scope ingests *.CATRsc and finds Ctrl+N
    acc_res = json.loads(search_catia_settings(query="Ctrl+N", scope="accelerators"))
    assert acc_res["scope"] == "accelerators"
    assert acc_res["total_nls_matches"] > 0
    assert "related_option_docs" not in acc_res
    assert any("Ctrl+N" in e["text"] and e["entry_kind"] == "accelerator" for e in acc_res["nls_entries"])


def test_docs_and_samples_scoped_controls():
    docs_path = resolve_docs_db_path()
    if not docs_path or not docs_path.exists():
        pytest.skip("catalyst_docs.db not available on this machine")

    doc_idx = json.loads(search_catia_docs(query="Catalog Batch Mode", include_snippet=False, limit=2))
    assert doc_idx["total_matches"] > 0
    assert "snippet" not in doc_idx["results"][0]

    smp_startup = json.loads(search_catia_samples(query="importMaterialLibrary", source="startup", limit=5))
    assert smp_startup["total_matches"] > 0
    assert all(r["source"] == "startup" for r in smp_startup["results"])


def test_cli_help_and_subcommands_render_cleanly():
    for args in (["--help"], ["settings", "--help"], ["search", "--help"]):
        proc = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "catalyst_cli.py"), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert proc.returncode == 0
        assert "Examples:" in proc.stdout or "Example:" in proc.stdout
