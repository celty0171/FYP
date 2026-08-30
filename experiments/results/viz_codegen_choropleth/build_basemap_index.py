"""Build a **database-agnostic** index for the world-atlas choropleth basemap.

Unlike ``build_iso_crosswalk.py`` (which maps *Mondial's* country codes to feature ids), this
builds a generic lookup so a choropleth can join *any* database's region column: it resolves a
country **name**, an **ISO alpha-2 / alpha-3** code, or the raw numeric feature id to the
world-atlas feature id (``d.id``, the ISO 3166-1 numeric code).

Sources (both fetched at build time — needs network):
  * world-atlas ``countries-50m`` — the basemap itself (numeric id + feature name).
  * an ISO 3166-1 table (name / alpha-2 / alpha-3 / numeric) to add code lookups the basemap
    does not carry. Best-effort: if it can't be fetched, the index still covers names + ids.

Writes ``world_basemap_index.json`` next to the renderer. Run:
    python build_basemap_index.py
"""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASEMAP = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-50m.json"
# Widely used ISO 3166-1 dataset (name, alpha-2, alpha-3, numeric country-code).
ISO_TABLE = ("https://raw.githubusercontent.com/lukes/"
             "ISO-3166-Countries-with-Regional-Codes/master/all/all.json")


def norm(s: object) -> str:
    """Accent/punctuation-folded lower-case name key (must match the renderer's _norm)."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def _fetch(url: str) -> object:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def main() -> None:
    geos = _fetch(BASEMAP)["objects"]["countries"]["geometries"]
    name_to_id: dict[str, str] = {}
    ids: list[str] = []
    for g in geos:
        gid = g.get("id")
        if gid is None:
            continue
        ids.append(str(gid))
        nm = norm((g.get("properties") or {}).get("name"))
        if nm:
            name_to_id.setdefault(nm, str(gid))

    alpha2_to_id: dict[str, str] = {}
    alpha3_to_id: dict[str, str] = {}
    id_set = set(ids)
    try:
        iso = _fetch(ISO_TABLE)
        for row in iso:
            numeric = str(row.get("country-code") or "").zfill(3)
            if numeric not in id_set:
                continue
            a2 = (row.get("alpha-2") or "").lower()
            a3 = (row.get("alpha-3") or "").lower()
            if a2:
                alpha2_to_id[a2] = numeric
            if a3:
                alpha3_to_id[a3] = numeric
            # also fold the ISO English name in, in case the basemap name differs
            nm = norm(row.get("name"))
            if nm:
                name_to_id.setdefault(nm, numeric)
        iso_note = str(len(alpha3_to_id)) + " ISO codes"
    except Exception as exc:  # names + numeric ids still work without the code table
        iso_note = "no ISO code table (" + str(exc) + ")"

    out = {
        "_note": "Generic world-atlas (countries-50m) index: resolve a region name / ISO alpha-2 "
                 "/ alpha-3 / numeric id to the feature id (d.id). Built by build_basemap_index.py.",
        "basemap": BASEMAP,
        "join_property": "id",
        "name_to_id": name_to_id,
        "alpha2_to_id": alpha2_to_id,
        "alpha3_to_id": alpha3_to_id,
        "ids": sorted(id_set),
    }
    (HERE / "world_basemap_index.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), "utf-8")
    print("indexed " + str(len(name_to_id)) + " names, " + str(len(id_set)) + " ids, " + iso_note)


if __name__ == "__main__":
    main()
