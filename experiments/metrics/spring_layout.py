"""A small, deterministic force/spring layout (standard library only).

It mirrors the *kind* of layout the D3 force renderer produces (`sonnet_force.py`): a
deterministic circular seed, degree-scaled repulsion, spring links, collision separation and
(for the bipartite case) a left/right group `forceX`. It is **not** pixel-identical to
d3-force in the browser — it exists so the force graph's *geometric* readability metrics
(node occlusion, edge crossings, crossing angle) can be computed reproducibly and compared
before/after a change.

`layout(nodes, links, groups, width, height, iterations)` returns `{id: (x, y)}`.
"""

from __future__ import annotations

import math
from typing import Any


def layout(node_ids: list[str], links: list[tuple[str, str]],
           groups: dict[str, int] | None = None,
           width: float = 900.0, height: float = 650.0,
           iterations: int = 300, bipartite: bool = False) -> dict[str, tuple[float, float]]:
    n = len(node_ids)
    if n == 0:
        return {}
    idx = {nid: i for i, nid in enumerate(node_ids)}
    groups = groups or {}

    deg = [0] * n
    edges = []
    for a, b in links:
        if a in idx and b in idx and a != b:
            ia, ib = idx[a], idx[b]
            edges.append((ia, ib))
            deg[ia] += 1
            deg[ib] += 1

    cx, cy = width / 2.0, height / 2.0
    r0 = min(width, height) * 0.38
    # Deterministic circular seed (matches the renderer's reproducible start).
    x = [cx + r0 * math.cos(2 * math.pi * i / n) for i in range(n)]
    y = [cy + r0 * math.sin(2 * math.pi * i / n) for i in range(n)]
    vx = [0.0] * n
    vy = [0.0] * n
    radius = [max(3.0, min(14.0, 3.0 + 2.0 * math.sqrt(deg[i]))) for i in range(n)]

    velocity_decay = 0.6
    max_dist = min(width, height) * 0.9
    link_dist = 40.0
    gx = [0.0] * n
    if bipartite:
        for i in range(n):
            gx[i] = width * (0.27 if groups.get(node_ids[i], 0) == 0 else 0.73)
    else:
        for i in range(n):
            gx[i] = cx

    alpha = 1.0
    alpha_decay = 1.0 - 0.001 ** (1.0 / max(1, iterations))
    for _ in range(iterations):
        # charge: degree-scaled repulsion (O(n^2); n is small here)
        for i in range(n):
            for j in range(i + 1, n):
                dx = x[j] - x[i]
                dy = y[j] - y[i]
                d2 = dx * dx + dy * dy
                if d2 < 1e-6:
                    dx, dy, d2 = 0.5, 0.5, 0.5
                d = math.sqrt(d2)
                if d > max_dist:
                    continue
                strength = (30.0 + 6.0 * (deg[i] + deg[j]) / 2.0) * alpha
                f = strength / d2
                fx, fy = dx / d * f, dy / d * f
                vx[i] -= fx; vy[i] -= fy
                vx[j] += fx; vy[j] += fy
        # springs
        link_strength = (0.15 if bipartite else 0.35) * alpha
        for ia, ib in edges:
            dx = x[ib] - x[ia]
            dy = y[ib] - y[ia]
            d = math.hypot(dx, dy) or 1.0
            f = (d - link_dist) / d * link_strength
            fx, fy = dx * f, dy * f
            vx[ia] += fx; vy[ia] += fy
            vx[ib] -= fx; vy[ib] -= fy
        # group forceX / centring forceY
        sx = (0.28 if bipartite else 0.03) * alpha
        sy = 0.06 * alpha
        for i in range(n):
            vx[i] += (gx[i] - x[i]) * sx
            vy[i] += (cy - y[i]) * sy
        # integrate
        for i in range(n):
            vx[i] *= velocity_decay
            vy[i] *= velocity_decay
            x[i] += vx[i]
            y[i] += vy[i]
        # collision: resolve overlaps (a couple of relaxation passes)
        for _pass in range(2):
            for i in range(n):
                for j in range(i + 1, n):
                    dx = x[j] - x[i]
                    dy = y[j] - y[i]
                    d = math.hypot(dx, dy) or 1.0
                    overlap = (radius[i] + radius[j] + 2.0) - d
                    if overlap > 0:
                        ux, uy = dx / d, dy / d
                        shift = overlap / 2.0
                        x[i] -= ux * shift; y[i] -= uy * shift
                        x[j] += ux * shift; y[j] += uy * shift
        alpha += (0.0 - alpha) * alpha_decay

    return {node_ids[i]: (x[i], y[i]) for i in range(n)}, radius, deg
