#!/usr/bin/env bash
# Back up the SQLite database and profile to a timestamped tarball.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

BACKUP_DIR="backups"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/job-hunt-${TIMESTAMP}.tar.gz"

mkdir -p "$BACKUP_DIR"

if [ ! -f "data/jobs.db" ]; then
    echo "⚠️  No database found at data/jobs.db — nothing to back up"
    exit 0
fi

sqlite3 data/jobs.db ".backup 'data/jobs.db.bak'" 2>/dev/null || cp data/jobs.db data/jobs.db.bak

tar -czf "$BACKUP_FILE" \
    -C data \
    jobs.db.bak \
    $([ -f "data/profile.json" ] && echo "profile.json" || echo "") \
    2>/dev/null || true

rm -f data/jobs.db.bak

SIZE="$(du -h "$BACKUP_FILE" | cut -f1)"
echo "✅ Backup created: $BACKUP_FILE ($SIZE)"

ls -1t "$BACKUP_DIR"/job-hunt-*.tar.gz 2>/dev/null | tail -n +8 | xargs -r rm
echo "ℹ  Keeping last 7 backups"
