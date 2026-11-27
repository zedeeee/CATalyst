"""
MCP Server for CATalyst.
Exposes CATIA V5 Automation API knowledge as tools to AI Assistants via the Model Context Protocol.
"""

import os
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
from src.engine.docs_db import CatalystDocsDB, resolve_docs_db_path
from src.engine.formatter import dump_compact_json, format_interface_card

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
_docs_db_instance: Optional[CatalystDocsDB] = None


def _core_db_missing_error() -> str:
    return json.dumps(
        {
            "isError": True,
            "error": (
                "Core API database (dist/catalyst.db) is not initialized yet. "
                "Initialize it locally inside the isolated project virtual environment:\n"
                "  - One-click (Windows): .\\install.ps1\n"
                "  - One-click (macOS/Linux): ./install.sh\n"
                "  - Or manual: uv sync && uv run python build.py"
            ),
        },
        ensure_ascii=False,
    )


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


def get_docs_db() -> Optional[CatalystDocsDB]:
    """Dynamically initializes or retrieves the optional CatalystDocsDB connection."""
    global _docs_db_instance
    if _docs_db_instance is not None:
        if _docs_db_instance.db_path.exists():
            return _docs_db_instance
        _docs_db_instance = None
    try:
        resolved = resolve_docs_db_path()
        if resolved is None:
            return None
        _docs_db_instance = CatalystDocsDB(resolved)
        return _docs_db_instance
    except Exception as e:
        logger.error(f"Failed to connect to CatalystDocsDB: {e}")
        return None


