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

cleanup_workers() {
    # Always attempt to stop and reap children so failed workers do not leave
    # sibling loops running in the background.
    if [ ${#PIDS[@]} -eq 0 ]; then
        return
    fi
    kill "${PIDS[@]}" 2>/dev/null || true
    for pid in "${PIDS[@]}"; do
        wait "$pid" 2>/dev/null || true
    done
}

if [[ "$WORKERS" == *"gate"* ]]; then
    uv run python -m scripts.process_new_jobs --loop &
    gate_pid=$!
    PIDS+=("$gate_pid")
    echo "[workers] gate pid=$gate_pid"
fi

if [[ "$WORKERS" == *"tailor"* ]]; then
    uv run python -m scripts.process_qualified_jobs --loop &
    tailor_pid=$!
    PIDS+=("$tailor_pid")
    echo "[workers] tailor pid=$tailor_pid"
fi

if [[ "$WORKERS" == *"review"* ]]; then
    uv run python -m scripts.process_reviewed_resumes --loop &
    review_pid=$!
    PIDS+=("$review_pid")
    echo "[workers] review pid=$review_pid"
fi

if [ ${#PIDS[@]} -eq 0 ]; then
    echo "No workers started. Set WORKERS=gate,tailor,review" >&2
    exit 1
fi
trap cleanup_workers EXIT

# Exit the whole group if any worker dies. macOS bash 3.x does not support
# `wait -n`, so we poll child liveness and reap the first exited child.
while true; do
    for pid in "${PIDS[@]}"; do
        if ! kill -0 "$pid" 2>/dev/null; then
            set +e
            wait "$pid"
            EXIT_CODE=$?
            set -e
            echo "[workers] A worker exited ($EXIT_CODE) — stopping all"
            exit "$EXIT_CODE"
        fi
    done
    sleep 1
done
