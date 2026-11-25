"""
Lightweight Bilingual CAD Domain Thesaurus & Query Expander for CATalyst.
Bridges Chinese engineering terms and common English synonyms to CATIA V5 COM API
and documentation terminology with zero ML/vector dependencies.
"""

from __future__ import annotations

import re
from typing import Dict, List

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")

# Longest/specific multi-char keys checked before shorter keys
_CAD_SYNONYMS: Dict[str, List[str]] = {
    "几何图形集": ["HybridBody", "HybridBodies", "OpenBody", "HybridShapeFactory"],
    "混合体": ["HybridBody", "HybridShape"],
    "设计表": ["DesignTable", "Synchronize", "ConfigurationsNb", "AddAssociation"],
    "缩略图": ["Icon", "PutIcon", "GetIcon", "JPEG", "thumbnail"],
    "目录路径": ["folder", "PutIcon", "directory"],
    "文件夹": ["folder", "Folder", "PutIcon", "directory"],
    "工程图": ["Drawing", "DrawingDocument", "DrawingSheet", "DrawingView", "DrawingText"],
    "标题栏": ["DrawingText", "Title Block", "DrawingSheet", "DrwText"],
    "图框": ["DrawingSheet", "DrawingView", "Title Block"],
    "标准件": ["Catalog", "CatalogDocument", "Part Family", "PKT"],
    "选择集": ["Selection", "Search", "Selection.Search"],
    "包围盒": ["Bounding Box", "Measurable", "SPAWorkbench"],
    "凸台": ["Pad", "AddNewPad", "Prism"],
    "凹槽": ["Pocket", "AddNewPocket"],
    "型腔": ["Pocket", "AddNewPocket"],
    "倒圆角": ["Fillet", "EdgeFillet", "AddNewEdgeFillet"],
    "圆角": ["Fillet", "EdgeFillet", "ShapeFactory"],
    "倒角": ["Chamfer", "AddNewChamfer"],
    "草图": ["Sketch", "Sketches", "Factory2D"],
    "拉伸": ["Pad", "Extrude", "AddNewExtrude"],
    "旋转": ["Shaft", "Revolve", "Groove"],
    "扫描": ["Sweep", "HybridShapeSweep", "Rib"],
    "扫掠": ["Sweep", "HybridShapeSweep"],
    "接合": ["Assemble", "HybridShapeAssemble", "Join"],
    "修剪": ["Trim", "HybridShapeTrim"],
    "分割": ["Split", "HybridShapeSplit"],
    "装配": ["Product", "Products", "Assembly", "Constraint"],
    "约束": ["Constraint", "Constraints", "Coincidence"],
    "零件": ["Part", "PartDocument", "PartNumber"],
    "文档": ["Document", "Documents", "ActiveDocument"],
    "材质": ["Material", "CATMaterial", "MaterialDocument", "MaterialFamily", "RenderingMaterial"],
    "材料": ["Material", "CATMaterial", "MaterialDocument", "AnalysisMaterial"],
    "玻璃": ["RenderingMaterial", "Transparency", "Reflectivity", "Material"],
    "透明度": ["Transparency", "RenderingMaterial"],
    "图标": ["Icon", "PutIcon", "GetIcon"],
    "目录": ["Catalog", "CatalogDocument", "CreateCatalogFromcsv", "folder"],
    "参数": ["Parameter", "Parameters", "RealParam", "StrParam"],
    "公式": ["Formula", "Relation", "Relations"],
    "关系": ["Relation", "Relations", "KnowledgeObject"],
    "隐藏": ["Hidden", "VisPropertySet", "SetShow"],
    "颜色": ["Color", "VisPropertySet", "SetRealColor", "GetRealColor"],
    "质量": ["Mass", "Inertia", "GetTechnologicalObject"],
    "重心": ["COG", "Inertia", "CenterOfGravity"],
    "惯量": ["Inertia", "GetTechnologicalObject"],
    "导出": ["ExportData", "step", "stp", "iges"],
    "配置": ["Settings", "CATSettings", "SettingController", "Options"],
    "选项": ["Options", "ToolsOptions", "CATNls", "SettingController"],
    "批处理": ["batch", "CNEXT -batch", "CreateCatalogFromcsv"],
    "方向": ["Direction", "GetDirection", "SetDirection"],
    "孔": ["Hole", "AddNewHole"],
    # Common English aliases
    "thumbnail": ["Icon", "PutIcon", "GetIcon", "JPEG"],
    "thumbnails": ["Icon", "PutIcon", "GetIcon", "JPEG"],
    "step": ["stp", "ExportData", "STEP"],
    "bom": ["Product", "PartNumber", "Inertia"],
    "transparency": ["Transparency", "RenderingMaterial", "Material"],
}

_SORTED_SYN_KEYS = sorted(_CAD_SYNONYMS.keys(), key=len, reverse=True)


def contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def expand_bilingual_queries(query: str, max_variants: int = 4) -> List[str]:
    """
    Generate expanded English/domain query candidates when a query contains Chinese CAD
    terms or registered aliases. Returns [] if no expansion applies (avoiding noise on unknown ASCII tokens).
    """
    raw = (query or "").strip()
    if not raw:
        return []

    low = raw.lower()
    matched_groups: List[List[str]] = []
    consumed_spans: List[tuple[int, int]] = []

    for key in _SORTED_SYN_KEYS:
        key_low = key.lower()
        # For ASCII alias keys, match whole word boundaries to prevent partial word hijack
        if key.isascii():
            m = re.search(rf"\b{re.escape(key_low)}\b", low)
            if not m:
                continue
            span = m.span()
        else:
            idx = low.find(key_low)
            if idx < 0:
                continue
            span = (idx, idx + len(key_low))

        # Avoid double-matching substrings inside an already matched longer Chinese term
        if any(s <= span[0] and span[1] <= e for s, e in consumed_spans):
            continue
        consumed_spans.append(span)
        matched_groups.append(_CAD_SYNONYMS[key])

    if not matched_groups:
        return []

    # Also carry over any existing ASCII identifiers typed alongside Chinese (e.g., "导出 step" -> "step")
    ascii_tokens = re.findall(r"[A-Za-z0-9_.-]{2,}", raw)

    candidates: List[str] = []
    seen = {low}

    def _add(q: str) -> None:
        qn = " ".join(q.split()).strip()
        if qn and qn.lower() not in seen and len(candidates) < max_variants:
            seen.add(qn.lower())
            candidates.append(qn)

    if len(matched_groups) == 1:
        primary_terms = matched_groups[0]
        if ascii_tokens:
            for t in primary_terms[:2]:
                _add(f"{' '.join(ascii_tokens)} {t}")
        for t in primary_terms:
            _add(t)
    else:
        # Combine top terms from each matched concept (e.g., "凸台 方向" -> "Pad Direction")
        top_combo = " ".join(grp[0] for grp in matched_groups[:3])
        if ascii_tokens:
            top_combo = f"{top_combo} {' '.join(ascii_tokens)}"
        _add(top_combo)
        for grp in matched_groups:
            _add(grp[0])
            if len(grp) > 1:
                _add(grp[1])

    return candidates
