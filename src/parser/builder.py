"""
Builder Module for CATalyst.
Orchestrates the ETL pipeline: HTML Parsing -> Inheritance Fusion -> Usecase Extraction -> SQLite/JSON Export.
"""

import os
import json
import sqlite3
import logging
from pathlib import Path
from tqdm import tqdm

from .html_parser import CatiaHtmlParser
from .inheritance import InheritanceTree
from .usecase_parser import UsecaseParser

logger = logging.getLogger(__name__)

class CatalystBuilder:
    def __init__(self, raw_dir: str | Path, dist_dir: str | Path):
        self.raw_dir = Path(raw_dir)
        self.dist_dir = Path(dist_dir)
        self.db_path = self.dist_dir / "catalyst.db"
        
        self.html_parser = CatiaHtmlParser()
        self.usecase_parser = UsecaseParser()
        
        jstree_path = self.raw_dir / "generated" / "interfaces" / "_index" / "jsTree.js"
        self.inheritance_tree = InheritanceTree(jstree_path)
        
        self._init_db()

    def _init_db(self):
        """Initializes the SQLite database schema."""
        self.dist_dir.mkdir(parents=True, exist_ok=True)
        
        if self.db_path.exists():
            self.db_path.unlink()
            
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()
        
        # Interfaces Table
        cursor.execute('''
            CREATE TABLE interfaces (
                name TEXT PRIMARY KEY,
                framework TEXT,
                description TEXT,
                inheritance_chain TEXT
            )
        ''')
        
        # Properties Table (Flattened with declared_in)
        cursor.execute('''
            CREATE TABLE properties (
                interface_name TEXT,
                name TEXT,
                type TEXT,
                readonly BOOLEAN,
                declared_in TEXT,
                FOREIGN KEY(interface_name) REFERENCES interfaces(name)
            )
        ''')
        
        # Methods Table (Flattened with declared_in)
        cursor.execute('''
            CREATE TABLE methods (
                interface_name TEXT,
                name TEXT,
                return_type TEXT,
                params_json TEXT,
                declared_in TEXT,
                FOREIGN KEY(interface_name) REFERENCES interfaces(name)
            )
        ''')
        
        # Enums Table
        cursor.execute('''
            CREATE TABLE enums (
                name TEXT PRIMARY KEY,
                description TEXT,
                values_json TEXT
            )
        ''')
        
        # Usecases Table
        cursor.execute('''
            CREATE TABLE usecases (
                interface_name TEXT,
                context TEXT,
                code TEXT,
                FOREIGN KEY(interface_name) REFERENCES interfaces(name)
            )
        ''')
        
        self.conn.commit()

    def build(self):
        """Executes the full ETL build process."""
        interfaces_dir = self.raw_dir / "generated" / "interfaces"
        if not interfaces_dir.exists():
            logger.error(f"Interfaces directory not found: {interfaces_dir}")
            return
            
        htm_files = list(interfaces_dir.rglob("*.htm"))
        if not htm_files:
            logger.warning("No HTML files found to process.")
            return

        # Pass 1: Parse all base HTML files into memory
        logger.info("Pass 1: Parsing HTML files...")
        raw_interfaces = {}
        
        cursor = self.conn.cursor()
        
        for file_path in tqdm(htm_files, desc="Parsing HTML"):
            # Ignore _index directory
            if "_index" in file_path.parts:
                continue
                
            if file_path.name.startswith("enum_"):
                enum_data = self.html_parser.parse_enum(file_path)
                if enum_data["name"]:
                    cursor.execute(
                        "INSERT OR REPLACE INTO enums (name, description, values_json) VALUES (?, ?, ?)",
                        (enum_data["name"], enum_data["description"], json.dumps(enum_data["values"], ensure_ascii=False))
                    )
            elif file_path.name.startswith("interface_"):
                interface_data = self.html_parser.parse_interface(file_path)
                usecases = self.usecase_parser.extract_examples(file_path)
                
                # Use filename stem as ID for inheritance resolution (e.g., interface_Pad_13505)
                class_id = file_path.stem
                
                if interface_data["name"]:
                    raw_interfaces[class_id] = {
                        "data": interface_data,
                        "usecases": usecases,
                        "id": class_id
                    }

        # Pass 2: Inheritance Fusion and DB Insertion
        logger.info("Pass 2: Inheritance Fusion and Database Construction...")
        
        # Create a lookup for interface ID -> actual Name
        id_to_name = {c_id: v["data"]["name"] for c_id, v in raw_interfaces.items()}
        
        for class_id, payload in tqdm(raw_interfaces.items(), desc="Fusing Inheritance"):
            i_data = payload["data"]
            i_name = i_data["name"]
            
            # Resolve Ancestors
            ancestors_ids = self.inheritance_tree.get_ancestors(class_id)
            
            # Build actual name chain: Self -> Parent -> Grandparent
            ancestor_names = []
            for anc_id in ancestors_ids:
                if anc_id in raw_interfaces:
                    ancestor_names.append(raw_interfaces[anc_id]["data"]["name"])
            
            chain_list = [i_name] + ancestor_names
            
            # Insert Base Interface
            cursor.execute(
                "INSERT OR REPLACE INTO interfaces (name, framework, description, inheritance_chain) VALUES (?, ?, ?, ?)",
                (i_name, i_data["framework"], i_data["description"], json.dumps(chain_list, ensure_ascii=False))
            )
            
            # Insert Usecases
            for uc in payload["usecases"]:
                cursor.execute(
                    "INSERT INTO usecases (interface_name, context, code) VALUES (?, ?, ?)",
                    (i_name, uc["context"], uc["code"])
                )
            
            # Collect all properties and methods (start with self)
            # Use dictionary to override parent methods with child methods if overridden
            fused_props = {p["name"]: {**p, "declared_in": i_name} for p in i_data["properties"]}
            fused_methods = {m["name"]: {**m, "declared_in": i_name} for m in i_data["methods"]}
            
            # Traverse ancestors (closest first)
            for anc_id in ancestors_ids:
                if anc_id in raw_interfaces:
                    anc_data = raw_interfaces[anc_id]["data"]
                    anc_name = anc_data["name"]
                    
                    for p in anc_data["properties"]:
                        if p["name"] not in fused_props:
                            fused_props[p["name"]] = {**p, "declared_in": anc_name}
                            
                    for m in anc_data["methods"]:
                        if m["name"] not in fused_methods:
                            fused_methods[m["name"]] = {**m, "declared_in": anc_name}
            
            # Insert Fused Properties
            for p_name, p_data in fused_props.items():
                cursor.execute(
                    "INSERT INTO properties (interface_name, name, type, readonly, declared_in) VALUES (?, ?, ?, ?, ?)",
                    (i_name, p_name, p_data["type"], p_data["readonly"], p_data["declared_in"])
                )
                
            # Insert Fused Methods
            for m_name, m_data in fused_methods.items():
                cursor.execute(
                    "INSERT INTO methods (interface_name, name, return_type, params_json, declared_in) VALUES (?, ?, ?, ?, ?)",
                    (i_name, m_name, m_data["return_type"], json.dumps(m_data["params"], ensure_ascii=False), m_data["declared_in"])
                )

        self.conn.commit()
        
        # Create Indices for performance
        cursor.execute("CREATE INDEX idx_props_interface ON properties(interface_name)")
        cursor.execute("CREATE INDEX idx_methods_interface ON methods(interface_name)")
        cursor.execute("CREATE INDEX idx_usecases_interface ON usecases(interface_name)")
        self.conn.commit()
        
        logger.info(f"Build complete. Database saved to {self.db_path}")

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    builder = CatalystBuilder(raw_dir="data/raw", dist_dir="dist")
    builder.build()
