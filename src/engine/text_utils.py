"""
Shared text normalization and CamelCase tokenization helpers for CATalyst FTS5 indexing and search.
"""

from __future__ import annotations

import re

_CAMEL_LOWER_UPPER_RE = re.compile(r"([a-z0-9])([A-Z])")
_CAMEL_ACRONYM_RE = re.compile(r"([A-Z]+)([A-Z][a-z])")
_SEP_RE = re.compile(r"[._/\\:-]+")
_WS_RE = re.compile(r"\s+")


def split_camel_case(text: str) -> str:
    """Split CamelCase identifiers (e.g. PutIcon -> Put Icon, FavoriteCatalog -> Favorite Catalog)."""
    if not text:
        return ""
    s = _CAMEL_LOWER_UPPER_RE.sub(r"\1 \2", text)
    s = _CAMEL_ACRONYM_RE.sub(r"\1 \2", s)
    return s


def expand_camel_tokens(text: str) -> str:
    """
    Produce an FTS-friendly token string keeping original identifiers AND CamelCase-split subtokens.
    Example: 'Material.PutIcon' -> 'Material.PutIcon Material PutIcon Put Icon'
    so SQLite FTS5 unicode61 matches both 'PutIcon' and 'Icon'/'Put'.
    """
    raw = (text or "").strip()
    if not raw:
        return ""
    sep_clean = _SEP_RE.sub(" ", raw)
    camel_clean = split_camel_case(sep_clean)
    combined = f"{raw} {sep_clean} {camel_clean}"
    seen = set()
    tokens = []
    for tok in _WS_RE.split(combined):
        t = tok.strip()
        if not t:
            continue
        low = t.lower()
        if low not in seen:
            seen.add(low)
            tokens.append(t)
    return " ".join(tokens)
