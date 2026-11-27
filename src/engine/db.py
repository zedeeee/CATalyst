"""
Database Engine Module for CATalyst.
Provides a clean Python API over the generated SQLite database for fast retrieval.
"""

import os
import json
import fnmatch
import sqlite3
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Set

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
from .pitfalls import get_method_pitfall
from .text_utils import expand_camel_tokens, split_camel_case
from .object_graph import ObjectGraph
from .synonyms import expand_bilingual_queries
from .formatter import format_member_signature, sanitize_doc_text

_BASE_NOISE_INTERFACES: Set[str] = {
    "anyobject",
    "catbasedispatch",
    "catbaseunknown",
    "idispatch",
    "iunknown",
}
_PRIMITIVE_IDL_TYPES: Set[str] = {
    "",
    "void",
    "boolean",
    "long",
    "double",
    "short",
    "float",
    "catbstr",
    "catvariant",
    "catsafearrayvariant",
    "anyobject",
    "reference",
    "catbasedispatch",
}


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


def _format_fts_query(query_str: str, joiner: str = " AND ") -> str:
    """
    Sanitizes and formats a user search query into a valid SQLite FTS5 MATCH expression.
    Strips syntax control characters and uses prefix matching for each term.
    """
    import re
    cleaned = re.sub(r'["\'\*\^\:\(\)\{\}\[\]\+\-\~\?]', ' ', query_str)
    tokens = [t.strip() for t in cleaned.split() if t.strip()]
    if not tokens:
        return ""
    return joiner.join(f'"{t}"*' for t in tokens)


