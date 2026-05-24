# ============================================================
# Stage 1: Build React dashboard
# ============================================================
FROM node:22-slim AS dashboard-build
WORKDIR /app/dashboard
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm install
COPY dashboard/ ./
RUN npm run build

# ============================================================
# Stage 2: app — the single runtime image
#
# Contains the entire FastAPI process: API endpoints, the React
# dashboard, the tectonic LaTeX engine for resume tailoring, and
# the in-process asyncio supervisor that owns the discovery, gate,
# tailor, and apply loops.
#
# Chromium is intentionally NOT installed in the image — the apply
# loop talks to the user's host Chrome over CDP at
# `host.docker.internal:9222`. This drops ~400MB and the Xvfb
# dependency that came with the old in-image browser.
#
# `latexmk` is also no longer installed; tectonic is the only
# LaTeX engine and is verified at startup.
# ============================================================
FROM python:3.14-slim-bookworm AS app

# Multi-arch tectonic shipping (issue #61 §"Locked design decisions" item 5):
# tectonic does not publish a container image, so we COPY a host-prebuilt
# musl-linked binary keyed off `TARGETARCH` (set automatically by BuildKit
# during multi-platform builds). The repo ships both arm64 and amd64
# tarballs under `deploy/tectonic/`. To refresh either binary run
# `deploy/tectonic/fetch.sh`.
ARG TARGETARCH

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# uv — fast Python package installer (pinned for reproducible builds).
COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /usr/local/bin/uv

# Python dependencies — installed before the source copy so iterating on
# code does not invalidate the dep layer.
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Tectonic install — single statically-linked binary per arch. The
# tarball is COPYed rather than fetched at build time so the build does
# not depend on `apt-get` reaching Debian mirrors (BuildKit DNS to
# `deb.debian.org` has been flaky in practice).
COPY deploy/tectonic/tectonic-${TARGETARCH}.tar.gz /tmp/tectonic.tar.gz
RUN tar -xzf /tmp/tectonic.tar.gz -C /usr/local/bin tectonic \
    && chmod +x /usr/local/bin/tectonic \
    && rm /tmp/tectonic.tar.gz \
    && /usr/local/bin/tectonic --version

# Tectonic stores its on-demand CTAN cache here; the compose file mounts
# a named volume at this path so the cache survives container restarts.
ENV XDG_CACHE_HOME=/tectonic-cache
RUN mkdir -p /tectonic-cache && chmod 0777 /tectonic-cache

# Pre-warm the CTAN cache during the build so the first user-tailor
# compile does not pay the full package-fetch round trip. The stub
# imports every package the curated templates use.
COPY deploy/tectonic-prewarm.tex /tmp/prewarm.tex
RUN cd /tmp \
    && tectonic -X compile --outdir /tmp prewarm.tex \
    && rm -f /tmp/prewarm.tex /tmp/prewarm.pdf /tmp/prewarm.log /tmp/prewarm.aux

# Tailor cold-cache compiles can take longer than the upstream default;
# operators can override per-deployment via env if needed.
ENV TECTONIC_TIMEOUT_SECONDS=240

# Application source.
COPY src/ ./src/
COPY api/ ./api/
COPY scripts/ ./scripts/
COPY main.py ./
COPY deploy/ ./deploy/

# Pre-built React dashboard (built in the dashboard-build stage above).
COPY --from=dashboard-build /app/dashboard/dist ./dashboard/dist

ENV CODEX_HOME=/app/data/codex

VOLUME ["/app/data", "/app/logs", "/app/config"]
EXPOSE 8000

# Default command: run the API. The API's lifespan spawns the discovery
# / gate / tailor / apply loops as in-process asyncio tasks, so there is
# no separate worker container to start.
CMD ["uv", "run", "--no-dev", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
