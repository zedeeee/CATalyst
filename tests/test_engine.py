import pytest
from src.engine.db import CatalystDB

@pytest.fixture(scope="module")
def db():
    # Attempt to load the real database for integration testing
    try:
        return CatalystDB("dist/catalyst.db")
    except FileNotFoundError:
        pytest.skip("Database not built. Run build.py first.")

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

def test_search_interface(db):
    results = db.search("Pad")
    assert len(results) > 0
    # At least one result should be the Pad interface
    assert any(r["name"] == "Pad" and r["type"] == "interface" for r in results)

def test_search_enum_value(db):
    results = db.search("catCounterboredHole")
    assert len(results) > 0
    assert any(r["name"] == "CatHoleType" and r["type"] == "enum" for r in results)
