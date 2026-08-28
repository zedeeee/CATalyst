"""
CATIA V5 Selection.Search Query Syntax Grammar Module.
Provides structured knowledge and lookup for Dassault Systèmes Workbench Search Query Syntax.
"""

from typing import Dict, List, Any, Optional

SEARCH_WORKBENCHES = {
    "PartDesign": {
        "prefix": "CATPrtSearch",
        "description": "Part Design (Solid Modeling) features and geometry",
        "types": [
            {"type": "Pad", "description": "Extruded solid shape"},
            {"type": "Pocket", "description": "Cut extruded pocket shape"},
            {"type": "Hole", "description": "Cylindrical / counterbored / countersunk hole"},
            {"type": "Shaft", "description": "Revolved solid shape"},
            {"type": "Groove", "description": "Revolved cut groove"},
            {"type": "Fillet", "description": "Edge / face / tritangent fillet"},
            {"type": "Chamfer", "description": "Beveled edge feature"},
            {"type": "Draft", "description": "Draft angle feature"},
            {"type": "Shell", "description": "Hollowed body feature"},
            {"type": "Thread", "description": "Thread / tap feature"},
            {"type": "Split", "description": "Body split by surface/plane"},
            {"type": "Thick", "description": "Thick surface solid"},
            {"type": "Body", "description": "Part solid body (MechanicalBody / Body)"},
            {"type": "Sketch", "description": "2D Sketch profile"},
            {"type": "Part", "description": "Part root feature"},
        ],
        "examples": [
            "CATPrtSearch.Pad,all",
            "CATPrtSearch.Pocket.Visibility=Visible,all",
            "CATPrtSearch.Hole.Name='*M8*',all",
            "CATPrtSearch.Fillet.Color='(255,0,0)',all",
            "CATPrtSearch.Sketch.Visibility=Hidden,all",
            "CATPrtSearch.Body,all"
        ]
    },
    "GenerativeShapeDesign": {
        "prefix": "CATGspSearch",
        "description": "Generative Shape Design (GSD / Surfaces / Wireframe)",
        "types": [
            {"type": "Point", "description": "Wireframe point"},
            {"type": "Line", "description": "Wireframe line"},
            {"type": "Plane", "description": "Reference or constructed plane"},
            {"type": "Circle", "description": "Wireframe circular arc/circle"},
            {"type": "Spline", "description": "Wireframe spline curve"},
            {"type": "Curve", "description": "General wireframe curve"},
            {"type": "Extrude", "description": "Extruded surface"},
            {"type": "Revolve", "description": "Revolved surface"},
            {"type": "Sphere", "description": "Spherical surface"},
            {"type": "Cylinder", "description": "Cylindrical surface"},
            {"type": "Offset", "description": "Offset surface"},
            {"type": "Sweep", "description": "Swept surface"},
            {"type": "Fill", "description": "Filled surface patch"},
            {"type": "Join", "description": "Joined surface/curve element"},
            {"type": "Split", "description": "Split surface/wireframe"},
            {"type": "Trim", "description": "Trimmed surface/wireframe"},
            {"type": "Boundary", "description": "Boundary curve extracted from surface"},
            {"type": "Extract", "description": "Extracted sub-element geometry"},
            {"type": "OpenBody", "description": "Geometrical Set (HybridBody)"}
        ],
        "examples": [
            "CATGspSearch.Point,all",
            "CATGspSearch.Plane.Visibility=Visible,all",
            "CATGspSearch.Join.Name='*Aft*',all",
            "CATGspSearch.OpenBody.Name='*Datum*',all",
            "CATGspSearch.Surface.Color='(0,255,0)',all"
        ]
    },
    "Drafting": {
        "prefix": "CATDrwSearch",
        "description": "Drafting (2D Drawing Sheets, Views, Annotations)",
        "types": [
            {"type": "DrwText", "description": "2D text annotation"},
            {"type": "DrwDimension", "description": "Drafting dimension"},
            {"type": "DrwView", "description": "Drawing view"},
            {"type": "DrwSheet", "description": "Drawing sheet"},
            {"type": "DrwTable", "description": "Drafting table (BOM/Title block)"},
            {"type": "DrwHatching", "description": "Cross-hatching pattern"},
            {"type": "DrwPicture", "description": "Raster/vector embedded picture"},
            {"type": "DrwBalloon", "description": "Item balloon callout"}
        ],
        "examples": [
            "CATDrwSearch.DrwText.String='*NOTE*',all",
            "CATDrwSearch.DrwDimension.Visibility=Visible,all",
            "CATDrwSearch.DrwTable,all",
            "CATDrwSearch.DrwView.Name='*Section*',all"
        ]
    },
    "Assembly": {
        "prefix": "CATAsmSearch",
        "description": "Assembly Design & Constraints",
        "types": [
            {"type": "Product", "description": "Assembly product component"},
            {"type": "Constraint", "description": "Assembly constraint"},
            {"type": "FixConstraint", "description": "Fixed in space constraint"},
            {"type": "CoincidenceConstraint", "description": "Coincidence constraint"},
            {"type": "ContactConstraint", "description": "Surface contact constraint"},
            {"type": "AngleConstraint", "description": "Angle constraint"},
            {"type": "DistanceConstraint", "description": "Offset distance constraint"}
        ],
        "examples": [
            "CATAsmSearch.CoincidenceConstraint,all",
            "CATAsmSearch.FixConstraint,all",
            "CATAsmSearch.Constraint.Visibility=Visible,all"
        ]
    },
    "GenericTopology": {
        "prefix": "CATSearch",
        "description": "Generic Topology and B-Rep Geometry across workbenches",
        "types": [
            {"type": "Topology.Face", "description": "Topological B-Rep Face"},
            {"type": "Topology.Edge", "description": "Topological B-Rep Edge"},
            {"type": "Topology.Vertex", "description": "Topological B-Rep Vertex"},
            {"type": "Geometry.Surface", "description": "Generic surface geometry"},
            {"type": "Geometry.Curve", "description": "Generic curve geometry"}
        ],
        "examples": [
            "CATSearch.Topology.Face.Color='(255,0,0)',all",
            "CATSearch.Topology.Edge.Visibility=Visible,all",
            "CATSearch.Geometry.Surface,all"
        ]
    }
}

