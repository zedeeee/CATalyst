"""
Doc & Sample Code Linkage Builder for CATalyst.
Extracts method and property invocation linkages from official samples and documentation pages,
using IDL return-type propagation across chained calls and prose-noise filtering,
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
_ASSIGN_RE = re.compile(
    r"^\s*(?:Set\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$",
    re.IGNORECASE,
)
_CHAIN_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*(?:\s*(?:\([^()]*\))?\s*\.\s*[A-Za-z_][A-Za-z0-9_]*(?:\s*\([^()]*\))?)+)"
)
_SEGMENT_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(?:\s*\(([^()]*)\))?")

# Common file extensions & non-code dots to avoid mistaking prose/filenames for COM calls
_NON_CODE_EXTENSIONS = {
    "htm", "html", "txt", "csv", "xml", "jpg", "jpeg", "gif", "png", "bmp", "svg",
    "catpart", "catproduct", "catmaterial", "catdrawing", "catscript", "catvbs", "catfct",
    "catnls", "catsettings", "catprocess", "catanalysis", "catalog", "xls", "xlsx",
    "doc", "docx", "pdf", "exe", "dll", "zip", "cgr", "igs", "iges", "stp", "step",
    "stl", "vrml", "wrl", "bas", "cls", "frm", "py", "json", "md", "com", "org",
}
_PROSE_ABBREV_RE = re.compile(r"\b(?:e\.g|i\.e|vs|etc|fig|no|vol)\b", re.IGNORECASE)
_CODE_LINE_HINT_RE = re.compile(
    r"(?:^\s*(?:Set|Dim|Call|Sub|Function|For|If|While|Do|With|Select)\b|=|\([^\)]*\)|&)",
    re.IGNORECASE,
)

# High-collision generic COM member names that must not bind blindly via Rule C unique lookup
_AMBIGUOUS_MEMBERS = {
    "name", "count", "item", "parent", "application", "add", "remove",
    "get", "set", "value", "type", "open", "close", "save", "update",
    "clear", "write", "read", "copy", "paste", "delete", "refresh",
}

# Specialized document-type literal hints inside Documents.Add("...") or .Open("....CATPart")
_DOC_TYPE_LITERALS = {
    "part": "PartDocument",
    "product": "ProductDocument",
    "drawing": "DrawingDocument",
    "material": "MaterialDocument",
    "catalogdocument": "CatalogDocument",
    "analysis": "AnalysisDocument",
    "process": "ProcessDocument",
    "catpart": "PartDocument",
    "catproduct": "ProductDocument",
    "catdrawing": "DrawingDocument",
    "catmaterial": "MaterialDocument",
    "catalog": "CatalogDocument",
    "catanalysis": "AnalysisDocument",
}


def _strip_inline_comment(line: str) -> str:
    """Strip VBScript single-quote comment outside double quotes."""
    in_quotes = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == "'" and not in_quotes:
            return line[:i]
    return line


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
        Dict[Tuple[str, str], str],               # (iface_lower, member_lower) -> return interface canonical
    ]:
        cur = core_conn.cursor()
        interfaces: Dict[str, str] = {}
        for (name,) in cur.execute("SELECT name FROM interfaces"):
            interfaces[name.lower()] = name

        member_to_ifaces: Dict[str, Set[str]] = {}
        canonical_members: Dict[Tuple[str, str], str] = {}
        member_return_types: Dict[Tuple[str, str], str] = {}

        for iface, p_name, p_type in cur.execute("SELECT interface_name, name, type FROM properties"):
            canon_iface = interfaces.get(iface.lower(), iface)
            member_to_ifaces.setdefault(p_name.lower(), set()).add(canon_iface)
            canonical_members[(iface.lower(), p_name.lower())] = p_name

            # Refine Factory/Document properties whose property name matches concrete interface
            refined = interfaces.get(p_name.lower())
            base_ret = interfaces.get((p_type or "").lower())
            if refined and base_ret and base_ret.lower() in ("factory", "document"):
                member_return_types[(iface.lower(), p_name.lower())] = refined
            elif base_ret:
                member_return_types[(iface.lower(), p_name.lower())] = base_ret

        for iface, m_name, r_type in cur.execute("SELECT interface_name, name, return_type FROM methods"):
            canon_iface = interfaces.get(iface.lower(), iface)
            member_to_ifaces.setdefault(m_name.lower(), set()).add(canon_iface)
            canonical_members[(iface.lower(), m_name.lower())] = m_name
            ret_canon = interfaces.get((r_type or "").lower())
            if ret_canon:
                member_return_types[(iface.lower(), m_name.lower())] = ret_canon

        return interfaces, member_to_ifaces, canonical_members, member_return_types

    @staticmethod
    def _infer_doc_subtype_from_args(args_text: Optional[str]) -> Optional[str]:
        if not args_text:
            return None
        low = args_text.lower()
        for key, doc_iface in _DOC_TYPE_LITERALS.items():
            if key in low:
                return doc_iface
        return None

    def _scan_lines(
        self,
        lines: List[str],
        interfaces: Dict[str, str],
        member_to_ifaces: Dict[str, Set[str]],
        canonical_members: Dict[Tuple[str, str], str],
        member_return_types: Dict[Tuple[str, str], str],
        target_type: str,
        ref_id: str,
        rel_path: str,
        title: str,
        doc_note: Optional[str],
        seen_links: Set[Tuple[str, str, str, str, int]],
        links_out: List[Tuple[str, str, str, str, str, str, int, str, Optional[str]]],
        require_code_hint: bool = False,
    ) -> None:
        var_types: Dict[str, str] = {"catia": "Application"} if "application" in interfaces else {}

        # Pre-collect explicit Dim variable declarations across the block
        for raw_line in lines:
            m_dim = _DIM_VAR_RE.search(raw_line)
            if m_dim:
                v_name, type_name = m_dim.group(1).lower(), m_dim.group(2).lower()
                if type_name in interfaces:
                    var_types[v_name] = interfaces[type_name]

        for idx, raw_line in enumerate(lines, start=1):
            clean_line = raw_line.strip()
            if not clean_line or clean_line.startswith("'") or clean_line.startswith("//"):
                continue
            if require_code_hint:
                if clean_line.startswith("#") or not _CODE_LINE_HINT_RE.search(clean_line):
                    continue
                if _PROSE_ABBREV_RE.search(clean_line):
                    continue

            code_part = _strip_inline_comment(clean_line)
            if not code_part.strip():
                continue

            # Track assignment RHS type propagation first so sequential lines benefit
            assigned_lhs: Optional[str] = None
            eval_target = code_part
            m_assign = _ASSIGN_RE.match(code_part)
            if m_assign:
                assigned_lhs = m_assign.group(1).lower()
                eval_target = m_assign.group(2)

            last_chain_type: Optional[str] = None

            for m_chain in _CHAIN_RE.finditer(eval_target):
                chain_str = m_chain.group(1)
                segments = _SEGMENT_RE.findall(chain_str)
                if len(segments) < 2:
                    continue

                base_name, _ = segments[0]
                base_low = base_name.lower()

                # Resolve initial object type of the chain root
                curr_iface: Optional[str] = var_types.get(base_low)
                if not curr_iface:
                    stripped = _PREFIX_STRIP_RE.sub("", base_low)
                    if stripped in interfaces:
                        curr_iface = interfaces[stripped]

                for seg_name, seg_args in segments[1:]:
                    seg_low = seg_name.lower()
                    if seg_low in _NON_CODE_EXTENSIONS:
                        curr_iface = None
                        break

                    target_ifaces = member_to_ifaces.get(seg_low)
                    if not target_ifaces:
                        curr_iface = None
                        continue

                    matched_iface: Optional[str] = None
                    if curr_iface and curr_iface in target_ifaces:
                        matched_iface = curr_iface
                    elif not curr_iface and len(target_ifaces) == 1 and seg_low not in _AMBIGUOUS_MEMBERS:
                        matched_iface = next(iter(target_ifaces))

                    if matched_iface:
                        canon_member = canonical_members.get((matched_iface.lower(), seg_low), seg_name)
                        link_key = (matched_iface, canon_member, target_type, ref_id, idx)
                        if link_key not in seen_links:
                            seen_links.add(link_key)
                            links_out.append((
                                matched_iface,
                                canon_member,
                                target_type,
                                ref_id,
                                rel_path,
                                title,
                                idx,
                                clean_line[:400],
                                doc_note[:300] if doc_note else None,
                            ))

                        # Advance current type via return-type propagation
                        next_type = member_return_types.get((matched_iface.lower(), seg_low))
                        if next_type == "Document" and seg_low in ("add", "open", "newfrom", "item"):
                            sub_doc = self._infer_doc_subtype_from_args(seg_args)
                            if sub_doc and sub_doc.lower() in interfaces:
                                next_type = interfaces[sub_doc.lower()]
                        curr_iface = next_type
                    else:
                        curr_iface = None

                if curr_iface:
                    last_chain_type = curr_iface

            # Propagate resolved RHS type to LHS variable if LHS wasn't strongly Dim'd to a concrete subtype
            if assigned_lhs and last_chain_type:
                existing = var_types.get(assigned_lhs)
                if not existing or existing in ("Document", "Factory", "AnyObject", "CATBaseDispatch"):
                    var_types[assigned_lhs] = last_chain_type

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
        interfaces, member_to_ifaces, canonical_members, member_return_types = self._load_core_catalogue(core_conn)
        core_conn.close()

        docs_conn = sqlite3.connect(str(self.docs_db_path))
        cur = docs_conn.cursor()

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

        # 1. Scan doc_samples (pure script files: CATScript, catvbs, bas, etc.)
        cur.execute(
            "SELECT sample_id, rel_path, filename, content FROM doc_samples "
            "WHERE is_binary = 0 AND content IS NOT NULL AND length(content) > 0"
        )
        for sample_id, rel_path, filename, content in cur.fetchall():
            self._scan_lines(
                lines=content.splitlines(),
                interfaces=interfaces,
                member_to_ifaces=member_to_ifaces,
                canonical_members=canonical_members,
                member_return_types=member_return_types,
                target_type="sample",
                ref_id=sample_id,
                rel_path=rel_path,
                title=filename,
                doc_note=None,
                seen_links=seen_links,
                links_out=links_to_insert,
                require_code_hint=False,
            )

        # 2. Scan doc_pages (HTML documentation with prose-noise filter enabled)
        cur.execute(
            "SELECT doc_id, title, summary, warnings, body_text FROM doc_pages "
            "WHERE body_text IS NOT NULL AND length(body_text) > 0"
        )
        for doc_id, title, summary, warnings, body_text in cur.fetchall():
            doc_note = (warnings or "").strip() or (summary or "").strip() or None
            self._scan_lines(
                lines=body_text.splitlines(),
                interfaces=interfaces,
                member_to_ifaces=member_to_ifaces,
                canonical_members=canonical_members,
                member_return_types=member_return_types,
                target_type="doc",
                ref_id=doc_id,
                rel_path=doc_id,
                title=title or doc_id,
                doc_note=doc_note,
                seen_links=seen_links,
                links_out=links_to_insert,
                require_code_hint=True,
            )

        cur.executemany(
            "INSERT INTO doc_api_links ("
            "  interface_name, member_name, target_type, ref_id, rel_path, title, line_no, code_snippet, official_note"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            links_to_insert,
        )
        docs_conn.commit()

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    res = LinkageBuilder().build_linkages()
    print("Linkage rebuild complete:", res)
