"""
Static Implementation Caveat Miner for CATalyst.
Scans parsed CHM member descriptions (<dl><dd>), official documentation warnings,
and doc_api_links sample code for contract discrepancy clues (e.g. path vs folder,
batch-only methods, silent no-ops, inline commented workarounds).
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_DESC_CAVEAT_RULES: List[Tuple[str, re.Pattern[str], str]] = [
    (
        "FOLDER_PATH_CONTRACT",
        re.compile(r"\bpath of the folder\b|\bfolder where\b|Ex\s*:\s*[A-Za-z]:\\[^.\n]*\\", re.IGNORECASE),
        "Documentation requires a folder path (often with trailing separator), not a filename.",
    ),
    (
        "BATCH_MODE_ONLY",
        re.compile(r"\bBatch Mode\b|\bbatch only\b|\bCNEXT\s*-batch\b", re.IGNORECASE),
        "Method involves CATIA Batch Mode constraints.",
    ),
    (
        "SILENT_NOOP_BEHAVIOR",
        re.compile(r"\bdoes nothing if\b|\bno effect if\b|\bsilently\b", re.IGNORECASE),
        "Method may silently no-op without raising an exception under invalid preconditions.",
    ),
    (
        "STRICT_PRECONDITION",
        re.compile(r"\bmust be\b|\bhas to be\b|\bonly available if\b|\bnot supported\b|\bdeprecated\b|\bobsolete\b", re.IGNORECASE),
        "Method documentation specifies explicit runtime preconditions or deprecation.",
    ),
]

_INLINE_WORKAROUND_RE = re.compile(r"\)\s*'\s*[&+]|[A-Za-z0-9_]+\.[A-Za-z0-9_]+\([^)]*\)\s*'\s*(?:todo|fixme|bug|hack|note|&)", re.IGNORECASE)


class CaveatMiner:
    """Extracts candidate implementation caveats directly from catalyst.db and catalyst_docs.db."""

    def __init__(
        self,
        core_db_path: Optional[Path | str] = None,
        docs_db_path: Optional[Path | str] = None,
    ) -> None:
        self.core_db_path = Path(core_db_path) if core_db_path else (PROJECT_ROOT / "dist" / "catalyst.db")
        self.docs_db_path = Path(docs_db_path) if docs_db_path else (PROJECT_ROOT / "dist" / "local" / "catalyst_docs.db")

    def mine_caveats(self, output_path: Optional[Path | str] = None) -> List[Dict[str, Any]]:
        if not self.core_db_path.exists():
            raise FileNotFoundError(f"Core DB not found: {self.core_db_path}")

        candidates: List[Dict[str, Any]] = []
        seen: Set[Tuple[str, str, str]] = set()

        # 1. Scan member descriptions in catalyst.db (strictly native declarations to avoid duplication)
        core_conn = sqlite3.connect(str(self.core_db_path))
        cur = core_conn.cursor()

        has_meth_desc = any(r[1] == "description" for r in cur.execute("PRAGMA table_info(methods)").fetchall())
        if has_meth_desc:
            for iface, m_name, decl, desc, params_json in cur.execute(
                "SELECT interface_name, name, declared_in, COALESCE(description, ''), COALESCE(params_json, '[]') "
                "FROM methods WHERE declared_in = interface_name AND length(description) > 0"
            ).fetchall():
                full_text = desc
                try:
                    for p in json.loads(params_json):
                        if p.get("description"):
                            full_text += " " + p["description"]
                except Exception:
                    pass

                for cat, pat, rationale in _DESC_CAVEAT_RULES:
                    if pat.search(full_text):
                        key = (iface.lower(), m_name.lower(), cat)
                        if key not in seen:
                            seen.add(key)
                            candidates.append({
                                "interface": iface,
                                "member": m_name,
                                "signal_source": "chm_member_doc",
                                "category": cat,
                                "rationale": rationale,
                                "evidence": desc[:300],
                            })
        core_conn.close()

        # 2. Scan doc_api_links & doc_pages.warnings in catalyst_docs.db (if built)
        if self.docs_db_path.exists():
            docs_conn = sqlite3.connect(str(self.docs_db_path))
            dcur = docs_conn.cursor()
            has_links = (
                dcur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='doc_api_links'").fetchone()
                is not None
            )
            if has_links:
                for iface, m_name, ttype, rel_path, line_no, snip, note in dcur.execute(
                    "SELECT interface_name, member_name, target_type, rel_path, line_no, code_snippet, COALESCE(official_note, '') "
                    "FROM doc_api_links"
                ).fetchall():
                    if _INLINE_WORKAROUND_RE.search(snip):
                        key = (iface.lower(), m_name.lower(), "INLINE_WORKAROUND_COMMENT")
                        if key not in seen:
                            seen.add(key)
                            candidates.append({
                                "interface": iface,
                                "member": m_name,
                                "signal_source": f"{ttype}:{rel_path}#L{line_no}",
                                "category": "INLINE_WORKAROUND_COMMENT",
                                "rationale": "Sample or doc code contains inline commented workaround right after method call.",
                                "evidence": snip[:300],
                            })

                    if any(k in m_name.lower() or k in snip.lower() for k in ("folder", "path", "icon", "dir")):
                        # Check for Path vs Folder indicator inside sample call (e.g. ending with sSep or \)
                        if re.search(r"(?:ssep|\\['\"]\s*)\)", snip, re.IGNORECASE):
                            key = (iface.lower(), m_name.lower(), "SAMPLE_TRAILING_SEP")
                            if key not in seen:
                                seen.add(key)
                                candidates.append({
                                    "interface": iface,
                                    "member": m_name,
                                    "signal_source": f"{ttype}:{rel_path}#L{line_no}",
                                    "category": "SAMPLE_TRAILING_SEP",
                                    "rationale": "Sample passes path ending in folder separator.",
                                    "evidence": snip[:300],
                                })
            docs_conn.close()

        if output_path is not None:
            out_file = Path(output_path)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8")

        return candidates


if __name__ == "__main__":
    out = PROJECT_ROOT / "dist" / "local" / "extracted_caveats.json"
    cands = CaveatMiner().mine_caveats(output_path=out)
    print(f"Mined {len(cands)} caveat candidates -> {out}")
