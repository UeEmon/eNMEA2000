#!/usr/bin/env bash
# Docker Desktop / Compose backup. Does not stop ingestion.
set -euo pipefail
cd "$(dirname "$0")/.."
backup_dir="${1:-backups/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$backup_dir"
docker compose exec -T db pg_dump -U nmea -d nmea -Fc > "$backup_dir/nmea.dump"
docker compose exec -T app tar -C /data -czf - . > "$backup_dir/raw-data.tar.gz"
printf 'Backup written to %s. DB and raw archive timestamps can differ during active imports.\n' "$backup_dir"
