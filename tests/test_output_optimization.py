"""
Tests for token-efficient output formatting, CHM truncation sanitization,
wildcard/batch member filtering, base-member folding, inline Enum expansion,
terminal creator signature enrichment, and compact IDL card rendering.
"""

from __future__ import annotations

import json
import pytest

from src.engine.db import CatalystDB
from src.engine.formatter import (
    dump_compact_json,
    format_interface_card,
    sanitize_doc_text,
    strip_redundant_fields,
)
from src.mcp.server import get_catia_interface
from src.parser.html_parser import _clean_text


def test_sanitize_doc_text_and_html_clean_text():
    raw_see = "The support direction reference (see"
    assert sanitize_doc_text(raw_see) == "The support direction reference"
    assert _clean_text(raw_see) == "The support direction reference"

    raw_pad = "Creates and returns a new pad within the current body. The created pad"
    assert sanitize_doc_text(raw_pad) == "Creates and returns a new pad within the current body."

    raw_ex = "Represents the intersect boolean operation. Example The following example shows..."
    cleaned = sanitize_doc_text(raw_ex, strip_example=True, max_chars=140)
    assert "Example" not in cleaned
    assert cleaned == "Represents the intersect boolean operation."


def test_strip_redundant_fields_and_compact_json():
    payload = {
        "name": "Pad",
        "properties": [],
        "methods": [{"name": "Foo", "framework": "", "readonly": False, "description": ""}],
        "usecases": [],
    }
    stripped = strip_redundant_fields(payload)
    assert "properties" in stripped  # protected root key
    assert "usecases" not in stripped
    assert stripped["methods"][0] == {"name": "Foo"}

    s = dump_compact_json(payload)
    assert "\n" not in s
    assert ": " not in s


def test_wildcard_and_comma_member_filtering():
    db = CatalystDB()
    # Comma-separated filter
    res_multi = db.get_interface("Pad", member_name="FirstLimit,GetDirection", include_usecases=False)
    assert res_multi is not None
    assert [p["name"] for p in res_multi["properties"]] == ["FirstLimit"]
    assert [m["name"] for m in res_multi["methods"]] == ["GetDirection"]

    # Wildcard filter
    res_wild = db.get_interface("Pad", member_name="*Direction*", include_usecases=False)
    assert res_wild is not None
    prop_names = {p["name"] for p in res_wild["properties"]}
    meth_names = {m["name"] for m in res_wild["methods"]}
    assert "DirectionOrientation" in prop_names
    assert "GetDirection" in meth_names
    assert "SetDirection" in meth_names
    assert "FirstLimit" not in prop_names


def test_base_member_folding_and_inline_enums():
    db = CatalystDB()
    # Default db.get_interface retains GetItem for backward compatibility
    full_pad = db.get_interface("Pad", include_usecases=False)
    assert full_pad is not None
    assert any(m["name"] == "GetItem" for m in full_pad["methods"])

    # Compact MCP-style query folds AnyObject boilerplate and inlines Enums
    compact_pad = db.get_interface(
        "Pad",
        include_usecases=False,
        detail="compact",
        include_base_members=False,
        inline_enums=True,
    )
    assert compact_pad is not None
    assert "GetItem" in (compact_pad.get("omitted_base_members") or [])
    assert not any(m["name"] == "GetItem" for m in compact_pad["methods"])
    assert "sig" in compact_pad["methods"][0]
    assert "params" not in compact_pad["methods"][0]


def test_navigation_path_inlines_terminal_constructor_signature():
    db = CatalystDB()
    nav = db.get_navigation_path("Pad", from_interface="Application", compact=True)
    if nav is None:
        pytest.skip("Synthetic DB without ShapeFactory->Pad edge")
    assert "steps" not in nav
    assert "route" in nav
    assert "(...)" not in nav["python_chain"]
    assert "AddNewPad(" in nav["python_chain"]


def test_mcp_compact_json_and_card_output_budgets():
    # Compact JSON overview
    raw_json = get_catia_interface(
        "Pad",
        from_interface="Application",
        include_usecases=False,
    )
    data = json.loads(raw_json)
    assert not data.get("isError")
    assert len(raw_json) < 6000, f"Compact JSON Pad+Nav bloated: {len(raw_json)} chars"
    assert "\n" not in raw_json

    # Dense IDL Signature Card
    card = get_catia_interface(
        "Pad",
        from_interface="Application",
        include_usecases=False,
        output_format="card",
    )
    assert card.startswith("# Pad")
    assert len(card) < 4000, f"Card Pad+Nav bloated: {len(card)} chars"

    # Caveat preservation in card format
    puticon_card = get_catia_interface("Material", member_name="PutIcon", output_format="card")
    assert "!CAVEAT[CRITICAL]" in puticon_card
    assert "Safe:" in puticon_card
