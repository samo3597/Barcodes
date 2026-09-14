#!/bin/sh
# Native PostgreSQL custom archive, encrypted before leaving the backup agent.
set -eu
umask 077

: "${PGDATABASE:?Set PGDATABASE to the source database}"
: "${BACKUP_DIR:?Set BACKUP_DIR to an access-controlled backup directory}"
: "${AGE_RECIPIENT:?Set AGE_RECIPIENT to an age public recipient}"
case "$PGDATABASE" in
    ''|*[!a-zA-Z0-9_]*) echo 'Unsafe database name' >&2; exit 2 ;;
esac
command -v age >/dev/null
mkdir -p "$BACKUP_DIR"
backup_tmp=$(mktemp -d)
trap 'rm -f "$backup_tmp/source.dump"; rmdir "$backup_tmp"' EXIT HUP INT TERM
backup_name="${PGDATABASE}_$(date -u +%Y%m%dT%H%M%SZ)_$$.dump.age"
backup_path="$BACKUP_DIR/$backup_name"

pg_dump --format=custom --no-owner --no-privileges --file="$backup_tmp/source.dump"
pg_restore --list "$backup_tmp/source.dump" >/dev/null
age --recipient "$AGE_RECIPIENT" --output "$backup_path" "$backup_tmp/source.dump"
(cd "$BACKUP_DIR" && sha256sum "$backup_name" > "$backup_name.sha256")
if [ -n "${BACKUP_METRICS_FILE:-}" ]; then
    printf 'barcodes_backup_last_success_timestamp_seconds{database="%s"} %s\n' \
        "$PGDATABASE" "$(date -u +%s)" > "$BACKUP_METRICS_FILE.tmp"
    mv "$BACKUP_METRICS_FILE.tmp" "$BACKUP_METRICS_FILE"
fi
printf '%s\n' "$backup_path"
