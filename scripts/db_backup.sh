#!/bin/sh
# One Postgres backup in pg_dump custom format (compressed, pg_restore-able),
# then prune old local dumps, then ship to R2 if configured. Runs anywhere
# pg_dump (and, for the R2 step, rclone) is available; the compose db-backup
# service calls it on a schedule.
#
# Env (defaults match docker-compose.yml):
#   PGHOST=db PGUSER=finance PGDATABASE=finance PGPASSWORD=finance
#   BACKUP_DIR=/backups   BACKUP_KEEP_DAYS=14
#   R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BACKUP_BUCKET
#     optional; when all four are set, the dump is also uploaded to R2.
#     Remote retention is handled by an R2 bucket lifecycle rule, not here.
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

# retention: delete local dumps older than BACKUP_KEEP_DAYS
find "$BACKUP_DIR" -name "$PGDATABASE-*.dump" -mtime "+$BACKUP_KEEP_DAYS" -delete

# ship to R2 (Cloudflare's S3-compatible object storage), when configured
if [ -n "${R2_ACCOUNT_ID:-}" ] && [ -n "${R2_ACCESS_KEY_ID:-}" ] \
   && [ -n "${R2_SECRET_ACCESS_KEY:-}" ] && [ -n "${R2_BACKUP_BUCKET:-}" ]; then
  export RCLONE_CONFIG_R2BACKUP_TYPE=s3
  export RCLONE_CONFIG_R2BACKUP_PROVIDER=Cloudflare
  export RCLONE_CONFIG_R2BACKUP_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
  export RCLONE_CONFIG_R2BACKUP_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
  export RCLONE_CONFIG_R2BACKUP_ENDPOINT="https://$R2_ACCOUNT_ID.r2.cloudflarestorage.com"
  export RCLONE_CONFIG_R2BACKUP_ACL=private

  # --s3-no-check-bucket: skip rclone's pre-flight bucket-exists/create check.
  # R2 API tokens are scoped to an existing bucket's objects and don't carry
  # bucket-management permission, so that check 403s even when the bucket is
  # fine and the actual upload would succeed.
  rclone copyto --s3-no-check-bucket "$TARGET" "r2backup:$R2_BACKUP_BUCKET/$(basename "$TARGET")"
  echo "uploaded to r2://$R2_BACKUP_BUCKET/$(basename "$TARGET")"
else
  echo "R2 not configured (R2_ACCOUNT_ID/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY/R2_BACKUP_BUCKET) - skipping upload"
fi
