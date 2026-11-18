"""
5-tier machine-local path discovery & persistence for CATalyst offline docs.
Keeps catalyst_docs.db 100% portable (relative paths only) while giving fresh machines
zero-config auto-detection via Dassault CATEnv + explicit MCP env / local paths.json overrides.

Resolution precedence:
1. Explicit argument / environment variable (CATALYST_DOC_ROOT, CATALYST_INSTALL_ROOT)
2. Machine-local config file: dist/local/paths.json (gitignored)
3. Official Dassault CATEnv files (%ProgramData%/DassaultSystemes/CATEnv/*.txt -> CATDocView / CATInstallPath)
4. Standard install directories (C:/Program Files/Dassault Systemes/B*doc & B*/win_b64)
5. None (caller prompts interactively in CLI or attaches path_setup_hint in MCP response)
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.parser.docs_parser import normalize_doc_root, normalize_install_root

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOCAL_PATHS_CONFIG = PROJECT_ROOT / "dist" / "local" / "paths.json"


def is_running_in_venv() -> bool:
    """Return True if Python is executing inside an isolated virtual environment (.venv / conda)."""
    return (
        getattr(sys, "base_prefix", sys.prefix) != sys.prefix
        or hasattr(sys, "real_prefix")
        or bool(os.environ.get("VIRTUAL_ENV"))
        or bool(os.environ.get("CONDA_PREFIX"))
    )


def _catenv_dirs() -> List[Path]:
    dirs: List[Path] = []
    prog_data = os.environ.get("ProgramData") or os.environ.get("ALLUSERSPROFILE")
    if prog_data:
        dirs.append(Path(prog_data) / "DassaultSystemes" / "CATEnv")
    default_dir = Path(r"C:\ProgramData\DassaultSystemes\CATEnv")
    if default_dir not in dirs:
        dirs.append(default_dir)
    return [d for d in dirs if d.is_dir()]


def discover_from_catenv(
    release_hint: str = "",
    catenv_dirs: Optional[List[Path]] = None,
) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Parse Dassault CATEnv *.txt files for CATDocView and CATInstallPath.
    Handles semicolon-separated multi-path entries and prefers files matching release_hint (e.g. B27).
    """
    dirs = catenv_dirs if catenv_dirs is not None else _catenv_dirs()
    env_files: List[Path] = []
    for d in dirs:
        if d.is_dir():
            env_files.extend(sorted(d.glob("*.txt")))
    if not env_files:
        return None, None

    rel_up = release_hint.strip().upper()

    def _priority(fp: Path) -> Tuple[int, int, str]:
        name_up = fp.name.upper()
        rel_match = 0 if (rel_up and rel_up != "UNKNOWN" and rel_up in name_up) else 1
        catia_pref = 0 if name_up.startswith("CATIA") else 1
        return (rel_match, catia_pref, name_up)

    env_files.sort(key=_priority)

    found_doc: Optional[Path] = None
    found_install: Optional[Path] = None

    for fp in env_files:
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            if k == "CATDocView" and found_doc is None:
                for part in v.split(";"):
                    cand = normalize_doc_root(Path(part.strip())) if part.strip() else None
                    # Verify it looks like a real Bxxdoc online tree (contains *_C2 or *TOC.xml)
                    if cand and (list(cand.glob("*TOC.xml")) or list(cand.glob("*_C2"))):
                        found_doc = cand
                        break
            elif k == "CATInstallPath" and found_install is None:
                for part in v.split(";"):
                    cand = normalize_install_root(Path(part.strip())) if part.strip() else None
                    if cand and (cand / "resources" / "msgcatalog").is_dir():
                        found_install = cand
                        break
        if found_doc and found_install:
            break

    return found_doc, found_install


