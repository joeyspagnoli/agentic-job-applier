#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${REPO_ROOT}"

echo "[stack] Restarting docker compose stack from ${REPO_ROOT}"
docker compose down

echo "[stack] Stack stopped, starting again"
docker compose up -d

echo "[stack] Restart complete"
