"""Build a verified Mondial -> Natural Earth map-unit crosswalk for the choropleth renderer.

The choropleth uses the Natural Earth **admin-0 map units** basemap (50m) instead of a plain
country outline, so dependencies drawn as part of a sovereign state on an ordinary map — French
overseas departments (French Guiana, Guadeloupe, Martinique, Mayotte, Réunion), Macao, Svalbard,
the West Bank / Gaza split, and many island territories — are separate, joinable polygons. Each
feature carries a unique, stable geo-unit code ``GU_A3`` (265/265 distinct), which is the join key.

This script matches every Mondial country to its map unit once — automatically by
accent/punctuation-folded name against all Natural Earth name fields, plus a small curated alias
table for the few wording differences — and writes ``mondial_mapunit_crosswalk.json`` keyed by
both the Mondial ``code`` and ``name`` (the exact strings the renderer receives at run time,
whether the region role carries the code offline or the label-resolved name on the server).

Coverage: 242/246 Mondial countries. The 4 left out (Akrotiri and Dhekelia, Ceuta, Melilla,
Gibraltar) are micro-enclaves / bases that Natural Earth does not separate at 50m — no country
basemap represents them as distinct polygons.

Run: ``python build_mapunit_crosswalk.py`` (needs network for the basemap).
"""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MONDIAL = HERE.parents[1] / "mondial_database" / "mondial_data.json"
# Pinned Natural Earth release for reproducibility (same URL the renderer fetches).
BASEMAP = ("https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@v5.1.2/"
           "geojson/ne_50m_admin_0_map_units.geojson")

# Mondial code -> a Natural Earth name variant, for units that do not fold to the Mondial name.
ALIAS = {
    "CGO": "Democratic Republic of the Congo", "RCB": "Republic of the Congo",
    "VIRG": "United States Virgin Islands", "PN": "Pitcairn Islands",
    "NLB": "Caribbean Netherlands", "FSM": "Federated States of Micronesia",
    "SWZ": "eSwatini", "MK": "North Macedonia", "CI": "Côte d'Ivoire",
}
NAME_FIELDS = ("NAME", "GEOUNIT", "NAME_LONG", "NAME_EN", "BRK_NAME", "SUBUNIT", "ADMIN")


def norm(s: object) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def main() -> None:
    mon = json.loads(MONDIAL.read_text("utf-8"))["tables"]["country"]
    req = urllib.request.Request(BASEMAP, headers={"User-Agent": "crosswalk-build"})
    feats = json.loads(urllib.request.urlopen(req, timeout=60).read())["features"]

    idx: dict[str, str] = {}   # normalised NE name -> GU_A3
    for f in feats:
        p = f.get("properties") or {}
        gu = p.get("GU_A3")
        for k in NAME_FIELDS:
            if p.get(k):
                idx.setdefault(norm(p[k]), gu)

    code_to_id: dict[str, str] = {}
    name_to_id: dict[str, str] = {}
    missing = []
    for c in mon:
        code, name = c.get("code"), c.get("name")
        gu = idx.get(norm(name))
        if gu is None and code in ALIAS:
            gu = idx.get(norm(ALIAS[code]))
        if gu:
            code_to_id[code] = gu
            name_to_id[name] = gu
        else:
            missing.append((code, name))

    out = {
        "_note": "Mondial code/name -> Natural Earth GU_A3 (ne_50m_admin_0_map_units v5.1.2). "
                 "Built by build_mapunit_crosswalk.py; regenerate if Mondial's country set changes.",
        "basemap": BASEMAP,
        "join_property": "GU_A3",
        "code_to_id": code_to_id,
        "name_to_id": name_to_id,
    }
    (HERE / "mondial_mapunit_crosswalk.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), "utf-8")
    print(f"covered {len(code_to_id)}/{len(mon)} Mondial countries -> GU_A3")
    print(f"left out {len(missing)} (Natural Earth does not separate these at 50m):")
    for code, name in sorted(missing, key=lambda x: str(x[1])):
        print("   ", repr(code), repr(name))


if __name__ == "__main__":
    main()
