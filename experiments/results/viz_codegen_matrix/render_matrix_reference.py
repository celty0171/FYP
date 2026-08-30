"""Reference adjacency-matrix heatmap renderer for the two relationship patterns (D3 v7).

Faithful response to prompts/viz_codegen/base_d3v7.md + chart_matrix.md. A matrix
heatmap serves **both** relationship patterns and, unlike Sankey/chord, does not
require a scalar relationship attribute — when none exists the cell value is the
**edge count**:

* ``reflexive_many_many_relationship`` — both foreign keys reference the *same*
  entity set; the matrix is a square adjacency matrix over the sorted union of
  instances (symmetric: (a,b) and (b,a) both filled).
* ``many_many_relationship`` — the two foreign keys reference *two different* sets,
  so the matrix is **bipartite**: rows are the ``source`` (E1) instances, columns
  the ``target`` (E2) instances (an E1 x E2 rectangle). Not made square.

The cell value is a scalar ``value`` column, else the legacy ``width`` column, else
the literal edge ``"count"`` (unlocks relations with no scalar, e.g. is_member /
merges_with). An optional ``category`` column names a discrete edge attribute whose
per-cell dominant value is shown in the tooltip (colour still encodes count/value).

Node ordering reuses the chord seriation (sorted). HTML assembled by plain string
concatenation (no f-string / str.format). Std-lib only; D3 v7; hover interaction.
"""

from __future__ import annotations

import argparse
import html
import json
from collections import Counter
from pathlib import Path
from typing import Any

