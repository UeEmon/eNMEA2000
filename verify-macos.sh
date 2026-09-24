#!/usr/bin/env bash
# Run from the repository root on macOS with Docker Desktop started.
set -euo pipefail
cd "$(dirname "$0")"

if [[ "$(uname -s)" != "Darwin" ]]; then
  printf 'This helper is for macOS. Use start.sh and emulator/README.md on other systems.\n' >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  printf 'Start Docker Desktop, then rerun bash verify-macos.sh.\n' >&2
  exit 1
fi

bash start.sh
docker compose -f emulator/compose.yaml up -d --build --wait

# The app container has Python and the login token already; no host Python needed.
docker compose exec -T app python scripts/smoke.py
docker compose exec -T \
  -e NMEA_SMOKE_EMULATOR_URL=http://host.docker.internal:8090 \
  app python scripts/smoke_emulator.py

printf '\nVerification passed. Main UI: http://localhost:8080  Emulator: http://localhost:8090\n'
printf 'Sign in with APP_TOKEN in the local .env file.\n'
