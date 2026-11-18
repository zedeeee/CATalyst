"""
Offline CATIA V5 Documentation, CATNls Message Catalog, and Official Samples Parser.
Stores strictly portable relative POSIX paths (zero machine-specific absolute paths in DB).
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import unquote

from lxml import html as lxml_html

# Directories inside Bxxdoc/English/online that are pure assets or already covered by catalyst.db
SKIP_TOP_DIRS = {
    "icons_C2",
    "CAAScrAutomationImages",
    "CAAScrJavaScript",
    "interfaces",
}

SKIP_IMG_MARKERS = (
    "icons_c2/",
    "/common/",
    "butix_",
    "sm_bullet",
    "atarget.gif",
    "awarning.gif",
    "aprereq.gif",
    "ascenari.gif",
    "ainfo.gif",
    "anote.gif",
    "atip.gif",
    "aendtask.gif",
    "logo_",
)

TEXT_SAMPLE_EXTS = {".csv", ".catscript", ".txt", ".xml", ".vbs", ".catvbs", ".bas", ".cls"}
BINARY_SAMPLE_EXTS = {
    ".catpart",
    ".catproduct",
    ".catalog",
    ".catdrawing",
    ".catanalysis",
    ".catprocess",
    ".catshape",
    ".catmaterial",
    ".cgr",
    ".model",
    ".xls",
    ".xlsx",
    ".act",
    ".wrl",
    ".stp",
    ".step",
    ".igs",
    ".iges",
}
ALL_DOC_SAMPLE_EXTS = TEXT_SAMPLE_EXTS | BINARY_SAMPLE_EXTS
STARTUP_INDEX_EXTS = ALL_DOC_SAMPLE_EXTS
MAX_TEXT_SAMPLE_BYTES = 256 * 1024

_NOISE_NLS_VALUES = {
    "ok",
    "cancel",
    "apply",
    "close",
    "help",
    "yes",
    "no",
    "browse...",
    "browse",
    "preview",
    "reset",
    "default",
    "none",
    "all",
    "name",
    "name:",
    "type",
    "type:",
    "value",
    "value:",
    "more...",
    "less...",
    "add",
    "remove",
    "delete",
    "edit",
    "new",
    "open",
    "save",
}

_OPTION_FILE_RE = re.compile(
    r"(?i)(?:Option|Setting|ToolsOptions|Cui|Cust|Pref|Env|Catalog|DLName|Drafting|Assembly|Part|Knowledge)"
)
_NLS_KV_RE = re.compile(r'^\s*([A-Za-z0-9_.\-/]+)\s*=\s*"((?:[^"\\]|\\.)*)"\s*;?\s*$')
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")
_MENTIONED_FILE_RE = re.compile(
    r"\b([A-Za-z0-9_\-]+\.(?:csv|CATScript|CATVbs|CATPart|CATProduct|catalog|CATDrawing|CATAnalysis|CATProcess|txt|xml|xls|xlsx|cgr|model))\b",
    re.I,
)


def normalize_doc_root(path: Optional[Path]) -> Optional[Path]:
    """Allow passing either Bxxdoc, Bxxdoc/English, or Bxxdoc/English/online. Safe against unreachable SMB/UNC."""
    if not path:
        return None
    p = Path(path)
    try:
        if not p.exists():
            return None
        if (p / "English" / "online").is_dir():
            return (p / "English" / "online").resolve()
        if (p / "online").is_dir():
            return (p / "online").resolve()
        return p.resolve()
    except OSError:
        return None


def normalize_install_root(path: Optional[Path]) -> Optional[Path]:
    """Allow passing either Bxx or Bxx/win_b64. Safe against unreachable SMB/UNC."""
    if not path:
        return None
    p = Path(path)
    try:
        if not p.exists():
            return None
        if (p / "win_b64").is_dir():
            return (p / "win_b64").resolve()
        return p.resolve()
    except OSError:
        return None


def detect_release_from_path(path: Optional[Path]) -> str:
    """Infer CATIA release code such as B27 / B32 from path segments if present."""
    if not path:
        return "unknown"
    text = str(path)
    m = re.search(r"\b(B\d{2,3})(?:doc)?\b", text, re.I)
    if m:
        return m.group(1).upper()
    return "unknown"


def parse_toc_xml(doc_root: Path) -> Dict[str, Tuple[str, str]]:
    """
    Parse official CATIA_*_TOC.xml under doc_root (e.g. CATIA_P3_TOC.xml).
    Returns mapping: module_dir -> (solution_name, product_name).
    """
    mapping: Dict[str, Tuple[str, str]] = {}
    toc_files = sorted(doc_root.glob("*TOC.xml"))
    if not toc_files:
        return mapping

    for toc_file in toc_files:
        try:
            root = ET.parse(toc_file).getroot()
        except Exception:
            continue
        for sol in root.findall(".//ITEM"):
            if sol.attrib.get("searchFilter") == "Solution":
                solution_name = (sol.attrib.get("name") or "").strip()
                for ditem in sol.findall("DITEM"):
                    mod_dir = (ditem.attrib.get("dir") or "").strip()
                    prod_name = (ditem.attrib.get("name") or "").strip()
                    if mod_dir and mod_dir not in mapping:
                        mapping[mod_dir] = (solution_name, prod_name)
    return mapping


def classify_module(module_dir: str, toc_map: Dict[str, Tuple[str, str]]) -> Optional[Tuple[str, str, str]]:
    """
    Classify a top-level directory under doc_root.
    Returns (category, solution, product_name) or None if the directory should be skipped.
    """
    if module_dir in SKIP_TOP_DIRS:
        return None
    low = module_dir.lower()
    if low.endswith("images") or low.endswith("javascript"):
        return None

    solution, product = toc_map.get(module_dir, ("", ""))

    if low.startswith("bascu") or low == "caascrsettings":
        return ("options", solution or "Tools > Options", product or module_dir)

    if low.startswith("caascd") or low.startswith("caascr"):
        return ("automation_doc", solution or "Automation Documentation", product or module_dir)

    return ("user_guide", solution or "User's Guide", product or module_dir)


def build_module_sample_lookup(doc_root: Path) -> Dict[str, Dict[str, str]]:
    """
    Build lookup: module_name -> {filename_lower: rel_path_posix}
    so HTML pages mentioning e.g. 'BatchCatalog.csv' or 'PktRod.CATPart' bind directly to exact relative paths.
    """
    lookup: Dict[str, Dict[str, str]] = {}
    for root, _, files in os.walk(doc_root):
        rp = Path(root)
        rel_parts = rp.relative_to(doc_root).parts
        if not rel_parts:
            continue
        if "samples" not in [p.lower() for p in rel_parts]:
            continue
        mod = rel_parts[0]
        mod_map = lookup.setdefault(mod, {})
        for fn in files:
            ext = Path(fn).suffix.lower()
            if ext not in ALL_DOC_SAMPLE_EXTS:
                continue
            rel_posix = (rp / fn).relative_to(doc_root).as_posix()
            mod_map.setdefault(fn.lower(), rel_posix)
    return lookup


def _clean_inline(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").replace("\xa0", " ")).strip()


def _extract_table_row_text(img_el: Any) -> str:
    tr = img_el.getparent()
    while tr is not None and getattr(tr, "tag", "").lower() != "tr":
        tr = tr.getparent()
    if tr is None:
        return ""
    texts: List[str] = []
    for td in tr.findall(".//td"):
        t = _clean_inline(" ".join(td.itertext()))
        if t:
            texts.append(t)
    return _clean_inline(" ".join(texts))


def _node_to_markdown(root_el: Any) -> str:
    lines: List[str] = []

    for bad in root_el.xpath(".//script | .//style | .//noscript"):
        parent = bad.getparent()
        if parent is not None:
            parent.remove(bad)

    for el in root_el.iter():
        tag = getattr(el, "tag", "")
        if not isinstance(tag, str):
            continue
        t = tag.lower()
        if t in ("h1", "h2", "h3", "h4"):
            txt = _clean_inline(" ".join(el.itertext()))
            if txt:
                lvl = int(t[1])
                lines.append(f"\n{'#' * lvl} {txt}\n")
        elif t == "pre":
            code_txt = (el.text_content() or "").replace("\xa0", " ").strip("\r\n")
            if code_txt:
                lines.append(f"\n```\n{code_txt}\n```\n")
        elif t == "li":
            txt = _clean_inline(" ".join(el.itertext()))
            if txt:
                lines.append(f"- {txt}")
        elif t == "p":
            parent = el.getparent()
            if parent is not None and getattr(parent, "tag", "").lower() == "li":
                continue
            txt = _clean_inline(" ".join(el.itertext()))
            if txt:
                lines.append(txt)
        elif t == "td":
            if not el.xpath(".//p | .//li | .//h1 | .//h2 | .//h3 | .//h4 | .//pre | .//table"):
                txt = _clean_inline(" ".join(el.itertext()))
                if txt and len(txt) > 1:
                    lines.append(txt)

    if not lines:
        return _clean_inline(root_el.text_content() or "")

    deduped: List[str] = []
    prev = ""
    for ln in lines:
        s = ln.strip()
        if not s or s == prev:
            continue
        deduped.append(ln)
        prev = s

    joined = "\n".join(deduped)
    return _MULTI_NL_RE.sub("\n\n", joined).strip()


def _resolve_rel_href(rel_parent: Path, raw_href: str) -> Optional[str]:
    href = unquote((raw_href or "").strip())
    if not href or href.startswith("#"):
        return None
    low = href.lower()
    if low.startswith(("http://", "https://", "mailto:", "javascript:", "ftp:")):
        return None
    # Strip anchor fragment and query string
    href = href.split("#", 1)[0].split("?", 1)[0].strip()
    if not href:
        return None
    norm = os.path.normpath(str(rel_parent / href)).replace("\\", "/")
    if norm.startswith("..") or norm.startswith("/"):
        return None
    return norm


def parse_doc_html_task(
    args: Tuple[str, str, str, str, str, str, Dict[str, str]]
) -> Optional[Dict[str, Any]]:
    """
    Top-level picklable worker for ProcessPoolExecutor.
    args = (abs_path_str, rel_path_posix, module, category, solution, product_name, mod_sample_map)
    """
    abs_path_str, rel_path, module, category, solution, product_name, mod_sample_map = args
    fp = Path(abs_path_str)
    try:
        raw_bytes = fp.read_bytes()
    except OSError:
        return None
    if not raw_bytes:
        return None

    try:
        html_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        html_text = raw_bytes.decode("cp1252", errors="replace")

    try:
        doc = lxml_html.fromstring(html_text)
    except Exception:
        return None

    if doc.xpath(".//frameset"):
        return None

    title_nodes = doc.xpath(".//title/text()")
    title = _clean_inline(" ".join(title_nodes))
    if not title:
        h1_nodes = doc.xpath(".//h1")
        if h1_nodes:
            title = _clean_inline(" ".join(h1_nodes[0].itertext()))
    if not title:
        title = fp.stem

    headings_list: List[str] = []
    for h in doc.xpath(".//h1 | .//h2 | .//h3"):
        ht = _clean_inline(" ".join(h.itertext()))
        if ht and ht not in headings_list:
            headings_list.append(ht)

    ix_keywords: List[str] = []
    options_anchors: List[str] = []
    for a in doc.xpath(".//a[@name]"):
        aname = (a.attrib.get("name") or "").strip()
        if not aname:
            continue
        if aname.startswith("ix-"):
            kw = aname[3:].replace("::", " ").replace(";", ", ").strip()
            if kw and kw not in ix_keywords:
                ix_keywords.append(kw)
        elif "ToolsOptions" in aname or aname.startswith("Options."):
            if aname not in options_anchors:
                options_anchors.append(aname)

    rel_parent = Path(rel_path).parent

    # Extract hyperlinks to sibling docs and non-HTML linked asset/sample files
    linked_docs: List[str] = []
    linked_files: List[str] = []
    linked_files_seen: Set[str] = set()

    for a in doc.xpath(".//a[@href]"):
        resolved = _resolve_rel_href(rel_parent, a.attrib.get("href") or "")
        if not resolved or resolved == rel_path:
            continue
        res_low = resolved.lower()
        if res_low.endswith((".htm", ".html")):
            if not res_low.endswith("toc.htm") and resolved not in linked_docs:
                linked_docs.append(resolved)
        else:
            ext = Path(resolved).suffix.lower()
            if ext in ALL_DOC_SAMPLE_EXTS and resolved not in linked_files_seen:
                linked_files_seen.add(resolved)
                linked_files.append(resolved)

    summaries: List[str] = []
    warnings: List[str] = []
    images: List[str] = []

    for img in doc.xpath(".//img[@src]"):
        src = (img.attrib.get("src") or "").strip().replace("\\", "/")
        if not src:
            continue
        src_low = src.lower()
        if "atarget.gif" in src_low:
            txt = _extract_table_row_text(img)
            if txt and txt not in summaries:
                summaries.append(txt)
            continue
        if "awarning.gif" in src_low:
            txt = _extract_table_row_text(img)
            if txt and txt not in warnings:
                warnings.append(txt)
            continue
        if any(m in src_low for m in SKIP_IMG_MARKERS):
            continue
        norm_img = os.path.normpath(str(rel_parent / src)).replace("\\", "/")
        if not norm_img.startswith("..") and norm_img not in images:
            images.append(norm_img)

    body_nodes = doc.xpath(".//body")
    body_root = body_nodes[0] if body_nodes else doc
    body_text = _node_to_markdown(body_root)
    if not body_text or len(body_text) < 20:
        return None

    # Resolve sample filenames explicitly mentioned in prose against this module's samples/
    if mod_sample_map:
        for m in _MENTIONED_FILE_RE.finditer(body_text):
            fname_low = m.group(1).lower()
            matched_rel = mod_sample_map.get(fname_low)
            if matched_rel and matched_rel not in linked_files_seen:
                linked_files_seen.add(matched_rel)
                linked_files.append(matched_rel)

    final_category = "options" if options_anchors else category

    return {
        "doc_id": rel_path,
        "module": module,
        "solution": solution,
        "product_name": product_name,
        "category": final_category,
        "title": title,
        "ix_keywords": "; ".join(ix_keywords),
        "options_anchors": "; ".join(options_anchors),
        "headings": " | ".join(headings_list[:20]),
        "summary": " ".join(summaries[:2]),
        "warnings": "\n".join(warnings[:6]),
        "body_text": body_text,
        "images": images[:20],
        "linked_docs": linked_docs[:25],
        "linked_files": linked_files[:25],
    }


def iter_doc_html_tasks(
    doc_root: Path,
    toc_map: Dict[str, Tuple[str, str]],
    sample_lookup: Dict[str, Dict[str, str]],
    only_modules: Optional[Iterable[str]] = None,
) -> List[Tuple[str, str, str, str, str, str, Dict[str, str]]]:
    """Collect candidate HTML files across doc_root, skipping navigation frames and assets."""
    module_filter = {m.strip().lower() for m in (only_modules or []) if m.strip()}
    tasks: List[Tuple[str, str, str, str, str, str, Dict[str, str]]] = []

    for child in sorted(doc_root.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        mod = child.name
        if module_filter and mod.lower() not in module_filter:
            continue
        cls = classify_module(mod, toc_map)
        if cls is None:
            continue
        category, solution, product_name = cls
        mod_samples = sample_lookup.get(mod, {})

        for root, dirs, files in os.walk(child):
            dirs[:] = [
                d
                for d in dirs
                if d.lower() not in {"_navigation", "images", "samples", "icons"}
            ]
            rp = Path(root)
            for fn in files:
                fn_low = fn.lower()
                if not (fn_low.endswith(".htm") or fn_low.endswith(".html")):
                    continue
                if fn_low.endswith("toc.htm") or fn_low.endswith("_toc.htm"):
                    continue
                fp = rp / fn
                rel_posix = fp.relative_to(doc_root).as_posix()
                tasks.append((str(fp), rel_posix, mod, category, solution, product_name, mod_samples))
    return tasks


def parse_catnls_file(fp: Path) -> List[Tuple[str, str, str, int]]:
    """Parse a single .CATNls file into rows: (file_stem, nls_key, text, is_option_file)."""
    try:
        raw = fp.read_bytes()
    except OSError:
        return []
    if not raw:
        return []

    for enc in ("utf-8-sig", "utf-8", "cp1252", "gbk"):
        try:
            content = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        content = raw.decode("utf-8", errors="replace")

    stem = fp.stem
    is_opt = 1 if _OPTION_FILE_RE.search(stem) else 0
    rows: List[Tuple[str, str, str, int]] = []

    for line in content.splitlines():
        s = line.strip()
        if not s or s.startswith("//") or s.startswith("#") or "=" not in s:
            continue
        m = _NLS_KV_RE.match(s)
        if not m:
            continue
        key = m.group(1).strip()
        val = m.group(2).replace('\\"', '"').replace("\\n", " ").strip()
        val = _clean_inline(val)
        if len(val) < 3:
            continue
        if val.lower() in _NOISE_NLS_VALUES:
            continue
        row_opt = 1 if (is_opt or ".LongHelp" in key or ".ShortHelp" in key or "Option" in key) else 0
        rows.append((stem, key, val, row_opt))

    return rows


def _decode_text_file(fp: Path) -> Optional[str]:
    try:
        raw = fp.read_bytes()
    except OSError:
        return None
    if not raw or b"\x00" in raw[:4096]:
        return None
    for enc in ("utf-8-sig", "utf-8", "gbk", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def collect_samples(
    doc_root: Optional[Path] = None,
    install_root: Optional[Path] = None,
    only_modules: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Collect all official sample files with portable relative POSIX paths:
    - Text samples (.csv, .CATScript, .txt, .xml, .vbs): indexed with full text content (is_binary=0)
    - Binary CAD/Excel samples (.CATPart, .CATProduct, .catalog, .cgr, .xls, etc.): indexed by
      relative path & metadata only (is_binary=1, content=''), enabling zero-bloat lookup & runtime path resolution.
    """
    module_filter = {m.strip().lower() for m in (only_modules or []) if m.strip()}
    samples: List[Dict[str, Any]] = []

    if doc_root and doc_root.exists():
        for root, _, files in os.walk(doc_root):
            rp = Path(root)
            rel_parts = rp.relative_to(doc_root).parts
            if not rel_parts:
                continue
            mod = rel_parts[0]
            if module_filter and mod.lower() not in module_filter:
                continue
            if "samples" not in [p.lower() for p in rel_parts]:
                continue
            for fn in files:
                fp = rp / fn
                ext = fp.suffix.lower()
                if ext not in ALL_DOC_SAMPLE_EXTS:
                    continue
                try:
                    sz = fp.stat().st_size
                except OSError:
                    continue
                if sz == 0:
                    continue

                rel_posix = fp.relative_to(doc_root).as_posix()
                if ext in TEXT_SAMPLE_EXTS and sz <= MAX_TEXT_SAMPLE_BYTES:
                    text = _decode_text_file(fp)
                    is_bin = 0 if (text and text.strip()) else 1
                    content = text if is_bin == 0 else ""
                else:
                    is_bin = 1
                    content = ""

                samples.append(
                    {
                        "sample_id": f"doc:{rel_posix}",
                        "source": "doc_samples",
                        "module": mod,
                        "filename": fn,
                        "ext": ext,
                        "rel_path": rel_posix,
                        "size_bytes": sz,
                        "is_binary": is_bin,
                        "content": content,
                    }
                )

    if install_root and install_root.exists():
        startup_dir = install_root / "startup"
        if startup_dir.exists():
            for root, _, files in os.walk(startup_dir):
                rp = Path(root)
                for fn in files:
                    fp = rp / fn
                    ext = fp.suffix.lower()
                    if ext not in STARTUP_INDEX_EXTS:
                        continue
                    try:
                        sz = fp.stat().st_size
                    except OSError:
                        continue
                    if sz == 0:
                        continue
                    rel_posix = f"startup/{fp.relative_to(startup_dir).as_posix()}"
                    top_mod = fp.relative_to(startup_dir).parts[0] if fp.relative_to(startup_dir).parts else "startup"
                    if ext in TEXT_SAMPLE_EXTS and sz <= MAX_TEXT_SAMPLE_BYTES:
                        text = _decode_text_file(fp)
                        is_bin = 0 if (text and text.strip()) else 1
                        content = text if is_bin == 0 else ""
                    else:
                        is_bin = 1
                        content = ""
                    samples.append(
                        {
                            "sample_id": f"startup:{rel_posix}",
                            "source": "startup",
                            "module": top_mod,
                            "filename": fn,
                            "ext": ext,
                            "rel_path": rel_posix,
                            "size_bytes": sz,
                            "is_binary": is_bin,
                            "content": content,
                        }
                    )

    return samples
