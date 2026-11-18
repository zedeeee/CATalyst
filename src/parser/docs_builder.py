"""
SQLite FTS5 Builder for CATalyst Offline Documentation Extension DB (catalyst_docs.db).
Uses FTS5 external content tables to avoid duplicating body text and keeps build times
under ~25 seconds for full 14,700+ page CATIA V5 documentation sets.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, *args, **kwargs):
        return iterable

from .docs_parser import (
    collect_text_samples,
    detect_release_from_path,
    iter_doc_html_tasks,
    parse_catnls_file,
    parse_doc_html_task,
    parse_toc_xml,
)

logger = logging.getLogger(__name__)


class CatalystDocsBuilder:
    """Builds version-aligned local catalyst_docs.db from official Bxxdoc and msgcatalog."""

    def __init__(
        self,
        output_db: str | Path,
        doc_root: Optional[str | Path] = None,
        install_root: Optional[str | Path] = None,
        release: str = "",
        only_modules: Optional[Iterable[str]] = None,
        workers: Optional[int] = None,
    ) -> None:
        self.output_db = Path(output_db)
        self.doc_root = Path(doc_root) if doc_root else None
        self.install_root = Path(install_root) if install_root else None
        self.release = (
            release.strip()
            or detect_release_from_path(self.doc_root)
            or detect_release_from_path(self.install_root)
            or "unknown"
        )
        self.only_modules = list(only_modules) if only_modules else None
        self.workers = workers if workers and workers > 0 else max(1, min((os.cpu_count() or 4), 8))

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        cur.executescript(
            """
            PRAGMA synchronous = OFF;
            PRAGMA journal_mode = MEMORY;
            PRAGMA temp_store = MEMORY;

            DROP TABLE IF EXISTS docs_meta;
            DROP TABLE IF EXISTS doc_pages_fts;
            DROP TABLE IF EXISTS doc_pages;
            DROP TABLE IF EXISTS catnls_fts;
            DROP TABLE IF EXISTS catnls_entries;
            DROP TABLE IF EXISTS doc_samples_fts;
            DROP TABLE IF EXISTS doc_samples;

            CREATE TABLE docs_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE doc_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT UNIQUE NOT NULL,
                module TEXT NOT NULL,
                solution TEXT,
                product_name TEXT,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                ix_keywords TEXT,
                options_anchors TEXT,
                headings TEXT,
                summary TEXT,
                warnings TEXT,
                body_text TEXT,
                images_json TEXT
            );

            CREATE INDEX idx_doc_pages_module ON doc_pages(module);
            CREATE INDEX idx_doc_pages_category ON doc_pages(category);
            CREATE INDEX idx_doc_pages_solution ON doc_pages(solution);

            CREATE VIRTUAL TABLE doc_pages_fts USING fts5(
                title,
                ix_keywords,
                options_anchors,
                headings,
                warnings,
                body_text,
                content='doc_pages',
                content_rowid='id',
                tokenize='unicode61'
            );

            CREATE TABLE catnls_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_stem TEXT NOT NULL,
                nls_key TEXT NOT NULL,
                text TEXT NOT NULL,
                is_option_file INTEGER DEFAULT 0
            );

            CREATE INDEX idx_catnls_stem ON catnls_entries(file_stem);
            CREATE INDEX idx_catnls_opt ON catnls_entries(is_option_file);

            CREATE VIRTUAL TABLE catnls_fts USING fts5(
                file_stem,
                nls_key,
                text,
                content='catnls_entries',
                content_rowid='id',
                tokenize='unicode61'
            );

            CREATE TABLE doc_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id TEXT UNIQUE NOT NULL,
                source TEXT NOT NULL,
                module TEXT,
                filename TEXT NOT NULL,
                ext TEXT NOT NULL,
                rel_path TEXT NOT NULL,
                size_bytes INTEGER,
                content TEXT NOT NULL
            );

            CREATE INDEX idx_doc_samples_ext ON doc_samples(ext);
            CREATE INDEX idx_doc_samples_module ON doc_samples(module);

            CREATE VIRTUAL TABLE doc_samples_fts USING fts5(
                module,
                filename,
                rel_path,
                content,
                content='doc_samples',
                content_rowid='id',
                tokenize='unicode61'
            );
            """
        )
        conn.commit()

    def build(self) -> Dict[str, object]:
        t0 = time.perf_counter()
        self.output_db.parent.mkdir(parents=True, exist_ok=True)
        tmp_db = self.output_db.with_suffix(".building.db")
        if tmp_db.exists():
            tmp_db.unlink()

        conn = sqlite3.connect(tmp_db)
        try:
            self._init_schema(conn)
            page_count = self._build_doc_pages(conn)
            nls_count = self._build_catnls(conn)
            sample_count = self._build_samples(conn)

            logger.info("Rebuilding FTS5 external content indexes...")
            cur = conn.cursor()
            cur.execute("INSERT INTO doc_pages_fts(doc_pages_fts) VALUES('rebuild')")
            cur.execute("INSERT INTO catnls_fts(catnls_fts) VALUES('rebuild')")
            cur.execute("INSERT INTO doc_samples_fts(doc_samples_fts) VALUES('rebuild')")

            elapsed = round(time.perf_counter() - t0, 2)
            meta_rows = [
                ("catia_release", self.release),
                ("doc_root", str(self.doc_root) if self.doc_root else ""),
                ("install_root", str(self.install_root) if self.install_root else ""),
                ("built_at", datetime.now().astimezone().isoformat(timespec="seconds")),
                ("build_seconds", str(elapsed)),
                ("page_count", str(page_count)),
                ("nls_count", str(nls_count)),
                ("sample_count", str(sample_count)),
            ]
            cur.executemany("INSERT OR REPLACE INTO docs_meta(key, value) VALUES(?, ?)", meta_rows)
            cur.execute("ANALYZE")
            conn.commit()
        finally:
            conn.close()

        # Atomically replace target DB (fallback to overwrite if open by another process)
        try:
            os.replace(tmp_db, self.output_db)
        except PermissionError:
            logger.warning(f"Target DB {self.output_db} is locked; copying via SQLite backup API...")
            src_conn = sqlite3.connect(tmp_db)
            dst_conn = sqlite3.connect(self.output_db)
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
                src_conn.close()
            tmp_db.unlink(missing_ok=True)

        size_mb = round(self.output_db.stat().st_size / (1024 * 1024), 2)
        summary = {
            "output_db": str(self.output_db),
            "catia_release": self.release,
            "page_count": page_count,
            "nls_count": nls_count,
            "sample_count": sample_count,
            "size_mb": size_mb,
            "build_seconds": round(time.perf_counter() - t0, 2),
        }
        logger.info(
            f"Built {self.output_db} ({size_mb} MB) in {summary['build_seconds']}s: "
            f"{page_count} pages, {nls_count} CATNls entries, {sample_count} samples."
        )
        return summary

    def _build_doc_pages(self, conn: sqlite3.Connection) -> int:
        if not self.doc_root or not self.doc_root.exists():
            logger.info("No doc_root provided or path missing; skipping HTML User's Guide indexing.")
            return 0

        toc_map = parse_toc_xml(self.doc_root)
        tasks = iter_doc_html_tasks(self.doc_root, toc_map, only_modules=self.only_modules)
        logger.info(f"Indexing {len(tasks)} HTML documentation files using {self.workers} workers...")

        cur = conn.cursor()
        batch: List[tuple] = []
        inserted = 0

        def _flush() -> None:
            nonlocal inserted
            if not batch:
                return
            cur.executemany(
                """
                INSERT OR REPLACE INTO doc_pages (
                    doc_id, module, solution, product_name, category,
                    title, ix_keywords, options_anchors, headings,
                    summary, warnings, body_text, images_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch,
            )
            inserted += len(batch)
            batch.clear()

        if self.workers > 1 and len(tasks) >= 50:
            with ProcessPoolExecutor(max_workers=self.workers) as pool:
                for res in tqdm(
                    pool.map(parse_doc_html_task, tasks, chunksize=40),
                    total=len(tasks),
                    desc="Parsing HTML Docs",
                ):
                    if not res:
                        continue
                    batch.append(
                        (
                            res["doc_id"],
                            res["module"],
                            res["solution"],
                            res["product_name"],
                            res["category"],
                            res["title"],
                            res["ix_keywords"],
                            res["options_anchors"],
                            res["headings"],
                            res["summary"],
                            res["warnings"],
                            res["body_text"],
                            json.dumps(res["images"], ensure_ascii=False),
                        )
                    )
                    if len(batch) >= 500:
                        _flush()
        else:
            for t in tqdm(tasks, desc="Parsing HTML Docs"):
                res = parse_doc_html_task(t)
                if not res:
                    continue
                batch.append(
                    (
                        res["doc_id"],
                        res["module"],
                        res["solution"],
                        res["product_name"],
                        res["category"],
                        res["title"],
                        res["ix_keywords"],
                        res["options_anchors"],
                        res["headings"],
                        res["summary"],
                        res["warnings"],
                        res["body_text"],
                        json.dumps(res["images"], ensure_ascii=False),
                    )
                )
                if len(batch) >= 500:
                    _flush()

        _flush()
        conn.commit()
        return inserted

    def _build_catnls(self, conn: sqlite3.Connection) -> int:
        if not self.install_root or not self.install_root.exists():
            logger.info("No install_root provided or path missing; skipping CATNls indexing.")
            return 0

        msg_dir = self.install_root / "resources" / "msgcatalog"
        if not msg_dir.exists():
            # Allow passing msgcatalog directory directly
            if list(self.install_root.glob("*.CATNls")):
                msg_dir = self.install_root
            else:
                logger.info(f"msgcatalog directory not found under {self.install_root}; skipping CATNls.")
                return 0

        nls_files = sorted(msg_dir.glob("*.CATNls"))
        logger.info(f"Indexing {len(nls_files)} CATNls files from {msg_dir}...")

        cur = conn.cursor()
        batch: List[tuple] = []
        inserted = 0

        for fp in tqdm(nls_files, desc="Parsing CATNls"):
            rows = parse_catnls_file(fp)
            if rows:
                batch.extend(rows)
            if len(batch) >= 2000:
                cur.executemany(
                    "INSERT INTO catnls_entries (file_stem, nls_key, text, is_option_file) VALUES (?, ?, ?, ?)",
                    batch,
                )
                inserted += len(batch)
                batch.clear()

        if batch:
            cur.executemany(
                "INSERT INTO catnls_entries (file_stem, nls_key, text, is_option_file) VALUES (?, ?, ?, ?)",
                batch,
            )
            inserted += len(batch)
            batch.clear()

        conn.commit()
        return inserted

    def _build_samples(self, conn: sqlite3.Connection) -> int:
        samples = collect_text_samples(
            doc_root=self.doc_root,
            install_root=self.install_root,
            only_modules=self.only_modules,
        )
        if not samples:
            return 0
        logger.info(f"Indexing {len(samples)} official plain-text samples...")
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT OR REPLACE INTO doc_samples (
                sample_id, source, module, filename, ext, rel_path, size_bytes, content
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    s["sample_id"],
                    s["source"],
                    s["module"],
                    s["filename"],
                    s["ext"],
                    s["rel_path"],
                    s["size_bytes"],
                    s["content"],
                )
                for s in samples
            ],
        )
        conn.commit()
        return len(samples)
