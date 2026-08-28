"""
Database Engine Module for CATalyst.
Provides a clean Python API over the generated SQLite database for fast retrieval.
"""

import json
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class CatalystDB:
    def __init__(self, db_path: str | Path = "dist/catalyst.db"):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found at {self.db_path}. Please run build.py first.")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def get_interface(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieves an interface by name, including its fully resolved properties, methods, and usecases."""
        cursor = self.conn.cursor()
        
        # 1. Fetch Interface metadata
        cursor.execute("SELECT * FROM interfaces WHERE name = ? COLLATE NOCASE", (name,))
        i_row = cursor.fetchone()
        if not i_row:
            return None
            
        interface_data = {
            "name": i_row["name"],
            "framework": i_row["framework"],
            "description": i_row["description"],
            "inheritance_chain": json.loads(i_row["inheritance_chain"]) if i_row["inheritance_chain"] else [],
            "properties": [],
            "methods": [],
            "usecases": []
        }
        
        # 2. Fetch Properties
        cursor.execute("SELECT * FROM properties WHERE interface_name = ? COLLATE NOCASE ORDER BY name", (name,))
        for p in cursor.fetchall():
            interface_data["properties"].append({
                "name": p["name"],
                "type": p["type"],
                "readonly": bool(p["readonly"]),
                "declared_in": p["declared_in"]
            })
            
        # 3. Fetch Methods
        cursor.execute("SELECT * FROM methods WHERE interface_name = ? COLLATE NOCASE ORDER BY name", (name,))
        for m in cursor.fetchall():
            interface_data["methods"].append({
                "name": m["name"],
                "return_type": m["return_type"],
                "params": json.loads(m["params_json"]),
                "declared_in": m["declared_in"]
            })
            
        # 4. Fetch Usecases
        cursor.execute("SELECT * FROM usecases WHERE interface_name = ? COLLATE NOCASE", (name,))
        for uc in cursor.fetchall():
            interface_data["usecases"].append({
                "context": uc["context"],
                "code": uc["code"]
            })
            
        return interface_data

    def get_enum(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieves an enum by name."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM enums WHERE name = ? COLLATE NOCASE", (name,))
        row = cursor.fetchone()
        if not row:
            return None
            
        return {
            "name": row["name"],
            "description": row["description"],
            "values": json.loads(row["values_json"])
        }

    def search(self, query: str, item_type: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Fuzzy searches across interfaces, enums, properties, and methods.
        Supports filtering by item_type ('interface', 'enum', 'property', 'method', or None/'all').
        """
        cursor = self.conn.cursor()
        search_pattern = f"%{query}%"
        results = []
        
        filter_type = item_type.lower() if item_type else "all"

        # 1. Search Interfaces
        if filter_type in ("all", "interface"):
            cursor.execute("""
                SELECT 'interface' as type, name, description, framework, '' as parent_interface, '' as data_type, 0 as readonly
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
                    "readonly": False
                })

        # 2. Search Enums
        if filter_type in ("all", "enum") and (limit is None or len(results) < limit):
            rem = limit - len(results) if limit else 50
            cursor.execute("""
                SELECT 'enum' as type, name, description, '' as framework, '' as parent_interface, '' as data_type, 0 as readonly
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
                    "readonly": False
                })

        # 3. Search Properties
        if filter_type in ("all", "property") and (limit is None or len(results) < limit):
            rem = limit - len(results) if limit else 50
            cursor.execute("""
                SELECT 'property' as type, interface_name || '.' || name as name, '' as description, '' as framework,
                       interface_name as parent_interface, type as data_type, readonly
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
                    "readonly": bool(row["readonly"])
                })

        # 4. Search Methods
        if filter_type in ("all", "method") and (limit is None or len(results) < limit):
            rem = limit - len(results) if limit else 50
            cursor.execute("""
                SELECT 'method' as type, interface_name || '.' || name as name, '' as description, '' as framework,
                       interface_name as parent_interface, return_type as data_type, 0 as readonly
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
                    "readonly": False
                })

        return results[:limit] if limit else results

    def close(self):
        """Closes the underlying SQLite database connection."""
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()

