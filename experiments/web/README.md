# VizER Pipeline — interactive web front-end

A single-page UI that runs the full three-stage pipeline interactively:

1. **Selection** — pick a Mondial table and columns (or load one of the nine blind-case presets).
2. **Step 1 + 2** — ER pattern identification + chart mapping (`Qwen3-14B`, thinking on, `prompt_v8`).
3. **Step 3** — runnable Google Charts visualisation (`Qwen2.5-Coder-32B-Instruct`, no thinking).

Standard-library only (`http.server` + `urllib`). It imports `experiments/scripts/run_pipeline.py`,
so the web path and the CLI path behave identically.

## Files

- `server.py` — backend (static UI + JSON API).
- `index.html` — the UI (served at `/`).

## Prerequisites

Both self-hosted Qwen models must be reachable over SSH tunnels on `localhost`:

| Stage | Model | Port | Used for |
| --- | --- | --- | --- |
| 1 + 2 | `Qwen3-14B` | **8001** | pattern + mapping |
| 3 | `Qwen2.5-Coder-32B-Instruct` | **8004** | Google Charts HTML |

Open the tunnels first (see `最最新_HPC_Qwen_速查表.md` for the cluster details), e.g.:

```bash
ssh -N -L 8001:localhost:8001 -L 8004:localhost:8004 <user>@login-b.<cluster>
```

Confirm they are up:

```bash
curl -s http://localhost:8001/v1/models
curl -s http://localhost:8004/v1/models
```

Each should list its served model id.

## Start the server

From the **repository root** (`/rds/general/user/jm1125/home/FYP`):

```bash
python experiments/web/server.py            # serves http://127.0.0.1:8000
python experiments/web/server.py --port 8080
python experiments/web/server.py --host 0.0.0.0 --port 8080   # bind all interfaces
```

The console prints the bound address and which model backs each stage.

### Viewing it in a local browser

If the server runs on the HPC and you browse from your laptop, forward the UI port too. Either
add it to the same SSH command (`-L 8000:localhost:8000`), or run the UI on the login node and
tunnel that one port. Then open `http://localhost:8000`.

## Using the UI

1. (Optional) choose a **preset** to auto-fill a known blind case.
2. Pick a **table**, tick the **columns** you want to "select".
3. Click **Run Step 1 + 2**. Thinking mode takes roughly **70–150 s**; the panel shows a spinner
   and then the pattern, recommended chart(s), the chart mapping, and the full JSON.
4. Click **Run Step 3** (enabled once a mapping exists). Generation takes roughly **4–5 min**;
   the result renders inline in a sandboxed `iframe`, with a **download HTML** link.

## Configuration

The model/prompt/port choices are constants near the top of `server.py`
(`PATTERN_CFG`, `IMPL_CFG`, `COMMON`, and the `*_PROMPT` / `*_PATH` values). Edit them there to
point at different ports, swap prompts, change `temperature`, `max_rows`, or token caps.

## Notes & limits

- **Timing.** Requests are long-running by design; the backend per-request timeout is 600 s and
  the server is threaded (`ThreadingHTTPServer`), so the page stays responsive while a stage runs.
- **Context window.** Both servers run with `max_model_len = 16384`. Step 3 uses Google Charts
  precisely because its compact Sankey rows fit full data in that budget; d3 + thinking does not
  (see `../results/viz_case8/COMPARISON.md`).
- **One stage can fail independently.** If a model errors (e.g. tunnel down), the corresponding
  panel shows the error message; reopen the tunnel and re-run that step.
- **No persistence.** Results are not written to disk from the UI; use the per-result
  *download HTML* link, or the CLI (`run_pipeline.py` / `run_viz_stage3.py`) to save run dirs.
