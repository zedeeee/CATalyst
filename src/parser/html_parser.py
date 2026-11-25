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

_WS_RE = re.compile(r"\s+")


def _clean_text(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").replace("\xa0", " ")).strip()


def _extract_text_before_nested_blocks(node: Any) -> str:
    """Collect text from node children before any nested <dl> or <pre> block."""
    if node is None:
        return ""
    parts: List[str] = []
    for child in node.children:
        tag = getattr(child, "name", None)
        if tag in ("dl", "pre", "table", "h2", "hr"):
            break
        if tag == "br":
            parts.append(" ")
        elif tag is None:
            parts.append(str(child))
        else:
            # Strip trailing nested dl/pre inside wrapped inline nodes if any
            if hasattr(child, "find") and child.find(("dl", "pre")):
                parts.append(_extract_text_before_nested_blocks(child))
            else:
                parts.append(child.get_text(" ", strip=False))
    return _clean_text("".join(parts))


def _extract_member_doc(table_tag: Any) -> Dict[str, Any]:
    """Extract sibling <dl><dd> description, parameter docs, and Returns notes for a member."""
    doc: Dict[str, Any] = {"description": "", "returns_desc": "", "param_docs": {}}
    anchor = table_tag.find_parent("dt") or table_tag

    target_dl = None
    for sib in anchor.find_next_siblings():
        tag = getattr(sib, "name", None)
        if not tag:
            continue
        if tag in ("table", "h2", "hr", "dt") or (tag == "a" and sib.get("name")):
            break
        if tag == "dl":
            target_dl = sib
            break

    if target_dl is None:
        return doc

    first_dd = target_dl.find("dd")
    if first_dd:
        doc["description"] = _extract_text_before_nested_blocks(first_dd)

    for dt in target_dl.find_all("dt"):
        dt_label = _clean_text(dt.get_text(" ", strip=True)).lower()
        if "parameters:" in dt_label:
            param_dd = dt.find_next_sibling("dd")
            if not param_dd:
                continue
            param_dl = param_dd.find("dl")
            search_root = param_dl if param_dl else param_dd
            for p_dt in search_root.find_all("dt", recursive=(param_dl is not None)):
                tt = p_dt.find("tt")
                if not tt:
                    continue
                p_name = tt.get_text(strip=True)
                p_dd = p_dt.find_next_sibling("dd")
                p_desc = _extract_text_before_nested_blocks(p_dd)
                if p_name and p_desc:
                    doc["param_docs"][p_name] = p_desc
        elif "returns:" in dt_label:
            ret_dd = dt.find_next_sibling("dd")
            ret_text = _extract_text_before_nested_blocks(ret_dd)
            if ret_text:
                doc["returns_desc"] = ret_text

    return doc


def _extract_return_type_from_table(table_tag: Any, default_type: str = "Any") -> str:
    """
    Extract return/property type located strictly after ') As ' across the entire signature table.
    Avoids misreading the first parameter's type on multi-row parameter tables.
    """
    table_html = str(table_tag)
    m = re.search(r"\)\s*As\s*(.+?)(?:</td>|</tr>|</table>)", table_html, re.S | re.I)
    if m:
        tail = m.group(1)
        am = re.search(r"activateLink\(['\"]([^'\"]+)['\"]", tail)
        if am:
            return am.group(1).strip()
        plain = re.sub(r"<[^>]+>", " ", tail)
        plain = re.sub(r"\(Read Only\)", "", plain, flags=re.I)
        plain = _clean_text(plain)
        if plain:
            return plain

    # Fallback for simplified single-row templates without ') As'
    tr = table_tag.find("tr")
    if tr:
        scripts = tr.find_all("script")
        if scripts and scripts[-1].string and "activateLink" in scripts[-1].string:
            am = re.search(r"activateLink\(['\"]([^'\"]+)['\"]", scripts[-1].string)
            if am:
                return am.group(1).strip()
    return default_type


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

        # Extract Description (summary in <b><i>...</i></b> plus Role/details up to <hr>)
        for b_tag in soup.find_all("b"):
            if b_tag.find("i"):
                intro_parts = [_clean_text(b_tag.get_text(" ", strip=True))]
                for sib in b_tag.next_siblings:
                    tag = getattr(sib, "name", None)
                    if tag in ("hr", "dl", "h2", "table"):
                        break
                    if tag is None:
                        t = _clean_text(str(sib))
                        if t:
                            intro_parts.append(t)
                    elif tag not in ("script", "br"):
                        t = _clean_text(sib.get_text(" ", strip=True))
                        if t:
                            intro_parts.append(t)
                interface_data["description"] = _clean_text(" ".join(intro_parts))
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
                is_readonly = "(Read Only)" in table.text
                prop_type = _extract_return_type_from_table(table, default_type="Any")

                member_doc = _extract_member_doc(table)
                interface_data["properties"].append({
                    "name": prop_name,
                    "type": prop_type,
                    "readonly": is_readonly,
                    "description": member_doc["description"],
                })
                continue

            # Check for Func or Sub
            func_match = self.func_sub_pattern.search(text_content)
            if func_match:
                func_type = func_match.group(1)  # Func or Sub
                func_name = func_match.group(2)
                
                return_type = "void" if func_type == "Sub" else _extract_return_type_from_table(table, default_type="Any")

                member_doc = _extract_member_doc(table)

                # Extract Parameters (iterate over all <tt> tags within the method's table)
                params = []
                tts = table.find_all("tt")
                for tt in tts:
                    p_name = tt.text.strip()
                    p_type = "Any"
                    
                    # The <script> containing the type is usually in the preceding <td>
                    td = tt.find_parent("td")
                    if td:
                        prev_td = td.find_previous_sibling("td")
                        if prev_td:
                            script_tag = prev_td.find("script")
                            if script_tag and script_tag.string:
                                t_match = re.search(r"activateLink\(['\"]([^'\"]+)['\"]", script_tag.string)
                                if t_match:
                                    p_type = t_match.group(1)
                                    
                    p_entry: Dict[str, Any] = {
                        "name": p_name,
                        "type": p_type,
                    }
                    if p_name in member_doc["param_docs"]:
                        p_entry["description"] = member_doc["param_docs"][p_name]
                    params.append(p_entry)

                interface_data["methods"].append({
                    "name": func_name,
                    "return_type": return_type,
                    "params": params,
                    "description": member_doc["description"],
                    "returns_desc": member_doc["returns_desc"],
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
