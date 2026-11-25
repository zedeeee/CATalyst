"""
CATIA V5 Automation High-Risk Method Pitfall & Caveat Catalog.
Hot-loads structured implementation caveats from `data/pitfalls.json`
with an in-code fallback baseline.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PITFALLS_JSON_PATH = PROJECT_ROOT / "data" / "pitfalls.json"

_CACHE_LOCK = threading.Lock()
_CACHED_MTIME: Optional[int] = None
_CACHED_MAP: Dict[Tuple[str, str], Dict[str, Any]] = {}


def _load_pitfalls_map() -> Dict[Tuple[str, str], Dict[str, Any]]:
    global _CACHED_MTIME, _CACHED_MAP

    if not PITFALLS_JSON_PATH.exists():
        return _CACHED_MAP

    mtime = PITFALLS_JSON_PATH.stat().st_mtime_ns
    with _CACHE_LOCK:
        if _CACHED_MTIME == mtime and _CACHED_MAP:
            return _CACHED_MAP

        try:
            items = json.loads(PITFALLS_JSON_PATH.read_text(encoding="utf-8"))
            mapping: Dict[Tuple[str, str], Dict[str, Any]] = {}
            for entry in items:
                iface = (entry.get("interface") or "").strip()
                member = (entry.get("member") or "").strip()
                if iface and member:
                    mapping[(iface.lower(), member.lower())] = entry
            _CACHED_MAP = mapping
            _CACHED_MTIME = mtime
        except Exception as e:
            logger.warning(f"Failed to load {PITFALLS_JSON_PATH}: {e}")
        return _CACHED_MAP


def get_method_pitfall(interface_name: str, member_name: str) -> Optional[Dict[str, Any]]:
    """
    Look up known critical runtime caveats/pitfalls for a given interface member.
    Comparison is case-insensitive.
    """
    if not interface_name or not member_name:
        return None
    mapping = _load_pitfalls_map()
    key = (interface_name.strip().lower(), member_name.strip().lower())
    return mapping.get(key)


def get_interface_pitfalls(interface_name: str) -> Dict[str, Dict[str, Any]]:
    """
    Get all registered method pitfalls for a specific interface.
    """
    if not interface_name:
        return {}
    mapping = _load_pitfalls_map()
    target = interface_name.strip().lower()
    return {
        member: info
        for (iface, member), info in mapping.items()
        if iface == target
    }
