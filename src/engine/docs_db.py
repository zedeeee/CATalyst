"""
Offline Documentation Extension Engine for CATalyst (catalyst_docs.db).
Reads portable relative paths from catalyst_docs.db and resolves machine-local absolute paths
dynamically at runtime via CATALYST_DOC_ROOT / CATALYST_INSTALL_ROOT (configured in MCP env).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.engine.local_config import (
    resolve_doc_root as _resolve_doc_root_5tier,
    resolve_install_root as _resolve_install_root_5tier,
)
from src.parser.docs_parser import BINARY_SAMPLE_EXTS

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def resolve_docs_db_path(db_path: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """
    Resolve optional local catalyst_docs.db path:
    1. CATALYST_DOCS_DB_PATH environment variable
    2. Explicit db_path argument
    3. PROJECT_ROOT / dist / local / catalyst_docs.db
    4. CWD / dist / local / catalyst_docs.db
    5. PROJECT_ROOT / dist / catalyst_docs.db
    """
    candidates: List[Path] = []
    env_path = os.environ.get("CATALYST_DOCS_DB_PATH", "").strip()
    if env_path:
        candidates.append(Path(env_path))
    if db_path is not None:
        candidates.append(Path(db_path))

    cwd = Path.cwd()
    candidates.extend(
        [
            PROJECT_ROOT / "dist" / "local" / "catalyst_docs.db",
            cwd / "dist" / "local" / "catalyst_docs.db",
            PROJECT_ROOT / "dist" / "catalyst_docs.db",
        ]
    )

    seen = set()
    for cand in candidates:
        try:
            key = cand.resolve()
        except Exception:
            key = cand
        if key in seen:
            continue
        seen.add(key)
        if cand.exists() and cand.is_file():
            return cand.resolve()
    return None


def _join_portable_rel(base: Path, rel_path: str) -> Path:
    """Safely join a portable relative path (supporting '/' or '\\') onto a local OS base path."""
    parts = [p for p in (rel_path or "").replace("\\", "/").split("/") if p and p != "."]
    return base.joinpath(*parts) if parts else base


def resolve_runtime_doc_root(meta: Dict[str, str]) -> Optional[Path]:
    """5-tier dynamic doc root resolution (MCP env -> dist/local/paths.json -> CATEnv -> default)."""
    return _resolve_doc_root_5tier(
        release_hint=meta.get("catia_release", ""),
        legacy_meta_path=meta.get("doc_root", ""),
    )


def resolve_runtime_install_root(meta: Dict[str, str]) -> Optional[Path]:
    """5-tier dynamic install root resolution (MCP env -> dist/local/paths.json -> CATEnv -> default)."""
    return _resolve_install_root_5tier(
        release_hint=meta.get("catia_release", ""),
        legacy_meta_path=meta.get("install_root", ""),
    )


def _split_camel_case(text: str) -> str:
    """Split CamelCase identifiers (e.g. FavoriteCatalog -> Favorite Catalog) for FTS fallback."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)
    return s


def _format_fts_tokens(query: str, joiner: str = " AND ") -> str:
    """Convert raw query into safe FTS5 prefix MATCH syntax, preserving explicit OR."""
    raw = (query or "").strip()
    if not raw:
        return ""
    if " OR " in raw:
        parts = [p.strip() for p in raw.split(" OR ") if p.strip()]
        formatted = []
        for p in parts:
            sub = _format_fts_tokens(p, joiner=" AND ")
            if sub:
                formatted.append(f"({sub})")
        return " OR ".join(formatted)

    cleaned = re.sub(r'["\'\*\^\:\(\)\{\}\[\]\+\-\~\?\\/\.]+', " ", raw)
    tokens = [t.strip() for t in cleaned.split() if t.strip() and t.upper() not in {"AND", "OR", "NOT"}]
    if not tokens:
        return ""
    return joiner.join(f'"{t}"*' for t in tokens)


