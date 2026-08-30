"""Reference chord renderer for the two relationship patterns (D3 v7).

Faithful response to prompts/viz_codegen/base_d3v7.md + chart_chord.md. A chord
diagram serves **both** relationship patterns:

* ``reflexive_many_many_relationship`` — both foreign keys reference the *same*
  entity set; every point on the circle is an instance of one type, ribbons may
  connect any pair. Nodes are the sorted union; each gets its own rainbow colour.
* ``many_many_relationship`` — the two foreign keys reference *two different*
  entity sets, so the chord is **bipartite**: all source instances form one
  contiguous arc, all target instances another, coloured by two distinct colour
  families, and every ribbon runs between the groups (never within one).

The pattern is read from ``mapping["pattern"]`` when present; otherwise it is
inferred from the data (disjoint source/target value sets ⇒ bipartite). The
matrix machinery is identical for both — only node ordering and colouring differ.
HTML assembled by plain string concatenation (no f-string / str.format). Std-lib
only; D3 v7; hover interaction.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

# Plain string with literal JS braces; the dynamic values (names / matrix / size /
# groupOf / bipartite / colours / title) are concatenated in render(), never
# formatted into this body.
JS_BODY = """
const outerR = size / 2 - 90, innerR = outerR - 14;

// Colour: reflexive -> one rainbow per instance; bipartite -> two colour
// families, one per entity group, ramped so individual arcs stay distinguishable.
let color;
if (bipartite) {
  const ramps = [d3.interpolateBlues, d3.interpolateOranges];
  const size_g = [0, 0];
  groupOf.forEach(g => size_g[g]++);
  const seen = [0, 0];
  const cmap = groupOf.map(g => {
    const p = (seen[g] + 1) / (size_g[g] + 1);
    seen[g]++;
    return d3.color(ramps[g](0.35 + 0.55 * p)).formatHex();
  });
  color = i => cmap[i];
} else {
  const ord = d3.scaleOrdinal(names, d3.quantize(d3.interpolateRainbow, Math.max(2, names.length)));
  color = i => ord(names[i]);
}

const chords = d3.chord().padAngle(0.02).sortSubgroups(d3.descending)(matrix);
const arc = d3.arc().innerRadius(innerR).outerRadius(outerR);
const ribbon = d3.ribbon().radius(innerR);

const tip = d3.select("#tip");
// Escape values only where they enter innerHTML (the tooltip); on-canvas labels use .text() and stay raw.
const escHtml = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const moveTip = (event) => tip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY + 12) + "px");

const svg = d3.select("#chart").append("svg")
  .attr("width", size).attr("height", size)
  .append("g").attr("transform", `translate(${size / 2},${size / 2})`);

const group = svg.append("g").selectAll("g").data(chords.groups).join("g");
const arcs = group.append("path").attr("d", arc)
  .attr("fill", d => color(d.index))
  .attr("stroke", "#fff");

group.append("text")
  .each(d => { d.angle = (d.startAngle + d.endAngle) / 2; })
  .attr("dy", "0.35em")
  .attr("transform", d => `rotate(${d.angle * 180 / Math.PI - 90}) translate(${outerR + 6}) ${d.angle > Math.PI ? "rotate(180)" : ""}`)
  .attr("text-anchor", d => d.angle > Math.PI ? "end" : null)
  .text(d => names[d.index]);

const ribbons = svg.append("g").attr("fill-opacity", 0.7).selectAll("path").data(chords).join("path")
  .attr("d", ribbon)
  .attr("fill", d => color(d.source.index))
  .attr("stroke", "#fff");

arcs
  .on("mouseover", (event, d) => {
    ribbons.attr("fill-opacity", r => (r.source.index === d.index || r.target.index === d.index) ? 0.9 : 0.04);
    arcs.attr("opacity", a => (a.index === d.index) ? 1 : 0.3);
    tip.style("opacity", 1).html("<strong>" + escHtml(names[d.index]) + "</strong><br>total " + valueLabel + ": " + Math.round(d.value));
    moveTip(event);
  })
  .on("mousemove", moveTip)
  .on("mouseout", () => { ribbons.attr("fill-opacity", 0.7); arcs.attr("opacity", 1); tip.style("opacity", 0); });

ribbons
  .on("mouseover", (event, d) => {
    ribbons.attr("fill-opacity", r => (r === d) ? 0.95 : 0.04);
    tip.style("opacity", 1).html(escHtml(names[d.source.index]) + " &harr; " + escHtml(names[d.target.index]) + "<br>" + valueLabel + ": " + Math.round(d.source.value));
    moveTip(event);
  })
  .on("mousemove", moveTip)
  .on("mouseout", () => { ribbons.attr("fill-opacity", 0.7); tip.style("opacity", 0); });

