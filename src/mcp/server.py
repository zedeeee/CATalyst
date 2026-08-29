"""
MCP Server for CATalyst.
Exposes CATIA V5 Automation API knowledge as tools to AI Assistants via the Model Context Protocol.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("catalyst_mcp")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.engine.db import CatalystDB

try:
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("CATalyst", description="CATIA V5 Automation API Knowledge Base")
except (ImportError, ModuleNotFoundError):
    try:
        from mcp.server.mcpserver import MCPServer
        mcp = MCPServer("CATalyst", description="CATIA V5 Automation API Knowledge Base")
    except ImportError:
        try:
            from mcp.server import Server
            mcp = Server("CATalyst")
        except ImportError:
            class DummyMCP:
                def tool(self, *args, **kwargs):
                    def decorator(func):
                        return func
                    return decorator
            mcp = DummyMCP()

_db_instance: Optional[CatalystDB] = None


def get_db() -> Optional[CatalystDB]:
    """Dynamically initializes or retrieves the CatalystDB connection."""
    global _db_instance
    if _db_instance is not None:
        return _db_instance
    try:
        _db_instance = CatalystDB()
        return _db_instance
    except Exception as e:
        logger.error(f"Failed to connect to CatalystDB: {e}")
        return None


@mcp.tool()
def get_catia_interface(
    name: str = "",
    interface_name: str = "",
    interface: str = "",
    member_name: str = "",
    member: str = "",
    include_usecases: bool = True,
    max_usecases: int = 3
) -> str:
    """
    Retrieve full documentation for a specific CATIA V5 COM Interface.
    Supports member-level filtering and usecase granularity control to save tokens.
    
    Args:
        name: Name of the interface (e.g., 'Pad', 'Prism', 'PartDocument', 'VisPropertySet')
        interface_name: Alias for name
        interface: Alias for name
        member_name: Optional property or method name to filter by (e.g., 'SetShow', 'PartNumber')
        member: Alias for member_name
        include_usecases: Whether to include VBScript code examples (default: True, set False for signature-only)
        max_usecases: Maximum usecases to return in overview mode (default: 3)
    """
    try:
        target_name = (name or interface_name or interface).strip()
        target_member = (member_name or member).strip()

        if not target_name:
            return json.dumps({
                "isError": True,
                "error": "Missing interface name. Please provide 'name' or 'interface_name'."
            }, ensure_ascii=False)

        db = get_db()
        if not db:
            return json.dumps({
                "isError": True,
                "error": "Database not initialized. Please run `python build.py` or set CATALYST_DB_PATH."
            }, ensure_ascii=False)

        res = db.get_interface(
            target_name,
            member_name=target_member if target_member else None,
            include_usecases=include_usecases,
            max_usecases=max_usecases
        )
        if not res:
            return json.dumps({
                "isError": True,
                "error": f"Interface '{target_name}' not found in CATIA V5 documentation."
            }, ensure_ascii=False)

        return json.dumps(res, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"Exception in get_catia_interface: {e}")
        return json.dumps({
            "isError": True,
            "error": f"Internal Server Error in get_catia_interface: {str(e)}"
        }, ensure_ascii=False)


@mcp.tool()
def get_catia_usecases(
    interface: str = "",
    interface_name: str = "",
    name: str = "",
    member: str = "",
    member_name: str = "",
    source: str = "all",
    query: str = "",
    limit: int = 5
) -> str:
    """
    Retrieve code examples and practical recipes for a CATIA V5 Interface, method, or scenario intent.
    Supports dual-track sources (Official tutorials and Curated Community Recipes).
    
    Args:
        interface: Name of the interface (e.g., 'VisPropertySet', 'Selection', 'Pad', 'Product')
        interface_name: Alias for interface
        name: Alias for interface
        member: Optional method or property name (e.g., 'SetRealColor', 'Search')
        member_name: Alias for member
        source: Filter by source: 'all' (default: official first, then community), 'official', or 'community'
        query: Optional intent or scenario keywords (e.g., 'export step', 'bounding box')
        limit: Max examples to return (default: 5)
    """
    try:
        target_if = (interface or interface_name or name).strip()
        target_mbr = (member or member_name).strip()
        target_src = (source or "all").strip().lower()
        target_q = query.strip()

        db = get_db()
        if not db:
            return json.dumps({
                "isError": True,
                "error": "Database not initialized. Please run `python build.py` or set CATALYST_DB_PATH."
            }, ensure_ascii=False)

        if not target_if and target_q:
            # If no interface name provided, search recipes across entire DB by intent query
            results = db.search_recipes(query=target_q, source=target_src, limit=limit)
        elif target_if:
            results = db.get_usecases(
                target_if,
                member=target_mbr if target_mbr else None,
                source=target_src,
                query=target_q if target_q else None,
                limit=limit
            )
        else:
            return json.dumps({
                "isError": True,
                "error": "Missing parameters. Please provide 'interface' or scenario 'query'."
            }, ensure_ascii=False)

        if not results:
            desc = f"{target_if}.{target_mbr}" if (target_if and target_mbr) else (target_if or target_q)
            return json.dumps({
                "interface": target_if,
                "member": target_mbr,
                "source_filter": target_src,
                "total_examples": 0,
                "message": f"No code examples found for '{desc}'."
            }, indent=2, ensure_ascii=False)

        return json.dumps({
            "interface": target_if,
            "member": target_mbr,
            "source_filter": target_src,
            "total_examples": len(results),
            "usecases": results
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"Exception in get_catia_usecases: {e}")
        return json.dumps({
            "isError": True,
            "error": f"Internal Server Error in get_catia_usecases: {str(e)}"
        }, ensure_ascii=False)


@mcp.tool()
def search_catia_recipes(
    query: str = "",
    keyword: str = "",
    workbench: str = "",
    source: str = "all",
    limit: int = 5
) -> str:
    """
    Search practical industrial recipes and implementation patterns across CATIA workbenches by natural language intent.
    Ideal for finding end-to-end Python win32com scripts (e.g. batch export STEP, extract BOM, title block update).
    
    Args:
        query: Intent or scenario keywords (e.g., 'export step', 'bounding box', 'bom mass', 'title block')
        keyword: Alias for query
        workbench: Optional workbench filter ('Assembly', 'PartDesign', 'Drafting', 'GenerativeShapeDesign')
        source: Filter by 'all', 'official', or 'community' (default: 'all')
        limit: Maximum recipes to return (default: 5)
    """
    try:
        search_query = (query or keyword).strip()
        if not search_query:
            return json.dumps({
                "isError": True,
                "error": "Missing query. Please provide scenario keywords (e.g., 'export step', 'bounding box')."
            }, ensure_ascii=False)

        target_wb = workbench.strip() if workbench else None
        target_src = (source or "all").strip().lower()

        db = get_db()
        if not db:
            return json.dumps({
                "isError": True,
                "error": "Database not initialized. Please run `python build.py` or set CATALYST_DB_PATH."
            }, ensure_ascii=False)

        results = db.search_recipes(
            query=search_query,
            workbench=target_wb,
            source=target_src,
            limit=limit
        )

        return json.dumps({
            "query": search_query,
            "workbench_filter": target_wb,
            "source_filter": target_src,
            "total_matches": len(results),
            "recipes": results
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"Exception in search_catia_recipes: {e}")
        return json.dumps({
            "isError": True,
            "error": f"Internal Server Error in search_catia_recipes: {str(e)}"
        }, ensure_ascii=False)


@mcp.tool()
def get_catia_search_syntax(
    workbench: str = "",
    query_type: str = "",
    query: str = ""
) -> str:
    """
    Retrieve official CATIA Selection.Search query syntax grammar, workbench prefixes, and practical examples.
    Use this to construct valid query strings for catia.ActiveDocument.Selection.Search (e.g., 'CATPrtSearch.Pad,all').
    
    Args:
        workbench: Optional workbench filter ('PartDesign', 'GenerativeShapeDesign', 'Drafting', 'Assembly', 'GenericTopology')
        query_type: Optional geometry/feature type filter (e.g., 'Pad', 'Hole', 'Point', 'DrwText', 'Face')
        query: Alias for query_type
    """
    try:
        target_wb = workbench.strip()
        target_qt = (query_type or query).strip()

        db = get_db()
        if not db:
            return json.dumps({
                "isError": True,
                "error": "Database not initialized. Please run `python build.py` or set CATALYST_DB_PATH."
            }, ensure_ascii=False)

        res = db.get_search_syntax(
            workbench=target_wb if target_wb else None,
            query_type=target_qt if target_qt else None
        )
        return json.dumps(res, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"Exception in get_catia_search_syntax: {e}")
        return json.dumps({
            "isError": True,
            "error": f"Internal Server Error in get_catia_search_syntax: {str(e)}"
        }, ensure_ascii=False)



@mcp.tool()
def search_catia_api(
    query: str = "",
    keyword: str = "",
    item_type: str = "all",
    type: str = "",
    limit: int = 15
) -> str:
    """
    Fuzzy search the CATIA V5 API across interfaces, enums, properties, and methods.
    Supports reverse-searching host interfaces for properties/methods (e.g., search 'PartNumber' to find Product).
    
    Args:
        query: Search keywords (e.g., 'ServicePack', 'ActiveDocument', 'PartNumber', 'fillet')
        keyword: Alias for query
        item_type: Filter by 'all', 'interface', 'enum', 'property', or 'method'
        type: Alias for item_type
        limit: Max results to return
    """
    try:
        search_query = (query or keyword).strip()
        if not search_query:
            return json.dumps({
                "isError": True,
                "error": "Missing search query. Please provide 'query' or 'keyword'."
            }, ensure_ascii=False)

        filter_type = (item_type if item_type != "all" else (type or "all")).strip()

        db = get_db()
        if not db:
            return json.dumps({
                "isError": True,
                "error": "Database not initialized. Please run `python build.py` or set CATALYST_DB_PATH."
            }, ensure_ascii=False)

        results = db.search(search_query, item_type=filter_type, limit=limit)
        
        # If searching for property/method or single member query, check host interface aggregation
        reverse_hosts = None
        if filter_type in ("all", "property", "method"):
            member_lookup = db.get_interfaces_by_member(search_query, member_type=filter_type if filter_type != "all" else None)
            if member_lookup["total_host_interfaces"] > 0:
                reverse_hosts = member_lookup

        payload: Dict[str, Any] = {
            "query": search_query,
            "filter_type": filter_type,
            "total_matches": len(results),
            "results": results
        }
        if reverse_hosts:
            payload["host_interfaces_summary"] = reverse_hosts

        return json.dumps(payload, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"Exception in search_catia_api: {e}")
        return json.dumps({
            "isError": True,
            "error": f"Internal Server Error in search_catia_api: {str(e)}"
        }, ensure_ascii=False)


@mcp.tool()
def get_catia_enum(
    name: str = "",
    enum_name: str = "",
    enum: str = "",
    value: Optional[Union[int, str]] = None,
    member_name: str = "",
    member: str = ""
) -> str:
    """
    Retrieve details and possible values for a CATIA V5 Enumeration.
    Supports bidirectional lookup (by enum name, numeric value/index, or member name).
    
    Args:
        name: The name of the enum (e.g., 'CatProductSource') or member (e.g., 'catProductMade')
        enum_name: Alias for name
        enum: Alias for name
        value: Numeric index/value to reverse-lookup (e.g., 0, 1)
        member_name: Exact enum member name to reverse-lookup (e.g., 'catProductMade')
        member: Alias for member_name
    """
    try:
        target_name = (name or enum_name or enum).strip()
        target_member = (member_name or member).strip()

        if not target_name and not target_member and value is None:
            return json.dumps({
                "isError": True,
                "error": "Missing parameters. Please provide 'name', 'enum_name', 'member_name', or 'value'."
            }, ensure_ascii=False)

        db = get_db()
        if not db:
            return json.dumps({
                "isError": True,
                "error": "Database not initialized. Please run `python build.py` or set CATALYST_DB_PATH."
            }, ensure_ascii=False)

        res = db.get_enum(name=target_name, value=value, member_name=target_member)
        if not res:
            query_desc = target_name or target_member or f"value={value}"
            return json.dumps({
                "isError": True,
                "error": f"Enum '{query_desc}' not found."
            }, ensure_ascii=False)

        return json.dumps(res, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"Exception in get_catia_enum: {e}")
        return json.dumps({
            "isError": True,
            "error": f"Internal Server Error in get_catia_enum: {str(e)}"
        }, ensure_ascii=False)


if __name__ == "__main__":
    if hasattr(mcp, "run"):
        mcp.run()


