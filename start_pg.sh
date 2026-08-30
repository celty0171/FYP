#!/usr/bin/env bash
# Start a local PostgreSQL co-located with the web server (so `localhost` reaches it) and load
# Mondial — idempotent: safe to run repeatedly. Uses the conda-provided postgres binaries.
#
#   ./start_pg.sh            # init (first run) + start + create db + load Mondial
#   ./start_pg.sh stop       # stop the server
#   ./start_pg.sh status     # is it accepting connections?
#
# Override defaults via env vars:  PGPORT=5433 DBNAME=mydb PGDATA=$HOME/pgdata ./start_pg.sh
set -euo pipefail

PGPORT="${PGPORT:-5432}"
PGDATA="${PGDATA:-$HOME/pgdata}"
DBNAME="${DBNAME:-mondial}"
# DB superuser. A fresh dir our initdb creates is owned by $USER; an existing data dir may use a
# different superuser (often "postgres") — set PGUSER to match, e.g. PGUSER=postgres ./start_pg.sh
PGUSER="${PGUSER:-$USER}"
LOG="$PGDATA/server.log"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
URL="postgresql+psycopg2://$PGUSER@localhost:$PGPORT/$DBNAME"
# On Kerberos-enabled HPC nodes libpq tries GSSAPI first and prints a noisy failure; disable it
# (we authenticate over plain local TCP). Applies to psql/createdb/pg_isready and psycopg2.
export PGGSSENCMODE=disable

case "${1:-start}" in
  stop)
    pg_ctl -D "$PGDATA" stop; exit 0 ;;
  status)
    pg_isready -h localhost -p "$PGPORT"; exit $? ;;
esac

# 1) Initialise the data directory on first run (makes $USER the superuser).
if [ ! -f "$PGDATA/PG_VERSION" ]; then
  echo "• initdb -> $PGDATA"
  initdb -D "$PGDATA" >/dev/null
fi

# 2) Start the server if it isn't already accepting connections.
# Put the Unix socket in a PRIVATE dir (not the shared /tmp): on a multi-user HPC node another
# user's postgres owns /tmp/.s.PGSQL.<port>.lock, so we'd hit "Permission denied". All clients
# here connect over TCP (-h localhost), so relocating the socket changes nothing for them.
if ! pg_isready -h localhost -p "$PGPORT" -q; then
  echo "• starting postgres on port $PGPORT (log: $LOG)"
  pg_ctl -D "$PGDATA" -o "-p $PGPORT -k $PGDATA" -l "$LOG" start
  for _ in $(seq 1 30); do pg_isready -h localhost -p "$PGPORT" -q && break; sleep 1; done
fi
pg_isready -h localhost -p "$PGPORT"

# 3) Create the database if it doesn't exist.
if ! psql -h localhost -p "$PGPORT" -U "$PGUSER" -d postgres -tAc \
      "SELECT 1 FROM pg_database WHERE datname='$DBNAME'" | grep -q 1; then
  echo "• createdb $DBNAME"
  createdb -h localhost -p "$PGPORT" -U "$PGUSER" "$DBNAME"
fi

# 4) Load Mondial only if the database has no tables yet.
n=$(psql -h localhost -p "$PGPORT" -U "$PGUSER" -d "$DBNAME" -tAc \
     "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
if [ "${n:-0}" = "0" ]; then
  echo "• loading Mondial into $DBNAME"
  python "$REPO/experiments/scripts/load_mondial_postgres.py" --url "$URL"
fi

cat <<EOF

✅ PostgreSQL ready — connect the web app with:
     host=localhost  port=$PGPORT  database=$DBNAME  user=$PGUSER  (no password)
     URL: $URL
   Stop it later with:  ./start_pg.sh stop
EOF
