"""Interactive web front-end for the three-stage ER-pattern -> visualisation pipeline.

Standard-library only (http.server + urllib), matching the rest of the repo. It reuses the
pipeline functions from run_pipeline.py so the web path and the CLI path stay identical.

Stages, each backed by a self-hosted Qwen model reached over an SSH tunnel:

    Stage 1+2  pattern identification + chart mapping   -> Qwen3-14B  (thinking ON)  :8001
    Stage 3    runnable Google Charts visualisation     -> Coder-32B  (no thinking)  :8004

Run from the repo root:

    python experiments/web/server.py            # serves http://localhost:8000
    python experiments/web/server.py --port 8080

Endpoints:
    GET  /                  the single-page UI (web/index.html)
    GET  /api/schema        tables + columns from the clean schema (for the picker)
    GET  /api/presets       the nine blind cases, as quick presets
    POST /api/pattern       {table, columns}          -> Stage 1+2 result JSON
    POST /api/visualise     {table, columns, mapping, library?} -> {html, seconds}
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "experiments" / "scripts"))

import run_pipeline as rp  # noqa: E402  (after sys.path tweak)

# --------------------------------------------------------------------------- #
# Fixed configuration — the best-performing setup established by the experiments
# --------------------------------------------------------------------------- #
SCHEMA_PATH = REPO_ROOT / "experiments" / "mondial_database" / "mondial_schema_summary_clean.json"
DATA_PATH = REPO_ROOT / "experiments" / "mondial_database" / "mondial_data.json"
CASES_PATH = REPO_ROOT / "experiments" / "inputs" / "mondial_blind_cases.json"
PATTERN_PROMPT = REPO_ROOT / "experiments" / "prompts" / "prompt_v8.md"
IMPL_PROMPT = REPO_ROOT / "experiments" / "prompts" / "visualisation_implementation_prompt.md"

PATTERN_CFG = dict(
    model="Qwen3-14B",
    base_url="http://localhost:8001/v1",
    enable_thinking=True,
    pattern_max_tokens=12288,
)
IMPL_CFG = dict(
    model="Qwen2.5-Coder-32B-Instruct",
    base_url="http://localhost:8004/v1",
    enable_thinking=False,
    impl_max_tokens=12288,
)
COMMON = dict(temperature=0.0, timeout=600.0, max_rows=500, data_filter="")

# Loaded once at startup.
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
DATA = json.loads(DATA_PATH.read_text(encoding="utf-8"))
PATTERN_TEMPLATE = PATTERN_PROMPT.read_text(encoding="utf-8")
IMPL_TEMPLATE = IMPL_PROMPT.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Stage runners (thin wrappers over run_pipeline)
# --------------------------------------------------------------------------- #
def run_stage12(table: str, columns: list[str]) -> dict:
    case = {"case_id": "web", "selected_table": table, "selected_columns": columns}
    args = SimpleNamespace(**PATTERN_CFG, **COMMON)
    _, result = rp.run_pattern_stage(case, SCHEMA, PATTERN_TEMPLATE, args=args)
    return result


def run_stage3(table: str, columns: list[str], mapping: dict, library: str) -> str:
    case = {"case_id": "web", "selected_table": table, "selected_columns": columns}
    args = SimpleNamespace(library=library, **IMPL_CFG, **COMMON)
    return rp.run_impl_stage(case, mapping, DATA, IMPL_TEMPLATE, args=args)


def schema_listing() -> list[dict]:
    out = []
    for name, spec in sorted(SCHEMA["tables"].items()):
        out.append({"table": name, "columns": [c["name"] for c in spec["columns"]]})
    return out


def presets() -> list[dict]:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    items = cases if isinstance(cases, list) else cases.get("cases", [])
    out = []
    for c in items:
        sel = c.get("selection", c)
        out.append(
            {
                "case_id": str(c.get("case_id", c.get("id", "?"))),
                "table": sel.get("selected_table"),
                "columns": sel.get("selected_columns", []),
            }
        )
    return out


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "VizERPipeline/1.0"

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict, code: int = 200) -> None:
        self._send(code, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._send(200, (WEB_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/schema":
            self._send_json({"tables": schema_listing()})
        elif self.path == "/api/presets":
            self._send_json({"presets": presets()})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = self._read_json()
            if self.path == "/api/pattern":
                table, columns = body["table"], body["columns"]
                started = time.monotonic()
                result = run_stage12(table, columns)
                self._send_json({"result": result, "seconds": round(time.monotonic() - started, 1)})
            elif self.path == "/api/visualise":
                table, columns = body["table"], body["columns"]
                mapping = body.get("mapping", {})
                library = body.get("library", "google_charts")
                started = time.monotonic()
                html = run_stage3(table, columns, mapping, library)
                self._send_json({"html": html, "seconds": round(time.monotonic() - started, 1)})
            else:
                self._send_json({"error": "not found"}, 404)
        except Exception as exc:  # surface any pipeline/model error to the UI
            self._send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def log_message(self, fmt: str, *args) -> None:  # quieter console
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"VizER pipeline UI on http://{args.host}:{args.port}")
    print(f"  Stage 1+2 -> {PATTERN_CFG['model']} @ {PATTERN_CFG['base_url']} (thinking on)")
    print(f"  Stage 3   -> {IMPL_CFG['model']} @ {IMPL_CFG['base_url']} (google_charts)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
