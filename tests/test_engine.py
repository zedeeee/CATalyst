import os
from pathlib import Path
try:
    import pytest
except ImportError:
    class DummyPytest:
        def fixture(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
        def skip(self, msg=""):
            pass
        def raises(self, exc):
            import contextlib
            return contextlib.nullcontext()
    pytest = DummyPytest()

from src.engine.db import CatalystDB, _resolve_db_path

@pytest.fixture(scope="module")
def db():
    # Attempt to load the real database for integration testing
    try:
        return CatalystDB()
    except FileNotFoundError:
        pytest.skip("Database not built. Run build.py first.")

def test_db_path_fallback():
    # Test path resolution without error when db exists
    resolved = _resolve_db_path()
    assert resolved.exists()
    assert resolved.name == "catalyst.db"

def test_db_env_override(monkeypatch, tmp_path):
    fake_db = tmp_path / "fake.db"
    fake_db.touch()
    monkeypatch.setenv("CATALYST_DB_PATH", str(fake_db))
    resolved = _resolve_db_path()
    assert resolved == fake_db.resolve()

def test_db_not_found_raises(monkeypatch, tmp_path):
    import src.engine.db as db_module
    monkeypatch.setattr(db_module, "PROJECT_ROOT", tmp_path / "empty_proj")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CATALYST_DB_PATH", str(tmp_path / "non_existent_env.db"))
    with pytest.raises(FileNotFoundError) as exc_info:
        _resolve_db_path(tmp_path / "another_non_existent.db")
    assert "CATalyst SQLite database not found" in str(exc_info.value)

def test_get_interface_exact(db):
    res = db.get_interface("Pad")
    assert res is not None
    assert res["name"] == "Pad"
    assert "inheritance_chain" in res
    assert "Pad" in res["inheritance_chain"]
    assert "Prism" in res["inheritance_chain"]
    
    # Check if inherited methods are present
    method_names = [m["name"] for m in res["methods"]]
    assert "GetDirection" in method_names # Inherited from Prism
    assert "GetItem" in method_names # Inherited from AnyObject

def test_get_interface_member_filter(db):
    res = db.get_interface("Pad", member_name="GetDirection")
    assert res is not None
    assert res["name"] == "Pad"
    assert len(res["methods"]) == 1
    assert res["methods"][0]["name"] == "GetDirection"
    assert len(res["properties"]) == 0

def test_get_interface_no_usecases(db):
    res = db.get_interface("Pad", include_usecases=False)
    assert res is not None
    assert len(res["usecases"]) == 0

def test_get_usecases_standalone(db):
    ucs = db.get_usecases("VisPropertySet", member="GetRealColor")
    assert len(ucs) > 0
    assert all("GetRealColor" in u["context"] or "GetRealColor" in u["code"] for u in ucs)

def test_get_search_syntax(db):
    syntax = db.get_search_syntax(workbench="PartDesign")
    assert syntax["prefix"] == "CATPrtSearch"
    assert len(syntax["types"]) > 0
    assert any(t["type"] == "Pad" for t in syntax["types"])

def test_python_mapping_hints(db):
    vis_res = db.get_interface("VisPropertySet", member_name="GetRealColor")
    assert vis_res and len(vis_res["methods"]) == 1
    method_data = vis_res["methods"][0]
    assert "python_mapping" in method_data
    assert "pywin32_call" in method_data["python_mapping"]

def test_get_interface_not_found(db):
    res = db.get_interface("NonExistentInterface123")
    assert res is None

def test_get_enum_exact(db):
    res = db.get_enum("CatHoleType")
    assert res is not None
    assert res["name"] == "CatHoleType"
    
    # Check values
    values = [v["name"] for v in res["values"]]
    assert "catSimpleHole" in values
    assert "catCounterboredHole" in values
    # Check enriched value index
    assert all("value" in v for v in res["values"])

def test_get_enum_by_value(db):
    # Test CatProductSource: 0 = catProductSourceUnknown, 1 = catProductMade, 2 = catProductBought
    res = db.get_enum(name="CatProductSource", value=1)
    assert res is not None
    assert "matched_value" in res
    assert res["matched_value"]["name"] == "catProductMade"
    assert res["matched_value"]["value"] == 1

def test_get_enum_by_member_name(db):
    # Lookup by member name directly
    res = db.get_enum(member_name="catProductMade")
    assert res is not None
    assert res["name"] == "CatProductSource"
    assert res.get("matched_value", {}).get("name") == "catProductMade"

def test_get_enum_by_name_param_as_member(db):
    # Passing member name as the first argument
    res = db.get_enum("catProductMade")
    assert res is not None
    assert res["name"] == "CatProductSource"
    assert res.get("matched_value", {}).get("name") == "catProductMade"

def test_get_interfaces_by_member(db):
    res = db.get_interfaces_by_member("PartNumber", member_type="property")
    assert res["total_host_interfaces"] > 0
    assert "Product" in res["host_interfaces"]
    assert any(p["interface"] == "Product" for p in res["properties"])

def test_search_interface(db):
    results = db.search("Pad")
    assert len(results) > 0
    assert any(r["name"] == "Pad" and r["type"] == "interface" for r in results)

def test_search_property(db):
    results = db.search("ServicePack", item_type="property")
    assert len(results) > 0
    assert any("ServicePack" in r["name"] and r["type"] == "property" for r in results)
    
    # Check property attributes
    sp_prop = next(r for r in results if "SystemConfiguration.ServicePack" in r["name"])
    assert sp_prop["data_type"] == "long"
    assert sp_prop["readonly"] is True

def test_search_type_filter(db):
    # Only interfaces
    res_if = db.search("Pad", item_type="interface")
    assert all(r["type"] == "interface" for r in res_if)
    
    # Only properties
    res_prop = db.search("Release", item_type="property")
    assert all(r["type"] == "property" for r in res_prop)
    
    # Only methods
    res_meth = db.search("GetProductNames", item_type="method")
    assert all(r["type"] == "method" for r in res_meth)
    assert any("SystemConfiguration.GetProductNames" in r["name"] for r in res_meth)

def test_get_usecases_dual_track(db):
    # Test community source
    comm_ucs = db.get_usecases("Product", source="community")
    assert len(comm_ucs) > 0
    assert all(u["source"] == "community" for u in comm_ucs)
    assert any("STEP" in u["title"] or "BOM" in u["title"] for u in comm_ucs)
    assert comm_ucs[0].get("provenance") is not None

    # Test all source with Pad
    all_ucs = db.get_usecases("Pad", source="all")
    assert len(all_ucs) > 0

def test_search_recipes(db):
    # Search by intent
    res = db.search_recipes("export step")
    assert len(res) > 0
    match = res[0]
    assert match["interface"] == "Product"
    assert match["workbench"] == "Assembly"
    assert "STEP" in match["title"]
    assert "win32com" in match["code"]

    # Search with workbench filter
    res_part = db.search_recipes("pad", workbench="PartDesign")
    assert len(res_part) > 0
    assert any(r["workbench"] == "PartDesign" for r in res_part)