class CatalystDB:
    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.db_path = _resolve_db_path(db_path)
        self._local = threading.local()
        self._fts_checked = False
        self._comm_fts_lock = threading.Lock()
        self._comm_fts_conn: Optional[sqlite3.Connection] = None
        self._comm_fts_sig: Optional[tuple] = None
        self._graph_lock = threading.Lock()
        self._object_graph: Optional[ObjectGraph] = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Returns a thread-local SQLite connection to ensure 100% thread safety during concurrent FastMCP queries."""
        conn_instance = getattr(self._local, "conn", None)
        if conn_instance is None:
            conn_instance = sqlite3.connect(self.db_path, check_same_thread=False)
            conn_instance.row_factory = sqlite3.Row
            self._local.conn = conn_instance
            if not self._fts_checked:
                self._ensure_fts_indexes(conn_instance)
                self._fts_checked = True
        return conn_instance

    def _has_table(self, table_name: str) -> bool:
        """Checks if a specific table exists in the database."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        return cursor.fetchone() is not None

    def _has_column(self, table_name: str, column_name: str, conn: Optional[sqlite3.Connection] = None) -> bool:
        """Checks if a specific column exists on a SQLite table."""
        target_conn = conn or self.conn
        cursor = target_conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        return any(row[1] == column_name for row in cursor.fetchall())

    def _ensure_fts_indexes(self, conn: sqlite3.Connection):
        """
        Idempotently verifies and builds FTS5 virtual tables if missing or legacy.
        Allows legacy databases to automatically gain CamelCase + weighted BM25 search capabilities.
        """
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='usecases_fts'")
            has_usecases_fts = cursor.fetchone() is not None

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='apis_fts'")
            has_apis_fts = cursor.fetchone() is not None
            has_modern_apis_fts = has_apis_fts and self._has_column("apis_fts", "camel_tokens", conn)

            if not has_usecases_fts:
                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS usecases_fts USING fts5(
                        id UNINDEXED,
                        interface_name,
                        title,
                        workbench,
                        tags,
                        context,
                        code,
                        tokenize = 'unicode61'
                    )
                """)
                cursor.execute("""
                    INSERT INTO usecases_fts (id, interface_name, title, workbench, tags, context, code)
                    SELECT id, interface_name, title, workbench, tags, context, code FROM usecases
                """)

            if not has_modern_apis_fts:
                if has_apis_fts:
                    cursor.execute("DROP TABLE IF EXISTS apis_fts")
                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS apis_fts USING fts5(
                        item_type,
                        name,
                        camel_tokens,
                        description,
                        framework,
                        parent_interface,
                        declared_in,
                        data_type,
                        readonly UNINDEXED,
                        is_inherited UNINDEXED,
                        tokenize = 'unicode61'
                    )
                """)
                has_prop_desc = self._has_column("properties", "description", conn)
                has_meth_desc = self._has_column("methods", "description", conn)
                has_meth_ret = self._has_column("methods", "returns_desc", conn)

                fts_rows = []
                for name, desc, fw in cursor.execute(
                    "SELECT name, COALESCE(description, ''), COALESCE(framework, '') FROM interfaces"
                ).fetchall():
                    fts_rows.append(("interface", name, expand_camel_tokens(name), desc, fw, "", name, "", 0, 0))

                for name, desc in cursor.execute(
                    "SELECT name, COALESCE(description, '') FROM enums"
                ).fetchall():
                    fts_rows.append(("enum", name, expand_camel_tokens(name), desc, "", "", name, "", 0, 0))

                prop_desc_expr = "COALESCE(description, '')" if has_prop_desc else "''"
                for iface, name, ptype, ro, decl, desc in cursor.execute(
                    f"SELECT interface_name, name, COALESCE(type, ''), readonly, COALESCE(declared_in, ''), {prop_desc_expr} FROM properties"
                ).fetchall():
                    full_name = f"{iface}.{name}"
                    is_inh = 0 if (not decl or decl.lower() == iface.lower()) else 1
                    fts_rows.append(("property", full_name, expand_camel_tokens(name), desc, "", iface, decl, ptype, ro, is_inh))

                meth_desc_expr = "COALESCE(description, '')" if has_meth_desc else "''"
                meth_ret_expr = "COALESCE(returns_desc, '')" if has_meth_ret else "''"
                for iface, name, rtype, decl, desc, ret_desc in cursor.execute(
                    f"SELECT interface_name, name, COALESCE(return_type, ''), COALESCE(declared_in, ''), {meth_desc_expr}, {meth_ret_expr} FROM methods"
                ).fetchall():
                    full_name = f"{iface}.{name}"
                    full_desc = f"{desc} {ret_desc}".strip()
                    is_inh = 0 if (not decl or decl.lower() == iface.lower()) else 1
                    fts_rows.append(("method", full_name, expand_camel_tokens(name), full_desc, "", iface, decl, rtype, 0, is_inh))

                cursor.executemany(
                    "INSERT INTO apis_fts ("
                    "item_type, name, camel_tokens, description, framework, parent_interface, declared_in, data_type, readonly, is_inherited"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    fts_rows,
                )
            conn.commit()
        except Exception as e:
            logger.debug(f"FTS5 auto-initialization skipped or unsupported: {e}")

    def _load_community_recipes(self) -> List[Dict[str, Any]]:
        """
        Dynamically loads community recipes from data/recipes directory on disk.
        Allows hot-reloading community recipes without touching or rebuilding the official SQLite DB.
        """
        recipes_dir = PROJECT_ROOT / "data" / "recipes"
        if not recipes_dir.exists():
            return []

        recipes = []
        for json_file in sorted(recipes_dir.glob("*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            entry = {
                                "interface": item.get("interface_name", "General"),
                                "source": "community",
                                "title": item.get("title", ""),
                                "workbench": item.get("workbench", ""),
                                "tags": item.get("tags", ""),
                                "provenance": item.get("provenance", {"license": "MIT"}),
                                "context": item.get("description", ""),
                                "code": item.get("code", "")
                            }
                            recipes.append(entry)
            except Exception as e:
                logger.warning(f"Failed to load recipe file {json_file}: {e}")
        return recipes

    def get_interface(
        self,
        name: str,
        member_name: Optional[str] = None,
        include_usecases: bool = True,
        max_usecases: int = 3,
        detail: str = "full",
        include_base_members: bool = True,
        inline_enums: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves an interface by name with optional member filtering (supports exact,
        comma-separated, and '*'/'?' wildcards), base-member folding, and adaptive detail granularity.
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
        raw_member = (member_name or "").strip()
        member_patterns = [p.strip().lower() for p in raw_member.split(",") if p.strip()] if raw_member else []
        detail_norm = (detail or "full").strip().lower()
        if detail_norm == "auto":
            effective_detail = "full" if member_patterns else "compact"
        elif detail_norm in ("summary", "compact", "full"):
            effective_detail = detail_norm
        else:
            effective_detail = "full"

        def _matches_member(cand_name: str) -> bool:
            if not member_patterns:
                return True
            cand_low = cand_name.lower()
            for pat in member_patterns:
                if "*" in pat or "?" in pat:
                    if fnmatch.fnmatchcase(cand_low, pat):
                        return True
                elif cand_low == pat:
                    return True
            return False

        fold_base = (not include_base_members) and (not member_patterns) and (
            canonical_name.lower() not in _BASE_NOISE_INTERFACES
        )
        omitted_base_members: List[str] = []

        # Fetch total counts for transparency and preventing silent truncation misunderstanding
        cursor.execute("SELECT COUNT(*) as cnt FROM properties WHERE interface_name = ? COLLATE NOCASE", (canonical_name,))
        total_props = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM methods WHERE interface_name = ? COLLATE NOCASE", (canonical_name,))
        total_methods = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM usecases WHERE interface_name = ? COLLATE NOCASE", (canonical_name,))
        total_usecases = cursor.fetchone()["cnt"]

        iface_desc = i_row["description"] or ""
        if effective_detail != "full":
            iface_desc = sanitize_doc_text(iface_desc, max_chars=220)
        else:
            iface_desc = sanitize_doc_text(iface_desc)

        interface_data: Dict[str, Any] = {
            "name": canonical_name,
            "framework": i_row["framework"],
            "description": iface_desc,
            "inheritance_chain": json.loads(i_row["inheritance_chain"]) if i_row["inheritance_chain"] else [],
            "total_properties": total_props,
            "total_methods": total_methods,
            "total_usecases": total_usecases,
            "properties": [],
            "methods": [],
            "usecases": [],
        }

        # 2. Fetch & filter Properties
        raw_props: List[Dict[str, Any]] = []
        cursor.execute("SELECT * FROM properties WHERE interface_name = ? COLLATE NOCASE ORDER BY name", (canonical_name,))
        for p in cursor.fetchall():
            p_name = p["name"]
            if not _matches_member(p_name):
                continue
            decl = p["declared_in"] or canonical_name
            if fold_base and decl.lower() in _BASE_NOISE_INTERFACES:
                omitted_base_members.append(p_name)
                continue
            prop_entry: Dict[str, Any] = {
                "name": p_name,
                "type": p["type"],
                "readonly": bool(p["readonly"]),
                "declared_in": decl,
            }
            if "description" in p.keys() and p["description"]:
                prop_entry["description"] = sanitize_doc_text(p["description"])
            raw_props.append(prop_entry)

        # 3. Fetch & filter Methods
        raw_methods: List[Dict[str, Any]] = []
        cursor.execute("SELECT * FROM methods WHERE interface_name = ? COLLATE NOCASE ORDER BY name", (canonical_name,))
        for m in cursor.fetchall():
            m_name = m["name"]
            if not _matches_member(m_name):
                continue
            decl = m["declared_in"] or canonical_name
            if fold_base and decl.lower() in _BASE_NOISE_INTERFACES:
                omitted_base_members.append(m_name)
                continue
            params = json.loads(m["params_json"])
            for prm in params:
                if prm.get("description"):
                    prm["description"] = sanitize_doc_text(prm["description"])
            method_entry: Dict[str, Any] = {
                "name": m_name,
                "return_type": m["return_type"],
                "params": params,
                "declared_in": decl,
            }
            if "description" in m.keys() and m["description"]:
                method_entry["description"] = sanitize_doc_text(m["description"])
            if "returns_desc" in m.keys() and m["returns_desc"]:
                method_entry["returns_desc"] = sanitize_doc_text(m["returns_desc"])
            py_hints = _generate_python_method_hint(m_name, m["return_type"], params)
            if py_hints:
                method_entry["python_mapping"] = py_hints

            pitfall = get_method_pitfall(canonical_name, m_name)
            if pitfall:
                method_entry["pitfall_warning"] = pitfall

            raw_methods.append(method_entry)

        # Format properties/methods according to effective_detail
        total_displayed = len(raw_props) + len(raw_methods)
        include_short_desc = total_displayed <= 25

        if effective_detail == "summary":
            interface_data["properties"] = [{"name": p["name"], "type": p["type"]} for p in raw_props]
            interface_data["methods"] = [{"name": m["name"], "return_type": m["return_type"]} for m in raw_methods]
        elif effective_detail == "compact":
            for p in raw_props:
                cp: Dict[str, Any] = {
                    "name": p["name"],
                    "sig": format_member_signature(p, canonical_name, is_property=True),
                }
                if include_short_desc and p.get("description"):
                    cp["description"] = sanitize_doc_text(p["description"], max_chars=110)
                interface_data["properties"].append(cp)

            for m in raw_methods:
                cm: Dict[str, Any] = {
                    "name": m["name"],
                    "sig": format_member_signature(m, canonical_name, is_property=False),
                }
                if isinstance(m.get("python_mapping"), dict) and m["python_mapping"].get("pywin32_call"):
                    cm["py"] = m["python_mapping"]["pywin32_call"]
                if include_short_desc and m.get("description"):
                    cm["description"] = sanitize_doc_text(m["description"], max_chars=110)
                if m.get("pitfall_warning"):
                    cm["pitfall_warning"] = m["pitfall_warning"]
                interface_data["methods"].append(cm)
        else:
            interface_data["properties"] = raw_props
            interface_data["methods"] = raw_methods

        if omitted_base_members:
            interface_data["omitted_base_members"] = omitted_base_members

        # Optional inline Enum expansion to eliminate follow-up get_catia_enum round-trips
        if inline_enums and (raw_props or raw_methods):
            cand_types: List[str] = []
            seen_types: Set[str] = set()
            for p in raw_props:
                t = (p.get("type") or "").strip()
                if t.lower() not in _PRIMITIVE_IDL_TYPES and t.lower() not in seen_types:
                    seen_types.add(t.lower())
                    cand_types.append(t)
            for m in raw_methods:
                rt = (m.get("return_type") or "").strip()
                if rt.lower() not in _PRIMITIVE_IDL_TYPES and rt.lower() not in seen_types:
                    seen_types.add(rt.lower())
                    cand_types.append(rt)
                for prm in m.get("params") or []:
                    pt = (prm.get("type") or "").strip()
                    if pt.lower() not in _PRIMITIVE_IDL_TYPES and pt.lower() not in seen_types:
                        seen_types.add(pt.lower())
                        cand_types.append(pt)

            if cand_types:
                placeholders = ",".join("?" for _ in cand_types)
                cursor.execute(
                    f"SELECT name, values_json FROM enums WHERE name IN ({placeholders}) COLLATE NOCASE",
                    cand_types,
                )
                enum_rows = cursor.fetchall()
                max_inline = len(enum_rows) if member_patterns else 8
                referenced_enums: Dict[str, str] = {}
                for erow in enum_rows[:max_inline]:
                    vals = json.loads(erow["values_json"])
                    parts = []
                    for idx, item in enumerate(vals[:12]):
                        v_idx = item.get("value", idx)
                        parts.append(f"{v_idx}={item.get('name', '')}")
                    if len(vals) > 12:
                        parts.append(f"...(+{len(vals) - 12})")
                    referenced_enums[erow["name"]] = ", ".join(parts)
                if referenced_enums:
                    interface_data["referenced_enums"] = referenced_enums

        # 4. Fetch Usecases (if enabled)
        if include_usecases:
            if member_patterns:
                exact_pat = member_patterns[0]
                cursor.execute(
                    "SELECT context, code FROM usecases WHERE interface_name = ? COLLATE NOCASE AND context = ? COLLATE NOCASE",
                    (canonical_name, exact_pat)
                )
                matching_ucs = cursor.fetchall()
                if not matching_ucs:
                    clean_pat = exact_pat.replace("*", "").replace("?", "")
                    cursor.execute(
                        "SELECT context, code FROM usecases WHERE interface_name = ? COLLATE NOCASE AND (context LIKE ? OR code LIKE ?)",
                        (canonical_name, f"%{clean_pat}%", f"%{clean_pat}%")
                    )
                    matching_ucs = cursor.fetchall()
                for uc in matching_ucs[:max_usecases if max_usecases > 0 else 10]:
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
        if member_patterns and not raw_props and not raw_methods:
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
        source: str = "all",
        query: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieves targeted code usecases/recipes for an interface and optional member/query.
        Official examples from SQLite DB + Community recipes dynamically loaded from data/recipes/.
        """
        if not interface:
            return []
        target_if = interface.strip().lower()
        target_mbr = member.strip().lower() if member else None
        target_q = query.strip().lower() if query else None
        target_src = source.strip().lower() if source else "all"
        results: List[Dict[str, Any]] = []

        # 1. Fetch Official Usecases from SQLite DB
        if target_src in ("all", "official"):
            cursor = self.conn.cursor()
            cursor.execute("PRAGMA table_info(usecases)")
            columns = [r[1] for r in cursor.fetchall()]
            has_extended = "source" in columns

            where_clauses = ["interface_name = ? COLLATE NOCASE"]
            params: List[Any] = [interface.strip()]

            if has_extended:
                where_clauses.append("(source = 'official' OR source IS NULL)")

            if target_mbr:
                where_clauses.append("(context = ? COLLATE NOCASE OR context LIKE ? OR code LIKE ?)")
                params.extend([member.strip(), f"%{member.strip()}%", f"%{member.strip()}%"])

            if target_q:
                q_words = [w for w in query.strip().split() if w]
                for w in q_words:
                    if has_extended:
                        where_clauses.append("(title LIKE ? OR tags LIKE ? OR context LIKE ? OR code LIKE ?)")
                        params.extend([f"%{w}%", f"%{w}%", f"%{w}%", f"%{w}%"])
                    else:
                        where_clauses.append("(context LIKE ? OR code LIKE ?)")
                        params.extend([f"%{w}%", f"%{w}%"])

            where_sql = " AND ".join(where_clauses)
            query_sql = f"SELECT * FROM usecases WHERE {where_sql} ORDER BY rowid ASC LIMIT ?"
            params.append(limit)

            cursor.execute(query_sql, params)
            rows = cursor.fetchall()
            for r in rows:
                entry = {
                    "interface": r["interface_name"],
                    "source": "official",
                    "title": r["title"] if (has_extended and "title" in r.keys() and r["title"]) else f"{r['interface_name']} Official Example ({r['context']})",
                    "workbench": r["workbench"] if (has_extended and "workbench" in r.keys()) else "",
                    "tags": r["tags"] if (has_extended and "tags" in r.keys()) else "",
                    "provenance": {"source": "V5Automation.chm"},
                    "context": r["context"],
                    "code": r["code"]
                }
                results.append(entry)

        # 2. Fetch Community Recipes dynamically from data/recipes/
        if target_src in ("all", "community") and len(results) < limit:
            comm_recipes = self._load_community_recipes()
            for rc in comm_recipes:
                if rc["interface"].lower() != target_if:
                    continue
                if target_mbr and (target_mbr not in rc["context"].lower() and target_mbr not in rc["code"].lower() and target_mbr not in rc["title"].lower()):
                    continue
                if target_q:
                    q_words = [w for w in target_q.split() if w]
                    text_blob = f"{rc['title']} {rc['tags']} {rc['context']} {rc['code']}".lower()
                    if not all(w in text_blob for w in q_words):
                        continue
                results.append(rc)
                if len(results) >= limit:
                    break

        return results[:limit]

    def _get_community_fts(self) -> tuple[sqlite3.Connection, List[Dict[str, Any]]]:
        """Builds/caches an in-memory FTS5 index over data/recipes/*.json for BM25 ranking."""
        recipes_dir = PROJECT_ROOT / "data" / "recipes"
        files = sorted(recipes_dir.glob("*.json")) if recipes_dir.exists() else []
        sig = tuple((str(f), f.stat().st_mtime_ns) for f in files)

        with self._comm_fts_lock:
            if self._comm_fts_conn is not None and self._comm_fts_sig == sig:
                return self._comm_fts_conn, self._comm_recipes_cache  # type: ignore[attr-defined]

            if self._comm_fts_conn is not None:
                try:
                    self._comm_fts_conn.close()
                except Exception:
                    pass

            recipes = self._load_community_recipes()
            mem = sqlite3.connect(":memory:", check_same_thread=False)
            mem.row_factory = sqlite3.Row
            mem.execute("""
                CREATE VIRTUAL TABLE comm_fts USING fts5(
                    idx UNINDEXED,
                    title,
                    tags,
                    interface_name,
                    context,
                    workbench,
                    code,
                    tokenize = 'unicode61'
                )
            """)
            rows = []
            for idx, rc in enumerate(recipes):
                rows.append((
                    idx,
                    expand_camel_tokens(rc.get("title", "")),
                    expand_camel_tokens(rc.get("tags", "").replace(",", " ")),
                    expand_camel_tokens(rc.get("interface", "")),
                    expand_camel_tokens(rc.get("context", "")),
                    rc.get("workbench", ""),
                    rc.get("code", ""),
                ))
            mem.executemany(
                "INSERT INTO comm_fts (idx, title, tags, interface_name, context, workbench, code) VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            mem.commit()
            self._comm_fts_conn = mem
            self._comm_recipes_cache = recipes
            self._comm_fts_sig = sig
            return mem, recipes

    def _search_community_recipes(
        self,
        query: str,
        workbench: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """BM25 FTS5 search over hot-loaded community recipes with OR/CamelCase/substring fallback."""
        search_wb = workbench.strip().lower() if workbench else None
        mem, recipes = self._get_community_fts()
        if not recipes:
            return []

        def _run_fts(expr: str) -> List[Dict[str, Any]]:
            if not expr:
                return []
            with self._comm_fts_lock:
                cur = mem.cursor()
                cur.execute(
                    """
                    SELECT idx, bm25(comm_fts, 10.0, 8.0, 6.0, 4.0, 2.0, 1.0) AS rank
                    FROM comm_fts
                    WHERE comm_fts MATCH ?
                    ORDER BY rank ASC
                    """,
                    (expr,),
                )
                matched: List[Dict[str, Any]] = []
                for r in cur.fetchall():
                    rc = recipes[int(r["idx"])]
                    if search_wb and search_wb not in rc["workbench"].lower():
                        continue
                    matched.append(rc)
                    if len(matched) >= limit:
                        break
                return matched

        fts_and = _format_fts_query(query, joiner=" AND ")
        hits = _run_fts(fts_and)
        if not hits:
            camel_q = split_camel_case(query)
            if camel_q != query:
                hits = _run_fts(_format_fts_query(camel_q, joiner=" AND "))
        if not hits and " " in query.strip():
            fts_or = _format_fts_query(query, joiner=" OR ")
            if fts_or and fts_or != fts_and:
                hits = _run_fts(fts_or)
        if not hits:
            q_words = [w for w in query.strip().lower().split() if w]
            for rc in recipes:
                if search_wb and search_wb not in rc["workbench"].lower():
                    continue
                text_blob = f"{rc['interface']} {rc['title']} {rc['tags']} {rc['context']} {rc['code']}".lower()
                if all(w in text_blob for w in q_words):
                    hits.append(rc)
                    if len(hits) >= limit:
                        break
        return hits[:limit]

    def search_recipes(
        self,
        query: str,
        workbench: Optional[str] = None,
        source: str = "all",
        limit: int = 5,
        _allow_synonym: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Searches practical code recipes across all interfaces by intent keyword, tags, or workbench.
        Official examples from SQLite DB + Community recipes indexed via BM25 FTS5 with fair dual-track quota.
        """
        if not query:
            return []
        search_q = query.strip().lower()
        search_wb = workbench.strip().lower() if workbench else None
        target_src = source.strip().lower() if source else "all"

        official_results: List[Dict[str, Any]] = []
        community_results: List[Dict[str, Any]] = []

        # 1. Official Usecases Search from DB (FTS5 BM25 first, fallback to LIKE)
        if target_src in ("all", "official"):
            cursor = self.conn.cursor()
            cursor.execute("PRAGMA table_info(usecases)")
            columns = [r[1] for r in cursor.fetchall()]
            has_extended = "source" in columns

            def _exec_official_fts(fts_expr: str) -> List[sqlite3.Row]:
                if not fts_expr:
                    return []
                where_clauses = ["usecases_fts MATCH ?"]
                params: List[Any] = [fts_expr]
                if has_extended:
                    where_clauses.append("(source = 'official' OR source IS NULL)")
                if has_extended and search_wb:
                    where_clauses.append("workbench = ? COLLATE NOCASE")
                    params.append(workbench.strip())
                where_sql = " AND ".join(where_clauses)
                fts_sql = f"""
                    SELECT u.*, bm25(usecases_fts, 6.0, 10.0, 2.0, 8.0, 4.0, 1.0) as rank
                    FROM usecases_fts fts
                    JOIN usecases u ON fts.id = u.id
                    WHERE {where_sql}
                    ORDER BY rank ASC
                    LIMIT ?
                """
                params.append(limit)
                cursor.execute(fts_sql, params)
                return cursor.fetchall()

            used_fts = False
            if self._has_table("usecases_fts"):
                try:
                    fts_and = _format_fts_query(query, joiner=" AND ")
                    rows = _exec_official_fts(fts_and)
                    if not rows:
                        camel_q = split_camel_case(query)
                        if camel_q != query:
                            rows = _exec_official_fts(_format_fts_query(camel_q, joiner=" AND "))
                    if not rows and " " in query.strip():
                        fts_or = _format_fts_query(query, joiner=" OR ")
                        if fts_or and fts_or != fts_and:
                            rows = _exec_official_fts(fts_or)
                    if rows:
                        used_fts = True
                        for r in rows:
                            entry = {
                                "interface": r["interface_name"],
                                "source": "official",
                                "title": r["title"] if (has_extended and "title" in r.keys() and r["title"]) else f"{r['interface_name']} Official Example ({r['context']})",
                                "workbench": r["workbench"] if (has_extended and "workbench" in r.keys()) else "",
                                "tags": r["tags"] if (has_extended and "tags" in r.keys()) else "",
                                "provenance": {"source": "V5Automation.chm"},
                                "context": r["context"],
                                "code": r["code"]
                            }
                            official_results.append(entry)
                except Exception as e:
                    logger.debug(f"FTS5 recipe search fallback to LIKE: {e}")

            if not used_fts:
                where_clauses = []
                params = []

                if has_extended:
                    where_clauses.append("(source = 'official' OR source IS NULL)")

                if has_extended and search_wb:
                    where_clauses.append("workbench = ? COLLATE NOCASE")
                    params.append(workbench.strip())

                q_words = [w for w in search_q.split() if w]
                for w in q_words:
                    if has_extended:
                        where_clauses.append("(title LIKE ? OR tags LIKE ? OR context LIKE ? OR interface_name LIKE ? OR code LIKE ?)")
                        params.extend([f"%{w}%", f"%{w}%", f"%{w}%", f"%{w}%", f"%{w}%"])
                    else:
                        where_clauses.append("(interface_name LIKE ? OR context LIKE ? OR code LIKE ?)")
                        params.extend([f"%{w}%", f"%{w}%", f"%{w}%"])

                where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
                query_sql = f"SELECT * FROM usecases WHERE {where_sql} ORDER BY rowid ASC LIMIT ?"
                params.append(limit)

                cursor.execute(query_sql, params)
                rows = cursor.fetchall()
                for r in rows:
                    entry = {
                        "interface": r["interface_name"],
                        "source": "official",
                        "title": r["title"] if (has_extended and "title" in r.keys() and r["title"]) else f"{r['interface_name']} Official Example ({r['context']})",
                        "workbench": r["workbench"] if (has_extended and "workbench" in r.keys()) else "",
                        "tags": r["tags"] if (has_extended and "tags" in r.keys()) else "",
                        "provenance": {"source": "V5Automation.chm"},
                        "context": r["context"],
                        "code": r["code"]
                    }
                    official_results.append(entry)

        # 2. Community Recipes Search from data/recipes/ (no starvation when official fills limit)
        if target_src in ("all", "community"):
            community_results = self._search_community_recipes(query=query, workbench=workbench, limit=limit)

        if target_src == "official":
            return official_results[:limit]
        if target_src == "community":
            return community_results[:limit]

        comm_quota = max(2, (limit + 1) // 2)
        merged: List[Dict[str, Any]] = []
        merged.extend(community_results[:comm_quota])
        rem = limit - len(merged)
        if rem > 0:
            merged.extend(official_results[:rem])
        rem = limit - len(merged)
        if rem > 0 and len(community_results) > comm_quota:
            merged.extend(community_results[comm_quota:comm_quota + rem])

        if not merged and _allow_synonym:
            seen_keys = set()
            for alt_q in expand_bilingual_queries(query):
                for item in self.search_recipes(
                    alt_q, workbench=workbench, source=source, limit=limit, _allow_synonym=False
                ):
                    key = (item.get("source"), item.get("interface"), item.get("title"))
                    if key not in seen_keys:
                        seen_keys.add(key)
                        merged.append(item)
                        if len(merged) >= limit:
                            return merged[:limit]
        return merged[:limit]

    def get_navigation_path(
        self,
        target_interface: str,
        from_interface: str = "Application",
        max_hops: int = 8,
        compact: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Finds the shortest COM access chain from `from_interface` (default 'Application')
        to `target_interface` using the object model graph, enriching terminal method signatures.
        """
        with self._graph_lock:
            if self._object_graph is None:
                self._object_graph = ObjectGraph(self.conn)
            graph = self._object_graph
        nav = graph.find_navigation_path(from_interface, target_interface, max_hops=max_hops, compact=False)
        if not nav:
            return None

        steps = nav.get("steps") or []
        if steps and steps[-1]["kind"] == "method":
            last = steps[-1]
            cur = self.conn.cursor()
            cur.execute(
                "SELECT return_type, params_json FROM methods WHERE interface_name = ? COLLATE NOCASE AND name = ? COLLATE NOCASE",
                (last["from"], last["via"]),
            )
            mrow = cur.fetchone()
            if mrow:
                params = json.loads(mrow["params_json"]) if mrow["params_json"] else []
                p_str = ", ".join(f"{p.get('name', '')}: {p.get('type', 'Variant')}" for p in params)
                ret = mrow["return_type"] or "void"
                chain = nav.get("python_chain", "")
                placeholder = f"{last['via']}(...)"
                if chain.endswith(placeholder):
                    nav["python_chain"] = f"{chain[:-len(placeholder)]}{last['via']}({p_str}) -> {ret}"
            pitfall = get_method_pitfall(last["from"], last["via"])
            if pitfall:
                nav["terminal_pitfall"] = pitfall

        if compact:
            nav.pop("steps", None)
        return nav

    def get_search_syntax(
        self,
        workbench: Optional[str] = None,
        query_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieves Selection.Search query syntax grammar for CATIA workbenches and geometry types.
        Delegates directly to src.engine.search_grammar.get_search_grammar (single source of truth).
        """
        return get_search_grammar(workbench=workbench, query_type=query_type)

    def get_enum(
        self,
        name: Optional[str] = None,
        value: Optional[Union[int, str]] = None,
        member_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves an enum with bidirectional and reverse-lookup support.
        """
        cursor = self.conn.cursor()
        target_name = (name or "").strip()
        target_member = (member_name or "").strip()
        
        row = None
        if target_name:
            cursor.execute("SELECT * FROM enums WHERE name = ? COLLATE NOCASE", (target_name,))
            row = cursor.fetchone()
            
        member_to_search = target_member or (target_name if not row else "")
        if not row and member_to_search:
            search_pattern = f"%\"{member_to_search}\"%"
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

        values = json.loads(row["values_json"])
        for idx, item in enumerate(values):
            if "value" not in item:
                item["value"] = idx

        enum_data: Dict[str, Any] = {
            "name": row["name"],
            "description": row["description"] or "",
            "values": values
        }

        if value is not None or member_to_search:
            matched_item = None
            int_val = None
            str_val = None
            if value is not None:
                if isinstance(value, int):
                    int_val = value
                else:
                    try:
                        int_val = int(value.strip())
                    except ValueError:
                        str_val = value.strip().lower()

            for val_entry in values:
                if int_val is not None and val_entry.get("value") == int_val:
                    matched_item = val_entry
                    break
                elif str_val is not None and val_entry["name"].lower() == str_val:
                    matched_item = val_entry
                    break
                elif member_to_search and val_entry["name"].lower() == member_to_search.lower():
                    matched_item = val_entry
                    break

            if matched_item:
                enum_data["matched_value"] = matched_item

        return enum_data

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

    def search(self, query: str, item_type: Optional[str] = None, limit: int = 20, _allow_synonym: bool = True, detail: str = "full") -> List[Dict[str, Any]]:
        """
        Searches across interfaces, enums, properties, and methods.
        Prioritizes SQLite FTS5 BM25 full-text indexing, with automatic fallback to LIKE queries.
        Supports filtering by item_type ('interface', 'enum', 'property', 'method', or None/'all').
        """
        cursor = self.conn.cursor()
        search_pattern = f"%{query.strip()}%"
        results = []
        
        filter_type = item_type.lower() if item_type else "all"

        # Try FTS5 BM25 search first (weighted + CamelCase + anti-inheritance dilution)
        if self._has_table("apis_fts"):
            try:
                has_modern_fts = self._has_column("apis_fts", "camel_tokens")
                q_clean = query.strip()

                def _exec_api_fts(fts_expr: str) -> List[sqlite3.Row]:
                    if not fts_expr:
                        return []
                    where_clauses = ["apis_fts MATCH ?"]
                    params: List[Any] = [fts_expr]
                    if filter_type != "all":
                        where_clauses.append("item_type = ?")
                        params.append(filter_type)
                    where_sql = " AND ".join(where_clauses)
                    row_limit = limit if limit else 50
                    if has_modern_fts:
                        query_sql = f"""
                            SELECT item_type as type, name, description, framework, parent_interface,
                                   data_type, readonly, declared_in, is_inherited,
                                   (
                                       bm25(apis_fts, 1.0, 16.0, 12.0, 2.0, 1.0, 1.0, 1.0, 1.5)
                                       * CASE
                                           WHEN item_type = 'interface' THEN 2.0
                                           WHEN item_type = 'enum' THEN 1.8
                                           WHEN is_inherited = 0 THEN 1.5
                                           ELSE 0.25
                                         END
                                       - CASE
                                           WHEN LOWER(name) = LOWER(?) THEN 50.0
                                           WHEN LOWER(name) LIKE '%.' || LOWER(?) AND is_inherited = 0 THEN 25.0
                                           WHEN LOWER(camel_tokens) LIKE '% ' || LOWER(?) AND is_inherited = 0 THEN 12.0
                                           ELSE 0.0
                                         END
                                   ) AS rank
                            FROM apis_fts
                            WHERE {where_sql}
                            ORDER BY rank ASC
                            LIMIT ?
                        """
                        exec_params = [q_clean, q_clean, q_clean] + params + [row_limit]
                    else:
                        query_sql = f"""
                            SELECT item_type as type, name, description, framework, parent_interface,
                                   data_type, readonly, declared_in, bm25(apis_fts) AS rank
                            FROM apis_fts
                            WHERE {where_sql}
                            ORDER BY rank ASC
                            LIMIT ?
                        """
                        exec_params = params + [row_limit]
                    cursor.execute(query_sql, exec_params)
                    return cursor.fetchall()

                fts_and = _format_fts_query(q_clean, joiner=" AND ")
                rows = _exec_api_fts(fts_and)
                if not rows:
                    camel_q = split_camel_case(q_clean)
                    if camel_q != q_clean:
                        fts_camel = _format_fts_query(camel_q, joiner=" AND ")
                        if fts_camel and fts_camel != fts_and:
                            rows = _exec_api_fts(fts_camel)
                if not rows and " " in q_clean:
                    fts_or = _format_fts_query(q_clean, joiner=" OR ")
                    if fts_or and fts_or != fts_and:
                        rows = _exec_api_fts(fts_or)

                if rows:
                    is_compact = (detail or "full").strip().lower() == "compact"
                    for row in rows:
                        entry = {
                            "type": row["type"],
                            "name": row["name"],
                            "framework": row["framework"] or "",
                            "parent_interface": row["parent_interface"] or "",
                            "data_type": row["data_type"] or "",
                            "readonly": bool(row["readonly"]),
                            "declared_in": row["declared_in"]
                        }
                        if not is_compact:
                            entry["description"] = sanitize_doc_text(row["description"] or "", strip_example=True, max_chars=140)
                        results.append(entry)
                    return results
            except Exception as e:
                logger.debug(f"FTS5 API search fallback to LIKE: {e}")

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
                    "description": sanitize_doc_text(row["description"] or "", strip_example=True, max_chars=140),
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

        if not results and _allow_synonym:
            seen_names = set()
            target_limit = limit if limit else 20
            for alt_q in expand_bilingual_queries(query):
                for item in self.search(alt_q, item_type=item_type, limit=target_limit, _allow_synonym=False, detail=detail):
                    key = (item["type"], item["name"])
                    if key not in seen_names:
                        seen_names.add(key)
                        results.append(item)
                        if len(results) >= target_limit:
                            return results[:target_limit]

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
        if getattr(self, "_comm_fts_conn", None) is not None:
            try:
                self._comm_fts_conn.close()
            except Exception:
                pass
            self._comm_fts_conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()


