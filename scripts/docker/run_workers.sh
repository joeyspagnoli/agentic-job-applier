#!/usr/bin/env bash
# Run all queue workers locally (outside Docker) for development.
#
# In Docker, each worker runs as its own Compose service (gate, tailor,
# review) so they can be enabled independently.  Use this script only
# when running the stack directly on your machine without Compose.
#
# Requires LaTeX + pi CLI installed locally to use tailor + review.
#
# Usage:
#   bash scripts/docker/run_workers.sh            # all three
#   WORKERS=gate bash scripts/docker/run_workers.sh  # gate only
set -euo pipefail

WORKERS="${WORKERS:-gate,tailor,review}"

declare -a PIDS=()

if [[ "$WORKERS" == *"gate"* ]]; then
    uv run python -m scripts.process_new_jobs --loop &
    PIDS+=($!)
    echo "[workers] gate pid=${PIDS[-1]}"
fi

if [[ "$WORKERS" == *"tailor"* ]]; then
    uv run python -m scripts.process_qualified_jobs --loop &
    PIDS+=($!)
    echo "[workers] tailor pid=${PIDS[-1]}"
fi

if [[ "$WORKERS" == *"review"* ]]; then
    uv run python -m scripts.process_reviewed_resumes --loop &
    PIDS+=($!)
    echo "[workers] review pid=${PIDS[-1]}"
fi

if [ ${#PIDS[@]} -eq 0 ]; then
    echo "No workers started. Set WORKERS=gate,tailor,review" >&2
    exit 1
fi

# Exit the whole group if any worker dies
wait -n
EXIT_CODE=$?
echo "[workers] A worker exited ($EXIT_CODE) — stopping all"
kill "${PIDS[@]}" 2>/dev/null || true
wait
exit "$EXIT_CODE"
