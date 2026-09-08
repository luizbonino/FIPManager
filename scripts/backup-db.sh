#!/usr/bin/env bash
# FIPManager SQLite backup script
#
# Usage examples:
#
#   # Direct invocation
#   FIPM_DB_PATH=/path/to/fipm.db ./scripts/backup-db.sh
#
#   # Via crontab (daily at 2 AM)
#   0 2 * * * /bin/bash -c 'FIPM_DB_PATH=/var/data/fipm.db FIPM_BACKUP_DIR=/var/backups FIPM_BACKUP_KEEP=7 /app/scripts/backup-db.sh' >> /var/log/fipm-backup.log 2>&1
#
#   # Via docker-compose
#   docker compose exec app FIPM_DB_PATH=/var/data/fipm.db FIPM_BACKUP_DIR=/var/backups /app/scripts/backup-db.sh
#
set -euo pipefail

DB="${FIPM_DB_PATH:-$1}"
BACKUP_DIR="${FIPM_BACKUP_DIR:-./backups}"
KEEP="${FIPM_BACKUP_KEEP:-30}"

# Validate sqlite3 is available
if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "Error: sqlite3 command not found" >&2
  exit 1
fi

# Validate DB path
if [ -z "$DB" ] || [ ! -f "$DB" ]; then
  echo "Error: Database not found at '$DB'" >&2
  exit 1
fi

# Create backup directory if missing
mkdir -p "$BACKUP_DIR"

# UTC timestamp for filename
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
BASENAME=$(basename "$DB")
OUT="$BACKUP_DIR/${BASENAME}.${TIMESTAMP}.sql"

# Run WAL-safe backup
sqlite3 "$DB" ".backup '$OUT'"

# Gzip the backup
GZ_OUT="${OUT}.gz"
gzip -f "$OUT"

# Cleanup old backups: keep newest $KEEP
# Sort by modification time (newest first), skip first $KEEP, delete the rest
find "$BACKUP_DIR" -maxdepth 1 -name '*.sql.gz' -printf '%T@ %p\n' | \
  sort -rn | \
  awk -v keep="$KEEP" 'NR > keep {print $2}' | \
  xargs -r rm -f

echo "$GZ_OUT"
