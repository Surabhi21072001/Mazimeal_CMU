#!/usr/bin/env bash
# Build a DISPOSABLE local PostgreSQL database from repository files only.
#
#   tests/load_local_db.sh mazi_derived_audit            # unix socket in /tmp
#   PGHOST=127.0.0.1 PGPORT=54329 tests/load_local_db.sh mazi_audit
#
# Safety: refuses any host that is not this machine, refuses to touch a database that
# already exists, and never reads credentials from the environment beyond libpq defaults.
# Nothing here contacts Supabase or any shared environment.
set -euo pipefail

DB="${1:?usage: load_local_db.sh <new_database_name>}"
HOST="${PGHOST:-/tmp}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "$HOST" in
  /*|localhost|127.0.0.1|::1) ;;
  *) echo "refusing non-local host: $HOST" >&2; exit 2 ;;
esac
case "$HOST" in
  *supabase*|*amazonaws*|*neon.tech*|*render.com*|*pooler*)
    echo "refusing hosted database host: $HOST" >&2; exit 2 ;;
esac

export PGOPTIONS='-c client_min_messages=warning'
if psql -h "$HOST" -d postgres -Atc "select 1 from pg_database where datname='$DB'" | grep -q 1; then
  echo "database $DB already exists; refusing to modify it" >&2; exit 3
fi
createdb -h "$HOST" "$DB"

run() { psql -q -h "$HOST" -d "$DB" -v ON_ERROR_STOP=1 -f "$1" >/dev/null; }

cd "$REPO"
for f in schema/[0-9][0-9]_*.sql; do run "$f"; done
for f in foodcom_400 usda_nutrition ingredient_grams ingredient_sources \
         business_rules rule_codes ingredient_rule_tags; do
  run "schema/seed/$f.sql"
done
# Migrations in numeric order. 004 (app_admins: needs the Supabase `anon` role) and 005
# (one_account: needs auth.users) exist only on Supabase; creating cluster-level roles or an
# auth schema locally would leak outside the disposable database, so they are skipped.
SKIP_MIGRATIONS="${SKIP_MIGRATIONS:-004 005}"
for f in schema/migrations/[0-9][0-9][0-9]_*.sql; do
  n="$(basename "$f" | cut -c1-3)"
  case " $SKIP_MIGRATIONS " in *" $n "*) echo "skip $f (Supabase-only)"; continue ;; esac
  run "$f"
done
echo "loaded $DB on $HOST"
