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

    def get_interface(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieves an interface by name, including its fully resolved properties, methods, and usecases."""
        if not name:
            return None
        cursor = self.conn.cursor()
        
        # 1. Fetch Interface metadata
        cursor.execute("SELECT * FROM interfaces WHERE name = ? COLLATE NOCASE", (name.strip(),))
        i_row = cursor.fetchone()
        if not i_row:
            return None
            
        canonical_name = i_row["name"]
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
            interface_data["properties"].append({
                "name": p["name"],
                "type": p["type"],
                "readonly": bool(p["readonly"]),
                "declared_in": p["declared_in"]
            })
            
        # 3. Fetch Methods
        cursor.execute("SELECT * FROM methods WHERE interface_name = ? COLLATE NOCASE ORDER BY name", (canonical_name,))
        for m in cursor.fetchall():
            interface_data["methods"].append({
                "name": m["name"],
                "return_type": m["return_type"],
                "params": json.loads(m["params_json"]),
                "declared_in": m["declared_in"]
            })
            
        # 4. Fetch Usecases
        cursor.execute("SELECT * FROM usecases WHERE interface_name = ? COLLATE NOCASE", (canonical_name,))
        for uc in cursor.fetchall():
            interface_data["usecases"].append({
                "context": uc["context"],
                "code": uc["code"]
            })
            
        return interface_data

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


