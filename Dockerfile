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
# Estimated build time: +8-12 min  (texlive-fonts-extra is
# the slow step — needed for the newtx font family)
# ============================================================
FROM base AS latex

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    latexmk \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Pinned for reproducible builds. Bump these together when upgrading.
ARG PI_CODING_AGENT_VERSION=0.129.0
ARG CODEX_CLI_VERSION=0.129.0
RUN npm install -g \
        @anthropic-ai/pi-coding-agent@${PI_CODING_AGENT_VERSION} \
        @openai/codex@${CODEX_CLI_VERSION}

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
