#!/usr/bin/env bash
# Import a Chrome profile tarball into the Docker chrome-profile volume.
#
# Run this on your server after copying the tarball produced by profile_export.sh.
#
# Usage:
#   ./scripts/docker/profile_import.sh [tarball]
#
# Default tarball: chrome-profile.tar.gz in the current directory.
#
# The script uses a temporary container to unpack the archive into the
# chrome-profile Docker volume.  The apply service must be stopped first.
set -euo pipefail

TARBALL="${1:-chrome-profile.tar.gz}"

if [ ! -f "$TARBALL" ]; then
    echo "Tarball not found: $TARBALL" >&2
    echo "Usage: $0 [path/to/chrome-profile.tar.gz]" >&2
    exit 1
fi

TARBALL_ABS="$(cd "$(dirname "$TARBALL")" && pwd)/$(basename "$TARBALL")"
VOLUME_NAME="agentic-job-applier_chrome-profile"

echo "Importing Chrome profile from: $TARBALL_ABS"
echo "Target Docker volume: $VOLUME_NAME"
echo ""

# Ensure the volume exists (create it if needed)
docker volume inspect "$VOLUME_NAME" > /dev/null 2>&1 \
    || docker volume create "$VOLUME_NAME"

# Clear the volume and extract the tarball into it
docker run --rm \
    -v "$TARBALL_ABS:/tmp/chrome-profile.tar.gz:ro" \
    -v "$VOLUME_NAME:/data" \
    debian:bookworm-slim \
    bash -c "
        rm -rf /data/* /data/.[!.]*
        tar -xzf /tmp/chrome-profile.tar.gz -C /tmp
        EXTRACTED=\$(find /tmp -maxdepth 1 -mindepth 1 -type d | head -1)
        if [ -z \"\$EXTRACTED\" ]; then
            echo 'Could not find extracted directory in tarball' >&2
            exit 1
        fi
        cp -a \"\$EXTRACTED/.\" /data/
        echo 'Import complete. Files in volume:'
        ls /data/ | head -20
    "

echo ""
echo "Done. Start the apply service with:"
echo "  docker compose --profile full up -d apply"
