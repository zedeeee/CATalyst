#!/usr/bin/env python
"""
One-Click Installer for CATalyst MCP Server (Isolated Virtual Environment).

End-to-end automated workflow:
1. Auto-detect local CATIA V5 paths (V5Automation.chm, install root, release-aligned Bxxdoc).
   If a required/optional path cannot be found automatically, interactively prompts the user to specify it.
2. Check CHM unpacker (7-Zip strongly recommended); if missing, ask the user whether to exit and install
   7-Zip, specify a local 7z path, or explicitly continue with Windows hh.exe.
3. Build dist/catalyst.db (Core COM API + Recipes) and run 8/8 smoke tests.
4. Optionally build dist/local/catalyst_docs.db if a release-aligned Bxxdoc directory is available.
5. Safely merge `mcpServers.catalyst` into the target MCP client config (Antigravity / Cursor / Claude)
   with automatic `.bak` backup and zero impact on other configured MCP servers.
6. Run an end-to-end MCP server tool self-check and print a ready-to-use summary.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _parse_path(raw: str) -> Optional[Path]:
    from src.engine.local_config import parse_user_path

    return parse_user_path(raw)


def _configure_stdio_utf8() -> None:
    """Avoid Windows GBK console encoding crashes when printing Unicode status markers."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _is_interactive(assume_yes: bool) -> bool:
    return (not assume_yes) and bool(sys.stdin and sys.stdin.isatty())


def _resolve_chm_from_user_input(raw: str) -> Optional[Path]:
    """
    Accept either a direct path to V5Automation.chm OR a CATIA install directory
    (e.g. 'C:/Program Files/Dassault Systemes/B27' or '.../win_b64').
    """
    p = _parse_path(raw)
    if not p:
        return None
    if p.is_file() and p.suffix.lower() == ".chm":
        return p.resolve()

    if p.is_dir():
        candidates = [
            p / "V5Automation.chm",
            p / "code" / "bin" / "V5Automation.chm",
            p / "win_b64" / "code" / "bin" / "V5Automation.chm",
            p / "intel_a" / "code" / "bin" / "V5Automation.chm",
            p / "online" / "V5Automation.chm",
            p / "win_b64" / "online" / "V5Automation.chm",
            p / "intel_a" / "online" / "V5Automation.chm",
        ]
        for cand in candidates:
            if cand.is_file():
                return cand.resolve()
    return None


