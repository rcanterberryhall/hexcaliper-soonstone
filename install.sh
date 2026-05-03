#!/usr/bin/env bash
# Soonstone install / update script.
# Idempotent: safe to re-run after `git pull`.

set -euo pipefail

cd "$(dirname "$0")"

echo "==> Ensuring data and logs directories exist"
mkdir -p data logs

echo "==> Building image"
docker compose build

echo "==> Bringing up service"
docker compose up -d

echo "==> Container status"
sleep 5
docker compose ps soonstone

echo
echo "Done. Logs: docker logs -f soonstone"
echo "First ingest cycle will fire at the next :25 or :55 minute mark."
echo "To trigger immediately: docker exec soonstone python -m soonstone --run-once ingest_metars"
