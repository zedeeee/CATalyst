"""
MCP Server for CATalyst.
Exposes CATIA V5 Automation API knowledge as tools to AI Assistants via the Model Context Protocol.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List
try:
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("CATalyst", description="CATIA V5 Automation API Knowledge Base")
except ImportError:
    try:
        from mcp.server.mcpserver import MCPServer
        mcp = MCPServer("CATalyst", description="CATIA V5 Automation API Knowledge Base")
    except ImportError:
        # Fallback if neither is directly named
        from mcp.server import Server
        mcp = Server("CATalyst")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "dist" / "catalyst.db"

try:
    db = CatalystDB(DB_PATH)
except Exception as e:
    logger.error(f"Failed to initialize CatalystDB: {e}")
    db = None


@mcp.tool()
def get_catia_interface(name: str) -> str:
    """
    Retrieve full documentation for a specific CATIA V5 COM Interface.
    Includes inherited properties, methods, and VBScript examples.
    Use this when you need exact signatures to write automation scripts.
    
    Args:
        name: The exact name of the interface (e.g., 'Pad', 'Prism', 'PartDocument', 'SystemConfiguration')
    """
    if not db:
        return "Error: Database not found. Please run the CATalyst build pipeline first."
        
    res = db.get_interface(name)
    if not res:
        return f"Error: Interface '{name}' not found in CATIA V5 documentation."
        
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def search_catia_api(query: str, item_type: str = "all", limit: int = 15) -> str:
    """
    Fuzzy search the CATIA V5 API across interfaces, enums, properties, and methods.
    Use this when you don't know the exact interface name or want to find properties/methods.
    
    Args:
        query: Search keywords (e.g., 'ServicePack', 'ActiveDocument', 'fillet', 'export')
        item_type: Filter by 'all', 'interface', 'enum', 'property', or 'method'
        limit: Max results to return
    """
    if not db:
        return "Error: Database not found."
        
    results = db.search(query, item_type=item_type, limit=limit)
    if not results:
        return f"No matches found for '{query}' (type={item_type})."
        
    return json.dumps(results, indent=2, ensure_ascii=False)


@mcp.tool()
def get_catia_enum(name: str) -> str:
    """
    Retrieve details and possible values for a CATIA V5 Enumeration.
    
    Args:
        name: The exact name of the enum (e.g., 'CatHoleType')
    """
    if not db:
        return "Error: Database not found."
        
    res = db.get_enum(name)
    if not res:
        return f"Error: Enum '{name}' not found."
        
    return json.dumps(res, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    if hasattr(mcp, "run"):
        mcp.run()