def _prompt_for_chm() -> Optional[Path]:
    sample = r"C:\Program Files\Dassault Systemes\B27" if os.name == "nt" else "/path/to/V5Automation.chm"
    print("\n[ACTION REQUIRED] 未自动检测到 V5Automation.chm（核心 COM API 数据库必需文件）。")
    print(f"请输入 V5Automation.chm 的完整路径，或输入 CATIA 安装目录（例如 {sample}），")
    print("支持直接拖入文件/文件夹（兼容含空格路径与 `/` / `\\`）；输入 q 退出：")
    while True:
        try:
            raw = input("V5Automation.chm / CATIA 目录 > ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not raw or raw.lower() in ("q", "quit", "exit"):
            return None
        resolved = _resolve_chm_from_user_input(raw)
        if resolved:
            print(f"  [OK] 已定位 CHM: {resolved}")
            return resolved
        print(f"  [INVALID] 未在该路径下找到 V5Automation.chm: {raw}，请重新输入（或输入 q 退出）。")


def _prompt_for_doc_root(release: str) -> Optional[Path]:
    from src.parser.docs_parser import detect_release_from_path, normalize_doc_root

    rel_label = release if release and release != "UNKNOWN" else "Bxx"
    print(f"\n[OPTIONAL] 未自动检测到同版本（{rel_label}）CATIA 离线帮助文档目录（Bxxdoc）。")
    print("  说明：不构建离线文档也能完整使用全部 6 个核心 COM API / Recipe MCP 工具。")
    print("  如果你本机有对应版本的 Bxxdoc 目录，可在此输入路径（或直接回车跳过）：")
    while True:
        try:
            raw = input("Bxxdoc 目录（回车跳过） > ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not raw:
            print("  [SKIP] 已跳过离线帮助文档扩展，后续随时可运行 `uv run python build_docs.py` 补建。")
            return None
        parsed = _parse_path(raw)
        norm = normalize_doc_root(parsed) if parsed else None
        if norm and (list(norm.glob("*TOC.xml")) or list(norm.glob("*_C2"))):
            doc_rel = detect_release_from_path(norm).upper()
            if release and release != "UNKNOWN" and doc_rel != "UNKNOWN" and doc_rel != release:
                print(f"  [WARN] 检测到的文档版本 ({doc_rel}) 与当前 CATIA 版本 ({release}) 不一致。")
                try:
                    confirm = input("  仍要使用该目录吗？[y/N]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    return None
                if confirm not in ("y", "yes"):
                    continue
            print(f"  [OK] 已定位离线文档目录: {norm}")
            return norm
        print(f"  [INVALID] 该路径不是有效的 CATIA Bxxdoc 离线文档目录: {raw}，请重试或直接回车跳过。")


def find_uv_executable() -> str:
    """Resolve absolute path to uv so GUI MCP hosts work even without shell PATH inheritance."""
    found = shutil.which("uv")
    if found:
        return str(Path(found).resolve())

    home = Path.home()
    candidates = [
        home / ".local" / "bin" / ("uv.exe" if os.name == "nt" else "uv"),
        home / ".cargo" / "bin" / ("uv.exe" if os.name == "nt" else "uv"),
    ]
    for cand in candidates:
        if cand.is_file():
            return str(cand.resolve())
    return "uv"


def resolve_client_config_path(client: str, explicit_config: str = "") -> Path:
    """Return the target MCP client config path."""
    if explicit_config:
        parsed = _parse_path(explicit_config)
        if not parsed:
            raise ValueError(f"Invalid --config path: {explicit_config}")
        return parsed.resolve()

    home = Path.home()
    client_key = client.strip().lower()
    if client_key == "antigravity":
        return home / ".gemini" / "config" / "mcp_config.json"
    if client_key == "cursor":
        return home / ".cursor" / "mcp.json"
    if client_key == "claude":
        if os.name == "nt":
            appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
            return appdata / "Claude" / "claude_desktop_config.json"
        if sys.platform == "darwin":
            return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        return home / ".config" / "Claude" / "claude_desktop_config.json"

    raise ValueError(f"Unsupported client '{client}'. Use antigravity, cursor, claude, or --config.")


def _top_level_catia_dir(path: Optional[Path]) -> Optional[str]:
    """
    Normalize .../B27/win_b64 -> .../B27 and .../B27doc/English/online -> .../B27doc,
    returning native OS path separators consistent with mcp_config.json command/args.
    """
    if not path:
        return None
    p = path.resolve()
    if p.name.lower() in ("win_b64", "intel_a"):
        return str(p.parent)
    if p.name.lower() == "online" and p.parent.name.lower() == "english":
        return str(p.parent.parent)
    return str(p)


def build_catalyst_mcp_entry(
    project_root: Path,
    uv_bin: str,
    install_root: Optional[Path] = None,
    doc_root: Optional[Path] = None,
    existing_env: Optional[Dict[str, str]] = None,
) -> Dict[str, object]:
    """Build the normalized mcpServers.catalyst entry dict."""
    env_block: Dict[str, str] = dict(existing_env or {})
    env_block["PYTHONIOENCODING"] = "utf-8"
    env_block["PYTHONUTF8"] = "1"

    inst_env = _top_level_catia_dir(install_root)
    if inst_env:
        env_block["CATALYST_INSTALL_ROOT"] = inst_env
    doc_env = _top_level_catia_dir(doc_root)
    if doc_env:
        env_block["CATALYST_DOC_ROOT"] = doc_env

    return {
        "command": uv_bin,
        "args": [
            "--directory",
            str(project_root.resolve()),
            "run",
            "python",
            "-m",
            "src.mcp.server",
        ],
        "env": env_block,
    }


def register_mcp_config(
    config_path: Path,
    project_root: Path,
    uv_bin: str,
    install_root: Optional[Path] = None,
    doc_root: Optional[Path] = None,
) -> Tuple[Path, Optional[Path]]:
    """
    Safely merge mcpServers.catalyst into config_path without modifying any other MCP entries.
    Creates a `.bak` backup if the file already exists.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Optional[Path] = None
    data: Dict[str, object] = {}

    if config_path.is_file():
        raw_text = config_path.read_text(encoding="utf-8")
        if raw_text.strip():
            data = json.loads(raw_text)
            if not isinstance(data, dict):
                raise ValueError(f"Existing MCP config is not a JSON object: {config_path}")
        backup_path = config_path.with_suffix(config_path.suffix + ".bak")
        shutil.copy2(config_path, backup_path)

    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
        data["mcpServers"] = servers

    existing_entry = servers.get("catalyst")
    existing_env: Dict[str, str] = {}
    if isinstance(existing_entry, dict) and isinstance(existing_entry.get("env"), dict):
        existing_env = {str(k): str(v) for k, v in existing_entry["env"].items()}

    servers["catalyst"] = build_catalyst_mcp_entry(
        project_root=project_root,
        uv_bin=uv_bin,
        install_root=install_root,
        doc_root=doc_root,
        existing_env=existing_env,
    )

    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return config_path, backup_path


def run_mcp_self_check(expect_docs_db: bool = False) -> Dict[str, object]:
    """Execute end-to-end verification against src.mcp.server tool functions."""
    import src.mcp.server as mcp_server

    # Reset cached singletons so the check loads freshly built DB files
    mcp_server._db_instance = None
    mcp_server._docs_db_instance = None

    iface_res = json.loads(mcp_server.get_catia_interface(interface_name="Pad", member_name="GetDirection"))
    if iface_res.get("isError") or iface_res.get("name") != "Pad":
        raise RuntimeError(f"MCP get_catia_interface failed: {iface_res}")

    recipe_res = json.loads(mcp_server.search_catia_recipes(query="STEP", limit=1))
    if recipe_res.get("isError") or recipe_res.get("total_matches", 0) < 1:
        raise RuntimeError(f"MCP search_catia_recipes failed: {recipe_res}")

    docs_active = False
    docs_db = mcp_server.get_docs_db()
    if docs_db is not None:
        docs_active = True
    elif expect_docs_db:
        raise RuntimeError("Expected dist/local/catalyst_docs.db to be active, but get_docs_db() returned None.")

    return {
        "core_ok": True,
        "docs_active": docs_active,
        "active_tools": 10 if docs_active else 6,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    prog = os.environ.get("CATALYST_INSTALLER_PROG", "").strip() or None
    parser = argparse.ArgumentParser(
        prog=prog,
        description="One-click installer for CATalyst MCP Server (local DB build + MCP registration).",
    )
    parser.add_argument("--chm", default="", help="Explicit path to local V5Automation.chm.")
    parser.add_argument("--install-root", default="", help="Explicit path to CATIA Bxx or Bxx/win_b64.")
    parser.add_argument("--doc-root", default="", help="Explicit path to CATIA Bxxdoc offline docs (optional).")
    parser.add_argument("--release", default="", help="Explicit CATIA release tag (e.g. B27).")
    parser.add_argument("--7z", dest="seven_zip", default="", help="Explicit path to 7z/7za executable (recommended).")
    parser.add_argument(
        "--use-hh",
        action="store_true",
        help="Windows only: explicitly authorize hh.exe when 7-Zip is unavailable (non-interactive mode).",
    )
    parser.add_argument(
        "--client",
        default="antigravity",
        choices=["antigravity", "cursor", "claude"],
        help="Target MCP client to register (default: antigravity).",
    )
    parser.add_argument("--config", default="", help="Custom MCP config JSON path (overrides --client).")
    parser.add_argument("--skip-docs", action="store_true", help="Skip optional offline Bxxdoc DB build.")
    parser.add_argument("--skip-mcp-config", action="store_true", help="Build DBs only; do not edit MCP config.")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuilding existing SQLite databases.")
    parser.add_argument("--yes", "-y", action="store_true", help="Non-interactive mode (no prompts).")
    return parser


def main() -> None:
    _configure_stdio_utf8()

    args = build_arg_parser().parse_args()

    if sys.version_info < (3, 10):
        print(f"[ERROR] CATalyst requires Python 3.10+, current: {sys.version.split()[0]}")
        sys.exit(1)

    # Deferred project imports so `--help` works instantly even before `uv sync` installs dependencies
    from src.engine.local_config import (
        LOCAL_PATHS_CONFIG,
        is_running_in_venv,
        parse_user_path,
        resolve_chm_path,
        resolve_doc_root,
        resolve_install_root,
        save_local_paths_config,
    )
    from src.parser.chm_unpacker import detect_unpacker_backend, ensure_unpacker_choice
    from src.parser.docs_parser import (
        detect_release_from_path,
        normalize_install_root,
    )

    if args.seven_zip:
        seven_zip_path = parse_user_path(args.seven_zip)
        if not seven_zip_path or not seven_zip_path.is_file():
            print(f"[ERROR] 指定的 7z 可执行文件不存在: {args.seven_zip}")
            sys.exit(1)
        os.environ["CATALYST_7Z_PATH"] = str(seven_zip_path.resolve())

    interactive = _is_interactive(args.yes)

    print("============================================================")
    print("  CATalyst MCP One-Click Installer (Isolated .venv)         ")
    print("============================================================")
    if not is_running_in_venv():
        entry_hint = ".\\install.ps1" if os.name == "nt" else "./install.sh"
        print(f"[WARN] 当前运行在全局 Python ({sys.executable})，建议通过 `{entry_hint}` 或 `uv run python install.py` 运行。")

    # 1. Resolve local CATIA installation, CHM, and release-aligned docs
    install_root = resolve_install_root(explicit=args.install_root or None, release_hint=args.release)
    chm_path = resolve_chm_path(explicit=args.chm or None, release_hint=args.release)

    if not chm_path and install_root:
        chm_path = _resolve_chm_from_user_input(str(install_root))

    core_db = PROJECT_ROOT / "dist" / "catalyst.db"
    raw_dir = PROJECT_ROOT / "data" / "raw"
    has_raw_html = raw_dir.is_dir() and next(raw_dir.rglob("*.htm"), None) is not None
    need_core_build = args.rebuild or not core_db.is_file()
    need_chm_unpack = need_core_build and (args.rebuild or not has_raw_html)

    allow_hh = args.use_hh
    if need_chm_unpack:
        ready, allow_hh = ensure_unpacker_choice(interactive=interactive, allow_hh_fallback=allow_hh)
        if not ready:
            sys.exit(1)

    unpacker_kind, unpacker_path = detect_unpacker_backend()

    if need_chm_unpack and not chm_path:
        if interactive:
            chm_path = _prompt_for_chm()
        if not chm_path:
            print("\n[ERROR] 未找到 V5Automation.chm，无法构建核心数据库 dist/catalyst.db。")
            print("        请重新运行并通过 `--chm \"<path/to/V5Automation.chm>\"` 指定路径。")
            sys.exit(1)

    if chm_path and not install_root:
        # Derive install root if CHM resides under <Bxx>/win_b64/code/bin/V5Automation.chm
        norm_inst = normalize_install_root(chm_path.parent.parent.parent)
        if norm_inst and (norm_inst / "resources" / "msgcatalog").is_dir():
            install_root = norm_inst

    release = args.release.strip().upper()
    if not release:
        for cand in (install_root, chm_path):
            if cand:
                det = detect_release_from_path(cand).upper()
                if det != "UNKNOWN":
                    release = det
                    break

    doc_root: Optional[Path] = None
    if not args.skip_docs:
        doc_root = resolve_doc_root(explicit=args.doc_root or None, release_hint=release)
        if not doc_root and interactive:
            doc_root = _prompt_for_doc_root(release)

    if unpacker_kind == "7z":
        unpacker_label = f"7-Zip [推荐] ({unpacker_path})"
    elif unpacker_kind == "hh" and allow_hh:
        unpacker_label = f"Windows hh.exe [已显式启用] ({unpacker_path})"
    elif unpacker_kind == "hh":
        unpacker_label = f"未检测到 7-Zip（无需解包时可直接复用已有库）"
    else:
        unpacker_label = "(无，仅支持复用已有 dist/catalyst.db 或 data/raw)"

    print("\n[1/4] 本地环境识别结果：")
    print(f"  Project Root : {PROJECT_ROOT}")
    print(f"  Python Env   : {sys.executable} (Python {sys.version.split()[0]})")
    print(f"  CHM Unpacker : {unpacker_label}")
    print(f"  CATIA Release: {release or 'UNKNOWN'}")
    print(f"  V5Automation : {chm_path or ('(复用已有 data/raw)' if has_raw_html and need_core_build else '(复用已有 dist/catalyst.db)')}")
    print(f"  Install Root : {install_root or '(未检测到)'}")
    print(f"  Offline Docs : {doc_root or '(未安装/已跳过，6 个核心 API/Recipe 工具仍完全可用)'}")

    if chm_path or install_root or doc_root:
        save_local_paths_config(
            doc_root=doc_root,
            install_root=install_root,
            chm_path=chm_path,
            release=release,
        )

    # 2. Build Core API DB (dist/catalyst.db)
    print("\n[2/4] 初始化核心 API 数据库 (dist/catalyst.db)...")
    if need_core_build:
        build_cmd = [sys.executable, str(PROJECT_ROOT / "build.py"), "--yes"]
        if chm_path:
            build_cmd.extend(["--chm", str(chm_path)])
        if allow_hh:
            build_cmd.append("--use-hh")
        if args.rebuild:
            build_cmd.append("--force-unpack")
        sys.stdout.flush()
        subprocess.run(build_cmd, cwd=str(PROJECT_ROOT), check=True)
    else:
        print(f"  [SKIP] 已存在核心数据库: {core_db}（如需强制重建请加 --rebuild）")

    # 3. Optional Offline Docs DB (dist/local/catalyst_docs.db)
    docs_db = PROJECT_ROOT / "dist" / "local" / "catalyst_docs.db"
    built_docs = False
    if not args.skip_docs and doc_root:
        if args.rebuild or not docs_db.is_file():
            print("\n[3/4] 构建离线文档扩展库 (dist/local/catalyst_docs.db)...")
            docs_cmd = [
                sys.executable,
                str(PROJECT_ROOT / "build_docs.py"),
                "--doc-root",
                str(doc_root),
                "--yes",
            ]
            if install_root:
                docs_cmd.extend(["--install-root", str(install_root)])
            if release:
                docs_cmd.extend(["--release", release])
            sys.stdout.flush()
            subprocess.run(docs_cmd, cwd=str(PROJECT_ROOT), check=True)
            built_docs = True
        else:
            print(f"\n[3/4] [SKIP] 已存在离线文档库: {docs_db}")
            built_docs = True
    else:
        entry_cmd = ".\\install.ps1" if os.name == "nt" else "./install.sh"
        rel_tag = f"{release}doc" if release and release != "UNKNOWN" else "Bxxdoc"
        if args.skip_docs:
            print("\n[3/4] 已按 --skip-docs 跳过可选离线文档库。")
        else:
            print(f"\n[3/4] 未检测到同版本离线文档目录（{rel_tag}），已跳过可选离线文档库。")
            print(f"      [TIP] 如本机其他目录装有 {rel_tag}，可随时运行以下命令补建并激活全部 10/10 个 MCP 工具：")
            print(f'            {entry_cmd} --doc-root "<path-to-{rel_tag}>"')

    # 4. Register MCP Server config
    mcp_cfg_path: Optional[Path] = None
    backup_path: Optional[Path] = None
    if not args.skip_mcp_config:
        print(f"\n[4/4] 写入 MCP 客户端配置 ({args.config or args.client})...")
        target_cfg = resolve_client_config_path(args.client, args.config)
        uv_bin = find_uv_executable()
        try:
            mcp_cfg_path, backup_path = register_mcp_config(
                config_path=target_cfg,
                project_root=PROJECT_ROOT,
                uv_bin=uv_bin,
                install_root=install_root,
                doc_root=doc_root,
            )
            print(f"  [OK] 已更新 MCP 配置: {mcp_cfg_path}")
            if backup_path:
                print(f"  [OK] 原配置已备份至: {backup_path}")
        except (PermissionError, json.JSONDecodeError, ValueError, OSError) as exc:
            snippet = json.dumps(
                {
                    "mcpServers": {
                        "catalyst": build_catalyst_mcp_entry(
                            project_root=PROJECT_ROOT,
                            uv_bin=uv_bin,
                            install_root=install_root,
                            doc_root=doc_root,
                        )
                    }
                },
                indent=2,
                ensure_ascii=False,
            )
            print(f"  [WARN] 无法自动写入 {target_cfg} ({exc})。")
            print("  请手动将以下 `catalyst` 条目合并到你的 MCP 配置文件中：")
            print(snippet)
    else:
        print("\n[4/4] 已按 --skip-mcp-config 跳过 MCP 配置写入。")

    # 5. End-to-End MCP Self-Check
    print("\n[VERIFY] 执行 MCP 工具端到端验收...")
    status = run_mcp_self_check(expect_docs_db=built_docs)
    print(f"  [PASS] 核心接口查询与社区 Recipe 检索均已就绪（已激活 {status['active_tools']}/10 个 MCP 工具）。")

    print("\n============================================================")
    print("  CATalyst MCP 安装完成！")
    print("============================================================")
    print(f"  Core DB      : {core_db}")
    print(f"  Docs DB      : {docs_db if docs_db.is_file() else '(未构建，可选)'}")
    print(f"  Local Paths  : {LOCAL_PATHS_CONFIG}")
    if mcp_cfg_path:
        print(f"  MCP Config   : {mcp_cfg_path}")
        print("  提示：如果客户端尚未加载最新配置，请在 MCP 面板点击 Refresh 或重启客户端。")


if __name__ == "__main__":
    main()
