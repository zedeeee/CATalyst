"""
COM Object Model Directed Graph & Shortest-Path Navigator for CATalyst.
Derives directed navigation edges from CATIA V5 IDL property/method return types
and concrete Factory/Document subtype casts to help Agents traverse from root objects
(e.g. Application / PartDocument / MaterialDocument) to target interfaces.
"""

from __future__ import annotations

import heapq
import json
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple

# Base interfaces whose subtype cast is too generic/fan-out heavy for BFS downcasting
_NON_DOWNCAST_BASES = {
    "anyobject",
    "catbasedispatch",
    "catbaseunknown",
    "idispatch",
    "iunknown",
    "collection",
    "reference",
    "references",
}

# Specialized polymorphic base types returned by factory/document APIs
_POLYMORPHIC_CAST_BASES = {"document", "factory"}

# Generic AnyObject back-jump or lookup members suppressed during forward navigation
_DEMOTED_NAV_MEMBERS = {"application", "parent", "getitem"}


class ObjectGraph:
    """In-memory weighted directed graph over CATIA V5 COM interfaces."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.canonical_ifaces: Dict[str, str] = {}
        self.edges: Dict[str, List[Tuple[str, str, str, float, str]]] = {}
        self._build_from_db(conn)

    def _build_from_db(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()

        # Load canonical interface names and inheritance chains
        subtypes_by_base: Dict[str, List[str]] = {}
        for row in cur.execute("SELECT name, inheritance_chain FROM interfaces"):
            iface = row[0]
            self.canonical_ifaces[iface.lower()] = iface
            chain = json.loads(row[1]) if row[1] else [iface]
            # Direct/nearest base classes (skip self at index 0)
            for anc in chain[1:]:
                anc_low = anc.lower()
                if anc_low in _POLYMORPHIC_CAST_BASES:
                    subtypes_by_base.setdefault(anc_low, []).append(iface)

        # Prefer pre-computed object_edges table when present
        has_edges_table = (
            cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='object_edges'").fetchone()
            is not None
        )

        if has_edges_table:
            for row in cur.execute(
                "SELECT source_interface, member_name, member_kind, target_interface, weight, declared_in FROM object_edges"
            ):
                src, mbr, kind, tgt, weight, decl = row
                self.edges.setdefault(src.lower(), []).append((mbr, kind, tgt, float(weight), decl or src))
            return

        # Dynamic graph derivation fallback (supports legacy DBs and synthetic fixtures)
        seen_edges: Set[Tuple[str, str, str, str]] = set()

        def _add_edge(src: str, mbr: str, kind: str, tgt: str, weight: float, decl: str) -> None:
            key = (src.lower(), mbr.lower(), kind, tgt.lower())
            if key in seen_edges:
                return
            seen_edges.add(key)
            self.edges.setdefault(src.lower(), []).append((mbr, kind, tgt, weight, decl))

        # 1. Property edges
        for src, p_name, p_type, decl in cur.execute(
            "SELECT interface_name, name, type, declared_in FROM properties"
        ):
            src_canon = self.canonical_ifaces.get(src.lower(), src)
            decl_canon = decl or src_canon
            # Special CATIA IDL case: Part.ShapeFactory / Part.HybridShapeFactory return 'Factory'
            # in IDL, while concrete interface matches property name.
            refined_tgt = self.canonical_ifaces.get(p_name.lower())
            base_tgt = self.canonical_ifaces.get((p_type or "").lower())

            if refined_tgt and base_tgt and base_tgt.lower() in _POLYMORPHIC_CAST_BASES:
                target = refined_tgt
            elif base_tgt:
                target = base_tgt
            else:
                continue

            if target.lower() == src_canon.lower():
                continue

            is_inherited = decl_canon.lower() != src_canon.lower()
            base_cost = 1.0 if not is_inherited else 2.5
            if p_name.lower() in _DEMOTED_NAV_MEMBERS:
                base_cost = 25.0
            _add_edge(src_canon, p_name, "property", target, base_cost, decl_canon)

        # 2. Method return-type edges
        for src, m_name, r_type, decl in cur.execute(
            "SELECT interface_name, name, return_type, declared_in FROM methods"
        ):
            src_canon = self.canonical_ifaces.get(src.lower(), src)
            decl_canon = decl or src_canon
            target = self.canonical_ifaces.get((r_type or "").lower())
            if not target or target.lower() == src_canon.lower():
                continue

            is_inherited = decl_canon.lower() != src_canon.lower()
            m_low = m_name.lower()
            if m_low in _DEMOTED_NAV_MEMBERS:
                cost = 25.0
            elif m_low == "item":
                cost = 1.0 if not is_inherited else 2.0
            elif m_low.startswith(("add", "create", "open", "get")):
                cost = 1.3 if not is_inherited else 2.5
            else:
                cost = 1.8 if not is_inherited else 3.0
            _add_edge(src_canon, m_name, "method", target, cost, decl_canon)

        # 3. Polymorphic Document / Factory downcast edges
        for base_low, subs in subtypes_by_base.items():
            base_canon = self.canonical_ifaces.get(base_low)
            if not base_canon or base_low in _NON_DOWNCAST_BASES:
                continue
            for sub in subs:
                _add_edge(base_canon, f"[as {sub}]", "subtype_cast", sub, 0.5, base_canon)

    def find_navigation_path(
        self,
        source_iface: str,
        target_iface: str,
        max_hops: int = 8,
        compact: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Compute the lowest-cost directed navigation path from source_iface to target_iface.
        Uses Dijkstra with cycle protection and avoids AnyObject.Parent/Application loops.
        """
        src_canon = self.canonical_ifaces.get((source_iface or "").strip().lower())
        tgt_canon = self.canonical_ifaces.get((target_iface or "").strip().lower())
        if not src_canon or not tgt_canon:
            return None

        if src_canon == tgt_canon:
            out: Dict[str, Any] = {
                "source": src_canon,
                "target": tgt_canon,
                "hops": 0,
                "route": src_canon,
                "python_chain": src_canon.lower(),
            }
            if not compact:
                out["steps"] = []
            return out

        tgt_low = tgt_canon.lower()
        # Heap items: (total_cost, step_count, curr_iface_lower, path_steps)
        pq: List[Tuple[float, int, str, List[Dict[str, str]]]] = [(0.0, 0, src_canon.lower(), [])]
        best_cost: Dict[str, float] = {src_canon.lower(): 0.0}

        while pq:
            cost, hops, curr_low, steps = heapq.heappop(pq)
            if curr_low == tgt_low:
                # Filter out subtype casts when synthesizing copy-ready Python chain
                py_parts = ["catia" if src_canon == "Application" else src_canon[0].lower() + src_canon[1:]]
                route_parts = [src_canon]
                for st in steps:
                    if st["kind"] == "subtype_cast":
                        route_parts.append(f"{st['via']}->{st['to']}")
                        continue
                    route_parts.append(f".{st['via']}->{st['to']}")
                    if st["kind"] == "method":
                        if st["via"] == "Item":
                            py_parts.append("Item(1)")
                        else:
                            py_parts.append(f"{st['via']}(...)")
                    else:
                        py_parts.append(st["via"])

                real_hops = sum(1 for st in steps if st["kind"] != "subtype_cast")
                out = {
                    "source": src_canon,
                    "target": tgt_canon,
                    "hops": real_hops,
                    "route": " ".join(route_parts),
                    "python_chain": ".".join(py_parts),
                }
                if not compact:
                    out["steps"] = steps
                return out

            if cost > best_cost.get(curr_low, float("inf")):
                continue
            if hops >= max_hops:
                continue

            curr_canon = self.canonical_ifaces.get(curr_low, curr_low)
            for mbr, kind, next_canon, edge_w, decl in self.edges.get(curr_low, []):
                # Do not traverse through AnyObject back-jumps unless directly starting there
                if mbr.lower() in _DEMOTED_NAV_MEMBERS and len(steps) > 0:
                    continue
                next_low = next_canon.lower()
                new_cost = cost + edge_w
                if new_cost < best_cost.get(next_low, float("inf")):
                    best_cost[next_low] = new_cost
                    new_steps = steps + [{
                        "from": curr_canon,
                        "via": mbr,
                        "kind": kind,
                        "to": next_canon,
                        "declared_in": decl,
                    }]
                    heapq.heappush(pq, (new_cost, hops + 1, next_low, new_steps))

        return None


