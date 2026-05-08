#!/usr/bin/env bash
# Run the job-discovery script on a repeating interval.
#
# Replaces the systemd timer (job-discovery.timer) used in the bare-metal
# deployment.  Runs main.py once per cycle and sleeps between runs.
#
# Environment:
#   RUN_INTERVAL_MINUTES — minutes between discovery runs (default: 30)
set -euo pipefail

INTERVAL="${RUN_INTERVAL_MINUTES:-30}"

while true; do
    echo "[discovery] Starting run at $(date -Iseconds)"
    uv run --no-dev python main.py \
        || echo "[discovery] Run failed — will retry next cycle"
    echo "[discovery] Sleeping ${INTERVAL}m until next run"
    sleep "${INTERVAL}m"
done