// Legend (bipartite only): name the two entity groups and their colour families.
if (bipartite && legend.length === 2) {
  const lg = d3.select("#chart svg").append("g").attr("transform", "translate(16,16)");
  const swatch = [d3.interpolateBlues(0.65), d3.interpolateOranges(0.65)];
  legend.forEach((lab, i) => {
    const row = lg.append("g").attr("transform", `translate(0,${i * 18})`);
    row.append("rect").attr("width", 12).attr("height", 12).attr("fill", swatch[i]);
    row.append("text").attr("x", 17).attr("y", 10).attr("font-size", 11).text(lab);
  });
}
"""

HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__T__</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  body { font-family: Arial, sans-serif; margin: 16px; }
  h1 { font-size: 18px; margin-bottom: 2px; }
  #sub { color: #555; font-size: 12px; margin: 0 0 8px; }
  text { font-size: 9px; }
  #tip { position: absolute; opacity: 0; pointer-events: none; background: rgba(0,0,0,0.82);
         color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 12px; line-height: 1.4; }
</style>
</head>
<body>
<h1>__T__</h1>
<p id="sub">__SUB__</p>
<div id="chart"></div>
<div id="tip"></div>
<script>
"""


def _rows_for(mapping: dict[str, Any], data: Any) -> list[dict[str, Any]]:
    """Accept either a flat row array, or the grouped Mondial DB and select the table.

    The grouped form is ``{"tables": {<name>: [rows]}}`` (e.g. mondial_data.json); the
    relation to read is named by ``mapping["table"]``.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        table = mapping.get("table")
        if isinstance(data.get("tables"), dict):
            if not table:
                raise ValueError("data is a grouped database; mapping must name the relation via 'table'")
            return data["tables"][table]
        if table in data:
            return data[table]
    raise ValueError("unsupported data shape: expected a row array or a grouped {'tables': {...}} database")


def _encoding(mapping: dict[str, Any]) -> dict[str, str]:
    if {"source", "target", "width"} <= set(mapping):
        return {k: mapping[k] for k in ("source", "target", "width")}
    sub = mapping.get("chart_mapping")
    if isinstance(sub, dict) and {"source", "target", "width"} <= set(sub):
        return {k: sub[k] for k in ("source", "target", "width")}
    sel = mapping.get("selected_visualisation", {})
    enc = sel.get("encoding") if isinstance(sel, dict) else None
    if isinstance(enc, dict) and {"source", "target", "width"} <= set(enc):
        return {k: enc[k] for k in ("source", "target", "width")}
    raise ValueError("mapping must provide source/target/width")


def render(mapping: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    enc = _encoding(mapping)
    s_col, t_col, w_col = enc["source"], enc["target"], enc["width"]

    src_vals = sorted({str(r[s_col]) for r in rows if s_col in r})
    tgt_vals = sorted({str(r[t_col]) for r in rows if t_col in r})

    # Decide framing: explicit pattern hint wins; else infer (disjoint sets => bipartite).
    pattern = str(mapping.get("pattern", "")).lower()
    if "reflexive" in pattern:
        bipartite = False
    elif "many_many" in pattern:
        bipartite = True
    else:
        bipartite = len(set(src_vals) & set(tgt_vals)) == 0 and bool(src_vals) and bool(tgt_vals)

    if bipartite:
        # Two contiguous arcs: all sources (group 0), then all targets (group 1).
        names = src_vals + tgt_vals
        group_of = [0] * len(src_vals) + [1] * len(tgt_vals)
    else:
        # One shared set: sorted union, one colour per instance.
        names = sorted(set(src_vals) | set(tgt_vals))
        group_of = [0] * len(names)
    idx = {name: i for i, name in enumerate(names)}

    n = len(names)
    matrix = [[0.0] * n for _ in range(n)]
    for r in rows:
        if s_col not in r or t_col not in r or w_col not in r:
            continue
        try:
            w = float(r[w_col])
        except (TypeError, ValueError):
            continue
        i, j = idx[str(r[s_col])], idx[str(r[t_col])]
        matrix[i][j] += w
        if i != j:
            matrix[j][i] += w

    connector = " → " if bipartite else " ↔ "
    default_title = s_col + connector + t_col + " chord diagram"
    title = html.escape(mapping.get("title") or default_title)
    if bipartite:
        subtitle = "Ribbon width represents '" + w_col + "'. Bipartite: '" + s_col + "' (blue) linked to '" + t_col + "' (orange)."
        legend = [s_col, t_col]
    else:
        subtitle = "Ribbon width represents '" + w_col + "'. Reflexive: one entity set linked to itself."
        legend = []
    names_json = json.dumps(names)
    size = max(700, min(1400, n * 9 + 300))

    # Plain concatenation: inject the dynamic values, keep JS braces literal.
    return (
        HEAD.replace("__T__", title).replace("__SUB__", html.escape(subtitle))
        + "const names = " + names_json + ";\n"
        + "const matrix = " + json.dumps(matrix) + ";\n"
        + "const groupOf = " + json.dumps(group_of) + ";\n"
        + "const bipartite = " + ("true" if bipartite else "false") + ";\n"
        + "const legend = " + json.dumps(legend) + ";\n"
        + "const valueLabel = " + json.dumps(html.escape(w_col)) + ";\n"
        + "const size = " + str(size) + ";\n"
        + JS_BODY
        + "</script>\n</body>\n</html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a many-many / reflexive chord diagram to standalone HTML (D3 v7).")
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    rows = _rows_for(mapping, json.loads(Path(args.data).read_text(encoding="utf-8")))
    html_doc = render(mapping, rows)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {out} ({len(html_doc)} bytes)")


if __name__ == "__main__":
    main()
