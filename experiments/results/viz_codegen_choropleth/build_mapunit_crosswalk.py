"""Build a verified Natural-Earth-map-unit -> Mondial crosswalk for the choropleth renderer.

The choropleth uses the Natural Earth **admin-0 map units** basemap (50m), where dependencies
an ordinary country outline folds into a sovereign state (French overseas departments, Macao,
the West Bank / Gaza split, island territories) are separate, joinable polygons.

But map units also *split* some sovereign states into sub-national units — the United Kingdom
into England/Scotland/Wales/N. Ireland, Belgium into Flemish/Walloon/Brussels — while Mondial
has ONE row per sovereign. So the crosswalk is built **per map unit** (reverse: GU_A3 ->
Mondial code), assigning each unit to a Mondial country by:
  1. its own name (GEOUNIT/NAME/...), so units Mondial lists separately (French Guiana, Bermuda)
     map to their own Mondial row; else
  2. its sovereign (the ADMIN field), so England/Scotland/Wales/N. Ireland all map to Mondial
     'United Kingdom' and the three Belgian regions all map to 'Belgium'.
This colours every unit of a country, not just one, while keeping the dependencies separate.

Output ``mondial_mapunit_crosswalk.json`` has ``gu_to_code`` (GU_A3 -> Mondial code) and
``name_to_code`` (Mondial name -> code, so the renderer can resolve a name-valued region).

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
BASEMAP = ("https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@v5.1.2/"
           "geojson/ne_50m_admin_0_map_units.geojson")

# Natural Earth unit name -> Mondial name, for units whose name does not fold to the Mondial
# name (abbreviations / wording / accents). Keyed by the NE string, valued by the Mondial name.
NE_TO_MONDIAL = {
    "Democratic Republic of the Congo": "Congo, Dem.Rep.", "Republic of the Congo": "Congo",
    "United States Virgin Islands": "Virgin Islands", "Pitcairn Islands": "Pitcairn",
    "Caribbean Netherlands": "Bonaire", "Federated States of Micronesia": "Micronesia",
    "eSwatini": "Swaziland", "Republic of Serbia": "Serbia", "Czechia": "Czech Republic",
    "Macedonia": "North Macedonia", "United Republic of Tanzania": "Tanzania",
    "The Bahamas": "Bahamas", "East Timor": "East Timor",
}
UNIT_NAME_FIELDS = ("GEOUNIT", "NAME", "NAME_LONG", "NAME_EN", "BRK_NAME", "SUBUNIT")


def norm(s: object) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def main() -> None:
    mon = json.loads(MONDIAL.read_text("utf-8"))["tables"]["country"]
    name_to_code = {c["name"]: c["code"] for c in mon}

    # normalised Mondial name -> code, plus the curated NE-name aliases
    mon_by_norm: dict[str, str] = {norm(c["name"]): c["code"] for c in mon}
    for ne_name, mon_name in NE_TO_MONDIAL.items():
        if mon_name in name_to_code:
            mon_by_norm[norm(ne_name)] = name_to_code[mon_name]

    req = urllib.request.Request(BASEMAP, headers={"User-Agent": "crosswalk-build"})
    feats = json.loads(urllib.request.urlopen(req, timeout=60).read())["features"]

    gu_to_code: dict[str, str] = {}
    unassigned = []
    for f in feats:
        p = f.get("properties") or {}
        gu = p.get("GU_A3")
        code = None
        for k in UNIT_NAME_FIELDS:          # 1) the unit's own name (keeps dependencies separate)
            if p.get(k) and norm(p[k]) in mon_by_norm:
                code = mon_by_norm[norm(p[k])]
                break
        if code is None and p.get("ADMIN"):  # 2) else its sovereign (UK/Belgium sub-units)
            code = mon_by_norm.get(norm(p["ADMIN"]))
        if code:
            gu_to_code[gu] = code
        else:
            unassigned.append((gu, p.get("GEOUNIT")))

    out = {
        "_note": "Natural Earth GU_A3 -> Mondial code (ne_50m_admin_0_map_units v5.1.2), built "
                 "per unit (own name, else sovereign ADMIN). Regenerate via build_mapunit_crosswalk.py.",
        "basemap": BASEMAP,
        "join_property": "GU_A3",
        "gu_to_code": gu_to_code,
        "name_to_code": name_to_code,
    }
    (HERE / "mondial_mapunit_crosswalk.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), "utf-8")
    covered = sorted(set(gu_to_code.values()))
    print(f"assigned {len(gu_to_code)}/{len(feats)} map units to {len(covered)} Mondial countries")
    print(f"unassigned units (no Mondial country / not a state): {len(unassigned)}")


if __name__ == "__main__":
    main()
