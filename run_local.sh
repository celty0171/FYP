#!/usr/bin/env bash
# One command for local/HPC testing: bring up the co-located PostgreSQL (via start_pg.sh) and
# launch the web server pointed at it — server and database on the same machine, so `localhost`
# reaches the DB and an `ssh -L 8090:localhost:8090` tunnel reaches the web UI.
#
#   ./run_local.sh                          # DB on 5432, web UI on 127.0.0.1:8090
#   PORT=9000 ./run_local.sh                # custom web port
#   PGPORT=5433 DBNAME=mydb ./run_local.sh  # override DB (kept in sync with start_pg.sh)
#   HOST=0.0.0.0 ./run_local.sh             # bind all interfaces (e.g. inside a container)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PGPORT="${PGPORT:-5432}"
DBNAME="${DBNAME:-mondial}"
PGUSER="${PGUSER:-$USER}"      # set PGUSER=postgres if your existing cluster's superuser is postgres
PORT="${PORT:-8090}"
HOST="${HOST:-127.0.0.1}"

# 1) Ensure the database is up and Mondial is loaded (idempotent — see start_pg.sh).
PGPORT="$PGPORT" DBNAME="$DBNAME" PGUSER="$PGUSER" "$REPO/start_pg.sh"

# 2) Launch the web server against that live database. PGGSSENCMODE=disable silences the HPC
# Kerberos/GSSAPI probe for psycopg2 too.
echo
echo "• starting web server on http://$HOST:$PORT  (SCHEMAVISLM_DATASOURCE=postgres, db=$DBNAME)"
echo "  from your laptop:  ssh -L $PORT:localhost:$PORT <you@hpc>   then open http://localhost:$PORT"
exec env \
  SCHEMAVISLM_DATASOURCE=postgres PGGSSENCMODE=disable \
  PG_HOST=localhost PG_PORT="$PGPORT" PG_USER="$PGUSER" PG_DATABASE="$DBNAME" \
  python "$REPO/schemavislm/web_pipeline/server.py" --host "$HOST" --port "$PORT"
