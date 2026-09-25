#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
docker info >/dev/null
if [ ! -f .env ]; then
  docker run --rm --mount "type=bind,source=$PWD,target=/work" -w /work python:3.12-slim python scripts/setup.py
fi
docker compose up -d --build --wait
printf 'Open http://localhost:18081 and sign in using APP_TOKEN from .env\n'
