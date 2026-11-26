"""
Output Formatting, Sanitization & Token-Efficiency Utilities for CATalyst.
Provides:
1. CHM HTML truncation sanitizer (strips broken trailing '(see' clauses and search Example bloat).
2. Compact JSON serializer (strips empty redundant item keys and pretty-print indentation).
3. Dense IDL Signature Card renderer (`output_format="card"`) saving 80-90% output tokens.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Set

_TRUNCATED_TAIL_RE = re.compile(
    r"(?:\s*\(\s*see(?:\s+also)?|\s+The\s+created\s+[a-z]+|\s+For\s+more\s+information,?\s*see)\s*$",
    re.IGNORECASE,
)
_INLINE_EXAMPLE_RE = re.compile(r"\s+\bExample\b\s+.*$", re.IGNORECASE | re.DOTALL)
_WS_RE = re.compile(r"\s+")


def sanitize_doc_text(
    text: str,
    *,
    strip_example: bool = False,
    max_chars: int = 0,
) -> str:
    """
    Clean broken CHM HTML text artifacts (e.g. dangling '(see' from malformed <a> tags)
    and optionally strip verbose inline VB examples or cap length cleanly.
    """
    if not text:
        return ""
    s = _WS_RE.sub(" ", text).strip()
    if strip_example:
        s = _INLINE_EXAMPLE_RE.sub("", s).strip()
    s = _TRUNCATED_TAIL_RE.sub("", s).strip()
    # Close dangling unmatched '(' created by truncated CHM link blocks
    if s.endswith("("):
        s = s[:-1].rstrip()
    if max_chars > 0 and len(s) > max_chars:
        cut = s[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:")
        s = f"{cut}..." if cut else s[:max_chars]
    return s


def strip_redundant_fields(
    obj: Any,
    *,
    preserve_keys: Optional[Set[str]] = None,
    _is_root: bool = True,
) -> Any:
    """
    Recursively remove empty strings, empty lists (except protected root keys like
    'properties'/'methods'/'results'), and None values to eliminate token waste.
    """
    keep = preserve_keys or {"properties", "methods", "results", "recipes", "values"}
    if isinstance(obj, dict):
        cleaned: Dict[str, Any] = {}
        for k, v in obj.items():
            if v is None:
                continue
            if _is_root and k in keep:
                cleaned[k] = strip_redundant_fields(v, preserve_keys=keep, _is_root=False)
                continue
            if v == "" or v == []:
                continue
            # Omit redundant false boolean flags on search items (e.g. readonly=False on interfaces)
            if not _is_root and k == "readonly" and v is False:
                continue
            cleaned_val = strip_redundant_fields(v, preserve_keys=keep, _is_root=False)
            if cleaned_val == "" or cleaned_val == [] or cleaned_val == {}:
                continue
            cleaned[k] = cleaned_val
        return cleaned
    if isinstance(obj, list):
        return [strip_redundant_fields(item, preserve_keys=keep, _is_root=False) for item in obj]
    return obj


def dump_compact_json(payload: Any, *, strip_empty: bool = True) -> str:
    """
    Serialize JSON without whitespace bloat by default (saves ~20% tokens).
    Set CATALYST_PRETTY_JSON=1 for human-indented debugging output.
    """
    data = strip_redundant_fields(payload) if strip_empty else payload
    if os.environ.get("CATALYST_PRETTY_JSON") == "1":
        return json.dumps(data, indent=2, ensure_ascii=False)
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def format_member_signature(member: Dict[str, Any], host_iface: str, *, is_property: bool = False) -> str:
    """Render a property or method dict as a single-line typed IDL signature."""
    decl = member.get("declared_in", "")
    decl_tag = f", {decl}" if decl and decl.lower() != host_iface.lower() else ""
    if is_property:
        ro = "ro" if member.get("readonly") else "rw"
        return f"{member['type']} [{ro}{decl_tag}]"

    params = member.get("params") or []
    p_str = ", ".join(f"{p.get('name', '')}: {p.get('type', 'Variant')}" for p in params)
    ret = member.get("return_type") or "void"
    decl_bracket = f" [{decl}]" if decl and decl.lower() != host_iface.lower() else ""
    return f"({p_str}) -> {ret}{decl_bracket}"


def format_interface_card(data: Dict[str, Any]) -> str:
    """
    Render get_catia_interface payload as an ultra-dense IDL signature card
    (zero JSON key repetition, saving 80-90% tokens while keeping 100% signature accuracy).
    """
    if data.get("isError"):
        return f"ERROR: {data.get('error', 'Unknown error')}"
    if "member_not_found" in data:
        return f"# {data['name']}\nNotFound: {data.get('message', '')}"

    name = data.get("name", "")
    fw = f" ({data['framework']})" if data.get("framework") else ""
    chain = data.get("inheritance_chain") or []
    chain_str = " < ".join(chain[1:]) if len(chain) > 1 else ""
    header = f"# {name}{fw}" + (f" < {chain_str}" if chain_str else "")
    lines: List[str] = [header]

    if data.get("description"):
        lines.append(f"Desc: {sanitize_doc_text(data['description'], max_chars=240)}")

    nav = data.get("navigation_path")
    if nav:
        lines.append(f"Nav({nav.get('hops', 0)}): {nav.get('python_chain', '')}")
        if nav.get("terminal_pitfall"):
            tp = nav["terminal_pitfall"]
            lines.append(f"  !CreatorCaveat[{tp.get('severity','WARN')}]: {tp.get('summary','')}")

    omitted = data.get("omitted_base_members") or []
    omitted_note = f", omitted base[{','.join(omitted)}]" if omitted else ""

    props = data.get("properties") or []
    if props:
        lines.append(f"Props({len(props)}/{data.get('total_properties', len(props))}{omitted_note}):")
        for p in props:
            if "sig" in p:
                sig_line = f"  {p['name']}: {p['sig']}"
            else:
                sig_line = f"  {p['name']}: {format_member_signature(p, name, is_property=True)}"
            if p.get("description"):
                sig_line += f" — {sanitize_doc_text(p['description'], max_chars=120)}"
            lines.append(sig_line)
    elif omitted:
        lines.append(f"Props(0 displayed/{data.get('total_properties', 0)}{omitted_note})")

    methods = data.get("methods") or []
    if methods:
        lines.append(f"Methods({len(methods)}/{data.get('total_methods', len(methods))}):")
        for m in methods:
            if "sig" in m:
                sig_line = f"  {m['name']}{m['sig']}"
            else:
                sig_line = f"  {m['name']}{format_member_signature(m, name, is_property=False)}"
            if m.get("py"):
                sig_line += f" | py: {m['py']}"
            elif isinstance(m.get("python_mapping"), dict) and m["python_mapping"].get("pywin32_call"):
                sig_line += f" | py: {m['python_mapping']['pywin32_call']}"
            if m.get("description"):
                sig_line += f" — {sanitize_doc_text(m['description'], max_chars=120)}"
            lines.append(sig_line)
            if m.get("pitfall_warning"):
                pw = m["pitfall_warning"]
                lines.append(f"    !CAVEAT[{pw.get('severity', 'WARN')}]: {pw.get('summary', '')}")
                if pw.get("safe_pattern"):
                    lines.append(f"    Safe: {pw['safe_pattern']}")

    enums = data.get("referenced_enums")
    if enums:
        lines.append("Enums:")
        for ename, evals in enums.items():
            lines.append(f"  {ename}: {evals}")

    ucs = data.get("usecases") or []
    if ucs:
        lines.append(f"Examples({len(ucs)}):")
        for uc in ucs:
            lines.append(f"  [{uc.get('context', '')}] {uc.get('code', '').strip()}")

    docs = data.get("linked_official_docs") or []
    if docs:
        doc_strs = [f"{d.get('doc_id', '')}#{d.get('line_no', 0)} ({d.get('code_context', '')})" for d in docs]
        lines.append("Docs: " + " | ".join(doc_strs))

    samples = data.get("linked_sample_scripts") or []
    if samples:
        smp_strs = [f"{s.get('file', '')}#{s.get('line_no', 0)} ({s.get('code_context', '')})" for s in samples]
        lines.append("Samples: " + " | ".join(smp_strs))

    return "\n".join(lines)
