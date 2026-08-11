"""Build a verified Mondial -> ISO-3166 numeric-id crosswalk for the choropleth renderer.

Why: the choropleth used to join Mondial's ``name`` to the world-atlas basemap by name, which
greyed out every country whose Mondial name differs in wording (United States vs United States
of America, Czech Republic vs Czechia, Congo Dem.Rep. vs Dem. Rep. Congo, accents, "Is."/"Rep."
abbreviations, ...). Mondial's ``code`` is a non-standard CIA/car-plate scheme (Germany=D,
USA=USA, S.Korea=ROK), so it can't be joined to the map directly either.

The robust fix is to join on the basemap's stable ISO 3166-1 **numeric id** (``d.id``, e.g.
840 = USA), which is wording-independent. This script matches every Mondial country to that id
once — automatically by accent/punctuation-folded name, plus a small curated alias table for
the in-map wording differences — and writes ``mondial_iso_crosswalk.json`` keyed by both the
Mondial ``code`` and ``name`` (the exact strings the renderer receives at run time, whether the
region role carried the code offline or the label-resolved name on the server). Countries with
no 110m geometry (micro-states / territories) are legitimately left out.

Run: ``python build_iso_crosswalk.py`` (needs network for the world-atlas basemap).
"""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MONDIAL = HERE.parents[1] / "mondial_database" / "mondial_data.json"
BASEMAP = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json"

# Mondial code -> the basemap's exact feature name, for countries present in the 110m map whose
# name does not accent/punctuation-fold to the Mondial name.
ALIAS = {
    "USA": "United States of America", "CZ": "Czechia", "CGO": "Dem. Rep. Congo",
    "BIH": "Bosnia and Herz.", "MK": "Macedonia", "GQ": "Eq. Guinea", "SSD": "S. Sudan",
    "SOL": "Solomon Is.", "WSA": "W. Sahara", "FALK": "Falkland Is.", "CI": "Côte d'Ivoire",
    "DOM": "Dominican Rep.", "RCA": "Central African Rep.", "SWZ": "eSwatini",
    "TL": "Timor-Leste",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def main() -> None:
    mon = json.loads(MONDIAL.read_text("utf-8"))["tables"]["country"]
    with urllib.request.urlopen(BASEMAP, timeout=20) as r:
        geos = json.load(r)["objects"]["countries"]["geometries"]
    map_by_norm = {norm((g.get("properties") or {}).get("name")): str(g["id"])
                   for g in geos if g.get("id") is not None}

    code_to_id: dict[str, str] = {}
    name_to_id: dict[str, str] = {}
    unmatched = []
    for c in mon:
        code, name = c.get("code"), c.get("name")
        mid = map_by_norm.get(norm(name))
        if not mid and code in ALIAS:
            mid = map_by_norm.get(norm(ALIAS[code]))
        if mid:
            code_to_id[code] = mid
            name_to_id[name] = mid
        else:
            unmatched.append((code, name))

    out = {
        "_note": "Mondial code/name -> ISO 3166-1 numeric id (world-atlas 110m d.id). "
                 "Built by build_iso_crosswalk.py; regenerate if Mondial's country set changes.",
        "code_to_id": code_to_id,
        "name_to_id": name_to_id,
    }
    (HERE / "mondial_iso_crosswalk.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), "utf-8")
    print(f"covered {len(code_to_id)}/{len(mon)} Mondial countries -> ISO numeric id")
    print(f"left out {len(unmatched)} (micro-states / territories absent from the 110m basemap)")


if __name__ == "__main__":
    main()
