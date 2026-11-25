"""
Unit tests for COM Object Model Directed Graph & Shortest-Path Navigation.
Verifies forward path resolution, subtype casting, cycle avoidance, and MCP integration.
"""

from __future__ import annotations

import json
import sqlite3

from src.engine.db import CatalystDB
from src.engine.object_graph import ObjectGraph, materialize_object_edges
from src.mcp.server import get_catia_interface


def test_object_graph_navigation_application_to_rendering_material():
    db = CatalystDB()
    nav = db.get_navigation_path("RenderingMaterial", from_interface="Application")
    assert nav is not None
    assert nav["source"] == "Application"
    assert nav["target"] == "RenderingMaterial"
    assert nav["hops"] >= 4
    assert "Families" in nav["python_chain"]
    assert "Materials" in nav["python_chain"]
    assert nav["python_chain"].endswith(".RenderingMaterial")


def test_object_graph_avoids_parent_cycle_and_unreachable_island(tmp_path):
    db_file = tmp_path / "graph_cycle.db"
    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE interfaces (name TEXT PRIMARY KEY, framework TEXT, description TEXT, inheritance_chain TEXT);
        CREATE TABLE properties (interface_name TEXT, name TEXT, type TEXT, readonly BOOLEAN, declared_in TEXT);
        CREATE TABLE methods (interface_name TEXT, name TEXT, return_type TEXT, params_json TEXT, declared_in TEXT);
    """)
    conn.executemany(
        "INSERT INTO interfaces VALUES (?, '', '', ?)",
        [
            ("Application", json.dumps(["Application", "AnyObject"])),
            ("AnyObject", json.dumps(["AnyObject"])),
            ("PartDocument", json.dumps(["PartDocument", "AnyObject"])),
            ("Part", json.dumps(["Part", "AnyObject"])),
            ("UnreachableIsland", json.dumps(["UnreachableIsland"])),
        ],
    )
    conn.executemany(
        "INSERT INTO properties VALUES (?, ?, ?, 1, ?)",
        [
            ("Application", "ActiveDocument", "PartDocument", "Application"),
            ("PartDocument", "Part", "Part", "PartDocument"),
            # Cyclic AnyObject back-edges
            ("Part", "Application", "Application", "AnyObject"),
            ("Part", "Parent", "AnyObject", "AnyObject"),
            ("PartDocument", "Application", "Application", "AnyObject"),
        ],
    )
    conn.commit()

    count = materialize_object_edges(conn)
    assert count > 0

    graph = ObjectGraph(conn)
    nav = graph.find_navigation_path("Application", "Part")
    assert nav is not None
    assert nav["python_chain"] == "catia.ActiveDocument.Part"
    assert nav["hops"] == 2

    # Unreachable island terminates cleanly with None
    assert graph.find_navigation_path("Application", "UnreachableIsland") is None
    # Self path
    self_nav = graph.find_navigation_path("Part", "Part")
    assert self_nav is not None and self_nav["hops"] == 0
    conn.close()


def test_mcp_get_catia_interface_with_from_interface():
    raw = get_catia_interface(name="Material", from_interface="Application")
    data = json.loads(raw)
    assert not data.get("isError")
    assert "navigation_path" in data
    nav = data["navigation_path"]
    assert nav["source"] == "Application"
    assert nav["target"] == "Material"
    assert "Families" in nav["python_chain"]
