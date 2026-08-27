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

    def search(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Fuzzy searches across interfaces and enums by name or description.
        Returns a list of brief matches.
        """
        cursor = self.conn.cursor()
        search_pattern = f"%{query}%"
        
        results = []
        
        # Search Interfaces
        cursor.execute("""
            SELECT 'interface' as type, name, description 
            FROM interfaces 
            WHERE name LIKE ? OR description LIKE ?
            LIMIT ?
        """, (search_pattern, search_pattern, limit))
        
        for row in cursor.fetchall():
            results.append({
                "type": row["type"],
                "name": row["name"],
                "description": row["description"]
            })
            
        # Search Enums
        cursor.execute("""
            SELECT 'enum' as type, name, description 
            FROM enums 
            WHERE name LIKE ? OR description LIKE ?
            LIMIT ?
        """, (search_pattern, search_pattern, limit))
        
        for row in cursor.fetchall():
            results.append({
                "type": row["type"],
                "name": row["name"],
                "description": row["description"]
            })
            
        # Optional: Search Methods (Can be noisy, but useful for 'how do I add a line')
        if len(results) < limit:
            cursor.execute("""
                SELECT 'method' as type, interface_name || '.' || name as name, '' as description 
                FROM methods 
                WHERE name LIKE ?
                LIMIT ?
            """, (search_pattern, limit - len(results)))
            
            for row in cursor.fetchall():
                results.append({
                    "type": row["type"],
                    "name": row["name"],
                    "description": ""
                })
        
        return results

    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()
