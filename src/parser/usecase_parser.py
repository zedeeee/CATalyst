"""
UseCase Parser Module for CATalyst.
Extracts VBScript examples from CATIA CHM HTML dumps.
These examples are crucial for providing contextual snippets to the LLM.
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Any
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class UsecaseParser:
    def __init__(self):
        pass

    def extract_examples(self, file_path: Path) -> List[Dict[str, str]]:
        """
        Parses an HTML file and extracts inline VBScript examples.
        Returns a list of dictionaries containing the example context and code.
        """
        examples = []
        try:
            with open(file_path, "r", encoding="iso-8859-1", errors="replace") as f:
                html_content = f.read()
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return examples

        soup = BeautifulSoup(html_content, "lxml")
        
        # In CATIA docs, examples are usually under <dt><b>Example:</b></dt> 
        # followed by a <dd> which contains a <pre> block.
        # Alternatively, they might just be <pre> tags. We'll look for <pre> tags 
        # and try to infer their context.

        pre_tags = soup.find_all("pre")
        
        for pre in pre_tags:
            # Clean up the code by getting plain text (removes <font color="red">, etc.)
            code_snippet = pre.get_text().strip()
            if not code_snippet:
                continue
                
            # Try to find the associated method/property name.
            # Traverse upwards in the document order to find the closest <a name="...">
            context_name = "Unknown"
            prev_a = pre.find_previous("a", attrs={"name": True})
            if prev_a and prev_a.get("name"):
                context_name = prev_a["name"]
                
            examples.append({
                "context": context_name,
                "code": code_snippet,
                "source_file": file_path.name
            })

        return examples

if __name__ == "__main__":
    import argparse
    import json
    
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    parser = argparse.ArgumentParser(description="Extract VBScript usecases from an HTML file")
    parser.add_argument("file", type=str, help="Path to the .htm file to parse")
    args = parser.parse_args()
    
    uc_parser = UsecaseParser()
    res = uc_parser.extract_examples(Path(args.file))
    
    print(json.dumps(res, indent=2, ensure_ascii=False))
