#!/usr/bin/env python
"""
Main Build Script for CATalyst.
Executes the full pipeline:
1. Unpack CHM (if raw/ is empty)
2. Parse HTML and fuse inheritance
3. Build SQLite/JSON Database
4. Run Post-Build Smoke Tests on DB Engine and MCP Server
"""

import sys
import json
import logging
from pathlib import Path
from src.parser.chm_unpacker import unpack_chm
from src.parser.builder import CatalystBuilder

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def run_smoke_test(db_path: Path):
    """
    Executes an automated smoke test suite against the generated SQLite database
    and MCP Server endpoints to prevent damaged builds from going live.
    """
    logger.info("\n--- Starting Post-Build Smoke Tests ---")
    
    from src.engine.db import CatalystDB
    import src.mcp.server as mcp_server
    
    # 1. Test Database Connectivity & Resolution
    db = CatalystDB(db_path)
    logger.info("  [1/6] Database connection & resolution verified.")

    # 2. Test get_interface & Inheritance Fusion
    pad_data = db.get_interface("Pad")
    assert pad_data is not None, "Smoke test failed: 'Pad' interface not found."
    assert "Prism" in pad_data.get("inheritance_chain", []), "Smoke test failed: 'Pad' inheritance chain missing 'Prism'."
    method_names = [m["name"] for m in pad_data.get("methods", [])]
    assert "GetDirection" in method_names, "Smoke test failed: Inherited method 'GetDirection' missing from 'Pad'."
    logger.info("  [2/6] Interface retrieval & inheritance fusion verified ('Pad').")

    # 3. Test Bidirectional Enum Retrieval
    enum_data = db.get_enum("CatProductSource")
    assert enum_data is not None, "Smoke test failed: 'CatProductSource' enum not found."
    assert any(v["name"] == "catProductMade" for v in enum_data["values"]), "Smoke test failed: 'catProductMade' missing in values."

    rev_val = db.get_enum(name="CatProductSource", value=1)
    assert rev_val is not None and rev_val.get("matched_value", {}).get("name") == "catProductMade", (
        f"Smoke test failed: Enum value lookup failed. Got: {rev_val}"
    )

    rev_member = db.get_enum(member_name="catProductMade")
    assert rev_member is not None and rev_member["name"] == "CatProductSource", (
        f"Smoke test failed: Enum member reverse lookup failed. Got: {rev_member}"
    )
    logger.info("  [3/6] Bidirectional enum query & reverse lookup verified ('CatProductSource').")

    # 4. Test Property/Method Reverse Interface Search
    prop_lookup = db.get_interfaces_by_member("PartNumber", member_type="property")
    assert prop_lookup["total_host_interfaces"] > 0, "Smoke test failed: Reverse search for 'PartNumber' returned 0 hosts."
    assert "Product" in prop_lookup["host_interfaces"], "Smoke test failed: 'Product' not found in host interfaces of 'PartNumber'."
    logger.info("  [4/6] Property/method reverse host interface lookup verified ('PartNumber' -> 'Product').")

    # 5. Test MCP Server Tool Endpoints & Alias Compatibility
    # 5.1 get_catia_interface with alias
    mcp_if_res = json.loads(mcp_server.get_catia_interface(interface_name="Pad"))
    assert not mcp_if_res.get("isError") and mcp_if_res.get("name") == "Pad", f"MCP interface query failed: {mcp_if_res}"

    # 5.2 get_catia_enum with alias and value
    mcp_enum_res = json.loads(mcp_server.get_catia_enum(enum_name="CatProductSource", value=1))
    assert not mcp_enum_res.get("isError") and mcp_enum_res.get("matched_value", {}).get("name") == "catProductMade", (
        f"MCP enum query failed: {mcp_enum_res}"
    )

    # 5.3 search_catia_api with alias
    mcp_search_res = json.loads(mcp_server.search_catia_api(keyword="PartNumber", item_type="property"))
    assert not mcp_search_res.get("isError") and mcp_search_res.get("total_matches", 0) > 0, (
        f"MCP search query failed: {mcp_search_res}"
    )
    logger.info("  [5/6] MCP tool endpoints and parameter aliases verified.")

    # 6. Test MCP Server Global Exception Safety
    err_res = json.loads(mcp_server.get_catia_interface(name="NonExistentInterface999"))
    assert err_res.get("isError") is True, "MCP error handling failed: Expected isError: True for missing interface."
    logger.info("  [6/6] MCP global exception safety & error responses verified.")

    logger.info("--- Smoke Tests Passed Successfully (6/6) ---\n")


def main():
    chm_file = Path("data/V5Automation.chm")
    raw_dir = Path("data/raw")
    dist_dir = Path("dist")

    # Step 1: Unpack if needed
    if not chm_file.exists():
        logger.error(f"Cannot find CHM file at {chm_file}. Please place your V5Automation.chm there.")
        sys.exit(1)
        
    has_html = False
    if raw_dir.exists():
        has_html = any(raw_dir.glob("**/*.htm"))
        
    if not has_html:
        logger.info("Raw HTML not found. Extracting from CHM...")
        success = unpack_chm(chm_file, raw_dir)
        if not success:
            logger.error("Failed to extract CHM. Aborting build.")
            sys.exit(1)
    else:
        logger.info("Found existing raw HTML extraction. Skipping unpack.")

    # Step 2 & 3: ETL & Build Database
    logger.info("Starting CATalyst Builder...")
    builder = CatalystBuilder(raw_dir=raw_dir, dist_dir=dist_dir)
    builder.build()
    
    # Step 4: Run Post-Build Smoke Tests
    db_path = dist_dir / "catalyst.db"
    try:
        run_smoke_test(db_path)
    except Exception as e:
        logger.error(f"Post-build smoke tests failed: {e}")
        sys.exit(1)

    logger.info("Build finished successfully.")


if __name__ == "__main__":
    main()

