"""Literature-grounded layout-quality metrics for the four relationship charts.

Metrics follow Purchase (edge crossings are the dominant readability factor) and Dunne &
Shneiderman (readability scores normalised to [0,1], 1 = best): edge crossings, node
occlusion, crossing angle. They are computed from the layout each renderer actually emits:
we render the chart and extract the injected data arrays (`NAMES`/`LINKS`, `matrix`,
`RAW_LINKS`, `NODES`/`LINKS`), so the numbers reflect the real output, not a re-derivation.

Order-based charts (arc, chord, sankey) have crossings that are an exact function of the node
order; the force graph is geometric and is measured via the deterministic `spring_layout`.

Std-lib only. Reference: Purchase 1997/2002; Dunne & Shneiderman, HCIL TR 2009-13.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

try:
    from spring_layout import layout as _spring_layout
except ImportError:  # when imported as a package
    from .spring_layout import layout as _spring_layout

_DEC = json.JSONDecoder()
_CROSS_GUARD = 4000  # skip O(E^2) crossing counts above this many edges


def extract_const(html: str, name: str) -> Any:
    """Extract the JSON value of an injected `const <name> = <json>;`."""
    m = re.search(r"const\s+" + re.escape(name) + r"\s*=\s*", html)
    if not m:
        return None
    try:
        val, _ = _DEC.raw_decode(html, m.end())
        return val
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------- crossings --
def crossings_linear(edges: list[tuple[int, int]]) -> int | None:
    """Crossings for chords/arcs on a 1-D or circular axis: two edges cross iff their
    endpoint positions interleave. Edges sharing a node never cross (checked by equal
    position). O(E^2), guarded for very dense relations."""
    E = [(a, b) if a < b else (b, a) for a, b in edges]
    n = len(E)
    if n > _CROSS_GUARD:
        return None
    c = 0
    for i in range(n):
        a, b = E[i]
        for j in range(i + 1, n):
            cc, d = E[j]
            if a == cc or a == d or b == cc or b == d:
                continue
            if a < cc < b < d or cc < a < d < b:
                c += 1
    return c


def crossings_bipartite(links: list[tuple[int, int]]) -> int | None:
    """Two-layer (Sankey) crossings: links (sOrder, tOrder) cross iff the source order and
    the target order disagree. Links sharing a source or target never cross."""
    n = len(links)
    if n > _CROSS_GUARD:
        return None
    c = 0
    for i in range(n):
        s1, t1 = links[i]
        for j in range(i + 1, n):
            s2, t2 = links[j]
            if s1 == s2 or t1 == t2:
                continue
            if (s1 < s2) != (t1 < t2):
                c += 1
    return c


def crossing_score(crossings: int | None, degrees: list[int], m: int) -> float | None:
    """Dunne normalisation of crossings to [0,1] (1 = none). Excludes pairs that share a
    node (which can never cross) from the maximum."""
    if crossings is None:
        return None
    c_all = m * (m - 1) / 2.0
    c_imp = sum(d * (d - 1) / 2.0 for d in degrees)
    c_max = c_all - c_imp
    if c_max <= 0:
        return 1.0
    return max(0.0, 1.0 - crossings / c_max)


def _degrees_from_edges(edges: list[tuple[int, int]], n_nodes: int) -> list[int]:
    deg = [0] * max(1, n_nodes)
    for a, b in edges:
        if a < len(deg):
            deg[a] += 1
        if b < len(deg):
            deg[b] += 1
    return deg


# ---------------------------------------------------------- per-chart metrics --
def arc_metrics(html: str) -> dict[str, Any]:
    names = extract_const(html, "NAMES") or []
    links = extract_const(html, "LINKS") or []
    n = len(names)
    edges = [(int(l["i"]), int(l["j"])) for l in links if "i" in l and "j" in l]
    cross = crossings_linear(edges)
    deg = _degrees_from_edges(edges, n)
    spans = [abs(a - b) for a, b in edges] or [0]
    return {
        "chart": "arc", "nodes": n, "edges": len(edges),
        "crossings": cross,
        "crossing_score": crossing_score(cross, deg, len(edges)),
        "total_span": sum(spans), "max_span": max(spans),
        "max_span_frac": max(spans) / (n - 1) if n > 1 else 0.0,
    }


def chord_metrics(html: str) -> dict[str, Any]:
    names = extract_const(html, "names") or []
    matrix = extract_const(html, "matrix") or []
    n = len(names)
    edges = []
    for i in range(len(matrix)):
        for j in range(i + 1, len(matrix)):
            if (matrix[i][j] or 0) > 0 or (matrix[j][i] or 0) > 0:
                edges.append((i, j))
    cross = crossings_linear(edges)  # circular crossings == interleaving on ring positions
    deg = _degrees_from_edges(edges, n)
    spans = [min(abs(a - b), n - abs(a - b)) for a, b in edges] or [0]  # circular span
    return {
        "chart": "chord", "nodes": n, "edges": len(edges),
        "crossings": cross,
        "crossing_score": crossing_score(cross, deg, len(edges)),
        "total_span": sum(spans), "max_span": max(spans),
    }


def sankey_metrics(html: str) -> dict[str, Any]:
    links = extract_const(html, "RAW_LINKS") or []
    nodes = extract_const(html, "RAW_NODES") or []
    pairs = [(int(l["sourceOrder"]), int(l["targetOrder"])) for l in links
             if "sourceOrder" in l and "targetOrder" in l]
    cross = crossings_bipartite(pairs)
    # Dunne normalisation over a bipartite max: links sharing an endpoint cannot cross.
    from collections import Counter
    sc = Counter(s for s, _ in pairs)
    tc = Counter(t for _, t in pairs)
    m = len(pairs)
    c_imp = sum(v * (v - 1) / 2 for v in sc.values()) + sum(v * (v - 1) / 2 for v in tc.values())
    c_max = m * (m - 1) / 2.0 - c_imp
    score = None if cross is None else (1.0 if c_max <= 0 else max(0.0, 1.0 - cross / c_max))
    return {
        "chart": "sankey", "nodes": len(nodes), "edges": m,
        "crossings": cross, "crossing_score": score,
    }


# ------------------------------------------------------------- force (geometry) --
def _segments_cross(p1, p2, p3, p4):
    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) - (b[1] - a[1]) * (c[0] - a[0])
    d1 = ccw(p3, p4, p1); d2 = ccw(p3, p4, p2)
    d3 = ccw(p1, p2, p3); d4 = ccw(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _angle(p1, p2, p3, p4):
    a1 = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    a2 = math.atan2(p4[1] - p3[1], p4[0] - p3[0])
    d = abs(math.degrees(a1 - a2)) % 180.0
    return min(d, 180.0 - d)


def force_metrics(html: str, iterations: int = 300) -> dict[str, Any]:
    nodes = extract_const(html, "NODES") or []
    links = extract_const(html, "LINKS") or []
    ids = [str(nd.get("id")) for nd in nodes]
    groups = {str(nd.get("id")): int(nd.get("group", 0)) for nd in nodes}
    bipartite = any(int(nd.get("group", 0)) == 1 for nd in nodes)
    edge_ids = [(str(l["source"]), str(l["target"])) for l in links if "source" in l and "target" in l]

    pos, radius, deg = _spring_layout(ids, edge_ids, groups, bipartite=bipartite, iterations=iterations)
    n = len(ids)

    # node occlusion (Dunne): fraction of node pairs closer than the sum of their radii
    occ = 0; total = 0
    coords = [pos[i] for i in ids]
    for i in range(n):
        for j in range(i + 1, n):
            total += 1
            dx = coords[i][0] - coords[j][0]; dy = coords[i][1] - coords[j][1]
            if math.hypot(dx, dy) < (radius[i] + radius[j]):
                occ += 1
    occ_score = 1.0 - (occ / total if total else 0.0)

    # geometric edge crossings + crossing angle
    idx = {nid: k for k, nid in enumerate(ids)}
    segs = [(coords[idx[a]], coords[idx[b]], a, b) for a, b in edge_ids if a in idx and b in idx]
    cross = 0; angles = []
    if len(segs) <= _CROSS_GUARD:
        for i in range(len(segs)):
            p1, p2, a1, b1 = segs[i]
            for j in range(i + 1, len(segs)):
                p3, p4, a2, b2 = segs[j]
                if a1 in (a2, b2) or b1 in (a2, b2):
                    continue
                if _segments_cross(p1, p2, p3, p4):
                    cross += 1
                    angles.append(_angle(p1, p2, p3, p4))
    else:
        cross = None
    cs = crossing_score(cross, deg, len(edge_ids))
    return {
        "chart": "force", "nodes": n, "edges": len(edge_ids),
        "crossings": cross, "crossing_score": cs,
        "node_occlusion": occ, "occlusion_score": round(occ_score, 4),
        "min_crossing_angle": round(min(angles), 1) if angles else None,
        "mean_crossing_angle": round(sum(angles) / len(angles), 1) if angles else None,
    }
