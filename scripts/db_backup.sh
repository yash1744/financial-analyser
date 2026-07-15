#!/bin/sh
# One Postgres backup in pg_dump custom format (compressed, pg_restore-able),
# then prune old dumps. Runs anywhere pg_dump is available; the compose
# db-backup service calls it on a schedule.
#
# Env (defaults match docker-compose.yml):
#   PGHOST=db PGUSER=finance PGDATABASE=finance PGPASSWORD=finance
#   BACKUP_DIR=/backups   BACKUP_KEEP_DAYS=14
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
: "${PGHOST:=db}" "${PGUSER:=finance}" "${PGDATABASE:=finance}"
export PGHOST PGUSER PGDATABASE

STAMP="$(date -u +%Y%m%d-%H%M%S)"
TARGET="$BACKUP_DIR/$PGDATABASE-$STAMP.dump"

mkdir -p "$BACKUP_DIR"
pg_dump --format=custom --file="$TARGET"
echo "backup written: $TARGET ($(du -h "$TARGET" | cut -f1))"

# retention: delete dumps older than BACKUP_KEEP_DAYS
find "$BACKUP_DIR" -name "$PGDATABASE-*.dump" -mtime "+$BACKUP_KEEP_DAYS" -delete
