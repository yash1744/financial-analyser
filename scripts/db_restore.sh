#!/bin/sh
# Restore a pg_dump custom-format backup.
#
#   db_restore.sh /backups/finance-20260714-020000.dump [target_db]
#
# Restoring into the LIVE database drops and recreates its objects
# (--clean). To verify a backup without touching live data, pass a scratch
# database name as the second argument; it will be created if missing.
set -eu

DUMP="${1:?usage: db_restore.sh <dump-file> [target_db]}"
: "${PGHOST:=db}" "${PGUSER:=finance}"
export PGHOST PGUSER
TARGET_DB="${2:-${PGDATABASE:-finance}}"

if ! psql -d postgres -tAc "select 1 from pg_database where datname = '$TARGET_DB'" | grep -q 1; then
  echo "creating database $TARGET_DB"
  createdb "$TARGET_DB"
fi

pg_restore --clean --if-exists --no-owner --dbname="$TARGET_DB" "$DUMP"
echo "restored $DUMP into $TARGET_DB"
