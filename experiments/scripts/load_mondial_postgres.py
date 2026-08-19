"""Load the bundled Mondial dump into a PostgreSQL database.

Runs ``mondial_schema.sql`` then ``mondial_data.sql`` (both standard SQL, in valid
dependency order) against the database configured in the repo-root ``.env``
(``DATABASE_URL`` or the ``PG_*`` parts, via ``config.load_config``), or against a
``--url`` given on the command line. This is the one-command way to stand up the live
database the web app now reads by default (``VIZER_DATASOURCE=postgres``).

Prerequisites: an existing, empty target database (e.g. ``createdb mondial``) and the
production dependencies (``pip install -r requirements.txt``). Example:

    python experiments/scripts/load_mondial_postgres.py \
        --url postgresql+psycopg2://postgres@localhost:5432/mondial

Reuses the same SQLAlchemy engine + URL convention as ``datasource/postgres_source.py``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]           # experiments/
DB_DIR = EXP / "mondial_database"


def _resolve_url(cli_url: str | None) -> str:
    if cli_url:
        return cli_url
    # Reuse the production config so the URL matches what the web app connects to.
    sys.path.insert(0, str(EXP))
    from config import load_config

    url = load_config().database_url
    if not url:
        raise SystemExit(
            "No database URL: pass --url, or set DATABASE_URL / PG_* in .env "
            "(see .env.example)."
        )
    return url


def _run_sql_file(conn, path: Path) -> None:
    sql = path.read_text("utf-8")
    # psycopg2 executes multiple ';'-separated statements (and -- comments) in one call;
    # the whole file runs inside the caller's transaction.
    conn.exec_driver_sql(sql)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=None,
                        help="SQLAlchemy URL (default: DATABASE_URL / PG_* from .env)")
    parser.add_argument("--schema", type=Path, default=DB_DIR / "mondial_schema.sql")
    parser.add_argument("--data", type=Path, default=DB_DIR / "mondial_data.sql")
    args = parser.parse_args()

    try:
        from sqlalchemy import create_engine
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "This helper needs SQLAlchemy + psycopg2 "
            "(pip install -r requirements.txt)"
        ) from exc

    url = _resolve_url(args.url)
    engine = create_engine(url)
    with engine.begin() as conn:            # one transaction: schema then data
        print("Loading schema:", args.schema)
        _run_sql_file(conn, args.schema)
        print("Loading data:  ", args.data)
        _run_sql_file(conn, args.data)
    print("Done. Mondial loaded into", engine.url.render_as_string(hide_password=True))


if __name__ == "__main__":
    main()
