#!/usr/bin/env bash
# Export your local Chrome profile for import into the Docker chrome-profile volume.
#
# Run this on your desktop machine (macOS or Linux) where you have Chrome
# installed with the Simplify extension already set up and authenticated.
#
# Usage:
#   ./scripts/docker/profile_export.sh [output_file]
#
# Output:
#   chrome-profile.tar.gz in the current directory (or the path you specify)
#
# After running, upload the tarball to your server and run profile_import.sh.
set -euo pipefail

OUTPUT_FILE="${1:-chrome-profile.tar.gz}"

# Locate Chrome profile directory based on OS
case "$(uname -s)" in
    Darwin)
        PROFILE_DIR="$HOME/Library/Application Support/Google/Chrome"
        ;;
    Linux)
        PROFILE_DIR="$HOME/.config/google-chrome"
        ;;
    *)
        echo "Unsupported OS: $(uname -s)" >&2
        exit 1
        ;;
esac

if [ ! -d "$PROFILE_DIR" ]; then
    echo "Chrome profile directory not found: $PROFILE_DIR" >&2
    echo "Install Chrome and log in to Simplify before running this script." >&2
    exit 1
fi

echo "Exporting Chrome profile from: $PROFILE_DIR"
echo "Output: $OUTPUT_FILE"

# Archive only the Default profile (extensions, cookies, localStorage).
# Exclude the Cache dirs to keep the tarball small.
tar -czf "$OUTPUT_FILE" \
    --exclude="*/Cache/*" \
    --exclude="*/cache/*" \
    --exclude="*/*Cache*" \
    --exclude="*/GPUCache/*" \
    --exclude="*/ShaderCache/*" \
    --exclude="*/Code Cache/*" \
    -C "$(dirname "$PROFILE_DIR")" \
    "$(basename "$PROFILE_DIR")"

SIZE=$(du -sh "$OUTPUT_FILE" | cut -f1)
echo "Done. Archive size: $SIZE"
echo ""
echo "Next steps:"
echo "  1. Copy $OUTPUT_FILE to your server"
echo "  2. Run: bash scripts/docker/profile_import.sh $OUTPUT_FILE"
