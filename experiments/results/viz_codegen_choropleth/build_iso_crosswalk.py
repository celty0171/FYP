"""Build a Mondial -> ISO-3166 numeric-id crosswalk for the *world-atlas countries* choropleth.

This is the alternative, country-outline basemap (world-atlas 50m): sovereign states are single
polygons (UK, Belgium each one feature) and dependencies are merged into their sovereign, keyed
by the stable ISO 3166-1 numeric id (``d.id``). Compared with the Natural Earth map-units basemap
it is cleaner/simpler but does not draw dependencies (French overseas departments, etc.) as
separate regions — the professor can switch between the two in the UI and pick.

Matches every Mondial country to that id once (accent/punctuation-folded name + a curated alias
table) and writes ``mondial_iso_crosswalk.json`` keyed by Mondial ``code`` and ``name``.

Run: ``python build_iso_crosswalk.py`` (needs network for the basemap).
"""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MONDIAL = HERE.parents[1] / "mondial_database" / "mondial_data.json"
BASEMAP = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-50m.json"

# Mondial code -> the basemap's exact feature name, for countries present in the 50m map whose
# name does not accent/punctuation-fold to the Mondial name.
ALIAS = {
    "USA": "United States of America", "CZ": "Czechia", "CGO": "Dem. Rep. Congo",
    "BIH": "Bosnia and Herz.", "MK": "North Macedonia", "GQ": "Eq. Guinea", "SSD": "S. Sudan",
    "SOL": "Solomon Is.", "WSA": "W. Sahara", "FALK": "Falkland Is.", "CI": "Côte d'Ivoire",
    "DOM": "Dominican Rep.", "RCA": "Central African Rep.", "SWZ": "eSwatini",
    "TL": "Timor-Leste", "CV": "Cabo Verde", "MAC": "Macao", "VIRG": "U.S. Virgin Is.",
    "BRN": "Bahrain", "FSM": "Micronesia", "CGO2": "Congo",
}


def norm(s: object) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def main() -> None:
    mon = json.loads(MONDIAL.read_text("utf-8"))["tables"]["country"]
    with urllib.request.urlopen(BASEMAP, timeout=30) as r:
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
        "_note": "Mondial code/name -> ISO 3166-1 numeric id (world-atlas countries-50m d.id). "
                 "Built by build_iso_crosswalk.py; regenerate if Mondial's country set changes.",
        "basemap": BASEMAP,
        "join_property": "id",
        "code_to_id": code_to_id,
        "name_to_id": name_to_id,
    }
    (HERE / "mondial_iso_crosswalk.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), "utf-8")
    print(f"covered {len(code_to_id)}/{len(mon)} Mondial countries -> ISO numeric id")
    print(f"left out {len(unmatched)} (absent from the world-atlas 50m country set)")


if __name__ == "__main__":
    main()
