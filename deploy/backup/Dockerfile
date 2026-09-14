FROM postgres:17-alpine

RUN apk add --no-cache age
COPY scripts/backup.sh scripts/verify_restore.sh /opt/barcodes/
RUN chmod 755 /opt/barcodes/*.sh
