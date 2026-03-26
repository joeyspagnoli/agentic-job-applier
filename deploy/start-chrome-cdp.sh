#!/usr/bin/env bash
# Start Xvfb virtual display and Chrome with CDP enabled.
#
# This script is intended to be run by the job-apply-chrome.service
# systemd unit.  Chrome runs with the user's real profile so the
# Simplify extension is available and authenticated.
#
# Usage:
#   ./start-chrome-cdp.sh
#
# Environment:
#   DISPLAY   - Set to :99 for the virtual framebuffer (default).
#   CDP_PORT  - Chrome remote debugging port (default: 9222).

set -euo pipefail

DISPLAY="${DISPLAY:-:99}"
CDP_PORT="${CDP_PORT:-9222}"
DISPLAY_NUMBER="${DISPLAY#:}"
DISPLAY_SOCKET="/tmp/.X11-unix/X${DISPLAY_NUMBER}"

# Start Xvfb in the background if the target display is not ready.
if ! pgrep -af "Xvfb[[:space:]]+${DISPLAY}([[:space:]]|$)" > /dev/null 2>&1 \
   || [ ! -S "${DISPLAY_SOCKET}" ]; then
    Xvfb "${DISPLAY}" -screen 0 1920x1080x24 -nolisten tcp &
    sleep 1
fi

export DISPLAY

exec google-chrome \
    --remote-debugging-port="${CDP_PORT}" \
    --no-first-run \
    --disable-background-timer-throttling \
    --disable-backgrounding-occluded-windows \
    --disable-renderer-backgrounding \
    --disable-features=TranslateUI \
    --disable-sync
