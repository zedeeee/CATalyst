"""
Pytest configuration and BYOD synthetic fixture DB.
Allows the entire test suite to pass cleanly in CI / fresh clones without bundling
any proprietary Dassault Systemes CHM or derived catalyst.db binaries.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def build_synthetic_core_db(db_path: Path) -> Path:
    """Create a minimal 100% original synthetic SQLite DB matching CatalystDB schema."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE interfaces (
            name TEXT PRIMARY KEY,
            framework TEXT,
            description TEXT,
            inheritance_chain TEXT
        );
        CREATE TABLE properties (
            interface_name TEXT,
            name TEXT,
            type TEXT,
            readonly BOOLEAN,
            declared_in TEXT
        );
        CREATE TABLE methods (
            interface_name TEXT,
            name TEXT,
            return_type TEXT,
            params_json TEXT,
            declared_in TEXT
        );
        CREATE TABLE enums (
            name TEXT PRIMARY KEY,
            description TEXT,
            values_json TEXT
        );
        CREATE TABLE usecases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            interface_name TEXT,
            source TEXT DEFAULT 'official',
            title TEXT,
            workbench TEXT,
            tags TEXT,
            provenance_json TEXT,
            context TEXT,
            code TEXT
        );
        CREATE VIRTUAL TABLE usecases_fts USING fts5(
            id UNINDEXED, interface_name, title, workbench, tags, context, code, tokenize='unicode61'
        );
        CREATE VIRTUAL TABLE apis_fts USING fts5(
            item_type, name, description, framework, parent_interface, declared_in, data_type, readonly UNINDEXED, tokenize='unicode61'
        );
        """
    )

    interfaces = [
        ("Pad", "PartInterfaces", "Synthetic Pad interface fixture.", json.dumps(["Pad", "Prism", "SketchBasedShape", "Shape", "AnyObject"])),
        ("Prism", "PartInterfaces", "Synthetic Prism interface fixture.", json.dumps(["Prism", "SketchBasedShape", "Shape", "AnyObject"])),
        ("Product", "ProductStructureInterfaces", "Synthetic Product interface fixture.", json.dumps(["Product", "AnyObject"])),
        ("VisPropertySet", "InfInterfaces", "Synthetic VisPropertySet interface fixture.", json.dumps(["VisPropertySet", "AnyObject"])),
        ("SystemConfiguration", "InfInterfaces", "Synthetic SystemConfiguration fixture.", json.dumps(["SystemConfiguration", "AnyObject"])),
    ]
    cur.executemany("INSERT INTO interfaces VALUES (?, ?, ?, ?)", interfaces)

    properties = [
        ("Product", "PartNumber", "CATBSTR", 0, "Product"),
        ("SystemConfiguration", "ServicePack", "long", 1, "SystemConfiguration"),
        ("SystemConfiguration", "Release", "long", 1, "SystemConfiguration"),
    ]
    cur.executemany("INSERT INTO properties VALUES (?, ?, ?, ?, ?)", properties)

    methods = [
        ("Pad", "GetDirection", "void", json.dumps([{"name": "ioDirection", "type": "CATSafeArrayVariant"}]), "Prism"),
        ("Pad", "GetItem", "CATBaseDispatch", json.dumps([{"name": "IDName", "type": "CATBSTR"}]), "AnyObject"),
        ("Prism", "GetDirection", "void", json.dumps([{"name": "ioDirection", "type": "CATSafeArrayVariant"}]), "Prism"),
        (
            "VisPropertySet",
            "GetRealColor",
            "CatVisPropertyStatus",
            json.dumps([
                {"name": "oRed", "type": "long"},
                {"name": "oGreen", "type": "long"},
                {"name": "oBlue", "type": "long"},
                {"name": "oInheritance", "type": "long"},
            ]),
            "VisPropertySet",
        ),
        ("SystemConfiguration", "GetProductNames", "void", json.dumps([{"name": "ioProductNames", "type": "CATSafeArrayVariant"}]), "SystemConfiguration"),
    ]
    cur.executemany("INSERT INTO methods VALUES (?, ?, ?, ?, ?)", methods)

    enums = [
        (
            "CatHoleType",
            "Synthetic hole type enum fixture.",
            json.dumps([
                {"name": "catSimpleHole", "value": 0, "description": "Simple hole"},
                {"name": "catTaperedHole", "value": 1, "description": "Tapered hole"},
                {"name": "catCounterboredHole", "value": 2, "description": "Counterbored hole"},
            ]),
        ),
        (
            "CatProductSource",
            "Synthetic product source enum fixture.",
            json.dumps([
                {"name": "catProductSourceUnknown", "value": 0, "description": "Unknown"},
                {"name": "catProductMade", "value": 1, "description": "Made"},
                {"name": "catProductBought", "value": 2, "description": "Bought"},
            ]),
        ),
    ]
    cur.executemany("INSERT INTO enums VALUES (?, ?, ?)", enums)

    # Synthetic official usecases
    cur.execute(
        "INSERT INTO usecases (interface_name, source, title, workbench, tags, provenance_json, context, code) VALUES (?, 'official', ?, '', '', NULL, ?, ?)",
        ("VisPropertySet", "Synthetic GetRealColor Example", "GetRealColor synthetic example", "status = vis.GetRealColor(r, g, b, inh)"),
    )
    cur.execute(
        "INSERT INTO usecases (interface_name, source, title, workbench, tags, provenance_json, context, code) VALUES (?, 'official', ?, '', '', NULL, ?, ?)",
        ("Pad", "Synthetic Pad Example", "Pad synthetic example", "Set pad1 = sf.AddNewPad(sk1, 20.0)"),
    )

    # Load repo's own open-source community recipes
    recipes_file = PROJECT_ROOT / "data" / "recipes" / "community_recipes.json"
    if recipes_file.exists():
        recipes = json.loads(recipes_file.read_text(encoding="utf-8"))
        for rc in recipes:
            cur.execute(
                "INSERT INTO usecases (interface_name, source, title, workbench, tags, provenance_json, context, code) VALUES (?, 'community', ?, ?, ?, ?, ?, ?)",
                (
                    rc["interface_name"],
                    rc["title"],
                    rc["workbench"],
                    rc["tags"],
                    json.dumps(rc["provenance"], ensure_ascii=False),
                    rc["description"],
                    rc["code"],
                ),
            )

    # Populate FTS5 tables
    cur.execute(
        "INSERT INTO usecases_fts (id, interface_name, title, workbench, tags, context, code) "
        "SELECT id, COALESCE(interface_name,''), COALESCE(title,''), COALESCE(workbench,''), COALESCE(tags,''), COALESCE(context,''), COALESCE(code,'') FROM usecases"
    )
    cur.execute(
        "INSERT INTO apis_fts (item_type, name, description, framework, parent_interface, declared_in, data_type, readonly) "
        "SELECT 'interface', name, COALESCE(description,''), COALESCE(framework,''), '', '', '', 0 FROM interfaces"
    )
    cur.execute(
        "INSERT INTO apis_fts (item_type, name, description, framework, parent_interface, declared_in, data_type, readonly) "
        "SELECT 'enum', name, COALESCE(description,''), '', '', '', '', 0 FROM enums"
    )
    cur.execute(
        "INSERT INTO apis_fts (item_type, name, description, framework, parent_interface, declared_in, data_type, readonly) "
        "SELECT 'property', interface_name || '.' || name, '', '', interface_name, COALESCE(declared_in,''), COALESCE(type,''), readonly FROM properties"
    )
    cur.execute(
        "INSERT INTO apis_fts (item_type, name, description, framework, parent_interface, declared_in, data_type, readonly) "
        "SELECT 'method', interface_name || '.' || name, '', '', interface_name, COALESCE(declared_in,''), COALESCE(return_type,''), 0 FROM methods"
    )

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture(scope="session", autouse=True)
def ensure_test_core_db(tmp_path_factory):
    """
    If local dist/catalyst.db is absent (clean BYOD clone / CI), automatically
    provide a synthetic open-source catalyst.db via CATALYST_DB_PATH.
    """
    real_db = PROJECT_ROOT / "dist" / "catalyst.db"
    if real_db.exists() or os.environ.get("CATALYST_DB_PATH"):
        yield
        return

    synth_dir = tmp_path_factory.mktemp("synthetic_core_db")
    synth_db = build_synthetic_core_db(synth_dir / "catalyst.db")
    os.environ["CATALYST_DB_PATH"] = str(synth_db)
    try:
        yield
    finally:
        os.environ.pop("CATALYST_DB_PATH", None)
