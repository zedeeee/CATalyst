"""
Regression tests for CHM unpacker reliability, explicit 7z/hh choice,
cross-platform path parsing/joining, CATEnv release alignment,
and one-click MCP installer compatibility.
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
from src.parser import chm_unpacker


class TestChmUnpackerAndInstaller(unittest.TestCase):
    def test_has_extracted_html_ignores_gitkeep(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            (out_dir / ".gitkeep").write_text("", encoding="utf-8")
            self.assertFalse(chm_unpacker._has_extracted_html(out_dir))

            nested = out_dir / "generated" / "interfaces"
            nested.mkdir(parents=True)
            (nested / "Pad.htm").write_text("<html></html>", encoding="utf-8")
            self.assertTrue(chm_unpacker._has_extracted_html(out_dir))

    def test_no_silent_hh_fallback_when_7z_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chm = root / "My Source Dir" / "V5Automation.chm"
            chm.parent.mkdir(parents=True)
            chm.write_bytes(b"ITSF")
            out_dir = root / "My Target Dir" / "raw"

            with (
                mock.patch.object(chm_unpacker, "_find_7z", return_value=None),
                mock.patch.object(chm_unpacker, "_unpack_with_hh", return_value=True) as mock_hh,
            ):
                ok_default = chm_unpacker.unpack_chm(chm, out_dir, allow_hh_fallback=False)
                self.assertFalse(ok_default)
                mock_hh.assert_not_called()

                if os.name == "nt":
                    ok_explicit = chm_unpacker.unpack_chm(chm, out_dir, allow_hh_fallback=True)
                    self.assertTrue(ok_explicit)
                    mock_hh.assert_called_once()

    def test_ensure_unpacker_choice_noninteractive_policy(self):
        with (
            mock.patch.object(chm_unpacker, "_find_7z", return_value=None),
            mock.patch.object(chm_unpacker, "_find_hh", return_value=r"C:\Windows\hh.exe"),
        ):
            ready, use_hh = chm_unpacker.ensure_unpacker_choice(interactive=False, allow_hh_fallback=False)
            self.assertEqual((ready, use_hh), (False, False))

            if os.name == "nt":
                ready2, use_hh2 = chm_unpacker.ensure_unpacker_choice(interactive=False, allow_hh_fallback=True)
                self.assertEqual((ready2, use_hh2), (True, True))

    def test_7z_invocation_preserves_spaces_in_source_and_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chm = root / "Program Files" / "Dassault Systemes" / "V5Automation.chm"
            chm.parent.mkdir(parents=True)
            chm.write_bytes(b"ITSF")
            out_dir = root / "My Projects" / "CATalyst Repo" / "data" / "raw"

            captured_cmd = []

            def _fake_run(cmd, **kwargs):
                captured_cmd.extend(cmd)
                (out_dir / "index.htm").write_text("<html>ok</html>", encoding="utf-8")
                return mock.Mock(returncode=0, stderr="")

            with (
                mock.patch.object(chm_unpacker, "_find_7z", return_value="7z"),
                mock.patch.object(chm_unpacker.subprocess, "run", side_effect=_fake_run),
            ):
                ok = chm_unpacker.unpack_chm(chm, out_dir)
                self.assertTrue(ok)
                self.assertEqual(captured_cmd[0], "7z")
                self.assertEqual(captured_cmd[1], "x")
                self.assertEqual(captured_cmd[2], str(chm.resolve()))
                self.assertEqual(captured_cmd[3], f"-o{out_dir.resolve()}")

    def test_parse_user_path_handles_spaces_quotes_powershell_and_mixed_slashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "Folder With Spaces" / "Sub Dir" / "V5Automation.chm"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"ITSF")

            # Quoted path with spaces
            p1 = local_config.parse_user_path(f'"{target}"')
            self.assertEqual(p1.resolve(), target.resolve())

            # PowerShell drag-and-drop syntax: & 'path with spaces'
            p2 = local_config.parse_user_path(f"& '{target}'")
            self.assertEqual(p2.resolve(), target.resolve())

            # Mixed '/' and '\' separators
            mixed = target.as_posix().replace("/Sub Dir/", "\\Sub Dir/")
            p3 = local_config.parse_user_path(mixed)
            self.assertEqual(p3.resolve(), target.resolve())

    def test_join_portable_rel_handles_both_slash_styles(self):
        base = Path("/opt/catia/B27doc/English/online") if os.name != "nt" else Path(r"D:\Docs\B27doc\English\online")
        p_posix = docs_db._join_portable_rel(base, "cceug_C2/images/pic.png")
        p_win = docs_db._join_portable_rel(base, r"cceug_C2\images\pic.png")
        self.assertEqual(p_posix, p_win)
        self.assertEqual(p_posix, base / "cceug_C2" / "images" / "pic.png")

    def test_catenv_blocks_cross_release_plugin_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            b27_inst = root / "Dassault Systemes" / "B27" / "win_b64"
            (b27_inst / "resources" / "msgcatalog").mkdir(parents=True)

            b21_plugin_doc = root / "TY3ToCATIA_WIN64" / "B21" / "win_b64" / "doc" / "English" / "online"
            (b21_plugin_doc / "plugin_C2").mkdir(parents=True)

            catenv_dir = root / "CATEnv"
            catenv_dir.mkdir()
            (catenv_dir / "CATIA_P3.V5-6R2017.B27.txt").write_text(
                f"CATInstallPath={b27_inst}\nCATDocView={root / 'Dassault Systemes' / 'B27doc'}\n",
                encoding="utf-8",
            )
            (catenv_dir / "Ty3CatiaV5.5-B21.txt").write_text(
                f"CATDocView={root / 'TY3ToCATIA_WIN64' / 'B21' / 'win_b64' / 'doc'}\n",
                encoding="utf-8",
            )

            found_doc, found_inst = local_config.discover_from_catenv(catenv_dirs=[catenv_dir])
            self.assertEqual(found_inst, b27_inst.resolve())
            self.assertIsNone(found_doc)

    def test_resolve_chm_from_user_input_accepts_file_or_install_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            b27 = Path(tmp) / "Dassault Systemes" / "B27"
            chm = b27 / "win_b64" / "code" / "bin" / "V5Automation.chm"
            chm.parent.mkdir(parents=True)
            chm.write_bytes(b"ITSF")

            self.assertEqual(installer._resolve_chm_from_user_input(f"& '{chm}'"), chm.resolve())
            self.assertEqual(installer._resolve_chm_from_user_input(str(b27)), chm.resolve())
            self.assertEqual(installer._resolve_chm_from_user_input(str(b27 / "win_b64")), chm.resolve())

    def test_register_mcp_config_preserves_other_servers_and_uses_native_separators(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg_path = root / "mcp_config.json"
            original = {
                "mcpServers": {
                    "kicad-mcp": {"command": "node", "args": ["index.js"]},
                    "catalyst": {
                        "command": "uv",
                        "args": ["run", "src/mcp/server.py"],
                        "env": {"CUSTOM_FLAG": "keep_me"},
                    },
                }
            }
            cfg_path.write_text(json.dumps(original, indent=2), encoding="utf-8")

            b27_inst = root / "Program Files" / "Dassault Systemes" / "B27" / "win_b64"
            b27_inst.mkdir(parents=True)

            out_cfg, bak = installer.register_mcp_config(
                config_path=cfg_path,
                project_root=root / "My Projects" / "CATalyst",
                uv_bin=str(root / "uv" / "uv.exe"),
                install_root=b27_inst,
                doc_root=None,
            )

            self.assertEqual(out_cfg, cfg_path)
            self.assertIsNotNone(bak)
            self.assertTrue(bak.is_file())

            updated = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertEqual(updated["mcpServers"]["kicad-mcp"], original["mcpServers"]["kicad-mcp"])

            cat = updated["mcpServers"]["catalyst"]
            self.assertIn("src.mcp.server", cat["args"])
            self.assertEqual(cat["env"]["CUSTOM_FLAG"], "keep_me")
            self.assertEqual(cat["env"]["PYTHONUTF8"], "1")
            expected_inst = str(b27_inst.parent.resolve())
            self.assertEqual(cat["env"]["CATALYST_INSTALL_ROOT"], expected_inst)
            self.assertNotIn("CATALYST_DOC_ROOT", cat["env"])

    def test_install_ps1_is_pure_ascii_for_powershell_51(self):
        ps1_bytes = (Path(__file__).resolve().parent.parent / "install.ps1").read_bytes()
        try:
            ps1_bytes.decode("ascii")
        except UnicodeDecodeError as exc:
            self.fail(
                f"install.ps1 must stay pure ASCII to avoid Windows PowerShell 5.1 codepage parsing bugs: {exc}"
            )


if __name__ == "__main__":
    unittest.main()
