"""
Database Engine Module for CATalyst.
Provides a clean Python API over the generated SQLite database for fast retrieval.
"""

import os
import json
import sqlite3
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_db_path(db_path: Optional[Union[str, Path]] = None) -> Path:
    """
    Resolves the SQLite database file path with multi-tier fallback detection:
    1. CATALYST_DB_PATH environment variable
    2. Explicit db_path passed to constructor
    3. PROJECT_ROOT / dist / catalyst.db
    4. CWD / dist / catalyst.db
    5. PROJECT_ROOT / catalyst.db
    6. CWD / catalyst.db
    """
    candidates: List[Path] = []

    env_path = os.environ.get("CATALYST_DB_PATH")
    if env_path:
        candidates.append(Path(env_path))

    if db_path is not None:
        candidates.append(Path(db_path))

    cwd = Path.cwd()
    candidates.extend([
        PROJECT_ROOT / "dist" / "catalyst.db",
        cwd / "dist" / "catalyst.db",
        PROJECT_ROOT / "catalyst.db",
        cwd / "catalyst.db",
    ])

    seen = set()
    unique_candidates: List[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        if resolved not in seen:
            seen.add(resolved)
            unique_candidates.append(candidate)

    for candidate in unique_candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()

    probed_str = "\n".join(f"  - {p.resolve() if hasattr(p, 'resolve') else p}" for p in unique_candidates)
    raise FileNotFoundError(
        f"CATalyst SQLite database not found. Probed paths:\n{probed_str}\n"
        "Please set CATALYST_DB_PATH or run `python build.py` to generate dist/catalyst.db."
    )


from .search_grammar import get_search_grammar


def _generate_python_method_hint(method_name: str, return_type: str, params: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """
    Generates pywin32 Python COM calling convention hints for CATIA methods,
    specifically highlighting tuple return unpacking for [out] parameters and safe arrays.
    """
    hints = {}
    out_params = []
    in_params = []
    has_safearray = False

    for p in params:
        p_name = p.get("name", "")
        p_type = p.get("type", "")
        if p_type == "CATSafeArrayVariant" or "SafeArray" in p_type:
            has_safearray = True

        # In CATIA COM IDL, parameters prefixed with 'o' or 'io' are typically out/inout reference values
        if (p_name.startswith("o") and len(p_name) > 1 and p_name[1].isupper()) or \
           (p_name.startswith("io") and len(p_name) > 2 and p_name[2].isupper()):
            out_params.append(p_name)
        else:
            in_params.append(p_name)

    if out_params:
        ret_clean = return_type.strip() if return_type and return_type != "void" else ""
        if ret_clean:
            lhs = f"{ret_clean.lower()}_status, " + ", ".join(out_params)
        elif len(out_params) == 1:
            lhs = out_params[0]
        else:
            lhs = f"({', '.join(out_params)})"

        in_args_str = ", ".join(in_params)
        hints["pywin32_call"] = f"{lhs} = obj.{method_name}({in_args_str})"
        hints["out_parameters"] = f"In Python (pywin32), out parameters ({', '.join(out_params)}) are returned as a tuple."

    if has_safearray:
        hints["safearray_note"] = "Parameters of type CATSafeArrayVariant must be passed as Python tuple/list (e.g. (x, y, z))."

    return hints if hints else None


class CatalystDB:
    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.db_path = _resolve_db_path(db_path)
        self._local = threading.local()

    @property
    def conn(self) -> sqlite3.Connection:
        """Returns a thread-local SQLite connection to ensure 100% thread safety during concurrent FastMCP queries."""
        conn_instance = getattr(self._local, "conn", None)
        if conn_instance is None:
            conn_instance = sqlite3.connect(self.db_path, check_same_thread=False)
            conn_instance.row_factory = sqlite3.Row
            self._local.conn = conn_instance
        return conn_instance

    def get_interface(
        self,
        name: str,
        member_name: Optional[str] = None,
        include_usecases: bool = True,
        max_usecases: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves an interface by name with optional member filtering and usecase granularity control.
        
        Args:
            name: Exact or case-insensitive interface name (e.g. 'Pad', 'VisPropertySet')
            member_name: Optional property or method name to filter by (e.g. 'SetShow', 'PartNumber')
            include_usecases: Whether to include VBScript code examples (default: True)
            max_usecases: Maximum usecases to return in overview mode (default: 3, 0 or negative for unlimited)
        """
        if not name:
            return None
        cursor = self.conn.cursor()
        
        # 1. Fetch Interface metadata
        cursor.execute("SELECT * FROM interfaces WHERE name = ? COLLATE NOCASE", (name.strip(),))
        i_row = cursor.fetchone()
        if not i_row:
            return None
            
        canonical_name = i_row["name"]
        filter_member = member_name.strip().lower() if member_name else None

        interface_data = {
            "name": canonical_name,
            "framework": i_row["framework"],
            "description": i_row["description"],
            "inheritance_chain": json.loads(i_row["inheritance_chain"]) if i_row["inheritance_chain"] else [],
            "properties": [],
            "methods": [],
            "usecases": []
        }
        
        # 2. Fetch Properties
        cursor.execute("SELECT * FROM properties WHERE interface_name = ? COLLATE NOCASE ORDER BY name", (canonical_name,))
        for p in cursor.fetchall():
            p_name = p["name"]
            if filter_member and p_name.lower() != filter_member:
                continue
            interface_data["properties"].append({
                "name": p_name,
                "type": p["type"],
                "readonly": bool(p["readonly"]),
                "declared_in": p["declared_in"]
            })
            
        # 3. Fetch Methods
        cursor.execute("SELECT * FROM methods WHERE interface_name = ? COLLATE NOCASE ORDER BY name", (canonical_name,))
        for m in cursor.fetchall():
            m_name = m["name"]
            if filter_member and m_name.lower() != filter_member:
                continue
            params = json.loads(m["params_json"])
            method_entry = {
                "name": m_name,
                "return_type": m["return_type"],
                "params": params,
                "declared_in": m["declared_in"]
            }
            py_hints = _generate_python_method_hint(m_name, m["return_type"], params)
            if py_hints:
                method_entry["python_mapping"] = py_hints

            interface_data["methods"].append(method_entry)
            
        # 4. Fetch Usecases (if enabled)
        if include_usecases:
            if filter_member:
                cursor.execute(
                    "SELECT context, code FROM usecases WHERE interface_name = ? COLLATE NOCASE AND context = ? COLLATE NOCASE",
                    (canonical_name, filter_member)
                )
                matching_ucs = cursor.fetchall()
                if not matching_ucs:
                    # Fallback to searching context or code text
                    cursor.execute(
                        "SELECT context, code FROM usecases WHERE interface_name = ? COLLATE NOCASE AND (context LIKE ? OR code LIKE ?)",
                        (canonical_name, f"%{filter_member}%", f"%{filter_member}%")
                    )
                    matching_ucs = cursor.fetchall()
                for uc in matching_ucs:
                    interface_data["usecases"].append({
                        "context": uc["context"],
                        "code": uc["code"]
                    })
            else:
                cursor.execute("SELECT context, code FROM usecases WHERE interface_name = ? COLLATE NOCASE", (canonical_name,))
                all_ucs = cursor.fetchall()
                if max_usecases > 0:
                    all_ucs = all_ucs[:max_usecases]
                for uc in all_ucs:
                    interface_data["usecases"].append({
                        "context": uc["context"],
                        "code": uc["code"]
                    })

        # If member_name was specified and neither properties nor methods matched
        if filter_member and not interface_data["properties"] and not interface_data["methods"]:
            return {
                "name": canonical_name,
                "member_not_found": member_name,
                "message": f"Member '{member_name}' not found in interface '{canonical_name}'."
            }
            
        return interface_data

    def get_usecases(
        self,
        interface: str,
        member: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieves targeted code usecases for an interface and optional member.
        """
        if not interface:
            return []
        cursor = self.conn.cursor()
        target_if = interface.strip()
        target_mbr = member.strip() if member else None

        if target_mbr:
            cursor.execute(
                "SELECT interface_name, context, code FROM usecases WHERE interface_name = ? COLLATE NOCASE AND context = ? COLLATE NOCASE LIMIT ?",
                (target_if, target_mbr, limit)
            )
            rows = cursor.fetchall()
            if not rows:
                cursor.execute(
                    "SELECT interface_name, context, code FROM usecases WHERE interface_name = ? COLLATE NOCASE AND (context LIKE ? OR code LIKE ?) LIMIT ?",
                    (target_if, f"%{target_mbr}%", f"%{target_mbr}%", limit)
                )
                rows = cursor.fetchall()
        else:
            cursor.execute(
                "SELECT interface_name, context, code FROM usecases WHERE interface_name = ? COLLATE NOCASE LIMIT ?",
                (target_if, limit)
            )
            rows = cursor.fetchall()

        return [{"interface": r["interface_name"], "context": r["context"], "code": r["code"]} for r in rows]

    def get_search_syntax(
        self,
        workbench: Optional[str] = None,
        query_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieves Selection.Search query syntax grammar for CATIA workbenches and geometry types.
        """
        return get_search_grammar(workbench=workbench, query_type=query_type)

    def get_enum(
        self,
        name: Optional[str] = None,
        value: Optional[Union[int, str]] = None,
        member_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves an enum with bidirectional and reverse-lookup support:
        - By Enum name (e.g., 'CatProductSource')
        - By Enum name + numeric index/value (e.g., name='CatProductSource', value=1 -> matches 'catProductMade')
        - By Member name (e.g., member_name='catProductMade' or name='catProductMade' -> returns parent enum + matched member)
        """
        cursor = self.conn.cursor()
        
        target_name = (name or "").strip()
        target_member = (member_name or "").strip()
        
        # Case 1: Direct Enum name lookup
        row = None
        if target_name:
            cursor.execute("SELECT * FROM enums WHERE name = ? COLLATE NOCASE", (target_name,))
            row = cursor.fetchone()
            
        # Case 2: If not found by enum name, check if target_name or target_member is an enum member name
        member_to_search = target_member or (target_name if not row else "")
        if not row and member_to_search:
            search_pattern = f'%"{member_to_search}"%'
            cursor.execute("SELECT * FROM enums WHERE values_json LIKE ? COLLATE NOCASE", (search_pattern,))
            candidates = cursor.fetchall()
            for cand in candidates:
                cand_vals = json.loads(cand["values_json"])
                for idx, v in enumerate(cand_vals):
                    if v.get("name", "").lower() == member_to_search.lower():
                        row = cand
                        if value is None:
                            value = idx
                        break
                if row:
                    break

        if not row:
            return None
            
        raw_values = json.loads(row["values_json"])
        enriched_values = []
        matched_item = None
        
        # Normalize search value if provided
        int_val = None
        str_val = None
        if value is not None:
            if isinstance(value, int):
                int_val = value
            elif isinstance(value, str):
                if value.strip().isdigit() or (value.strip().startswith("-") and value.strip()[1:].isdigit()):
                    int_val = int(value.strip())
                else:
                    str_val = value.strip().lower()

        for idx, item in enumerate(raw_values):
            item_val = item.get("value", idx)
            val_entry = {
                "name": item.get("name", ""),
                "value": item_val,
                "description": item.get("description", "")
            }
            enriched_values.append(val_entry)
            
            # Check match by index/value
            if int_val is not None and item_val == int_val:
                matched_item = val_entry
            elif str_val is not None and val_entry["name"].lower() == str_val:
                matched_item = val_entry
            elif member_to_search and val_entry["name"].lower() == member_to_search.lower():
                matched_item = val_entry

        result = {
            "name": row["name"],
            "description": row["description"],
            "values": enriched_values
        }
        if matched_item is not None:
            result["matched_value"] = matched_item

        return result

    def get_interfaces_by_member(
        self,
        member_name: str,
        member_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Reverse searches which interfaces contain or declare a specific property or method.
        Example: get_interfaces_by_member('PartNumber') returns host interfaces such as Product, StrMember, etc.
        """
        cursor = self.conn.cursor()
        query_member = member_name.strip()
        filter_type = (member_type or "all").lower()

        properties = []
        methods = []
        host_interfaces = set()

        if filter_type in ("all", "property"):
            cursor.execute(
                "SELECT interface_name, name, type, readonly, declared_in FROM properties WHERE name = ? COLLATE NOCASE",
                (query_member,)
            )
            for row in cursor.fetchall():
                host_interfaces.add(row["interface_name"])
                properties.append({
                    "interface": row["interface_name"],
                    "property": row["name"],
                    "data_type": row["type"],
                    "readonly": bool(row["readonly"]),
                    "declared_in": row["declared_in"]
                })

        if filter_type in ("all", "method"):
            cursor.execute(
                "SELECT interface_name, name, return_type, params_json, declared_in FROM methods WHERE name = ? COLLATE NOCASE",
                (query_member,)
            )
            for row in cursor.fetchall():
                host_interfaces.add(row["interface_name"])
                methods.append({
                    "interface": row["interface_name"],
                    "method": row["name"],
                    "return_type": row["return_type"],
                    "params": json.loads(row["params_json"]),
                    "declared_in": row["declared_in"]
                })

        return {
            "member_name": query_member,
            "total_host_interfaces": len(host_interfaces),
            "host_interfaces": sorted(list(host_interfaces)),
            "properties": properties,
            "methods": methods
        }

    def search(self, query: str, item_type: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Fuzzy searches across interfaces, enums, properties, and methods.
        Supports filtering by item_type ('interface', 'enum', 'property', 'method', or None/'all').
        """
        cursor = self.conn.cursor()
        search_pattern = f"%{query.strip()}%"
        results = []
        
        filter_type = item_type.lower() if item_type else "all"

        # 1. Search Interfaces
        if filter_type in ("all", "interface"):
            cursor.execute("""
                SELECT 'interface' as type, name, description, framework, '' as parent_interface, '' as data_type, 0 as readonly, name as declared_in
                FROM interfaces 
                WHERE name LIKE ? OR description LIKE ?
                LIMIT ?
            """, (search_pattern, search_pattern, limit))
            for row in cursor.fetchall():
                results.append({
                    "type": row["type"],
                    "name": row["name"],
                    "description": row["description"] or "",
                    "framework": row["framework"],
                    "parent_interface": "",
                    "data_type": "",
                    "readonly": False,
                    "declared_in": row["declared_in"]
                })

        # 2. Search Enums
        if filter_type in ("all", "enum") and (limit is None or len(results) < limit):
            rem = limit - len(results) if limit else 50
            cursor.execute("""
                SELECT 'enum' as type, name, description, '' as framework, '' as parent_interface, '' as data_type, 0 as readonly, name as declared_in
                FROM enums 
                WHERE name LIKE ? OR description LIKE ? OR values_json LIKE ?
                LIMIT ?
            """, (search_pattern, search_pattern, search_pattern, rem))
            for row in cursor.fetchall():
                results.append({
                    "type": row["type"],
                    "name": row["name"],
                    "description": row["description"] or "",
                    "framework": "",
                    "parent_interface": "",
                    "data_type": "",
                    "readonly": False,
                    "declared_in": row["declared_in"]
                })

        # 3. Search Properties
        if filter_type in ("all", "property") and (limit is None or len(results) < limit):
            rem = limit - len(results) if limit else 50
            cursor.execute("""
                SELECT 'property' as type, interface_name || '.' || name as name, '' as description, '' as framework,
                       interface_name as parent_interface, type as data_type, readonly, declared_in
                FROM properties
                WHERE name LIKE ?
                LIMIT ?
            """, (search_pattern, rem))
            for row in cursor.fetchall():
                results.append({
                    "type": row["type"],
                    "name": row["name"],
                    "description": "",
                    "framework": "",
                    "parent_interface": row["parent_interface"],
                    "data_type": row["data_type"],
                    "readonly": bool(row["readonly"]),
                    "declared_in": row["declared_in"]
                })

        # 4. Search Methods
        if filter_type in ("all", "method") and (limit is None or len(results) < limit):
            rem = limit - len(results) if limit else 50
            cursor.execute("""
                SELECT 'method' as type, interface_name || '.' || name as name, '' as description, '' as framework,
                       interface_name as parent_interface, return_type as data_type, 0 as readonly, declared_in
                FROM methods
                WHERE name LIKE ?
                LIMIT ?
            """, (search_pattern, rem))
            for row in cursor.fetchall():
                results.append({
                    "type": row["type"],
                    "name": row["name"],
                    "description": "",
                    "framework": "",
                    "parent_interface": row["parent_interface"],
                    "data_type": row["data_type"],
                    "readonly": False,
                    "declared_in": row["declared_in"]
                })

        return results[:limit] if limit else results

    def close(self):
        """Closes the current thread's SQLite database connection."""
        conn_instance = getattr(self._local, "conn", None)
        if conn_instance is not None:
            try:
                conn_instance.close()
            except Exception:
                pass
            self._local.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()


