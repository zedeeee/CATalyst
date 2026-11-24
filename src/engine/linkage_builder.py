"""
Doc & Sample Code Linkage Builder for CATalyst.
Extracts method and property invocation linkages from official samples and documentation pages,
building a fast reverse-index table `doc_api_links` inside `catalyst_docs.db`.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Common COM variable prefixes in Dassault sample scripts
_PREFIX_STRIP_RE = re.compile(r"^(?:o|my|the|curr|current|new|sub|target|active)", re.IGNORECASE)
_DIM_VAR_RE = re.compile(r"\bDim\s+([A-Za-z0-9_]+)\s+As\s+([A-Za-z0-9_]+)\b", re.IGNORECASE)
_METHOD_CALL_RE = re.compile(r"\b([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\b")


class LinkageBuilder:
    """Builds reverse index mapping Interface.Member -> official docs and sample code."""

    def __init__(
        self,
        core_db_path: Optional[Path | str] = None,
        docs_db_path: Optional[Path | str] = None,
    ) -> None:
        self.core_db_path = Path(core_db_path) if core_db_path else (PROJECT_ROOT / "dist" / "catalyst.db")
        self.docs_db_path = Path(docs_db_path) if docs_db_path else (PROJECT_ROOT / "dist" / "local" / "catalyst_docs.db")

    def _load_core_catalogue(self, core_conn: sqlite3.Connection) -> Tuple[
        Dict[str, str],                           # iface_lower -> canonical
        Dict[str, Set[str]],                      # member_lower -> set of canonical ifaces
        Dict[Tuple[str, str], str],               # (iface_lower, member_lower) -> canonical member
    ]:
        cur = core_conn.cursor()
        interfaces: Dict[str, str] = {}
        for (name,) in cur.execute("SELECT name FROM interfaces"):
            interfaces[name.lower()] = name

        member_to_ifaces: Dict[str, Set[str]] = {}
        canonical_members: Dict[Tuple[str, str], str] = {}

        for iface, m_name in cur.execute("SELECT interface_name, name FROM methods"):
            canon_iface = interfaces.get(iface.lower(), iface)
            member_to_ifaces.setdefault(m_name.lower(), set()).add(canon_iface)
            canonical_members[(iface.lower(), m_name.lower())] = m_name

        for iface, p_name in cur.execute("SELECT interface_name, name FROM properties"):
            canon_iface = interfaces.get(iface.lower(), iface)
            member_to_ifaces.setdefault(p_name.lower(), set()).add(canon_iface)
            canonical_members[(iface.lower(), p_name.lower())] = p_name

        return interfaces, member_to_ifaces, canonical_members

    def build_linkages(self) -> Dict[str, Any]:
        """
        Builds doc_api_links table inside docs_db and returns metrics.
        """
        start_time = time.time()
        if not self.core_db_path.exists():
            raise FileNotFoundError(f"Core DB not found at {self.core_db_path}")
        if not self.docs_db_path.exists():
            raise FileNotFoundError(f"Docs DB not found at {self.docs_db_path}")

        core_conn = sqlite3.connect(str(self.core_db_path))
        interfaces, member_to_ifaces, canonical_members = self._load_core_catalogue(core_conn)
        core_conn.close()

        docs_conn = sqlite3.connect(str(self.docs_db_path))
        cur = docs_conn.cursor()

        # Initialize schema
        cur.executescript("""
            DROP TABLE IF EXISTS doc_api_links;
            CREATE TABLE doc_api_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                interface_name TEXT NOT NULL,
                member_name TEXT NOT NULL,
                target_type TEXT NOT NULL,
                ref_id TEXT NOT NULL,
                rel_path TEXT NOT NULL,
                title TEXT,
                line_no INTEGER DEFAULT 0,
                code_snippet TEXT NOT NULL,
                official_note TEXT
            );
            CREATE INDEX idx_api_links_lookup ON doc_api_links(interface_name, member_name);
            CREATE INDEX idx_api_links_ref ON doc_api_links(ref_id);
        """)

        links_to_insert: List[Tuple[str, str, str, str, str, str, int, str, Optional[str]]] = []
        seen_links: Set[Tuple[str, str, str, str, int]] = set()

        # 1. Scan doc_samples (text-based scripts: CATScript, catvbs, bas, etc.)
        cur.execute(
            "SELECT sample_id, rel_path, filename, content FROM doc_samples "
            "WHERE is_binary = 0 AND content IS NOT NULL AND length(content) > 0"
        )
        sample_rows = cur.fetchall()

        for sample_id, rel_path, filename, content in sample_rows:
            lines = content.splitlines()
            var_types: Dict[str, str] = {}

            # First pass: type declarations
            for line in lines:
                m_dim = _DIM_VAR_RE.search(line)
                if m_dim:
                    v_name, type_name = m_dim.group(1).lower(), m_dim.group(2).lower()
                    if type_name in interfaces:
                        var_types[v_name] = interfaces[type_name]

            # Second pass: method and property calls
            for idx, raw_line in enumerate(lines, start=1):
                clean_line = raw_line.strip()
                if not clean_line or clean_line.startswith("'") or clean_line.startswith("//"):
                    continue

                for m_call in _METHOD_CALL_RE.finditer(clean_line):
                    var_name, member_name = m_call.group(1), m_call.group(2)
                    var_lower = var_name.lower()
                    member_lower = member_name.lower()

                    target_ifaces = member_to_ifaces.get(member_lower)
                    if not target_ifaces:
                        continue

                    matched_iface: Optional[str] = None
                    # Rule A: Explicit variable type
                    if var_lower in var_types:
                        cand = var_types[var_lower]
                        if cand in target_ifaces:
                            matched_iface = cand

                    # Rule B: Heuristic prefix match (e.g. oMaterial -> Material, partDoc -> PartDocument)
                    if not matched_iface:
                        stripped_var = _PREFIX_STRIP_RE.sub("", var_lower)
                        if stripped_var in interfaces:
                            cand = interfaces[stripped_var]
                            if cand in target_ifaces:
                                matched_iface = cand

                    # Rule C: Member is unique to exactly one interface
                    if not matched_iface and len(target_ifaces) == 1:
                        matched_iface = next(iter(target_ifaces))

                    if matched_iface:
                        canon_member = canonical_members.get((matched_iface.lower(), member_lower), member_name)
                        link_key = (matched_iface, canon_member, "sample", sample_id, idx)
                        if link_key not in seen_links:
                            seen_links.add(link_key)
                            links_to_insert.append((
                                matched_iface,
                                canon_member,
                                "sample",
                                sample_id,
                                rel_path,
                                filename,
                                idx,
                                clean_line[:400],
                                None,
                            ))

        # 2. Scan doc_pages (official HTML use cases & code blocks)
        cur.execute(
            "SELECT doc_id, title, summary, warnings, body_text FROM doc_pages "
            "WHERE body_text IS NOT NULL AND length(body_text) > 0"
        )
        doc_rows = cur.fetchall()

        for doc_id, title, summary, warnings, body_text in doc_rows:
            # Focus on code blocks or automation usecase documents
            lines = body_text.splitlines()
            var_types = {}

            # Gather doc-level note/warning if available
            doc_note = (warnings or "").strip()
            if not doc_note and summary:
                doc_note = summary.strip()

            for line in lines:
                m_dim = _DIM_VAR_RE.search(line)
                if m_dim:
                    v_name, type_name = m_dim.group(1).lower(), m_dim.group(2).lower()
                    if type_name in interfaces:
                        var_types[v_name] = interfaces[type_name]

            for idx, raw_line in enumerate(lines, start=1):
                clean_line = raw_line.strip()
                if not clean_line or clean_line.startswith("'") or clean_line.startswith("#"):
                    continue

                for m_call in _METHOD_CALL_RE.finditer(clean_line):
                    var_name, member_name = m_call.group(1), m_call.group(2)
                    var_lower = var_name.lower()
                    member_lower = member_name.lower()

                    target_ifaces = member_to_ifaces.get(member_lower)
                    if not target_ifaces:
                        continue

                    matched_iface = None
                    if var_lower in var_types:
                        cand = var_types[var_lower]
                        if cand in target_ifaces:
                            matched_iface = cand

                    if not matched_iface:
                        stripped_var = _PREFIX_STRIP_RE.sub("", var_lower)
                        if stripped_var in interfaces:
                            cand = interfaces[stripped_var]
                            if cand in target_ifaces:
                                matched_iface = cand

                    if not matched_iface and len(target_ifaces) == 1:
                        matched_iface = next(iter(target_ifaces))

                    if matched_iface:
                        canon_member = canonical_members.get((matched_iface.lower(), member_lower), member_name)
                        link_key = (matched_iface, canon_member, "doc", doc_id, idx)
                        if link_key not in seen_links:
                            seen_links.add(link_key)
                            links_to_insert.append((
                                matched_iface,
                                canon_member,
                                "doc",
                                doc_id,
                                doc_id,
                                title,
                                idx,
                                clean_line[:400],
                                doc_note[:300] if doc_note else None,
                            ))

        # Batch insert into SQLite
        cur.executemany(
            "INSERT INTO doc_api_links ("
            "  interface_name, member_name, target_type, ref_id, rel_path, title, line_no, code_snippet, official_note"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            links_to_insert,
        )
        docs_conn.commit()

        # Compute summary metrics
        cur.execute("SELECT COUNT(DISTINCT interface_name) FROM doc_api_links")
        linked_ifaces_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(DISTINCT member_name) FROM doc_api_links")
        linked_members_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM doc_api_links WHERE target_type = 'sample'")
        sample_links_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM doc_api_links WHERE target_type = 'doc'")
        doc_links_count = cur.fetchone()[0]

        docs_conn.close()
        elapsed = round(time.time() - start_time, 2)

        return {
            "total_links": len(links_to_insert),
            "linked_interfaces": linked_ifaces_count,
            "linked_members": linked_members_count,
            "sample_links": sample_links_count,
            "doc_links": doc_links_count,
            "elapsed_seconds": elapsed,
        }
