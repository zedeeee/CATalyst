"""
MCP Server for CATalyst.
Exposes CATIA V5 Automation API knowledge as tools to AI Assistants via the Model Context Protocol.
"""

import sys
import logging
from typing import Dict, List, Any
from mcp.server.fastmcp import FastMCP

from src.engine.db import CatalystDB

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("CATalyst", description="CATIA V5 Automation API Knowledge Base")

try:
    db = CatalystDB("dist/catalyst.db")
except Exception as e:
    logger.error(f"Failed to initialize CatalystDB: {e}")
    # Don't exit immediately, let the tools handle the error if the DB is missing
    db = None

@mcp.tool()
def get_catia_interface(name: str) -> str:
    """
    Retrieve full documentation for a specific CATIA V5 COM Interface.
    Includes inherited properties, methods, and VBScript examples.
    Use this when you need exact signatures to write automation scripts.
    
    Args:
        name: The exact name of the interface (e.g., 'Pad', 'Prism', 'PartDocument')
    """
    if not db:
        return "Error: Database not found. Please run the CATalyst build pipeline first."
        
    res = db.get_interface(name)
    if not res:
        return f"Error: Interface '{name}' not found in CATIA V5 documentation."
        
    # We return JSON string here as it is dense and AI easily parses it.
    import json
    return json.dumps(res, indent=2, ensure_ascii=False)

@mcp.tool()
def search_catia_api(query: str, limit: int = 10) -> str:
    """
    Fuzzy search the CATIA V5 API by keywords.
    Use this when you don't know the exact interface name or want to find related APIs.
    
    Args:
        query: Search keywords (e.g., 'fillet', 'export', 'measure')
        limit: Max results to return
    """
    if not db:
        return "Error: Database not found."
        
    results = db.search(query, limit)
    if not results:
        return f"No matches found for '{query}'."
        
    import json
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
        
    import json
    return json.dumps(res, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    mcp.run()
