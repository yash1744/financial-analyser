# db-backup sidecar: postgres client tools (pg_dump/pg_restore) plus rclone,
# used by scripts/db_backup.sh to ship dumps to R2 when R2_* env vars are set.
FROM postgres:17-alpine
RUN apk add --no-cache rclone