def load_local_paths_config(config_path: Optional[Path] = None) -> Dict[str, str]:
    path = config_path or LOCAL_PATHS_CONFIG
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_local_paths_config(
    doc_root: Optional[Path] = None,
    install_root: Optional[Path] = None,
    chm_path: Optional[Path] = None,
    release: str = "",
    config_path: Optional[Path] = None,
) -> Path:
    """Persist machine-local roots to gitignored dist/local/paths.json."""
    path = config_path or LOCAL_PATHS_CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    current = load_local_paths_config(path)
    if doc_root:
        current["doc_root"] = str(doc_root)
    if install_root:
        current["install_root"] = str(install_root)
    if chm_path:
        current["chm_path"] = str(chm_path)
    if release and release.lower() != "unknown":
        current["catia_release"] = release.upper()
    path.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def resolve_chm_path(
    explicit: Optional[str | Path] = None,
    release_hint: str = "",
    config_path: Optional[Path] = None,
    catenv_dirs: Optional[List[Path]] = None,
) -> Optional[Path]:
    """
    5-tier resolution for user's licensed V5Automation.chm (BYOD compliance):
    1. Explicit --chm arg or CATALYST_CHM_PATH env var
    2. Machine-local dist/local/paths.json ('chm_path')
    3. Official Dassault CATEnv (<CATInstallPath>/code/bin/V5Automation.chm)
    4. Project local drop-in data/V5Automation.chm (gitignored) or default Program Files
    """
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p.resolve()

    env_val = os.environ.get("CATALYST_CHM_PATH", "").strip()
    if env_val:
        p = Path(env_val)
        if p.is_file():
            return p.resolve()

    local_cfg = load_local_paths_config(config_path)
    if local_cfg.get("chm_path"):
        p = Path(local_cfg["chm_path"])
        if p.is_file():
            return p.resolve()

    inst = resolve_install_root(
        release_hint=release_hint,
        config_path=config_path,
        catenv_dirs=catenv_dirs,
    )
    if inst:
        for rel_sub in (
            Path("code") / "bin" / "V5Automation.chm",
            Path("online") / "V5Automation.chm",
        ):
            cand = inst / rel_sub
            if cand.is_file():
                return cand.resolve()

    local_dropin = PROJECT_ROOT / "data" / "V5Automation.chm"
    if local_dropin.is_file():
        return local_dropin.resolve()

    return None


def resolve_doc_root(
    explicit: Optional[str | Path] = None,
    release_hint: str = "",
    legacy_meta_path: str = "",
    config_path: Optional[Path] = None,
    catenv_dirs: Optional[List[Path]] = None,
) -> Optional[Path]:
    """5-tier resolution for CATIA offline documentation online directory."""
    # Tier 1: Explicit arg or MCP env var
    if explicit:
        norm = normalize_doc_root(Path(explicit))
        if norm:
            return norm
    env_val = os.environ.get("CATALYST_DOC_ROOT", "").strip()
    if env_val:
        norm = normalize_doc_root(Path(env_val))
        if norm:
            return norm

    # Tier 2: Machine-local dist/local/paths.json
    local_cfg = load_local_paths_config(config_path)
    if local_cfg.get("doc_root"):
        norm = normalize_doc_root(Path(local_cfg["doc_root"]))
        if norm:
            return norm

    # Legacy DB metadata fallback (schema v1 compatibility)
    if legacy_meta_path:
        norm = normalize_doc_root(Path(legacy_meta_path))
        if norm:
            return norm

    # Tier 3: Official Dassault CATEnv (CATDocView)
    env_doc, _ = discover_from_catenv(release_hint=release_hint, catenv_dirs=catenv_dirs)
    if env_doc:
        return env_doc

    # Tier 4: Standard default install directory
    base = Path(r"C:\Program Files\Dassault Systemes")
    if base.is_dir():
        rel = release_hint.strip().upper()
        if rel and rel != "UNKNOWN":
            norm = normalize_doc_root(base / f"{rel}doc")
            if norm:
                return norm
        for cand in sorted(base.glob("B*doc"), reverse=True):
            norm = normalize_doc_root(cand)
            if norm:
                return norm

    return None


def resolve_install_root(
    explicit: Optional[str | Path] = None,
    release_hint: str = "",
    legacy_meta_path: str = "",
    config_path: Optional[Path] = None,
    catenv_dirs: Optional[List[Path]] = None,
) -> Optional[Path]:
    """5-tier resolution for CATIA win_b64 installation directory."""
    if explicit:
        norm = normalize_install_root(Path(explicit))
        if norm:
            return norm
    env_val = os.environ.get("CATALYST_INSTALL_ROOT", "").strip()
    if env_val:
        norm = normalize_install_root(Path(env_val))
        if norm:
            return norm

    local_cfg = load_local_paths_config(config_path)
    if local_cfg.get("install_root"):
        norm = normalize_install_root(Path(local_cfg["install_root"]))
        if norm:
            return norm

    if legacy_meta_path:
        norm = normalize_install_root(Path(legacy_meta_path))
        if norm:
            return norm

    _, env_install = discover_from_catenv(release_hint=release_hint, catenv_dirs=catenv_dirs)
    if env_install:
        return env_install

    base = Path(r"C:\Program Files\Dassault Systemes")
    if base.is_dir():
        rel = release_hint.strip().upper()
        if rel and rel != "UNKNOWN":
            norm = normalize_install_root(base / rel)
            if norm and (norm / "resources" / "msgcatalog").is_dir():
                return norm
        for cand in sorted(base.glob("B*"), reverse=True):
            if cand.name.lower().endswith("doc"):
                continue
            norm = normalize_install_root(cand)
            if norm and (norm / "resources" / "msgcatalog").is_dir():
                return norm

    return None
