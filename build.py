#!/usr/bin/env python
"""
Main Build Script for CATalyst.
Executes the full pipeline:
1. Unpack CHM (if raw/ is empty)
2. Parse HTML and fuse inheritance
3. Build SQLite/JSON Database
"""

import sys
import logging
from pathlib import Path
from src.parser.chm_unpacker import unpack_chm
from src.parser.builder import CatalystBuilder

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

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
    
    logger.info("Build finished successfully.")

if __name__ == "__main__":
    main()