class CatalystDocsDB:
    """Thread-safe read-only query engine over portable catalyst_docs.db."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None) -> None:
        resolved = resolve_docs_db_path(db_path)
        if resolved is None:
            raise FileNotFoundError(
                "CATalyst offline docs database (catalyst_docs.db) not found. "
                "Build it locally with: `uv run python build_docs.py --doc-root <Bxxdoc> --install-root <Bxx>`."
            )
        self.db_path = resolved
        self._local = threading.local()

    @property
    def conn(self) -> sqlite3.Connection:
        conn_instance = getattr(self._local, "conn", None)
        if conn_instance is None:
            conn_instance = sqlite3.connect(self.db_path, check_same_thread=False)
            conn_instance.row_factory = sqlite3.Row
            self._local.conn = conn_instance
        return conn_instance

    def get_meta(self) -> Dict[str, str]:
        cur = self.conn.cursor()
        cur.execute("SELECT key, value FROM docs_meta")
        return {row["key"]: row["value"] for row in cur.fetchall()}

    def _has_column(self, table: str, column: str) -> bool:
        cur = self.conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        return any(row["name"] == column for row in cur.fetchall())

    def search_docs(
        self,
        query: str,
        category: str = "all",
        module: str = "",
        solution: str = "",
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Full-text BM25 search across indexed CATIA V5 HTML documentation."""
        meta = self.get_meta()
        clamped = max(1, min(limit, 30))
        fts_and = _format_fts_tokens(query, joiner=" AND ")
        if not fts_and:
            return {
                "catia_release": meta.get("catia_release", "unknown"),
                "query": query,
                "total_matches": 0,
                "results": [],
            }

        cat_norm = (category or "all").strip().lower()
        mod_norm = (module or "").strip()
        sol_norm = (solution or "").strip()
        has_links = self._has_column("doc_pages", "linked_files_json")

        def _exec(match_expr: str) -> List[sqlite3.Row]:
            where_parts = ["doc_pages_fts MATCH ?"]
            params: List[Any] = [match_expr]
            if cat_norm and cat_norm != "all":
                where_parts.append("p.category = ?")
                params.append(cat_norm)
            if mod_norm:
                where_parts.append("LOWER(p.module) LIKE LOWER(?)")
                params.append(f"%{mod_norm}%")
            if sol_norm:
                where_parts.append("LOWER(p.solution) LIKE LOWER(?)")
                params.append(f"%{sol_norm}%")

            params.append(clamped)
            extra_cols = ", p.linked_files_json" if has_links else ""
            sql = f"""
                SELECT
                    p.doc_id,
                    p.module,
                    p.solution,
                    p.product_name,
                    p.category,
                    p.title,
                    p.options_anchors,
                    p.summary,
                    p.warnings,
                    p.images_json{extra_cols},
                    snippet(doc_pages_fts, 5, '[', ']', '...', 24) AS snippet,
                    bm25(doc_pages_fts, 10.0, 8.0, 8.0, 5.0, 4.0, 1.0) AS score
                FROM doc_pages_fts
                JOIN doc_pages p ON p.id = doc_pages_fts.rowid
                WHERE {' AND '.join(where_parts)}
                ORDER BY score ASC
                LIMIT ?
            """
            cur = self.conn.cursor()
            cur.execute(sql, params)
            return cur.fetchall()

        rows = _exec(fts_and)
        fallback_used = False
        if not rows:
            camel_split = _split_camel_case(query)
            if camel_split != query:
                fts_camel = _format_fts_tokens(camel_split, joiner=" AND ")
                if fts_camel and fts_camel != fts_and:
                    rows = _exec(fts_camel)
        if not rows and (" AND " in fts_and or _split_camel_case(query) != query):
            fts_or = _format_fts_tokens(_split_camel_case(query), joiner=" OR ")
            if fts_or:
                rows = _exec(fts_or)
                fallback_used = bool(rows)

        results: List[Dict[str, Any]] = []
        for r in rows:
            imgs = json.loads(r["images_json"] or "[]")
            lfiles = json.loads(r["linked_files_json"] or "[]") if has_links else []
            warn_preview = (r["warnings"] or "").strip()
            if len(warn_preview) > 220:
                warn_preview = warn_preview[:220] + "..."
            results.append(
                {
                    "doc_id": r["doc_id"],
                    "title": r["title"],
                    "module": r["module"],
                    "product_name": r["product_name"],
                    "solution": r["solution"],
                    "category": r["category"],
                    "options_anchors": r["options_anchors"] or "",
                    "summary": r["summary"] or "",
                    "warnings_preview": warn_preview,
                    "snippet": r["snippet"] or "",
                    "image_count": len(imgs),
                    "linked_file_count": len(lfiles),
                }
            )

        return {
            "catia_release": meta.get("catia_release", "unknown"),
            "query": query,
            "category_filter": cat_norm,
            "module_filter": mod_norm or None,
            "or_fallback_used": fallback_used,
            "total_matches": len(results),
            "results": results,
        }

    def get_doc_page(
        self,
        doc_id: str,
        section: str = "",
        include_images: bool = True,
        max_chars: int = 12000,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single official documentation page.
        Resolves relative paths of HTML, images, and linked sample files against runtime CATALYST_DOC_ROOT.
        """
        meta = self.get_meta()
        norm_id = (doc_id or "").strip().replace("\\", "/")
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM doc_pages WHERE doc_id = ?", (norm_id,))
        row = cur.fetchone()
        if not row:
            cur.execute("SELECT * FROM doc_pages WHERE LOWER(doc_id) LIKE LOWER(?) LIMIT 1", (f"%/{norm_id}",))
            row = cur.fetchone()
        if not row:
            return None

        row_dict = dict(row)
        body = row_dict.get("body_text") or ""
        sec_filter = (section or "").strip().lower()
        section_matched = False
        if sec_filter:
            lines = body.splitlines()
            start_idx = None
            start_level = 6
            for idx, ln in enumerate(lines):
                m = re.match(r"^(#{1,4})\s+(.+)$", ln.strip())
                if m and sec_filter in m.group(2).lower():
                    start_idx = idx
                    start_level = len(m.group(1))
                    break
            if start_idx is not None:
                section_matched = True
                end_idx = len(lines)
                for idx in range(start_idx + 1, len(lines)):
                    m = re.match(r"^(#{1,4})\s+", lines[idx].strip())
                    if m and len(m.group(1)) <= start_level:
                        end_idx = idx
                        break
                body = "\n".join(lines[start_idx:end_idx]).strip()

        truncated = False
        if max_chars > 0 and len(body) > max_chars:
            omitted = len(body) - max_chars
            body = f"{body[:max_chars]}\n\n... [truncated {omitted} chars; pass section=... or larger max_chars]"
            truncated = True

        doc_root_path = resolve_runtime_doc_root(meta)

        def _attach_abs(rel_p: str) -> Dict[str, Any]:
            entry: Dict[str, Any] = {"rel_path": rel_p}
            if doc_root_path:
                cand = _join_portable_rel(doc_root_path, rel_p)
                if cand.exists():
                    entry["abs_path"] = str(cand)
            return entry

        result: Dict[str, Any] = {
            "catia_release": meta.get("catia_release", "unknown"),
            "doc_root_resolved": str(doc_root_path) if doc_root_path else None,
            "doc_id": row_dict["doc_id"],
            "title": row_dict["title"],
            "module": row_dict["module"],
            "solution": row_dict["solution"],
            "product_name": row_dict["product_name"],
            "category": row_dict["category"],
            "ix_keywords": row_dict.get("ix_keywords") or "",
            "options_anchors": row_dict.get("options_anchors") or "",
            "headings": row_dict.get("headings") or "",
            "summary": row_dict.get("summary") or "",
            "warnings": row_dict.get("warnings") or "",
            "section_filter": section or None,
            "section_matched": section_matched if sec_filter else None,
            "truncated": truncated,
            "body_text": body,
        }

        if doc_root_path:
            page_abs = _join_portable_rel(doc_root_path, row_dict["doc_id"])
            if page_abs.exists():
                result["abs_path"] = str(page_abs)
        else:
            result["path_setup_hint"] = (
                "Local CATIA doc root not configured on this machine (abs_path omitted). "
                "Set CATALYST_DOC_ROOT in MCP env or run `uv run python build_docs.py --set-paths` "
                "to point to your local Bxxdoc directory."
            )

        if include_images:
            raw_imgs = json.loads(row_dict.get("images_json") or "[]")
            result["images"] = [_attach_abs(rel_img) for rel_img in raw_imgs]

        raw_linked_docs = json.loads(row_dict.get("linked_docs_json") or "[]")
        if raw_linked_docs:
            result["linked_docs"] = raw_linked_docs

        raw_linked_files = json.loads(row_dict.get("linked_files_json") or "[]")
        if raw_linked_files:
            resolved_files = []
            for rf in raw_linked_files:
                item = _attach_abs(rf)
                ext = Path(rf).suffix.lower()
                item["ext"] = ext
                item["is_binary"] = ext in BINARY_SAMPLE_EXTS
                resolved_files.append(item)
            result["linked_files"] = resolved_files

        return result

    def search_settings(
        self,
        query: str = "",
        nls_file: str = "",
        options_only: bool = True,
        limit: int = 15,
    ) -> Dict[str, Any]:
        """Search CATNls UI option labels/keys and cross-link matching Tools>Options doc pages."""
        meta = self.get_meta()
        clamped = max(1, min(limit, 50))
        q = (query or "").strip()
        nf = (nls_file or "").strip()
        if nf.lower().endswith(".catnls"):
            nf = nf[:-7]

        cur = self.conn.cursor()
        nls_rows: List[sqlite3.Row] = []

        if nf and not q:
            cur.execute(
                """
                SELECT file_stem, nls_key, text, is_option_file
                FROM catnls_entries
                WHERE LOWER(file_stem) LIKE LOWER(?)
                ORDER BY id ASC
                LIMIT ?
                """,
                (f"%{nf}%", clamped),
            )
            nls_rows = cur.fetchall()
        elif q:
            fts_q = _format_fts_tokens(q, joiner=" AND ")
            if fts_q:
                where = ["catnls_fts MATCH ?"]
                params: List[Any] = [fts_q]
                if nf:
                    where.append("LOWER(c.file_stem) LIKE LOWER(?)")
                    params.append(f"%{nf}%")
                if options_only:
                    where.append("c.is_option_file = 1")
                params.append(clamped)
                sql = f"""
                    SELECT c.file_stem, c.nls_key, c.text, c.is_option_file,
                           bm25(catnls_fts, 4.0, 6.0, 2.0) AS score
                    FROM catnls_fts
                    JOIN catnls_entries c ON c.id = catnls_fts.rowid
                    WHERE {' AND '.join(where)}
                    ORDER BY score ASC
                    LIMIT ?
                """
                cur.execute(sql, params)
                nls_rows = cur.fetchall()

                if not nls_rows:
                    camel_q = _split_camel_case(q)
                    if camel_q != q:
                        fts_camel = _format_fts_tokens(camel_q, joiner=" AND ")
                        if fts_camel and fts_camel != fts_q:
                            camel_params = [fts_camel] + params[1:]
                            cur.execute(sql, camel_params)
                            nls_rows = cur.fetchall()

                if not nls_rows and options_only:
                    where_relaxed = [w for w in where if w != "c.is_option_file = 1"]
                    cur.execute(
                        f"""
                        SELECT c.file_stem, c.nls_key, c.text, c.is_option_file,
                               bm25(catnls_fts, 4.0, 6.0, 2.0) AS score
                        FROM catnls_fts
                        JOIN catnls_entries c ON c.id = catnls_fts.rowid
                        WHERE {' AND '.join(where_relaxed)}
                        ORDER BY score ASC
                        LIMIT ?
                        """,
                        params,
                    )
                    nls_rows = cur.fetchall()

        related_docs: List[Dict[str, Any]] = []
        doc_query = q or nf
        if doc_query:
            doc_res = self.search_docs(doc_query, category="options", limit=5)
            related_docs = [
                {
                    "doc_id": d["doc_id"],
                    "title": d["title"],
                    "module": d["module"],
                    "options_anchors": d["options_anchors"],
                }
                for d in doc_res["results"]
            ]

        return {
            "catia_release": meta.get("catia_release", "unknown"),
            "query": q,
            "nls_file_filter": nf or None,
            "total_nls_matches": len(nls_rows),
            "nls_entries": [
                {
                    "file_stem": r["file_stem"],
                    "nls_key": r["nls_key"],
                    "text": r["text"],
                    "is_option_file": bool(r["is_option_file"]),
                }
                for r in nls_rows
            ],
            "related_option_docs": related_docs,
            "xml_roundtrip_hint": (
                "For .CATSettings without COM SettingController, export/import via: "
                'CATSTART.exe -run "CATBatGenXMLSet.exe <OutDir> <RepoName>" / '
                'CATSTART.exe -run "CATBatImpXMLSet.exe <XmlFile>" '
                "(Note: DLNames.CATSettings requires CATSysDLExport)."
            ),
        }

    def search_samples(
        self,
        query: str = "",
        ext: str = "",
        module: str = "",
        include_content: bool = False,
        include_binary: bool = True,
        max_chars: int = 6000,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Search official CATIA V5 sample files (both text and binary CAD models).
        Returns portable rel_path plus dynamically resolved abs_path from CATALYST_DOC_ROOT / CATALYST_INSTALL_ROOT.
        """
        meta = self.get_meta()
        clamped = max(1, min(limit, 30))
        q = (query or "").strip()
        ext_norm = (ext or "").strip().lower()
        if ext_norm and not ext_norm.startswith("."):
            ext_norm = f".{ext_norm}"
        mod_norm = (module or "").strip()
        has_is_binary = self._has_column("doc_samples", "is_binary")

        cur = self.conn.cursor()
        where: List[str] = []
        params: List[Any] = []

        if q:
            fts_q = _format_fts_tokens(q, joiner=" AND ")
            if not fts_q:
                return {
                    "catia_release": meta.get("catia_release", "unknown"),
                    "query": q,
                    "total_matches": 0,
                    "results": [],
                }
            where.append("doc_samples_fts MATCH ?")
            params.append(fts_q)

        if ext_norm:
            where.append("LOWER(s.ext) = ?")
            params.append(ext_norm)
        if mod_norm:
            where.append("LOWER(s.module) LIKE LOWER(?)")
            params.append(f"%{mod_norm}%")
        if has_is_binary and not include_binary:
            where.append("s.is_binary = 0")

        params.append(clamped)
        if q:
            sql = f"""
                SELECT s.*, bm25(doc_samples_fts, 4.0, 10.0, 6.0, 1.0) AS score
                FROM doc_samples_fts
                JOIN doc_samples s ON s.id = doc_samples_fts.rowid
                WHERE {' AND '.join(where)}
                ORDER BY score ASC
                LIMIT ?
            """
        else:
            where_clause = f"WHERE {' AND '.join(where)}" if where else ""
            sql = f"SELECT s.* FROM doc_samples s {where_clause} ORDER BY s.sample_id ASC LIMIT ?"

        cur.execute(sql, params)
        rows = cur.fetchall()

        doc_root_path = resolve_runtime_doc_root(meta)
        install_root_path = resolve_runtime_install_root(meta)

        results: List[Dict[str, Any]] = []
        for r in rows:
            rd = dict(r)
            is_bin = bool(rd.get("is_binary", 0))
            rel_path = rd["rel_path"]
            item: Dict[str, Any] = {
                "sample_id": rd["sample_id"],
                "source": rd["source"],
                "module": rd["module"],
                "filename": rd["filename"],
                "ext": rd["ext"],
                "rel_path": rel_path,
                "size_bytes": rd["size_bytes"],
                "is_binary": is_bin,
            }

            # Dynamically resolve local absolute path from configured MCP roots
            base_root = doc_root_path if rd["source"] == "doc_samples" else install_root_path
            if base_root:
                cand = _join_portable_rel(base_root, rel_path)
                if cand.exists():
                    item["abs_path"] = str(cand)

            if not is_bin:
                if include_content:
                    content = rd.get("content") or ""
                    if max_chars > 0 and len(content) > max_chars:
                        content = f"{content[:max_chars]}\n... [truncated {len(content) - max_chars} chars]"
                    item["content"] = content
                else:
                    preview = (rd.get("content") or "").splitlines()[:5]
                    item["preview"] = "\n".join(preview)[:300]
            results.append(item)

        out: Dict[str, Any] = {
            "catia_release": meta.get("catia_release", "unknown"),
            "doc_root_resolved": str(doc_root_path) if doc_root_path else None,
            "install_root_resolved": str(install_root_path) if install_root_path else None,
            "query": q,
            "total_matches": len(results),
            "results": results,
        }
        if not doc_root_path and not install_root_path:
            out["path_setup_hint"] = (
                "Local CATIA doc/install roots not configured on this machine (abs_path omitted). "
                "Set CATALYST_DOC_ROOT / CATALYST_INSTALL_ROOT in MCP env or save them via "
                "`uv run python build_docs.py --set-paths`."
            )
        return out
