#!/usr/bin/env bash
# Download both musl-linked tectonic tarballs (arm64 and amd64) from the
# upstream GitHub release, so the Dockerfile can COPY them in by
# `TARGETARCH` for multi-arch builds.
#
# Tectonic does NOT publish a container image to ghcr.io or Docker Hub
# (verified during issue #61 design). Hosting the tarballs in-repo
# sidesteps that gap and the Dockerfile build's flaky BuildKit DNS to
# `deb.debian.org`.
#
# Usage:
#   deploy/tectonic/fetch.sh                # uses TECTONIC_VERSION default
#   TECTONIC_VERSION=0.15.0 ./fetch.sh      # pin to a specific release
#
# After running, commit the updated tarballs along with this script.

set -euo pipefail

TECTONIC_VERSION="${TECTONIC_VERSION:-0.15.0}"
DEST_DIR="$(cd "$(dirname "$0")" && pwd)"

declare -A ARCH_TO_TRIPLE=(
    ["arm64"]="aarch64-unknown-linux-musl"
    ["amd64"]="x86_64-unknown-linux-musl"
)

for arch in "${!ARCH_TO_TRIPLE[@]}"; do
    triple="${ARCH_TO_TRIPLE[$arch]}"
    out="${DEST_DIR}/tectonic-${arch}.tar.gz"
    url="https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40${TECTONIC_VERSION}/tectonic-${TECTONIC_VERSION}-${triple}.tar.gz"
    echo "Fetching tectonic ${TECTONIC_VERSION} (${arch}) -> ${out}"
    curl -fsSL -o "${out}" "${url}"
done

echo "Done. Tarballs ready in ${DEST_DIR}."
