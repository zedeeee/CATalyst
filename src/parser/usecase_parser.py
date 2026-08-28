"""
UseCase Parser Module for CATalyst.
Extracts VBScript examples from CATIA CHM HTML dumps.
These examples are crucial for providing contextual snippets to the LLM.
"""

import re
import hashlib
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
        Handles nested <pre> tag deduplication and context name normalization.
        """
        examples = []
        try:
            with open(file_path, "r", encoding="iso-8859-1", errors="replace") as f:
                html_content = f.read()
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return examples

        soup = BeautifulSoup(html_content, "lxml")
        
        # In CATIA docs, code examples often use nested <pre class="code"><pre>...</pre></pre>.
        # We only match top-level <pre> elements to avoid duplicate extracts.
        top_pre_tags = [p for p in soup.find_all("pre") if p.find_parent("pre") is None]
        seen_hashes = set()

        for pre in top_pre_tags:
            code_snippet = pre.get_text().strip()
            if not code_snippet:
                continue

            # Normalized hash to avoid exact duplicates within the same document
            normalized_code = "\n".join(l.rstrip() for l in code_snippet.splitlines() if l.strip())
            code_hash = hashlib.sha256(normalized_code.encode("utf-8")).hexdigest()
            if code_hash in seen_hashes:
                continue
            seen_hashes.add(code_hash)
                
            # Find the associated method/property name from preceding <a> anchor
            context_name = "Overview"
            prev_a = pre.find_previous("a", attrs={"name": True})
            if prev_a and prev_a.get("name"):
                raw_ctx = prev_a["name"].strip()
                if raw_ctx not in ("multiview", "Methods", "Properties", "Top", "HomeIdx"):
                    context_name = raw_ctx
                
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