SEARCH_SCOPES = {
    "all": "Searches the entire document model tree (default).",
    "in": "Searches inside the currently selected container or active UI object.",
    "sel": "Filters within the current selection set.",
    "scr": "Searches elements visible on the screen viewpoint."
}

SEARCH_ATTRIBUTES = {
    "Name": "Name matches string with wildcards '*' (e.g. Name='*Bolt*')",
    "Visibility": "Visible or Hidden state (e.g. Visibility=Visible, Visibility=Hidden)",
    "Color": "RGB triplet '(r,g,b)' or named color (e.g. Color='(255,0,0)')",
    "RealColor": "Real defined color before display inheritance overrides",
    "Layer": "Layer index number or name (e.g. Layer=0, Layer=100)",
    "Type": "Explicit type qualification (e.g. Type=Pad)"
}

OPERATORS = {
    "=": "Equal to",
    "!=": "Not equal to",
    "<": "Less than",
    ">": "Greater than",
    "&": "Logical AND combination (e.g. CATPrtSearch.Pad & Visibility=Visible)",
    "+": "Logical OR combination",
    "-": "Logical NOT / subtraction"
}


def get_search_grammar(
    workbench: Optional[str] = None,
    query_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Returns structured CATIA Selection.Search query grammar dictionary,
    including workbench prefixes, supported types, attributes, scopes, and valid query examples.
    """
    if workbench:
        wb_clean = workbench.strip().lower().replace(" ", "").replace("_", "")
        for key, data in SEARCH_WORKBENCHES.items():
            if wb_clean in key.lower() or wb_clean in data["prefix"].lower():
                return {
                    "workbench": key,
                    "prefix": data["prefix"],
                    "description": data["description"],
                    "types": data["types"],
                    "scopes": SEARCH_SCOPES,
                    "attributes": SEARCH_ATTRIBUTES,
                    "operators": OPERATORS,
                    "examples": data["examples"],
                    "python_usage_example": (
                        f'# Python pywin32 example:\n'
                        f'selection = catia.ActiveDocument.Selection\n'
                        f'selection.Clear()\n'
                        f'selection.Search("{data["examples"][0]}")\n'
                        f'print(f"Matched count: {{selection.Count}}")'
                    )
                }

    # If query_type specified
    if query_type:
        qt_clean = query_type.strip().lower()
        matched_entries = []
        for key, data in SEARCH_WORKBENCHES.items():
            for t in data["types"]:
                if qt_clean in t["type"].lower():
                    matched_entries.append({
                        "workbench": key,
                        "prefix": data["prefix"],
                        "type": t["type"],
                        "description": t["description"],
                        "query_example": f"{data['prefix']}.{t['type']},all"
                    })
        if matched_entries:
            return {
                "matched_types": matched_entries,
                "scopes": SEARCH_SCOPES,
                "attributes": SEARCH_ATTRIBUTES,
                "operators": OPERATORS
            }

    # Return full summary overview
    return {
        "syntax_format": "[WorkbenchPrefix].[Type].[Attribute][Operator][Value], [Scope]",
        "workbenches": {k: {"prefix": v["prefix"], "description": v["description"], "sample_query": v["examples"][0]} for k, v in SEARCH_WORKBENCHES.items()},
        "scopes": SEARCH_SCOPES,
        "attributes": SEARCH_ATTRIBUTES,
        "operators": OPERATORS,
        "general_examples": [
            "CATPrtSearch.Pad,all",
            "CATPrtSearch.Pocket.Visibility=Visible,all",
            "CATGspSearch.Point,all",
            "CATGspSearch.Plane.Visibility=Visible,all",
            "CATDrwSearch.DrwText.String='*NOTE*',all",
            "CATSearch.Topology.Face.Color='(255,0,0)',all"
        ],
        "python_usage_example": (
            '# Python pywin32 snippet:\n'
            'selection = catia.ActiveDocument.Selection\n'
            'selection.Clear()\n'
            'selection.Search("CATPrtSearch.Pad,all")\n'
            'for i in range(1, selection.Count + 1):\n'
            '    pad = selection.Item(i).Value\n'
            '    print(pad.Name)'
        )
    }
