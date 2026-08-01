#!/usr/bin/env bash
set -Eeuo pipefail

BACKUP_DIR=/var/backups/ghostdeveloper-license
STATE_DIR=/var/lib/ghostdeveloper-license
CONFIG_DIR=/etc/ghostdeveloper-license
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
DEST="$BACKUP_DIR/$TIMESTAMP"

[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "ERROR: se requiere root." >&2; exit 1; }
install -d -m 0700 "$DEST"

python3 - "$STATE_DIR/license.db" "$DEST/license.db" <<'PY'
import sqlite3
import sys
source, destination = sys.argv[1:]
with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
    src.backup(dst)
PY
chmod 0600 "$DEST/license.db"

cp -a "$CONFIG_DIR" "$DEST/config"
find "$DEST/config" -type f -exec chmod 0600 {} +
tar -C "$BACKUP_DIR" -czf "$BACKUP_DIR/ghost-license-$TIMESTAMP.tar.gz" "$TIMESTAMP"
chmod 0600 "$BACKUP_DIR/ghost-license-$TIMESTAMP.tar.gz"
rm -rf "$DEST"
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'ghost-license-*.tar.gz' -mtime +14 -delete
