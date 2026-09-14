#!/bin/sh
# Encrypted round-trip rehearsal; only drops the fresh database this script creates.
# Source must be quiescent: fail if its fingerprint changes during the rehearsal.
set -eu
umask 077
: "${PGDATABASE:?Set the source database}"
case "$PGDATABASE" in
    ''|*[!a-zA-Z0-9_]*) echo 'Unsafe database name' >&2; exit 2 ;;
esac
restore_tmp=$(mktemp -d)
restore_name="w8_restore_$(date -u +%Y%m%d%H%M%S)_$$"
restore_created=0
cleanup() {
    if [ "$restore_created" = 1 ]; then
        dropdb --if-exists "$restore_name"
    fi
    rm -f "$restore_tmp/identity" "$restore_tmp/restored.dump" \
        "$restore_tmp/before" "$restore_tmp/after" "$restore_tmp/restored" \
        "$restore_tmp/fingerprint.sql"
    rmdir "$restore_tmp"
}
trap cleanup EXIT HUP INT TERM

# Every public table: count + deterministic full-row digest, not only latest version.
printf '%s\n' \
    "SELECT format('SELECT %L || '':'' || count(*) || '':'' || coalesce(md5(string_agg(row_to_json(t)::text, E''\\n'' ORDER BY row_to_json(t)::text)), md5('''')) FROM %I.%I t;', tablename, schemaname, tablename) FROM pg_tables WHERE schemaname='public' ORDER BY tablename;" \
    '\gexec' > "$restore_tmp/fingerprint.sql"
psql -X -v ON_ERROR_STOP=1 -At -f "$restore_tmp/fingerprint.sql" > "$restore_tmp/before"
age-keygen -o "$restore_tmp/identity" 2>/dev/null
AGE_RECIPIENT=$(age-keygen -y "$restore_tmp/identity")
export AGE_RECIPIENT
: "${BACKUP_DIR:=$restore_tmp/backups}"
export BACKUP_DIR
backup_archive=$(sh /opt/barcodes/backup.sh)
(cd "$BACKUP_DIR" && sha256sum -c "$(basename "$backup_archive").sha256" >/dev/null)
age --decrypt --identity "$restore_tmp/identity" \
    --output "$restore_tmp/restored.dump" "$backup_archive"
createdb --template=template0 "$restore_name"
restore_created=1
pg_restore --exit-on-error --no-owner --no-privileges --dbname="$restore_name" \
    "$restore_tmp/restored.dump"
PGDATABASE="$restore_name" psql -X -v ON_ERROR_STOP=1 -At \
    -f "$restore_tmp/fingerprint.sql" > "$restore_tmp/restored"
psql -X -v ON_ERROR_STOP=1 -At -f "$restore_tmp/fingerprint.sql" > "$restore_tmp/after"
cmp "$restore_tmp/before" "$restore_tmp/after" >/dev/null || {
    echo 'Source changed during rehearsal: retry with writers quiesced' >&2; exit 1;
}
cmp "$restore_tmp/before" "$restore_tmp/restored" >/dev/null || {
    echo 'Restored data fingerprint mismatch' >&2; exit 1;
}
echo "PASS encrypted backup/restore: $PGDATABASE (all public-table fingerprints match)"
# The rehearsal key is ephemeral; delete its now-unreadable test archive only.
rm -f "$backup_archive" "$backup_archive.sha256"
if [ "$BACKUP_DIR" = "$restore_tmp/backups" ]; then rmdir "$BACKUP_DIR"; fi
