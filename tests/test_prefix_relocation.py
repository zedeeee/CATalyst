"""
Tests for multi-protocol runtime prefix relocation (local default, optional SMB UNC with offline
graceful degradation, and optional HTTP(S) URL) on portable catalyst_docs.db.
Runnable via both `pytest` and stdlib `python -m unittest`.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import install as installer
from src.engine import docs_db, local_config
from src.parser import docs_parser
from src.parser.docs_builder import CatalystDocsBuilder


def _build_minimal_synthetic_docs(root: Path):
    doc_online = root / "B27doc" / "English" / "online"
    mod = doc_online / "cceug_C2"
    (mod / "images").mkdir(parents=True)
    (mod / "samples").mkdir(parents=True)
    (doc_online / "CATIA_P3_TOC.xml").write_text(
        '<Root><Solution name="Infrastructure"><Product name="Catalog Editor" dir="cceug_C2"/></Solution></Root>',
        encoding="utf-8",
    )
    (mod / "images" / "batch shot.png").write_bytes(b"\x89PNG\r\n")
    (mod / "samples" / "BatchCatalog.csv").write_text("KEYWORD;PartNumber\n", encoding="utf-8")
    (mod / "cceugbt0102.htm").write_text(
        """<html><head><title>Catalog Batch Mode</title></head><body>
        <h1>Catalog Batch Mode</h1>
        <p>Run CreateCatalogFromcsv using <a href="samples/BatchCatalog.csv">BatchCatalog.csv</a>.</p>
        <img src="images/batch shot.png" width="400" height="200"/>
        </body></html>""",
        encoding="utf-8",
    )

    inst_root = root / "B27" / "win_b64"
    (inst_root / "resources" / "msgcatalog").mkdir(parents=True)
    (inst_root / "resources" / "msgcatalog" / "CATCatalog.CATNls").write_text(
        'ResolvedComponents.Title = "Allow resolved components";\n',
        encoding="utf-8",
    )
    return doc_online, inst_root


class TestPrefixRelocation(unittest.TestCase):
    def test_http_doc_root_normalization(self):
        self.assertEqual(
            local_config.normalize_http_doc_root("https://docs.example.com/B27doc"),
            "https://docs.example.com/B27doc/English/online",
        )
        self.assertEqual(
            local_config.normalize_http_doc_root("https://docs.example.com/B27doc/English/"),
            "https://docs.example.com/B27doc/English/online",
        )
        self.assertEqual(
            local_config.normalize_http_doc_root("https://docs.example.com/B27doc/English/online/"),
            "https://docs.example.com/B27doc/English/online",
        )
        self.assertEqual(
            local_config.normalize_http_doc_root("https://docs.example.com/B27doc/English/online/CATIA_P3_default.htm"),
            "https://docs.example.com/B27doc/English/online",
        )
        self.assertIsNone(local_config.parse_user_path("https://docs.example.com/B27doc"))

    def test_normalize_doc_root_survives_smb_oserror(self):
        with mock.patch.object(Path, "exists", side_effect=PermissionError(65, "Network access denied")):
            self.assertIsNone(docs_parser.normalize_doc_root(Path(r"\\nas-server\share\B27doc")))
            self.assertIsNone(docs_parser.normalize_install_root(Path(r"\\nas-server\share\B27")))

    def test_same_db_relocates_across_local_http_and_unreachable_smb(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc_online, inst_root = _build_minimal_synthetic_docs(root)
            db_path = root / "catalyst_docs.db"
            CatalystDocsBuilder(
                output_db=db_path,
                doc_root=doc_online,
                install_root=inst_root,
                release="B27",
                workers=1,
            ).build()

            db = docs_db.CatalystDocsDB(db_path)

            # 1. Local path prefix (default)
            with mock.patch.dict(
                os.environ,
                {"CATALYST_DOC_ROOT": str(root / "B27doc"), "CATALYST_INSTALL_ROOT": str(root / "B27")},
                clear=False,
            ):
                page_local = db.get_doc_page("cceug_C2/cceugbt0102.htm")
                self.assertEqual(page_local["doc_root_scheme"], "local")
                self.assertIn("abs_path", page_local)
                self.assertNotIn("url", page_local)
                self.assertTrue(Path(page_local["abs_path"]).is_file())

            # 2. HTTP(S) prefix (optional, zero network I/O, url-encoded spaces, no abs_path)
            with mock.patch.dict(
                os.environ,
                {
                    "CATALYST_DOC_ROOT": "https://docs.example.com/B27doc/English/online/CATIA_P3_default.htm",
                    "CATALYST_INSTALL_ROOT": str(root / "B27"),
                },
                clear=False,
            ):
                page_http = db.get_doc_page("cceug_C2/cceugbt0102.htm")
                self.assertEqual(page_http["doc_root_scheme"], "http")
                self.assertEqual(
                    page_http["url"],
                    "https://docs.example.com/B27doc/English/online/cceug_C2/cceugbt0102.htm",
                )
                self.assertNotIn("abs_path", page_http)
                self.assertEqual(
                    page_http["images"][0]["url"],
                    "https://docs.example.com/B27doc/English/online/cceug_C2/images/batch%20shot.png",
                )
                self.assertNotIn("abs_path", page_http["images"][0])

                smp_http = db.search_samples("BatchCatalog", include_content=True)
                self.assertEqual(smp_http["doc_root_scheme"], "http")
                self.assertEqual(
                    smp_http["results"][0]["url"],
                    "https://docs.example.com/B27doc/English/online/cceug_C2/samples/BatchCatalog.csv",
                )
                self.assertNotIn("abs_path", smp_http["results"][0])

            # 3. Unreachable SMB prefix degrades gracefully without crashing
            with (
                mock.patch.object(
                    docs_db,
                    "resolve_runtime_doc_root",
                    return_value=Path(r"\\nas-server\share\B27doc\English\online"),
                ),
                mock.patch.object(Path, "exists", side_effect=PermissionError(65, "Network access denied")),
            ):
                page_smb = db.get_doc_page("cceug_C2/cceugbt0102.htm")
                self.assertEqual(page_smb["doc_root_scheme"], "smb")
                self.assertIn("Catalog Batch Mode", page_smb["body_text"])
                self.assertNotIn("abs_path", page_smb)
                self.assertIn("path_unreachable_hint", page_smb)

            if hasattr(db, "close"):
                db.close()
            elif hasattr(db, "_local") and getattr(db._local, "conn", None) is not None:
                db._local.conn.close()
                db._local.conn = None

    def test_register_mcp_config_preserves_http_doc_root_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "mcp_config.json"
            installer.register_mcp_config(
                config_path=cfg,
                project_root=root / "CATalyst",
                uv_bin="uv",
                install_root=None,
                doc_root="https://docs.example.com/B27doc/English/online/CATIA_P3_default.htm",
            )
            data = json.loads(cfg.read_text(encoding="utf-8"))
            self.assertEqual(
                data["mcpServers"]["catalyst"]["env"]["CATALYST_DOC_ROOT"],
                "https://docs.example.com/B27doc/English/online",
            )


if __name__ == "__main__":
    unittest.main()
