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
# Stage 2: base — core pipeline only
#
# Includes: job discovery, gate (apply-decider) agent, API +
# dashboard.  No LaTeX, no browser.
#
# Services: api, discovery, gate
# Estimated build time: ~3-5 min
# ============================================================
FROM python:3.11-slim-bookworm AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# uv — fast Python package installer (pinned for reproducible builds)
COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /usr/local/bin/uv

# Python dependencies — installed before source copy for better layer caching
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Application source
COPY src/ ./src/
COPY api/ ./api/
COPY scripts/ ./scripts/
COPY main.py ./
COPY deploy/ ./deploy/

# Pre-built React dashboard
COPY --from=dashboard-build /app/dashboard/dist ./dashboard/dist

ENV CODEX_HOME=/app/data/codex

VOLUME ["/app/data", "/app/logs", "/app/config"]
EXPOSE 8000

# ============================================================
# Stage 3: latex — adds resume tailoring + review
#
# Adds on top of base:
#   - texlive packages (covers all \usepackage{} calls in
#     resume_base.tex: geometry, titlesec, enumitem, fancyhdr,
#     babel, hyperref, newtxtext/newtxmath)
#   - poppler-utils  (pdfinfo for page-count checks)
#   - Node.js + pi CLI  (AI-powered resume rewriting)
#
# Services: tailor, review
# Estimated build time: +1-2 min  (tectonic is a single ~50 MB
# binary; CTAN packages are fetched at runtime on first compile
# and cached in /tectonic-cache so subsequent compiles are fast)
# ============================================================
FROM base AS latex

# Tectonic is a self-contained LaTeX engine. We ship a prebuilt linux-musl
# binary directly via COPY so the build does not depend on apt-get reaching
# Debian mirrors (buildkit's DNS to deb.debian.org has been flaky locally).
# To bump the version: rerun `deploy/tectonic/fetch.sh` from the host.
COPY deploy/tectonic/tectonic.tar.gz /tmp/tectonic.tar.gz
RUN tar -xzf /tmp/tectonic.tar.gz -C /usr/local/bin tectonic \
    && chmod +x /usr/local/bin/tectonic \
    && rm /tmp/tectonic.tar.gz \
    && /usr/local/bin/tectonic --version

# Tectonic stores its on-demand package cache here. docker-compose mounts
# a named volume at this path so the cache survives container restarts.
ENV XDG_CACHE_HOME=/tectonic-cache
RUN mkdir -p /tectonic-cache && chmod 0777 /tectonic-cache

# Pre-warm the CTAN cache during the build so the first user-tailor
# compile doesn't pay the full package-fetch round trip. The stub
# imports every package any of the 10 curated templates uses.
COPY deploy/tectonic-prewarm.tex /tmp/prewarm.tex
RUN cd /tmp \
    && tectonic -X compile --outdir /tmp prewarm.tex \
    && rm -f /tmp/prewarm.tex /tmp/prewarm.pdf /tmp/prewarm.log /tmp/prewarm.aux

# Plan §3.2 raised the default compile timeout to 240s to accommodate
# cold-cache compiles. Operators can override per-deployment.
ENV TECTONIC_TIMEOUT_SECONDS=240

# ============================================================
# Stage 4: full — adds browser-based job applying
#
# Adds on top of latex:
#   - Chromium (via Playwright, with all system deps)
#   - Xvfb virtual display (headless X11 for Chrome on a
#     server with no GUI)
#
# Service: apply
# Estimated build time: +3-5 min
# ============================================================
FROM latex AS full

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

RUN uv run playwright install chromium --with-deps
