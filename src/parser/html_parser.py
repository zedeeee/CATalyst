"""
HTML Parser Module for CATalyst.
Extracts structured API metadata (Interfaces, Methods, Properties, Enums) from CATIA CHM HTML dumps.
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Any
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class CatiaHtmlParser:
    def __init__(self):
        # Regex to extract father class from generatedFatherClass('id', 'name', 'type')
        self.father_class_pattern = re.compile(r"generatedFatherClass\(['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]")
        
        # Regex to extract properties and methods signatures
        self.property_pattern = re.compile(r"o\s+Property\s+([A-Za-z0-9_]+)")
        self.func_sub_pattern = re.compile(r"o\s+(Func|Sub)\s+([A-Za-z0-9_]+)")

    def parse_enum(self, file_path: Path) -> Dict[str, Any]:
        """Parses an enum_*.htm file into a structured dictionary."""
        with open(file_path, "r", encoding="iso-8859-1", errors="replace") as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, "lxml")
        enum_data = {
            "type": "enum",
            "name": "",
            "description": "",
            "values": []
        }

        # Extract Enum Name from <h1>
        h1 = soup.find("h1")
        if h1:
            # e.g., <h1>CatPrismOrientation <font size=-1>(Enumeration)</font></h1>
            enum_data["name"] = h1.text.replace("(Enumeration)", "").strip()

        # Extract Description
        for b_tag in soup.find_all("b"):
            if b_tag.find("i"):
                enum_data["description"] = b_tag.text.strip()
                break

        # Extract Enum Values
        # Typically located in <dt><tt>ValueName</tt><dd>Value Description ...
        dts = soup.find_all("dt")
        for dt in dts:
            tt_val = dt.find("tt")
            if tt_val:
                val_name = tt_val.text.strip()
                if not val_name:
                    continue
                
                # The description is usually in the next <dd> sibling
                dd = dt.find_next_sibling("dd")
                val_desc = dd.text.strip() if dd else ""
                
                enum_data["values"].append({
                    "name": val_name,
                    "description": val_desc
                })

        return enum_data

    def parse_interface(self, file_path: Path) -> Dict[str, Any]:
        """Parses an interface_*.htm file into a structured dictionary."""
        with open(file_path, "r", encoding="iso-8859-1", errors="replace") as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, "lxml")
        
        framework = file_path.parent.name
        
        interface_data = {
            "type": "interface",
            "name": "",
            "framework": framework,
            "inherits": "",  # Populated by builder.py using jsTree.js
            "description": "",
            "properties": [],
            "methods": []
        }

        # Extract Name from generatedFatherClass script block
        for script in soup.find_all("script"):
            if script.string:
                match = self.father_class_pattern.search(script.string)
                if match:
                    interface_data["name"] = match.group(2)
                    break

        if not interface_data["name"]:
            h1 = soup.find("h1")
            if h1:
                interface_data["name"] = h1.text.split("(")[0].strip()

        # Extract Description
        for b_tag in soup.find_all("b"):
            if b_tag.find("i"):
                interface_data["description"] = b_tag.text.strip()
                break

        # Extract Members (Properties and Methods)
        # We iterate over all <table> tags which represent a Property/Func/Sub signature
        tables = soup.find_all("table")
        for table in tables:
            tr = table.find("tr")
            if not tr:
                continue
            
            text_content = tr.text.strip()
            
            # Check for Property
            prop_match = self.property_pattern.search(text_content)
            if prop_match:
                prop_name = prop_match.group(1)
                is_readonly = "(Read Only)" in text_content
                
                # Extract Type (usually inside an activateLink script or raw text)
                prop_type = "Any"
                script_link = tr.find("script")
                if script_link and script_link.string and "activateLink" in script_link.string:
                    # activateLink('Type','Type')
                    t_match = re.search(r"activateLink\(['\"]([^'\"]+)['\"]", script_link.string)
                    if t_match:
                        prop_type = t_match.group(1)
                
                interface_data["properties"].append({
                    "name": prop_name,
                    "type": prop_type,
                    "readonly": is_readonly
                })
                continue

            # Check for Func or Sub
            func_match = self.func_sub_pattern.search(text_content)
            if func_match:
                func_type = func_match.group(1)  # Func or Sub
                func_name = func_match.group(2)
                
                return_type = "void" if func_type == "Sub" else "Any"
                if func_type == "Func":
                    script_links = tr.find_all("script")
                    if script_links and script_links[-1].string:
                        t_match = re.search(r"activateLink\(['\"]([^'\"]+)['\"]", script_links[-1].string)
                        if t_match:
                            return_type = t_match.group(1)

                # Extract Parameters (usually inside <td><tt>paramName</tt></td>)
                params = []
                tts = tr.find_all("tt")
                for tt in tts:
                    params.append({
                        "name": tt.text.strip(),
                        "type": "Any" # Complex to parse reliably from raw HTML table, refined via AST later
                    })

                interface_data["methods"].append({
                    "name": func_name,
                    "return_type": return_type,
                    "params": params
                })

        return interface_data

if __name__ == "__main__":
    import argparse
    import json
    
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    parser = argparse.ArgumentParser(description="Test HTML Parser on a specific file")
    parser.add_argument("file", type=str, help="Path to the .htm file to parse")
    args = parser.parse_args()
    
    html_parser = CatiaHtmlParser()
    target_path = Path(args.file)
    
    if target_path.name.startswith("enum_"):
        res = html_parser.parse_enum(target_path)
    else:
        res = html_parser.parse_interface(target_path)
        
    print(json.dumps(res, indent=2, ensure_ascii=False))
