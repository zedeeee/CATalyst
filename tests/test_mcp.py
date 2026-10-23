import json
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

import src.mcp.server as mcp_server


def test_mcp_get_interface_standard():
    res_str = mcp_server.get_catia_interface(name="Pad")
    data = json.loads(res_str)
    assert not data.get("isError")
    assert data["name"] == "Pad"
    assert "Prism" in data["inheritance_chain"]


def test_mcp_get_interface_alias():
    # Test alias interface_name
    res_str = mcp_server.get_catia_interface(interface_name="Pad")
    data = json.loads(res_str)
    assert not data.get("isError")
    assert data["name"] == "Pad"

    # Test alias interface
    res_str2 = mcp_server.get_catia_interface(interface="Pad")
    data2 = json.loads(res_str2)
    assert not data2.get("isError")
    assert data2["name"] == "Pad"


def test_mcp_get_interface_member_filter():
    res_str = mcp_server.get_catia_interface(interface_name="Pad", member_name="GetDirection")
    data = json.loads(res_str)
    assert not data.get("isError")
    assert data["name"] == "Pad"
    assert len(data["methods"]) == 1
    assert data["methods"][0]["name"] == "GetDirection"
    assert len(data["properties"]) == 0


def test_mcp_get_usecases():
    res_str = mcp_server.get_catia_usecases(interface="VisPropertySet", member="GetRealColor")
    data = json.loads(res_str)
    assert not data.get("isError")
    assert data["interface"] == "VisPropertySet"
    assert data["total_examples"] > 0


def test_mcp_get_search_syntax():
    res_str = mcp_server.get_catia_search_syntax(workbench="PartDesign")
    data = json.loads(res_str)
    assert not data.get("isError")
    assert data["prefix"] == "CATPrtSearch"

    res_str2 = mcp_server.get_catia_search_syntax(query_type="Hole")
    data2 = json.loads(res_str2)
    assert not data2.get("isError")
    assert "matched_types" in data2



def test_mcp_get_interface_not_found():
    res_str = mcp_server.get_catia_interface(name="NonExistentInterface999")
    data = json.loads(res_str)
    assert data.get("isError") is True
    assert "not found" in data.get("error", "").lower()


def test_mcp_get_interface_missing_args():
    res_str = mcp_server.get_catia_interface()
    data = json.loads(res_str)
    assert data.get("isError") is True
    assert "Missing interface name" in data.get("error", "")


def test_mcp_get_enum_standard():
    res_str = mcp_server.get_catia_enum(name="CatHoleType")
    data = json.loads(res_str)
    assert not data.get("isError")
    assert data["name"] == "CatHoleType"
    assert len(data["values"]) > 0


def test_mcp_get_enum_alias_and_reverse_value():
    res_str = mcp_server.get_catia_enum(enum_name="CatProductSource", value=1)
    data = json.loads(res_str)
    assert not data.get("isError")
    assert data["name"] == "CatProductSource"
    assert data.get("matched_value", {}).get("name") == "catProductMade"
    assert data.get("matched_value", {}).get("value") == 1


def test_mcp_get_enum_reverse_member():
    res_str = mcp_server.get_catia_enum(member_name="catProductMade")
    data = json.loads(res_str)
    assert not data.get("isError")
    assert data["name"] == "CatProductSource"
    assert data.get("matched_value", {}).get("name") == "catProductMade"


def test_mcp_get_enum_missing_args():
    res_str = mcp_server.get_catia_enum()
    data = json.loads(res_str)
    assert data.get("isError") is True


def test_mcp_search_api_standard_and_alias():
    res_str = mcp_server.search_catia_api(query="Pad")
    data = json.loads(res_str)
    assert not data.get("isError")
    assert data["total_matches"] > 0

    res_str_alias = mcp_server.search_catia_api(keyword="Pad")
    data_alias = json.loads(res_str_alias)
    assert not data_alias.get("isError")
    assert data_alias["total_matches"] > 0


def test_mcp_search_api_reverse_hosts():
    res_str = mcp_server.search_catia_api(keyword="PartNumber", item_type="property")
    data = json.loads(res_str)
    assert not data.get("isError")
    assert "host_interfaces_summary" in data
    assert "Product" in data["host_interfaces_summary"]["host_interfaces"]


def test_mcp_search_api_missing_args():
    res_str = mcp_server.search_catia_api()
    data = json.loads(res_str)
    assert data.get("isError") is True


def test_mcp_concurrent_multithread_requests():
    from concurrent.futures import ThreadPoolExecutor

    def call_tool(args):
        tool_name, param = args
        if tool_name == "interface":
            return mcp_server.get_catia_interface(interface_name=param)
        elif tool_name == "enum":
            return mcp_server.get_catia_enum(enum_name=param)
        elif tool_name == "search":
            return mcp_server.search_catia_api(keyword=param)

    tasks = [
        ("interface", "Pad"),
        ("interface", "Prism"),
        ("enum", "CatProductSource"),
        ("enum", "CatHoleType"),
        ("search", "PartNumber"),
        ("search", "ServicePack"),
    ] * 5

    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(executor.map(call_tool, tasks))

    assert len(responses) == len(tasks)
    for raw in responses:
        parsed = json.loads(raw)
        assert not parsed.get("isError"), f"Multithreaded MCP call returned error: {parsed}"


def test_mcp_search_catia_recipes():
    res_str = mcp_server.search_catia_recipes(query="export step")
    data = json.loads(res_str)
    assert not data.get("isError")
    assert data["total_matches"] > 0
    first_recipe = data["recipes"][0]
    assert first_recipe["interface"] == "Product"
    assert "STEP" in first_recipe["title"]


def test_mcp_get_usecases_community():
    res_str = mcp_server.get_catia_usecases(interface="Product", source="community")
    data = json.loads(res_str)
    assert not data.get("isError")
    assert data["total_examples"] > 0
    assert all(uc["source"] == "community" for uc in data["usecases"])


