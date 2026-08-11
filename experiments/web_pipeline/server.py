"""Deterministic Step 1->2->3 pipeline web front-end (no model calls).

Wires three deterministic programs together:
  Step 1  pattern identification : results/prompt_v9_codegen/gpt_generated.py
  Step 2  chart recommend + map  : results/step2_codegen/gpt_recommend_charts.py
  Step 3  visualisation render   : results/viz_codegen_*/render_*_reference.py

A column selection flows: classify -> recommend -> render the chosen chart's mapping
against mondial_data.json. Charts without a renderer yet return "working in process".

Standard library only. Run:
    python experiments/web_pipeline/server.py --port 8090
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

EXP = Path(__file__).resolve().parents[1]          # experiments/
HERE = Path(__file__).resolve().parent
WORKING = "working in process"

# Import the production data-source / config / NL layers as top-level packages.
import sys
if str(EXP) not in sys.path:
    sys.path.insert(0, str(EXP))
from config import load_config                       # noqa: E402
from datasource import make_datasource               # noqa: E402


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# Data source is chosen by .env (VIZER_DATASOURCE): JSON files by default (experiments
# unchanged), or a live PostgreSQL database in production. Both yield the same schema
# dict + row dicts, so nothing downstream changes.
CONFIG = load_config()
DS = make_datasource(CONFIG)
SCHEMA = DS.get_schema()
TABLES = DS.tables_view()                            # {table: rows}; lazy for live DB

# Renderers load D3 (and, for a few charts, a D3 plugin) from CDNs. In an offline /
# restricted-network browser those fail (ERR_CONNECTION_CLOSED -> "d3 is not defined" ->
# blank chart), so inline vendored copies into each chart's HTML. The chart runs in a
# sandboxed srcdoc iframe (opaque origin), where a relative/absolute <script src> cannot
# resolve — inlining is the only robust fix. Any CDN whose vendored file is missing is
# left as a CDN tag (graceful fallback).
#
# Maps each exact CDN URL used by the renderers to its vendored file.
_VENDOR = {
    "https://d3js.org/d3.v7.min.js": "d3.v7.min.js",
    "https://cdn.jsdelivr.net/npm/d3-sankey@0.12/dist/d3-sankey.min.js": "d3-sankey.min.js",
    "https://cdn.jsdelivr.net/npm/d3-cloud@1/build/d3.layout.cloud.js": "d3.layout.cloud.js",
}


def _load_vendor():
    out = {}
    for url, fname in _VENDOR.items():
        p = HERE / "vendor" / fname
        if p.exists():
            out[url] = p.read_text("utf-8")
    return out


VENDOR_SRC = _load_vendor()


def _inline_d3(html: str) -> str:
    """Replace each vendored CDN <script src="URL"></script> with its inline source."""
    if not VENDOR_SRC or not isinstance(html, str):
        return html
    for url, src in VENDOR_SRC.items():
        tag = re.compile(r'<script[^>]*src="' + re.escape(url) + r'"[^>]*>\s*</script>')
        html = tag.sub(lambda _m, s=src: "<script>" + s + "</script>", html, count=1)
    return html

STEP1 = _load(EXP / "results" / "prompt_v9_codegen" / "gpt_generated.py", "step1_classifier")
STEP2 = _load(EXP / "results" / "step2_codegen" / "gpt_recommend_charts.py", "step2_recommender")
# Phase-1 same-table filtering: the deterministic prepare stage (see filter/PLAN.md).
FILTER = _load(EXP / "filter" / "apply_filters.py", "prepare_filter")
# Phase-1b same-table aggregation: group-by/resample -> derived basic_entity (see aggregate/PLAN.md).
AGG = _load(EXP / "aggregate" / "aggregate_rows.py", "prepare_aggregate")
# Phase-2 cross-table join: enrich base rows with foreign columns (see join/PLAN.md).
JOIN = _load(EXP / "join" / "join_tables.py", "prepare_join")

# chart-name (lower-case) -> renderer module file
RENDERER_PATHS = {
    "bar chart": "viz_codegen_bar/render_bar_reference.py",
    "scatter diagram": "viz_codegen_scatterbubble/render_scatterbubble_reference.py",
    "bubble chart": "viz_codegen_scatterbubble/render_scatterbubble_reference.py",
    "calendar chart": "viz_codegen_calendar/render_calendar_reference.py",
    "tree map": "viz_codegen_treemap/render_treemap_reference.py",
    "circle packing": "viz_codegen_circlepack/render_circlepack_reference.py",
    "hierarchy tree": "viz_codegen_hierarchytree/render_hierarchytree_reference.py",
    "sankey diagram": "viz_codegen_sankey_d3/sonnet_sankey.py",
    "chord diagram": "viz_codegen_chord/sonnet_chord.py",
    "matrix heatmap": "viz_codegen_matrix/sonnet_matrix.py",
    "force graph": "viz_codegen_force/sonnet_force.py",
    "arc diagram": "viz_codegen_arc/sonnet_arc.py",
    "line chart": "viz_codegen_weak/render_line_reference.py",
    "stacked bar chart": "viz_codegen_weak/render_stacked_reference.py",
    "grouped bar chart": "viz_codegen_weak/render_grouped_reference.py",
    "spider chart": "viz_codegen_weak/render_spider_reference.py",
    "choropleth map": "viz_codegen_choropleth/render_choropleth_reference.py",
    "word cloud": "viz_codegen_wordcloud/render_wordcloud_reference.py",
}
RENDERERS = {
    name: _load(EXP / "results" / path, "r_" + name.replace(" ", "_"))
    for name, path in RENDERER_PATHS.items()
}


# The active data source can be swapped at runtime from the web UI (POST /api/connect),
# mirroring VizER's live-DB login form. `.env` still provides the startup default; a form
# override rebinds the globals below so every downstream read sees the new source.
DS_STATUS: dict[str, Any] = {
    "mode": CONFIG.datasource, "database": "", "note": "startup default from .env"
}


def set_datasource(ds, *, mode: str, database: str = "", note: str = "") -> list[str]:
    """Make ``ds`` the active source (also validates it by reading its schema)."""
    global DS, SCHEMA, TABLES, DS_STATUS
    schema = ds.get_schema()
    DS, SCHEMA, TABLES = ds, schema, ds.tables_view()
    DS_STATUS = {"mode": mode, "database": database, "note": note}
    return sorted(SCHEMA.get("tables", {}))


def connect_postgres(params: dict[str, Any]) -> dict[str, Any]:
    """Build a live PostgreSQL source from web-form fields and make it active.

    Body: ``{host, port, user, password, database}`` (as in VizER's db-login). The
    password is used only to build the connection URL — never logged or echoed back.
    """
    from urllib.parse import quote

    host = (params.get("host") or "localhost").strip()
    port = str(params.get("port") or "5432").strip()
    user = (params.get("user") or "").strip()
    password = params.get("password") or ""
    database = (params.get("database") or "").strip()
    if not (user and database):
        return {"ok": False, "error": "user and database are required"}
    auth = quote(user) + ((":" + quote(password)) if password else "")
    url = "postgresql+psycopg2://" + auth + "@" + host + ":" + port + "/" + database
    try:
        from datasource.postgres_source import PostgresDataSource

        ds = PostgresDataSource(url, row_cap=CONFIG.row_cap)
        tables = set_datasource(
            ds, mode="postgres", database=database,
            note="connected to " + user + "@" + host + ":" + port + "/" + database,
        )
        return {"ok": True, "mode": "postgres", "database": database, "tables": tables}
    except Exception as exc:  # bad creds / driver missing / unreachable host
        return {"ok": False, "error": str(exc)}


def use_default_datasource() -> dict[str, Any]:
    """Revert to the .env-configured source (usually the bundled Mondial JSON)."""
    try:
        ds = make_datasource(CONFIG)
        tables = set_datasource(ds, mode=CONFIG.datasource, note="reverted to .env default")
        return {"ok": True, "mode": CONFIG.datasource, "tables": tables}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def joined_base_rows(table: str, joins: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """The base table's rows, enriched with any joined foreign columns (Phase 2).

    Runs before filtering so a joined column (e.g. `continent`) can be filtered and
    grouped like a native one. An empty/absent joins list is the identity.
    """
    rows = TABLES.get(table) or []
    if joins:
        rows = JOIN.enrich(SCHEMA, TABLES, table, rows, joins)
    return rows


def filtered_data(table: str, filters: list[dict[str, Any]] | None,
                  joins: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """A DATA-shaped view holding the chosen table's joined + filtered rows.

    The server selects rows from this view (``_select_rows`` -> ``data["tables"][table]``)
    and passes them to each renderer's ``render(mapping, rows)``, so passing this view
    (instead of the global DATA) draws the subset with no renderer change. Order is
    join -> filter; empty joins/filters are the identity.
    """
    rows = joined_base_rows(table, joins)
    return {"tables": {table: FILTER.apply(rows, filters or [])}}


def _select_rows(mapping: dict[str, Any], data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Pick the rows a renderer draws, owned by the server so it depends only on each
    renderer's one guaranteed public function `render(mapping, rows)` — never on a
    private helper whose name varies between LLM-authored renderers. `data` is already
    the grouped join/filter/aggregate view `{"tables": {table: rows}}`."""
    table = mapping.get("table")
    if data is None:
        # No prepared view supplied — read the raw table straight from the data source.
        return TABLES.get(table) or []
    if isinstance(data, dict) and isinstance(data.get("tables"), dict):
        return data["tables"].get(table, [])
    if isinstance(data, list):
        return data
    return []


# Mapping roles whose value is an entity *identifier* shown as a label — safe to swap a
# code for a readable name. `region` is included so the choropleth shows readable country
# names; the renderer itself now joins on the basemap's ISO numeric id via a crosswalk that
# resolves either the Mondial code or name (with a name fallback), so it no longer greys out
# on wording differences and works whichever the region role carries. Excludes measure/temporal.
LABEL_ROLES = ("key", "source", "target", "parent", "child", "region",
               "series", "group", "segment", "ring", "spoke", "node")


def _single_pk(table: str | None) -> str | None:
    pk = (SCHEMA.get("tables", {}).get(table) or {}).get("primary_key") or []
    return pk[0] if len(pk) == 1 else None


def _label_col(table: str | None) -> str | None:
    """The human-readable label column of an entity table, if distinct from its key.
    Convention: a `name` column, unless `name` is itself the key (already readable)."""
    tdef = SCHEMA.get("tables", {}).get(table) or {}
    names = [c.get("name") for c in tdef.get("columns", [])]
    if "name" not in names:
        return None
    if (tdef.get("primary_key") or []) == ["name"]:
        return None
    return "name"


def _fk_ref(tdef: dict[str, Any], col: str):
    for fk in tdef.get("foreign_keys", []) or []:
        fcols = fk.get("columns") or []
        if fcols and fcols[0] == col:
            ref = fk.get("references_table")
            ref_pk = (fk.get("references_columns") or [None])[0] or _single_pk(ref)
            return ref, ref_pk
    return None, None


def apply_display_labels(mapping: dict[str, Any], rows: list[dict[str, Any]]):
    """Display-only: swap entity codes for their readable `name` in the chart's label
    columns, keeping every internal key intact. A cross-table code (a foreign key, e.g.
    `encompasses.country`) is looked up in the referenced entity; a base entity's own key
    (e.g. `country.code`) takes the `name` from its own row. Never mutates the inputs, and
    a safe no-op for derived/aggregated tables (absent from the schema) or readable keys."""
    table = (mapping or {}).get("table")
    tdef = SCHEMA.get("tables", {}).get(table)
    if not tdef or not rows:
        return rows
    cols = {mapping[r] for r in LABEL_ROLES if isinstance(mapping.get(r), str)}
    relabel: dict[str, dict] = {}   # col -> {code: name} for a foreign-key column
    same_row: dict[str, str] = {}   # col -> label column in the same row
    for col in cols:
        ref, ref_pk = _fk_ref(tdef, col)
        if ref and ref_pk and _label_col(ref):
            lab = _label_col(ref)
            m = {r.get(ref_pk): r.get(lab) for r in (TABLES.get(ref) or [])
                 if isinstance(r, dict) and r.get(ref_pk) is not None}
            if m:
                relabel[col] = m
        elif col == _single_pk(table) and _label_col(table):
            same_row[col] = _label_col(table)
    if not relabel and not same_row:
        return rows
    out = []
    for r in rows:
        if not isinstance(r, dict):
            out.append(r)
            continue
        nr = dict(r)
        for col, m in relabel.items():
            if nr.get(col) in m and m[nr[col]] is not None:
                nr[col] = m[nr[col]]
        for col, lab in same_row.items():
            if nr.get(lab) is not None:
                nr[col] = nr[lab]
        out.append(nr)
    return out


def render_chart(chart: str | None, mapping: dict[str, Any],
                 data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Render a chart from its Step-2 mapping, or report it's not built yet."""
    key = (chart or "").strip().lower()
    mod = RENDERERS.get(key)
    if mod is None or not mapping:
        return {"chart": chart, "available": False, "html": WORKING}
    try:
        rows = _select_rows(mapping, data)
        if not rows:
            return {"chart": chart, "available": False, "html": "no rows match the current filter"}
        rows = apply_display_labels(mapping, rows)  # show readable names, keep internal keys
        html = _inline_d3(mod.render(mapping, rows))
        return {"chart": chart, "available": True, "html": html}
    except Exception as exc:  # keep the UI alive on a bad mapping
        return {"chart": chart, "available": False, "html": "render error: " + str(exc)}


def _is_aggregate(spec: dict[str, Any] | None) -> bool:
    spec = spec or {}
    return bool(spec.get("group_by") or spec.get("measures") or spec.get("resample"))


def prepared_data(table: str, filters: list[dict[str, Any]] | None,
                  aggregate: dict[str, Any] | None,
                  joins: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The DATA-shaped view a renderer/selector consumes after join + filter (+ aggregate).

    Without aggregation this is the joined+filtered base table; with aggregation it is
    the derived aggregated table (keyed by the derived table name the mapping references).
    """
    fdata = filtered_data(table, filters, joins)
    rows = fdata["tables"][table]
    if rows and _is_aggregate(aggregate):
        _dsch, dtable, _dcols, arows = AGG.prepare(SCHEMA, table, rows, aggregate)
        return {"tables": {dtable: arows}}
    return fdata


def nl_select(text: str) -> dict[str, Any]:
    """Resolve a natural-language request to a structured selection via Bailian.

    Returns ``{"ok", "selection", "error"}``; the front end shows the selection for
    confirmation and then submits it to ``/api/run``. Degrades gracefully if the LLM is
    not configured (no ``DASHSCOPE_API_KEY``) or the openai SDK is missing.
    """
    if not text:
        return {"ok": False, "selection": None, "error": "empty request"}
    if not CONFIG.has_llm:
        return {"ok": False, "selection": None,
                "error": "natural-language input needs DASHSCOPE_API_KEY in .env"}
    try:
        from nlquery.nl_to_selection import parse
        return parse(text, SCHEMA)
    except Exception as exc:  # keep the UI alive if the LLM/lib is unavailable
        return {"ok": False, "selection": None, "error": str(exc)}


# --- Opt-in LLM chart selection (Step 2) -----------------------------------
# When VIZER_LLM_STEP2 is on and a key is configured, an LLM ranks the deterministic
# Step-2 candidates and picks one to highlight (with a short English rationale, and
# optional same-dimension mapping swaps). Off/no-key -> deterministic pick, unchanged.
_LLM_CLIENT: Any = None
_LLM_CLIENT_INIT = False


def _get_llm_client() -> Any:
    """Lazily build (and cache) one Bailian client for Step-2 selection, or None."""
    global _LLM_CLIENT, _LLM_CLIENT_INIT
    if _LLM_CLIENT_INIT:
        return _LLM_CLIENT
    _LLM_CLIENT_INIT = True
    if not (CONFIG.llm_step2 and CONFIG.has_llm):
        return None
    try:
        from nlquery.bailian_client import BailianClient
        _LLM_CLIENT = BailianClient(
            api_key=CONFIG.dashscope_api_key,
            base_url=CONFIG.dashscope_base_url,
            model=CONFIG.step2_model,
        )
    except Exception:  # keep the pipeline alive if the SDK/key is unavailable
        _LLM_CLIENT = None
    return _LLM_CLIENT


def _step2_block(schema: dict[str, Any], table: str, columns: list[str],
                 pattern: str, s2: dict[str, Any],
                 rows: list[dict[str, Any]] | None = None,
                 intent: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the ``step2`` response block and the chart to render.

    All valid candidates are always returned; when LLM selection is on, the LLM's pick is
    highlighted via ``step2.llm`` and becomes ``selected`` (so Step 3 renders it). ``rows`` and
    ``intent`` make the pick data- and goal-aware. Returns ``(block, selected)``.
    """
    selected = s2.get("selected") or {}
    block = {
        "recommended_charts": s2.get("recommended_charts", []),
        "candidates": s2.get("candidates", []),
        "selected": selected,
    }
    client = _get_llm_client()
    if client is not None:
        from chartselect import select as llm_select
        pick = llm_select(schema, table, columns, pattern, s2, client=client,
                          rows=rows, intent=intent)
        if pick.get("source") == "llm" and pick.get("recommended_chart"):
            selected = {"chart": pick["recommended_chart"], "mapping": pick.get("mapping") or {}}
            block["selected"] = selected
        block["llm"] = {
            "recommended_chart": pick.get("recommended_chart"),
            "reason": pick.get("reason", ""),
            "source": pick.get("source"),
            "ranking": pick.get("ranking", []),
        }
    return block, selected


def _empty_run(table, columns, filters, aggregate, joins, pattern, reason, msg):
    return {
        "selected_table": table,
        "selected_columns": columns,
        "filters": filters or [],
        "aggregate": aggregate or {},
        "joins": joins or [],
        "step1": {"pattern": pattern, "reason": reason},
        "step2": {"recommended_charts": [], "candidates": [], "selected": {}},
        "step3": {"chart": None, "available": False, "html": msg},
    }


def run_pipeline(table: str, columns: list[str],
                 filters: list[dict[str, Any]] | None = None,
                 aggregate: dict[str, Any] | None = None,
                 joins: list[dict[str, Any]] | None = None,
                 intent: str = "") -> dict[str, Any]:
    # Order: join (enrich) -> filter -> (aggregate) -> Step 1/2/3. Join + filter run
    # before Step 2 so the selector measures on the subset the user sees.
    fdata = filtered_data(table, filters, joins)
    rows = fdata["tables"][table]

    if _is_aggregate(aggregate):
        base_pattern = STEP1.classify_selection(SCHEMA, table, columns).get("predicted_pattern", "")
        if not rows:
            return _empty_run(table, columns, filters, aggregate, joins, base_pattern, "",
                              "no rows match the current filter")
        # Aggregate -> derived basic_entity; re-run the SAME Step 1/2/3 on the derived table.
        dschema, dtable, dcols, arows = AGG.prepare(SCHEMA, table, rows, aggregate)
        if not arows:
            return _empty_run(table, columns, filters, aggregate, joins, base_pattern, "",
                              "aggregation produced no groups (or none matched the having condition)")
        s1 = STEP1.classify_selection(dschema, dtable, dcols)
        pattern = s1["predicted_pattern"]
        s2 = STEP2.recommend(dschema, dtable, dcols, pattern, rows=arows)
        step2, selected = _step2_block(dschema, dtable, dcols, pattern, s2, rows=arows, intent=intent)
        ddata = {"tables": {dtable: arows}}
        rendered = render_chart(selected.get("chart"), selected.get("mapping") or {}, data=ddata)
        return {
            "selected_table": table,
            "selected_columns": dcols,
            "filters": filters or [],
            "aggregate": aggregate or {},
            "joins": joins or [],
            "step1": {"pattern": pattern, "reason": s1.get("reason", ""),
                      "derived_table": dtable},
            "step2": step2,
            "step3": rendered,
        }

    # Non-aggregate path (Phase-1 filtering only).
    s1 = STEP1.classify_selection(SCHEMA, table, columns)
    pattern = s1["predicted_pattern"]
    if not rows:
        return _empty_run(table, columns, filters, aggregate, joins, pattern,
                          s1.get("reason", ""), "no rows match the current filter")
    s2 = STEP2.recommend(SCHEMA, table, columns, pattern, rows=rows)
    step2, selected = _step2_block(SCHEMA, table, columns, pattern, s2, rows=rows, intent=intent)
    rendered = render_chart(selected.get("chart"), selected.get("mapping") or {}, data=fdata)
    return {
        "selected_table": table,
        "selected_columns": columns,
        "filters": filters or [],
        "aggregate": aggregate or {},
        "joins": joins or [],
        "step1": {"pattern": pattern, "reason": s1.get("reason", "")},
        "step2": step2,
        "step3": rendered,
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: Any, ctype: str = "application/json") -> None:
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/schema":
            tables = {t: [c["name"] for c in SCHEMA["tables"][t]["columns"]] for t in sorted(SCHEMA["tables"])}
            self._send(200, {"tables": tables})
        elif self.path == "/api/datasource":
            self._send(200, {"status": DS_STATUS, "tables": sorted(SCHEMA.get("tables", {}))})
        elif self.path.startswith("/api/column_stats"):
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            table = (q.get("table", [""])[0]).strip()
            self._send(200, self._column_stats(table))
        elif self.path.startswith("/api/join_options"):
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            table = (q.get("table", [""])[0]).strip()
            self._send(200, self._join_options(table))
        else:
            self._send(404, {"error": "not found"})

    def _column_stats(self, table: str, columns: list[str] | None = None,
                      joins: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if table not in SCHEMA.get("tables", {}):
            return {"error": "unknown table", "stats": {}}
        # Stats come from the *unfiltered* (but joined) rows so control ranges/values
        # stay stable and a joined column gets a control.
        rows = joined_base_rows(table, joins)
        return {"table": table, "stats": FILTER.column_stats(rows, columns)}

    def _join_options(self, table: str) -> dict[str, Any]:
        if table not in SCHEMA.get("tables", {}):
            return {"error": "unknown table", "options": []}
        opts = [{"bring": r["table"] + "." + r["column"], "table": r["table"],
                 "column": r["column"], "multiplies": r["multiplies"], "hops": len(r["path"])}
                for r in JOIN.reachable_columns(SCHEMA, table)]
        opts.sort(key=lambda o: (o["hops"], o["table"], o["column"]))
        return {"table": table, "options": opts}

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = self._read_json()
            if self.path == "/api/run":
                table = (body.get("table") or "").strip()
                columns = body.get("columns") or []
                filters = body.get("filters") or []
                aggregate = body.get("aggregate") or {}
                joins = body.get("joins") or []
                intent = (body.get("intent") or "").strip()
                if not table or not columns:
                    self._send(400, {"error": "pick a table and at least one column"})
                    return
                self._send(200, run_pipeline(table, columns, filters, aggregate, joins, intent))
            elif self.path == "/api/connect":
                # Live-DB login from the web form: connect + swap the active data source.
                self._send(200, connect_postgres(body))
            elif self.path == "/api/disconnect":
                self._send(200, use_default_datasource())
            elif self.path == "/api/nl":
                # Natural-language -> structured selection (Bailian). Returns the resolved
                # {table, columns, filters, joins, aggregate} for the UI to confirm, then
                # the user runs it via /api/run. Never chooses a pattern or chart.
                self._send(200, nl_select((body.get("text") or "").strip()))
            elif self.path == "/api/render":
                table = (body.get("table") or (body.get("mapping") or {}).get("table") or "").strip()
                filters = body.get("filters") or []
                aggregate = body.get("aggregate") or {}
                joins = body.get("joins") or []
                data = prepared_data(table, filters, aggregate, joins) if table else None
                self._send(200, render_chart(body.get("chart"), body.get("mapping") or {}, data=data))
            elif self.path == "/api/column_stats":
                self._send(200, self._column_stats((body.get("table") or "").strip(),
                                                    body.get("columns"), body.get("joins")))
            elif self.path == "/api/join_options":
                self._send(200, self._join_options((body.get("table") or "").strip()))
            else:
                self._send(404, {"error": "not found"})
        except Exception as exc:
            self._send(500, {"error": str(exc)})

    def log_message(self, *args: Any) -> None:  # quiet
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    print(f"Pipeline front-end on http://{args.host}:{args.port}  (renderers: {', '.join(sorted(RENDERERS))})")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
