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
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, urlunparse

from src.parser.docs_parser import (
    detect_release_from_path,
    normalize_doc_root,
    normalize_install_root,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOCAL_PATHS_CONFIG = PROJECT_ROOT / "dist" / "local" / "paths.json"


def _strip_user_input(raw: Optional[str | Path]) -> str:
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    # Handle PowerShell drag-and-drop format: & 'C:\Program Files\...'
    if text.startswith("& ") and len(text) > 2:
        text = text[2:].strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        text = text[1:-1].strip()
    else:
        text = text.strip('"').strip("'")
    return text


def is_http_url(value: Optional[str | Path]) -> bool:
    """Return True if value looks like an http:// or https:// URL prefix."""
    text = _strip_user_input(value)
    low = text.lower()
    return low.startswith("http://") or low.startswith("https://")


def is_unc_path(value: Optional[str | Path]) -> bool:
    """Return True if value looks like a Samba/UNC network path (\\\\server\\share or //server/share)."""
    text = _strip_user_input(value)
    if is_http_url(text):
        return False
    return text.startswith("\\\\") or (text.startswith("//") and not text.startswith("///"))


def classify_location_scheme(value: Optional[str | Path]) -> Optional[str]:
    """Classify a resolved root prefix as 'http', 'smb', 'local', or None."""
    if not value:
        return None
    if is_http_url(value):
        return "http"
    if is_unc_path(value):
        return "smb"
    return "local"


def normalize_http_doc_root(raw: str | Path) -> Optional[str]:
    """
    Normalize an HTTP(S) doc root URL so it points to the online base directory:
    - Strips trailing slashes and default *.htm/*.html entry pages
    - Appends /English/online when given a top-level Bxxdoc URL (e.g. https://docs.example.com/B27doc)
    """
    text = _strip_user_input(raw)
    if not is_http_url(text):
        return None
    parsed = urlparse(text)
    if not parsed.netloc:
        return None

    path_parts = [seg for seg in parsed.path.split("/") if seg]
    if path_parts and path_parts[-1].lower().endswith((".htm", ".html")):
        path_parts.pop()

    low_parts = [seg.lower() for seg in path_parts]
    if not low_parts:
        pass
    elif low_parts[-1] == "online":
        pass
    elif low_parts[-1] == "english":
        path_parts.append("online")
    else:
        path_parts.extend(["English", "online"])

    clean_path = "/" + "/".join(path_parts) if path_parts else ""
    return urlunparse((parsed.scheme.lower(), parsed.netloc, clean_path, "", "", "")).rstrip("/")


def normalize_http_install_root(raw: str | Path) -> Optional[str]:
    """Normalize an HTTP(S) install root URL by stripping quotes, query/fragment, and trailing slash."""
    text = _strip_user_input(raw)
    if not is_http_url(text):
        return None
    parsed = urlparse(text)
    if not parsed.netloc:
        return None
    path_parts = [seg for seg in parsed.path.split("/") if seg]
    clean_path = "/" + "/".join(path_parts) if path_parts else ""
    return urlunparse((parsed.scheme.lower(), parsed.netloc, clean_path, "", "", "")).rstrip("/")


def parse_user_path(raw: Optional[str | Path]) -> Optional[Path]:
    """
    Cross-platform user/config filesystem path parser:
    - Strips surrounding quotes and PowerShell drag-and-drop '& ' prefix.
    - Returns None for http(s):// URLs (handled by normalize_http_* helpers).
    - Expands '~' user home directory.
    - Normalizes mixed '/' and '\\' separators for the active OS while preserving UNC prefixes.
    - On POSIX, unescapes terminal drag-and-drop '\\ ' spaces when needed.
    """
    text = _strip_user_input(raw)
    if not text or is_http_url(text):
        return None

    expanded = os.path.expanduser(text)
    if os.name == "nt":
        # Windows accepts both '/' and '\\'; normpath preserves leading '\\\\server\\share' UNC prefix
        return Path(os.path.normpath(expanded))

    p = Path(expanded)
    if not p.exists() and "\\ " in expanded:
        unescaped = Path(expanded.replace("\\ ", " "))
        if unescaped.exists():
            return unescaped
    return p


def is_running_in_venv() -> bool:
    """Return True if Python is executing inside an isolated virtual environment (.venv / conda)."""
    return (
        getattr(sys, "base_prefix", sys.prefix) != sys.prefix
        or hasattr(sys, "real_prefix")
        or bool(os.environ.get("VIRTUAL_ENV"))
        or bool(os.environ.get("CONDA_PREFIX"))
    )


def _catenv_dirs() -> List[Path]:
    if os.name != "nt":
        return []
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
    Handles semicolon-separated multi-path entries, prefers files matching release_hint (e.g. B27),
    and enforces release alignment so third-party plugin docs from another release (e.g. B21)
    are never mixed with the active CATIA installation (e.g. B27).
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

    install_candidates: List[Tuple[Path, str, bool]] = []
    doc_candidates: List[Tuple[Path, str, bool, bool]] = []

    for fp in env_files:
        is_official_env = fp.name.upper().startswith("CATIA")
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
            if k == "CATInstallPath":
                for part in v.split(";"):
                    cand = normalize_install_root(Path(part.strip())) if part.strip() else None
                    if cand and (cand / "resources" / "msgcatalog").is_dir():
                        cand_rel = detect_release_from_path(cand).upper()
                        install_candidates.append((cand, cand_rel, is_official_env))
            elif k == "CATDocView":
                for part in v.split(";"):
                    cand = normalize_doc_root(Path(part.strip())) if part.strip() else None
                    if not cand:
                        continue
                    has_toc = bool(list(cand.glob("*TOC.xml")))
                    has_modules = bool(list(cand.glob("*_C2")))
                    if has_toc or has_modules:
                        cand_rel = detect_release_from_path(cand).upper()
                        doc_candidates.append((cand, cand_rel, is_official_env, has_toc))

    def _matches_release(cand_rel: str, expected_rel: str) -> bool:
        if not expected_rel or expected_rel == "UNKNOWN":
            return True
        if not cand_rel or cand_rel == "UNKNOWN":
            return True
        return cand_rel == expected_rel

    found_install: Optional[Path] = None
    for cand, cand_rel, _ in install_candidates:
        if _matches_release(cand_rel, rel_up):
            found_install = cand
            break

    # Lock doc discovery to the active release (explicit hint or detected install release)
    target_rel = rel_up if (rel_up and rel_up != "UNKNOWN") else (
        detect_release_from_path(found_install).upper() if found_install else ""
    )

    found_doc: Optional[Path] = None
    # Pass 1: prefer release-aligned docs from official CATIA*.txt or with a full TOC
    for cand, cand_rel, is_official_env, has_toc in doc_candidates:
        if not _matches_release(cand_rel, target_rel):
            continue
        if is_official_env or has_toc:
            found_doc = cand
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
    doc_root: Optional[Union[Path, str]] = None,
    install_root: Optional[Union[Path, str]] = None,
    chm_path: Optional[Union[Path, str]] = None,
    release: str = "",
    config_path: Optional[Path] = None,
) -> Path:
    """Persist machine-local roots (local path, SMB UNC, or HTTP(S) URL) to dist/local/paths.json."""
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
    5-tier resolution for local V5Automation.chm:
    1. Explicit --chm arg or CATALYST_CHM_PATH env var
    2. Machine-local dist/local/paths.json ('chm_path')
    3. Official Dassault CATEnv (<CATInstallPath>/code/bin/V5Automation.chm)
    4. Project local drop-in data/V5Automation.chm (gitignored) or default install directory
    """
    if explicit:
        p = parse_user_path(explicit)
        if p and p.is_file():
            return p.resolve()

    env_val = os.environ.get("CATALYST_CHM_PATH", "").strip()
    if env_val:
        p = parse_user_path(env_val)
        if p and p.is_file():
            return p.resolve()

    local_cfg = load_local_paths_config(config_path)
    if local_cfg.get("chm_path"):
        p = parse_user_path(local_cfg["chm_path"])
        if p and p.is_file():
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
        norm = normalize_doc_root(parse_user_path(explicit))
        if norm:
            return norm
    env_val = os.environ.get("CATALYST_DOC_ROOT", "").strip()
    if env_val:
        norm = normalize_doc_root(parse_user_path(env_val))
        if norm:
            return norm

    # Tier 2: Machine-local dist/local/paths.json
    local_cfg = load_local_paths_config(config_path)
    if local_cfg.get("doc_root"):
        norm = normalize_doc_root(parse_user_path(local_cfg["doc_root"]))
        if norm:
            return norm

    # Legacy DB metadata fallback (schema v1 compatibility)
    if legacy_meta_path:
        norm = normalize_doc_root(parse_user_path(legacy_meta_path))
        if norm:
            return norm

    # Tier 3: Official Dassault CATEnv (CATDocView)
    env_doc, _ = discover_from_catenv(release_hint=release_hint, catenv_dirs=catenv_dirs)
    if env_doc:
        return env_doc

    # Tier 4: Standard default install directory (Windows only)
    if os.name == "nt":
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
        norm = normalize_install_root(parse_user_path(explicit))
        if norm:
            return norm
    env_val = os.environ.get("CATALYST_INSTALL_ROOT", "").strip()
    if env_val:
        norm = normalize_install_root(parse_user_path(env_val))
        if norm:
            return norm

    local_cfg = load_local_paths_config(config_path)
    if local_cfg.get("install_root"):
        norm = normalize_install_root(parse_user_path(local_cfg["install_root"]))
        if norm:
            return norm

    if legacy_meta_path:
        norm = normalize_install_root(parse_user_path(legacy_meta_path))
        if norm:
            return norm

    _, env_install = discover_from_catenv(release_hint=release_hint, catenv_dirs=catenv_dirs)
    if env_install:
        return env_install

    if os.name == "nt":
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


def resolve_doc_root_location(
    explicit: Optional[str | Path] = None,
    release_hint: str = "",
    legacy_meta_path: str = "",
    config_path: Optional[Path] = None,
    catenv_dirs: Optional[List[Path]] = None,
) -> Optional[Union[Path, str]]:
    """
    Runtime 5-tier doc root resolver supporting local filesystem (default), Samba UNC, and optional HTTP(S) URL.
    Returns Path for local/SMB filesystem directories, str for http(s):// base URLs, or None.
    """
    # Tier 1: Explicit arg or MCP env var
    if explicit:
        if is_http_url(explicit):
            return normalize_http_doc_root(explicit)
        norm = normalize_doc_root(parse_user_path(explicit))
        if norm:
            return norm

    env_val = os.environ.get("CATALYST_DOC_ROOT", "").strip()
    if env_val:
        if is_http_url(env_val):
            return normalize_http_doc_root(env_val)
        norm = normalize_doc_root(parse_user_path(env_val))
        if norm:
            return norm

    # Tier 2: Machine-local dist/local/paths.json
    local_cfg = load_local_paths_config(config_path)
    if local_cfg.get("doc_root"):
        cfg_val = local_cfg["doc_root"]
        if is_http_url(cfg_val):
            return normalize_http_doc_root(cfg_val)
        norm = normalize_doc_root(parse_user_path(cfg_val))
        if norm:
            return norm

    # Tiers 3-4: Legacy metadata, CATEnv, and standard local directories
    return resolve_doc_root(
        explicit=None,
        release_hint=release_hint,
        legacy_meta_path=legacy_meta_path,
        config_path=config_path,
        catenv_dirs=catenv_dirs,
    )


def resolve_install_root_location(
    explicit: Optional[str | Path] = None,
    release_hint: str = "",
    legacy_meta_path: str = "",
    config_path: Optional[Path] = None,
    catenv_dirs: Optional[List[Path]] = None,
) -> Optional[Union[Path, str]]:
    """
    Runtime 5-tier install root resolver supporting local filesystem (default), Samba UNC, and optional HTTP(S) URL.
    Returns Path for local/SMB filesystem directories, str for http(s):// base URLs, or None.
    """
    if explicit:
        if is_http_url(explicit):
            return normalize_http_install_root(explicit)
        norm = normalize_install_root(parse_user_path(explicit))
        if norm:
            return norm

    env_val = os.environ.get("CATALYST_INSTALL_ROOT", "").strip()
    if env_val:
        if is_http_url(env_val):
            return normalize_http_install_root(env_val)
        norm = normalize_install_root(parse_user_path(env_val))
        if norm:
            return norm

    local_cfg = load_local_paths_config(config_path)
    if local_cfg.get("install_root"):
        cfg_val = local_cfg["install_root"]
        if is_http_url(cfg_val):
            return normalize_http_install_root(cfg_val)
        norm = normalize_install_root(parse_user_path(cfg_val))
        if norm:
            return norm

    return resolve_install_root(
        explicit=None,
        release_hint=release_hint,
        legacy_meta_path=legacy_meta_path,
        config_path=config_path,
        catenv_dirs=catenv_dirs,
    )