# Plain string with literal JS braces; the dynamic values (rows/cols/matrix/labels/
# size/bipartite/valueLabel) are concatenated in render(), never formatted in.
JS_BODY = """
const FONT = 9, CHAR_W = 6;   // approx label pixel width per character at 9px

// Square cells, sized to the larger dimension so both small and 10k-cell matrices fit.
const cell = Math.max(6, Math.min(22, Math.floor(900 / Math.max(rowNames.length, colNames.length))));
const w = cell * colNames.length, h = cell * rowNames.length;

// Reserve margin from the longest label so rotated column / left row labels are not clipped
// (capped so an outlier name does not blow up the layout; getBBox below is the final safety net).
const maxColLen = d3.max(colNames, s => s.length) || 1;
const maxRowLen = d3.max(rowNames, s => s.length) || 1;
const margin = { top: Math.min(240, maxColLen * CHAR_W + 14), right: 24,
                 bottom: 72, left: Math.min(280, maxRowLen * CHAR_W + 14) };

const x = d3.scaleBand().domain(d3.range(colNames.length)).range([0, w]);
const y = d3.scaleBand().domain(d3.range(rowNames.length)).range([0, h]);

const maxVal = d3.max(cells, c => c.v) || 1;
const color = d3.scaleSequential(d3.interpolateYlGnBu).domain([0, maxVal]);

const svg = d3.select("#chart").append("svg")
  .attr("width", w + margin.left + margin.right)
  .attr("height", h + margin.top + margin.bottom)
  .append("g").attr("transform", `translate(${margin.left},${margin.top})`);

const tip = d3.select("#tip");
// Escape values only where they enter innerHTML (the tooltip); on-canvas labels use .text() and stay raw.
const escHtml = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const moveTip = (event) => tip.style("left", (event.pageX + 12) + "px").style("top", (event.pageY + 12) + "px");

// Faint frame around the grid so empty (unfilled) pairs still read as part of the matrix.
svg.append("rect").attr("x", 0).attr("y", 0).attr("width", w).attr("height", h)
  .attr("fill", "#fbfbfc").attr("stroke", "#e5e7eb");

// One rect per present pair; empty pairs stay blank so real relationships pop.
const rects = svg.append("g").selectAll("rect").data(cells).join("rect")
  .attr("x", d => x(d.j)).attr("y", d => y(d.i))
  .attr("width", x.bandwidth()).attr("height", y.bandwidth())
  .attr("fill", d => color(d.v))
  .attr("stroke", "#fff").attr("stroke-width", 0.5)
  .on("mouseover", (event, d) => {
    rects.attr("opacity", r => (r.i === d.i || r.j === d.j) ? 1 : 0.25);
    let msg = "<strong>" + escHtml(rowNames[d.i]) + "</strong> &harr; <strong>" + escHtml(colNames[d.j]) + "</strong>"
            + "<br>" + valueLabel + ": " + (Number.isInteger(d.v) ? d.v : d.v.toFixed(2));
    if (d.cat) msg += "<br>top " + categoryLabel + ": " + escHtml(d.cat);
    tip.style("opacity", 1).html(msg);
    moveTip(event);
  })
  .on("mousemove", moveTip)
  .on("mouseout", () => { rects.attr("opacity", 1); tip.style("opacity", 0); });

// Thin the tick labels when bands are narrower than the font so they never overlap.
const step = Math.max(1, Math.ceil((FONT + 2) / cell));

// Column labels (rotated, along the top).
svg.append("g").selectAll("text").data(colNames.map((nm, j) => ({ nm, j }))).join("text")
  .attr("transform", d => `translate(${x(d.j) + x.bandwidth() / 2},-6) rotate(-90)`)
  .attr("text-anchor", "start").attr("dy", "0.32em")
  .attr("display", d => (d.j % step === 0) ? null : "none")
  .text(d => d.nm);

// Row labels (down the left).
svg.append("g").selectAll("text").data(rowNames.map((nm, i) => ({ nm, i }))).join("text")
  .attr("x", -6).attr("y", d => y(d.i) + y.bandwidth() / 2)
  .attr("text-anchor", "end").attr("dy", "0.32em")
  .attr("display", d => (d.i % step === 0) ? null : "none")
  .text(d => d.nm);

// Colour legend / key below the grid: a segmented gradient bar with a 0..max axis.
{
  const legendW = 190, legendH = 10, segs = 64;
  const lg = svg.append("g").attr("transform", `translate(0,${h + 30})`);
  lg.append("text").attr("x", 0).attr("y", -6).attr("font-size", 10).attr("fill", "#333")
    .text("Colour — " + valueLabel);
  lg.selectAll("rect").data(d3.range(segs)).join("rect")
    .attr("x", k => (k / segs) * legendW).attr("y", 0)
    .attr("width", legendW / segs + 1).attr("height", legendH)
    .attr("fill", k => color((k / (segs - 1)) * maxVal));
  const lscale = d3.scaleLinear().domain([0, maxVal]).range([0, legendW]);
  lg.append("g").attr("transform", `translate(0,${legendH})`)
    .call(d3.axisBottom(lscale).ticks(4).tickSize(3))
    .call(g => g.selectAll("text").attr("font-size", 8))
    .call(g => g.select(".domain").attr("stroke", "#bbb"));
}

// Fit the SVG viewport to all rendered content so nothing is ever clipped, whatever the
// data (e.g. long rotated column labels can extend past the top margin). getBBox() returns
// the tight box of every mark; resize the root <svg> to match.
{
  const rootSvg = d3.select("#chart").select("svg");
  const bb = rootSvg.node().getBBox();
  const pad = 16;
  rootSvg.attr("viewBox", [bb.x - pad, bb.y - pad, bb.width + 2 * pad, bb.height + 2 * pad].join(" "))
         .attr("width", bb.width + 2 * pad)
         .attr("height", bb.height + 2 * pad);
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
  text { font-size: 9px; fill: #222; }
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


def _encoding(mapping: dict[str, Any]) -> dict[str, Any]:
    """Resolve source/target plus the optional weight and category columns.

    The weight column is read as ``value`` (may be a column name or the literal
    "count"), falling back to the legacy ``width`` field, else counting edges.
    """
    src = mapping.get("source")
    tgt = mapping.get("target")
    if not (src and tgt):
        sub = mapping.get("chart_mapping")
        if isinstance(sub, dict):
            src, tgt = sub.get("source"), sub.get("target")
            mapping = {**mapping, **sub}
    if not (src and tgt):
        sel = mapping.get("selected_visualisation", {})
        enc = sel.get("encoding") if isinstance(sel, dict) else None
        if isinstance(enc, dict):
            src, tgt = enc.get("source"), enc.get("target")
            mapping = {**mapping, **enc}
    if not (src and tgt):
        raise ValueError("mapping must provide source/target")

    value = mapping.get("value")
    if value is None:
        value = mapping.get("width")
    use_count = value is None or str(value).lower() == "count"
    return {
        "source": src,
        "target": tgt,
        "value": None if use_count else value,
        "category": mapping.get("category"),
    }


def render(mapping: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    enc = _encoding(mapping)
    s_col, t_col, v_col, c_col = enc["source"], enc["target"], enc["value"], enc["category"]

    src_vals = sorted({str(r[s_col]) for r in rows if s_col in r})
    tgt_vals = sorted({str(r[t_col]) for r in rows if t_col in r})

    pattern = str(mapping.get("pattern", "")).lower()
    if "reflexive" in pattern:
        bipartite = False
    elif "many_many" in pattern:
        bipartite = True
    else:
        bipartite = len(set(src_vals) & set(tgt_vals)) == 0 and bool(src_vals) and bool(tgt_vals)

    if bipartite:
        # Rectangular E1 x E2 matrix: rows = sources, cols = targets.
        row_names, col_names = src_vals, tgt_vals
    else:
        # Square symmetric adjacency matrix over the shared node set.
        row_names = col_names = sorted(set(src_vals) | set(tgt_vals))
    r_idx = {n: i for i, n in enumerate(row_names)}
    c_idx = {n: j for j, n in enumerate(col_names)}

    agg: dict[tuple[int, int], float] = {}
    cats: dict[tuple[int, int], Counter] = {}
    for r in rows:
        if s_col not in r or t_col not in r:
            continue
        sv, tv = str(r[s_col]), str(r[t_col])
        if v_col is None:
            w = 1.0
        else:
            try:
                w = float(r[v_col])
            except (TypeError, ValueError):
                continue
        i, j = r_idx[sv], c_idx[tv]
        agg[(i, j)] = agg.get((i, j), 0.0) + w
        if not bipartite and i != j:
            agg[(j, i)] = agg.get((j, i), 0.0) + w
        if c_col and c_col in r:
            cats.setdefault((i, j), Counter())[str(r[c_col])] += 1
            if not bipartite and i != j:
                cats.setdefault((j, i), Counter())[str(r[c_col])] += 1

    cells = []
    for (i, j), v in agg.items():
        cell: dict[str, Any] = {"i": i, "j": j, "v": v}
        if (i, j) in cats:
            cell["cat"] = cats[(i, j)].most_common(1)[0][0]
        cells.append(cell)

    value_label = "count" if v_col is None else v_col
    connector = " x " if bipartite else " x "
    default_title = s_col + connector + t_col + " adjacency matrix"
    title = html.escape(mapping.get("title") or default_title)
    frame = "bipartite (" + s_col + " rows x " + t_col + " cols)" if bipartite else "symmetric adjacency (shared node set)"
    subtitle = "Cell colour encodes '" + value_label + "'. " + frame + "."
    if c_col:
        subtitle += " Tooltip names the dominant '" + c_col + "'."

    return (
        HEAD.replace("__T__", title).replace("__SUB__", html.escape(subtitle))
        + "const rowNames = " + json.dumps(row_names) + ";\n"
        + "const colNames = " + json.dumps(col_names) + ";\n"
        + "const cells = " + json.dumps(cells) + ";\n"
        + "const valueLabel = " + json.dumps(html.escape(value_label)) + ";\n"
        + "const categoryLabel = " + json.dumps(html.escape(c_col or "")) + ";\n"
        + "const bipartite = " + ("true" if bipartite else "false") + ";\n"
        + JS_BODY
        + "</script>\n</body>\n</html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a many-many / reflexive adjacency-matrix heatmap to standalone HTML (D3 v7).")
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