def materialize_object_edges(conn: sqlite3.Connection) -> int:
    """Persist object_edges table into catalyst.db during build.py."""
    cur = conn.cursor()
    # Drop BEFORE instantiating ObjectGraph so it derives fresh edges from properties/methods
    cur.execute("DROP TABLE IF EXISTS object_edges")
    conn.commit()
    graph = ObjectGraph(conn)

    cur.executescript("""
        CREATE TABLE object_edges (
            source_interface TEXT NOT NULL,
            member_name TEXT NOT NULL,
            member_kind TEXT NOT NULL,
            target_interface TEXT NOT NULL,
            weight REAL NOT NULL,
            declared_in TEXT
        );
        CREATE INDEX idx_object_edges_src ON object_edges(source_interface);
        CREATE INDEX idx_object_edges_tgt ON object_edges(target_interface);
    """)
    rows: List[Tuple[str, str, str, str, float, str]] = []
    for src_low, edge_list in graph.edges.items():
        src_canon = graph.canonical_ifaces.get(src_low, src_low)
        for mbr, kind, tgt, weight, decl in edge_list:
            rows.append((src_canon, mbr, kind, tgt, weight, decl))
    cur.executemany(
        "INSERT INTO object_edges (source_interface, member_name, member_kind, target_interface, weight, declared_in) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)