@mcp.tool()
def get_catia_interface(
    name: str = "",
    interface_name: str = "",
    interface: str = "",
    member_name: str = "",
    member: str = "",
    from_interface: str = "",
    include_usecases: bool = True,
    max_usecases: int = 3,
    detail: str = "auto",
    include_base_members: bool = False,
    output_format: str = "",
) -> str:
    """
    Retrieve documentation for a CATIA V5 COM Interface with adaptive token efficiency.
    Supports exact, comma-separated, and wildcard ('*Fillet*') member filtering,
    COM object graph navigation path with terminal constructor signature, inline enum
    expansion, and optional ultra-dense IDL signature card formatting.
    
    Args:
        name: Name of the interface (e.g., 'Pad', 'Prism', 'PartDocument', 'VisPropertySet')
        interface_name: Alias for name
        interface: Alias for name
        member_name: Optional property/method filter (exact, comma-separated, or wildcard e.g. '*Fillet*')
        member: Alias for member_name
        from_interface: Optional starting COM interface to compute shortest access chain (e.g., 'Application')
        include_usecases: Whether to include code examples (default: True, set False for signature-only)
        max_usecases: Maximum usecases to return in overview mode (default: 3)
        detail: Granularity: 'auto' (compact overview / full when member_name set), 'summary', 'compact', or 'full'
        include_base_members: Include AnyObject/CATBaseDispatch boilerplate (Application, Name, Parent, GetItem) in overview (default False)
        output_format: 'json' (compact JSON, default) or 'card' (ultra-dense IDL text card, ~85% smaller)
    """
    try:
        target_name = (name or interface_name or interface).strip()
        target_member = (member_name or member).strip()
        start_iface = (from_interface or "").strip()
        eff_format = (output_format or os.environ.get("CATALYST_OUTPUT_FORMAT") or "json").strip().lower()

        if not target_name:
            return json.dumps({
                "isError": True,
                "error": "Missing interface name. Please provide 'name' or 'interface_name'."
            }, ensure_ascii=False)

        db = get_db()
        if not db:
            return _core_db_missing_error()

        res = db.get_interface(
            target_name,
            member_name=target_member if target_member else None,
            include_usecases=include_usecases,
            max_usecases=max_usecases,
            detail=detail,
            include_base_members=include_base_members,
            inline_enums=True,
        )
        if not res:
            return json.dumps({
                "isError": True,
                "error": f"Interface '{target_name}' not found in CATIA V5 documentation."
            }, ensure_ascii=False)

        if start_iface and isinstance(res, dict) and "name" in res:
            is_compact_nav = (detail != "full") and (not target_member)
            nav = db.get_navigation_path(res["name"], from_interface=start_iface, compact=is_compact_nav)
            if nav:
                res["navigation_path"] = nav

        docs_db = get_docs_db()
        if docs_db and isinstance(res, dict) and "name" in res and "member_not_found" not in res:
            try:
                linkages = docs_db.get_api_linkages(
                    res["name"],
                    member_name=target_member if (target_member and "*" not in target_member and "," not in target_member) else None,
                    max_samples=max_usecases if max_usecases > 0 else 5,
                    max_docs=max_usecases if max_usecases > 0 else 5,
                )
                if linkages.get("linked_official_docs"):
                    res["linked_official_docs"] = linkages["linked_official_docs"]
                if linkages.get("linked_sample_scripts"):
                    res["linked_sample_scripts"] = linkages["linked_sample_scripts"]
            except Exception as le:
                logger.debug(f"Failed to enrich interface with docs linkages: {le}")

        if eff_format == "card":
            return format_interface_card(res)
        return dump_compact_json(res)
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
            return _core_db_missing_error()

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
            return dump_compact_json({
                "interface": target_if,
                "member": target_mbr,
                "source_filter": target_src,
                "total_examples": 0,
                "message": f"No code examples found for '{desc}'."
            })

        return dump_compact_json({
            "interface": target_if,
            "member": target_mbr,
            "source_filter": target_src,
            "total_examples": len(results),
            "usecases": results
        })
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
            return _core_db_missing_error()

        results = db.search_recipes(
            query=search_query,
            workbench=target_wb,
            source=target_src,
            limit=limit
        )

        return dump_compact_json({
            "query": search_query,
            "workbench_filter": target_wb,
            "source_filter": target_src,
            "total_matches": len(results),
            "recipes": results
        })
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
            return _core_db_missing_error()

        res = db.get_search_syntax(
            workbench=target_wb if target_wb else None,
            query_type=target_qt if target_qt else None
        )
        return dump_compact_json(res)
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
    include_catnls: bool = False,
    include_cross_links: bool = True,
    detail: str = "full",
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
        include_catnls: Probe *.CATNls/*.CATRsc when 0 COM hits (default False; set True to look up Command Header IDs/shortcuts)
        include_cross_links: Include host_interfaces_summary, related_recipes, and related_docs (default True)
        detail: Result granularity: 'full' (default) or 'compact' (omits descriptions)
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
            return _core_db_missing_error()

        results = db.search(search_query, item_type=filter_type, limit=limit, detail=detail)
        
        # If searching for property/method or single member query, check host interface aggregation
        reverse_hosts = None
        if include_cross_links and filter_type in ("all", "property", "method"):
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

        # Cross-link curated community recipes & offline docs when enabled
        if include_cross_links and filter_type == "all":
            comm_hints = db.search_recipes(search_query, source="community", limit=2)
            if comm_hints:
                payload["related_recipes"] = [
                    {"interface": r["interface"], "title": r["title"], "workbench": r["workbench"]}
                    for r in comm_hints
                ]

        docs_db = get_docs_db()
        if docs_db is not None and (len(results) == 0 or (include_cross_links and filter_type == "all")):
            if include_cross_links:
                try:
                    doc_hits = docs_db.search_docs(search_query, limit=2)
                    if doc_hits.get("results"):
                        payload["related_docs"] = [
                            {"doc_id": d["doc_id"], "title": d["title"], "category": d["category"]}
                            for d in doc_hits["results"]
                        ]
                except Exception:
                    pass
            if len(results) == 0 and not reverse_hosts:
                if include_catnls and " " not in search_query and len(search_query) >= 3:
                    try:
                        nls_hits = docs_db.search_settings(
                            query=search_query,
                            options_only=False,
                            scope="all",
                            include_related_docs=False,
                            limit=4,
                        )
                        if nls_hits.get("nls_entries"):
                            payload["related_catnls_headers"] = nls_hits["nls_entries"]
                    except Exception:
                        pass
                payload["hint"] = (
                    "No COM Automation API matches found. For GUI Command Header IDs or shortcuts, "
                    "call search_catia_settings(scope='headers'|'accelerators') or pass include_catnls=True; "
                    "for Tools>Options or batch protocols, try search_catia_docs or search_catia_samples."
                )

        return dump_compact_json(payload)
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
            return _core_db_missing_error()

        res = db.get_enum(name=target_name, value=value, member_name=target_member)
        if not res:
            query_desc = target_name or target_member or f"value={value}"
            return json.dumps({
                "isError": True,
                "error": f"Enum '{query_desc}' not found."
            }, ensure_ascii=False)

        return dump_compact_json(res)
    except Exception as e:
        logger.exception(f"Exception in get_catia_enum: {e}")
        return json.dumps({
            "isError": True,
            "error": f"Internal Server Error in get_catia_enum: {str(e)}"
        }, ensure_ascii=False)


def _docs_missing_error() -> str:
    return json.dumps(
        {
            "isError": True,
            "error": (
                "Offline documentation DB (catalyst_docs.db) is not built on this machine. "
                "Run `uv run python build_docs.py --doc-root <Bxxdoc/English/online> "
                "--install-root <Bxx/win_b64>` or set CATALYST_DOCS_DB_PATH."
            ),
        },
        ensure_ascii=False,
    )


@mcp.tool()
def search_catia_docs(
    query: str = "",
    keyword: str = "",
    category: str = "all",
    module: str = "",
    solution: str = "",
    include_snippet: bool = True,
    limit: int = 10,
) -> str:
    """
    Search version-aligned offline CATIA V5 User's Guide, Tools>Options, and Automation technical articles.
    Returns compact metadata, official warnings previews, and doc_ids for targeted retrieval via get_catia_doc_page.

    Args:
        query: Full-text search keywords (e.g., 'Catalog Batch Mode', 'Document Template', 'Resolved Family Components')
        keyword: Alias for query
        category: Filter by 'all' (default), 'user_guide', 'options', or 'automation_doc'
        module: Optional module directory filter (e.g., 'cceug_C2', 'bascuctg_C2', 'cfyugpkt_C2')
        solution: Optional CATIA solution filter (e.g., 'Infrastructure', 'Mechanical Design')
        include_snippet: Include text snippet in each hit (default True; set False for ultra-compact doc_id index)
        limit: Max results to return (default 10, max 30)
    """
    try:
        q = (query or keyword).strip()
        if not q:
            return json.dumps({"isError": True, "error": "Missing query."}, ensure_ascii=False)
        docs_db = get_docs_db()
        if not docs_db:
            return _docs_missing_error()
        res = docs_db.search_docs(
            query=q,
            category=category,
            module=module,
            solution=solution,
            include_snippet=include_snippet,
            limit=limit,
        )
        return dump_compact_json(res)
    except Exception as e:
        logger.exception(f"Exception in search_catia_docs: {e}")
        return json.dumps({"isError": True, "error": f"Internal Server Error in search_catia_docs: {str(e)}"}, ensure_ascii=False)


@mcp.tool()
def get_catia_doc_page(
    doc_id: str = "",
    section: str = "",
    include_images: bool = True,
    max_chars: int = 12000,
    start_line: int = 0,
    end_line: int = 0,
) -> str:
    """
    Retrieve the cleaned text, official warnings, options anchors, and embedded screenshot paths
    for a specific CATIA V5 offline documentation page.

    Args:
        doc_id: Page ID from search_catia_docs (e.g., 'cceug_C2/cceugbt0102.htm' or 'bascuctg0000.htm')
        section: Optional heading substring to slice only a specific section and save tokens
        include_images: Include relative and resolved local absolute paths of content screenshots (default True)
        max_chars: Maximum characters of body_text to return (default 12000)
        start_line: Optional 1-based start line for slicing long script/source pages
        end_line: Optional 1-based end line for slicing long script/source pages
    """
    try:
        target = (doc_id or "").strip()
        if not target:
            return json.dumps({"isError": True, "error": "Missing doc_id."}, ensure_ascii=False)
        docs_db = get_docs_db()
        if not docs_db:
            return _docs_missing_error()
        res = docs_db.get_doc_page(
            doc_id=target,
            section=section,
            include_images=include_images,
            max_chars=max_chars,
            start_line=start_line,
            end_line=end_line,
        )
        if not res:
            return json.dumps({"isError": True, "error": f"Documentation page '{target}' not found."}, ensure_ascii=False)
        return dump_compact_json(res)
    except Exception as e:
        logger.exception(f"Exception in get_catia_doc_page: {e}")
        return json.dumps({"isError": True, "error": f"Internal Server Error in get_catia_doc_page: {str(e)}"}, ensure_ascii=False)


@mcp.tool()
def search_catia_settings(
    query: str = "",
    nls_file: str = "",
    options_only: bool = True,
    scope: str = "all",
    include_related_docs: Optional[bool] = None,
    limit: int = 15,
) -> str:
    """
    Search CATIA V5 msgcatalog (*.CATNls / *.CATRsc) across scoped targets:
    - scope='options': Tools>Options & .CATSettings keys (+ related_option_docs & XML hint)
    - scope='headers': GUI Command Header IDs (e.g., 'OpenInNewWnd') without Options noise
    - scope='accelerators': Keyboard shortcuts from *.CATRsc (e.g., 'Ctrl+N', 'Ctrl+O')
    - scope='all': Combined search (honors options_only)

    Args:
        query: UI wording, Command Header ID, shortcut ('Ctrl+N'), or option key
        nls_file: Optional file stem filter (e.g., 'CATCuiOptionEditor', 'CATFileHeader')
        options_only: Used when scope='all' to prioritize option entries (default True)
        scope: Scoped filter: 'all', 'options', 'headers', or 'accelerators'
        include_related_docs: Override whether to attach related_option_docs & xml_roundtrip_hint (default: True for options/all, False for headers/accelerators)
        limit: Max entries to return (default 15, max 50)
    """
    try:
        if not (query or "").strip() and not (nls_file or "").strip():
            return json.dumps({"isError": True, "error": "Provide 'query' or 'nls_file'."}, ensure_ascii=False)
        docs_db = get_docs_db()
        if not docs_db:
            return _docs_missing_error()
        res = docs_db.search_settings(
            query=query,
            nls_file=nls_file,
            options_only=options_only,
            scope=scope,
            include_related_docs=include_related_docs,
            limit=limit,
        )
        return dump_compact_json(res)
    except Exception as e:
        logger.exception(f"Exception in search_catia_settings: {e}")
        return json.dumps({"isError": True, "error": f"Internal Server Error in search_catia_settings: {str(e)}"}, ensure_ascii=False)


@mcp.tool()
def search_catia_samples(
    query: str = "",
    ext: str = "",
    module: str = "",
    source: str = "all",
    include_content: bool = False,
    include_binary: bool = True,
    max_chars: int = 6000,
    limit: int = 10,
) -> str:
    """
    Search official CATIA V5 sample files — both plain-text (.csv, .CATScript, .txt, .xml)
    and binary CAD/Excel samples (.CATPart, .CATProduct, .catalog, .cgr, .xls).
    Stores portable relative paths and resolves machine-local abs_path from CATALYST_DOC_ROOT / CATALYST_INSTALL_ROOT.

    Args:
        query: Keywords matching filename, module, path, or text sample content (e.g., 'BatchCatalog', 'PktRod', 'FHC_M03')
        ext: Optional extension filter (e.g., '.csv', '.catscript', '.catpart', '.catalog')
        module: Optional module directory filter (e.g., 'cceug_C2', 'cfyugpkt_C2')
        source: Source scope: 'all' (default), 'doc_samples', or 'startup' (win_b64/startup/)
        include_content: Return full text content for non-binary samples (default False)
        include_binary: Include binary CAD/Excel samples indexed by relative path (default True)
        max_chars: Max characters per text sample when include_content=True (default 6000)
        limit: Max samples to return (default 10, max 30)
    """
    try:
        docs_db = get_docs_db()
        if not docs_db:
            return _docs_missing_error()
        res = docs_db.search_samples(
            query=query,
            ext=ext,
            module=module,
            source=source,
            include_content=include_content,
            include_binary=include_binary,
            max_chars=max_chars,
            limit=limit,
        )
        return dump_compact_json(res)
    except Exception as e:
        logger.exception(f"Exception in search_catia_samples: {e}")
        return json.dumps({"isError": True, "error": f"Internal Server Error in search_catia_samples: {str(e)}"}, ensure_ascii=False)


if __name__ == "__main__":
    if hasattr(mcp, "run"):
        mcp.run()


