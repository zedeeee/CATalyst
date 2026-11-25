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

from src.engine.text_utils import expand_camel_tokens

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def build_synthetic_core_db(db_path: Path) -> Path:
    """Create a realistic 100% original synthetic SQLite DB with adversarial inheritance noise."""
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
            declared_in TEXT,
            description TEXT DEFAULT ''
        );
        CREATE TABLE methods (
            interface_name TEXT,
            name TEXT,
            return_type TEXT,
            params_json TEXT,
            declared_in TEXT,
            description TEXT DEFAULT '',
            returns_desc TEXT DEFAULT ''
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
            item_type, name, camel_tokens, description, framework, parent_interface, declared_in, data_type,
            readonly UNINDEXED, is_inherited UNINDEXED, tokenize='unicode61'
        );
        """
    )

    interfaces = [
        ("Application", "InfInterfaces", "Represents the root CATIA V5 Application object.", json.dumps(["Application", "AnyObject"])),
        ("AnyObject", "InfInterfaces", "Represents the base object for all Automation interfaces.", json.dumps(["AnyObject"])),
        ("Pad", "PartInterfaces", "Represents the pad extruded solid shape.", json.dumps(["Pad", "Prism", "SketchBasedShape", "Shape", "AnyObject"])),
        ("Prism", "PartInterfaces", "Represents the prism shape.", json.dumps(["Prism", "SketchBasedShape", "Shape", "AnyObject"])),
        ("PartDocument", "MecModInterfaces", "Represents a CATPart document.", json.dumps(["PartDocument", "Document", "AnyObject"])),
        ("Part", "MecModInterfaces", "Represents the mechanical Part root.", json.dumps(["Part", "AnyObject"])),
        ("Product", "ProductStructureInterfaces", "Represents an Assembly Product node.", json.dumps(["Product", "AnyObject"])),
        ("VisPropertySet", "InfInterfaces", "Represents visual graphic properties.", json.dumps(["VisPropertySet", "AnyObject"])),
        ("SystemConfiguration", "InfInterfaces", "Provides OS and CATIA release metadata.", json.dumps(["SystemConfiguration", "AnyObject"])),
        ("MaterialDocument", "CATMatInterfaces", "Represents a CATMaterial library document.", json.dumps(["MaterialDocument", "Document", "AnyObject"])),
        ("MaterialFamilies", "CATMatInterfaces", "Collection of material families.", json.dumps(["MaterialFamilies", "Collection", "AnyObject"])),
        ("MaterialFamily", "CATMatInterfaces", "Represents a material family.", json.dumps(["MaterialFamily", "AnyObject"])),
        ("Materials", "CATMatInterfaces", "Collection of materials inside a family.", json.dumps(["Materials", "Collection", "AnyObject"])),
        ("Material", "CATMatInterfaces", "Represents a Material object.", json.dumps(["Material", "AnyObject"])),
        ("RenderingMaterial", "CATRmaInterfaces", "Represents rendering optical properties of a material.", json.dumps(["RenderingMaterial", "AnyObject"])),
    ]
    # Add 20 noisy subclass interfaces carrying inherited Application/Name properties
    for idx in range(1, 21):
        interfaces.append((
            f"NoiseFeature{idx}",
            "PartInterfaces",
            f"Synthetic noise feature {idx} inheriting AnyObject.",
            json.dumps([f"NoiseFeature{idx}", "AnyObject"]),
        ))
    cur.executemany("INSERT INTO interfaces VALUES (?, ?, ?, ?)", interfaces)

    properties = [
        ("Application", "ActiveDocument", "Document", 1, "Application", "Returns the current active document."),
        ("Application", "Visible", "boolean", 0, "Application", "Sets or gets whether CATIA window is visible."),
        ("AnyObject", "Application", "Application", 1, "AnyObject", "Returns the root Application."),
        ("AnyObject", "Name", "CATBSTR", 0, "AnyObject", "Returns or sets the object name."),
        ("PartDocument", "Part", "Part", 1, "PartDocument", "Returns the root Part inside the PartDocument."),
        ("Product", "PartNumber", "CATBSTR", 0, "Product", "Returns or sets the product part number."),
        ("SystemConfiguration", "ServicePack", "long", 1, "SystemConfiguration", "Returns service pack number."),
        ("SystemConfiguration", "Release", "long", 1, "SystemConfiguration", "Returns CATIA release number."),
        ("MaterialDocument", "Families", "MaterialFamilies", 1, "MaterialDocument", "Returns the collection of material families."),
        ("MaterialFamily", "Materials", "Materials", 1, "MaterialFamily", "Returns the collection of materials."),
        ("Material", "RenderingMaterial", "RenderingMaterial", 1, "Material", "Returns rendering material parameters."),
    ]
    # Add inherited Application/Name clones across noise features + Material/Pad
    for iface_name in [f"NoiseFeature{i}" for i in range(1, 21)] + ["Pad", "Prism", "Product", "Material"]:
        properties.append((iface_name, "Application", "Application", 1, "AnyObject", "Returns the root Application."))
        properties.append((iface_name, "Name", "CATBSTR", 0, "AnyObject", "Returns or sets the object name."))
    cur.executemany("INSERT INTO properties VALUES (?, ?, ?, ?, ?, ?)", properties)

    methods = [
        ("Pad", "GetDirection", "void", json.dumps([{"name": "ioDirection", "type": "CATSafeArrayVariant"}]), "Prism", "Returns extrusion direction.", ""),
        ("Pad", "GetItem", "CATBaseDispatch", json.dumps([{"name": "IDName", "type": "CATBSTR"}]), "AnyObject", "Retrieves an automation item by name.", ""),
        ("Prism", "GetDirection", "void", json.dumps([{"name": "ioDirection", "type": "CATSafeArrayVariant"}]), "Prism", "Returns prism direction.", ""),
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
            "Retrieves real RGB color components.",
            "",
        ),
        ("SystemConfiguration", "GetProductNames", "void", json.dumps([{"name": "ioProductNames", "type": "CATSafeArrayVariant"}]), "SystemConfiguration", "Gets installed configuration names.", ""),
        ("MaterialFamilies", "Item", "MaterialFamily", json.dumps([{"name": "iIndex", "type": "CATVariant"}]), "MaterialFamilies", "Returns a material family by index or name.", ""),
        ("MaterialFamilies", "Add", "MaterialFamily", json.dumps([]), "MaterialFamilies", "Creates a new material family.", ""),
        ("Materials", "Item", "Material", json.dumps([{"name": "iIndex", "type": "CATVariant"}]), "Materials", "Returns a material by index or name.", ""),
        ("Materials", "Add", "Material", json.dumps([]), "Materials", "Adds a new material to the family.", ""),
        (
            "Material",
            "PutIcon",
            "void",
            json.dumps([{"name": "iPath", "type": "CATBSTR", "description": "Folder path ending with separator."}]),
            "Material",
            "Read the icon of a material from JPEG file. The parameter is the path of the folder where the JPEG is going to be read Ex : E:\\folder\\",
            "void",
        ),
        (
            "Material",
            "GetIcon",
            "void",
            json.dumps([{"name": "iPath", "type": "CATBSTR"}]),
            "Material",
            "Write the icon of a material as JPEG to disc folder.",
            "",
        ),
        ("Material", "CreateRenderingData", "RenderingMaterial", json.dumps([]), "Material", "Creates rendering optical data on the material.", ""),
    ]
    cur.executemany("INSERT INTO methods VALUES (?, ?, ?, ?, ?, ?, ?)", methods)

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

    # Synthetic official usecases (including 8 Material noise rows to test community recipe non-starvation)
    cur.execute(
        "INSERT INTO usecases (interface_name, source, title, workbench, tags, provenance_json, context, code) VALUES (?, 'official', ?, '', '', NULL, ?, ?)",
        ("VisPropertySet", "Synthetic GetRealColor Example", "GetRealColor synthetic example", "status = vis.GetRealColor(r, g, b, inh)"),
    )
    cur.execute(
        "INSERT INTO usecases (interface_name, source, title, workbench, tags, provenance_json, context, code) VALUES (?, 'official', ?, '', '', NULL, ?, ?)",
        ("Pad", "Synthetic Pad Example", "Pad synthetic example", "Set pad1 = sf.AddNewPad(sk1, 20.0)"),
    )
    for idx in range(1, 9):
        cur.execute(
            "INSERT INTO usecases (interface_name, source, title, workbench, tags, provenance_json, context, code) VALUES (?, 'official', ?, 'Material', 'material', NULL, ?, ?)",
            ("MaterialFamilies", f"MaterialFamilies Official Example #{idx}", f"Material item snippet {idx}", f"Set fam = fams.Item({idx}) ' material example"),
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
    fts_rows = []
    for name, fw, desc, _ in interfaces:
        fts_rows.append(("interface", name, expand_camel_tokens(name), desc, fw, "", name, "", 0, 0))
    for name, desc, _ in enums:
        fts_rows.append(("enum", name, expand_camel_tokens(name), desc, "", "", name, "", 0, 0))
    for iface, name, ptype, ro, decl, desc in properties:
        is_inh = 0 if (not decl or decl.lower() == iface.lower()) else 1
        fts_rows.append(("property", f"{iface}.{name}", expand_camel_tokens(name), desc, "", iface, decl, ptype, ro, is_inh))
    for iface, name, rtype, _, decl, desc, ret_desc in methods:
        is_inh = 0 if (not decl or decl.lower() == iface.lower()) else 1
        fts_rows.append(("method", f"{iface}.{name}", expand_camel_tokens(name), f"{desc} {ret_desc}".strip(), "", iface, decl, rtype, 0, is_inh))
    cur.executemany(
        "INSERT INTO apis_fts (item_type, name, camel_tokens, description, framework, parent_interface, declared_in, data_type, readonly, is_inherited) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        fts_rows,
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
