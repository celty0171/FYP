"""Runtime configuration for the production layer, read from a repo-root ``.env`` (with
``os.environ`` taking precedence). Std-lib only — no python-dotenv dependency.

The default data source is a live PostgreSQL database (``SCHEMAVISLM_DATASOURCE=postgres``): set
``DATABASE_URL`` or the ``PG_*`` parts in ``.env`` (see README for loading Mondial). Set
``SCHEMAVISLM_DATASOURCE=json`` to fall back to the bundled offline Mondial JSON files, which the
experiment scripts also read directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]      # FYP/
EXP = Path(__file__).resolve().parent                # schemavislm/


def _load_env_file(path: Path) -> dict[str, str]:
    """Parse a simple KEY=VALUE .env file (ignores blanks / # comments / quotes)."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip().strip('"').strip("'")
        out[key.strip()] = val
    return out


def _get(env: dict[str, str], key: str, default: str = "") -> str:
    # os.environ overrides the .env file, which overrides the default.
    return os.environ.get(key) or env.get(key) or default


@dataclass
class Config:
    datasource: str            # "json" | "postgres"
    schema_path: Path
    data_path: Path
    database_url: str
    row_cap: int
    pushdown: bool             # push join/filter/aggregate into SQL (Postgres only)
    statement_timeout_ms: int  # per-query ceiling for pushed-down SQL (0 = none)
    dashscope_api_key: str
    dashscope_base_url: str
    nl_model: str
    llm_step2: bool
    step2_model: str
    llm_geo: bool
    geo_model: str

    @property
    def has_llm(self) -> bool:
        return bool(self.dashscope_api_key)


def load_config(env_path: Path | None = None) -> Config:
    env = _load_env_file(env_path or (REPO_ROOT / ".env"))
    db = EXP / "mondial_database"

    database_url = _get(env, "DATABASE_URL")
    if not database_url and _get(env, "PG_HOST"):
        # Assemble a psycopg2 URL from discrete PG_* parts.
        user = _get(env, "PG_USER", "postgres")
        pw = _get(env, "PG_PASSWORD")
        host = _get(env, "PG_HOST", "localhost")
        port = _get(env, "PG_PORT", "5432")
        name = _get(env, "PG_DATABASE", "")
        auth = user + (":" + pw if pw else "")
        database_url = "postgresql+psycopg2://" + auth + "@" + host + ":" + port + "/" + name

    try:
        row_cap = int(_get(env, "SCHEMAVISLM_ROW_CAP", "5000"))
    except ValueError:
        row_cap = 5000
    try:
        statement_timeout_ms = int(_get(env, "SCHEMAVISLM_STATEMENT_TIMEOUT_MS", "15000"))
    except ValueError:
        statement_timeout_ms = 15000

    return Config(
        datasource=_get(env, "SCHEMAVISLM_DATASOURCE", "postgres").lower(),
        schema_path=Path(_get(env, "SCHEMAVISLM_SCHEMA_PATH", str(db / "mondial_schema_summary_clean.json"))),
        data_path=Path(_get(env, "SCHEMAVISLM_DATA_PATH", str(db / "mondial_data.json"))),
        database_url=database_url,
        row_cap=row_cap,
        pushdown=_get(env, "SCHEMAVISLM_PUSHDOWN", "on").lower() in ("1", "on", "true", "yes"),
        statement_timeout_ms=statement_timeout_ms,
        dashscope_api_key=_get(env, "DASHSCOPE_API_KEY"),
        dashscope_base_url=_get(
            env, "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
        nl_model=_get(env, "NL_MODEL", "qwen-plus"),
        llm_step2=_get(env, "SCHEMAVISLM_LLM_STEP2", "on").lower() in ("1", "on", "true", "yes"),
        step2_model=_get(env, "SCHEMAVISLM_STEP2_MODEL", "") or _get(env, "NL_MODEL", "qwen-plus"),
        llm_geo=_get(env, "SCHEMAVISLM_LLM_GEO", "on").lower() in ("1", "on", "true", "yes"),
        geo_model=_get(env, "SCHEMAVISLM_GEO_MODEL", "") or _get(env, "NL_MODEL", "qwen-plus"),
    )
