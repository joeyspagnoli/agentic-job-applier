# Deployment Instructions (Linux Homeserver)

## Runtime Model

- `job-discovery.timer` triggers `job-discovery.service` every 30 minutes.
- `job-agent-worker.service` continuously drains `NEW` jobs (gate stage).
- `job-tailor-worker.service` continuously drains `QUALIFIED` jobs.
- `job-review-worker.service` continuously drains successful tailor runs.
- `job-apply-worker.service` continuously drains eligible review runs.
- `job-apply-chrome.service` runs a CDP-enabled Chrome target for apply automation.
- SQLite is the queue/state backbone (`job_postings`, `tailor_runs`, `review_runs`, `apply_runs`, `apply_handoffs`, `cost_events`, `budget_settings`).

## Prerequisites

1. Python 3.11+
2. `uv`
3. Linux host with systemd
4. Project cloned on host
5. `pi` + `latexmk` for tailor/review workers
6. Chrome installed for apply worker CDP service

## 1. Clone And Install

```bash
cd /opt
git clone <your-repo-url> agentic-job-applier
cd agentic-job-applier
uv sync
npm --prefix dashboard install
```

## 2. Configure Environment

```bash
cp .env.example .env
nano .env
```

Minimum recommended keys:

- `OPENAI_API_KEY` for gate decisions
- `APIFY_API_TOKEN` (optional Workday source)
- `NTFY_TOPIC` (optional terminal failure alerts)

Optional cost-rate keys:

- `COST_RATE_GATE_USD`
- `COST_RATE_TAILOR_USD`
- `COST_RATE_REVIEW_USD`
- `COST_RATE_APPLY_USD`
- `COST_RATE_DISCOVERY_USD`

## 3. Preflight Checks

```bash
uv run python -c "import sqlite3; print(sqlite3.sqlite_version)"
uv run python -m scripts.process_new_jobs --once --limit 1
uv run python -m scripts.process_qualified_jobs --once
uv run python -m scripts.process_reviewed_resumes --once
uv run python -m scripts.process_apply_jobs --once
```

## 4. Configure Systemd Units

Edit placeholders in:

- `deploy/job-discovery.service`
- `deploy/job-agent-worker.service`
- `deploy/job-tailor-worker.service`
- `deploy/job-review-worker.service`
- `deploy/job-apply-worker.service`
- `deploy/job-apply-chrome.service`
- `deploy/job-agent-alert@.service` (optional)

Replace:

- `User=YOUR_USERNAME`
- `/path/to/agentic-job-applier`

## 5. Install And Enable Units

```bash
sudo cp deploy/job-discovery.service /etc/systemd/system/
sudo cp deploy/job-discovery.timer /etc/systemd/system/
sudo cp deploy/job-agent-worker.service /etc/systemd/system/
sudo cp deploy/job-tailor-worker.service /etc/systemd/system/
sudo cp deploy/job-review-worker.service /etc/systemd/system/
sudo cp deploy/job-apply-worker.service /etc/systemd/system/
sudo cp deploy/job-apply-chrome.service /etc/systemd/system/
sudo cp deploy/job-agent-alert@.service /etc/systemd/system/

sudo systemctl daemon-reload

sudo systemctl enable --now job-discovery.timer
sudo systemctl enable --now job-agent-worker.service
sudo systemctl enable --now job-tailor-worker.service
sudo systemctl enable --now job-review-worker.service
sudo systemctl enable --now job-apply-chrome.service
sudo systemctl enable --now job-apply-worker.service
```

## 6. Verify

```bash
systemctl status job-discovery.timer
systemctl status job-agent-worker.service
systemctl status job-tailor-worker.service
systemctl status job-review-worker.service
systemctl status job-apply-chrome.service
systemctl status job-apply-worker.service

journalctl -u job-discovery.service -f
journalctl -u job-agent-worker.service -f
journalctl -u job-tailor-worker.service -f
journalctl -u job-review-worker.service -f
journalctl -u job-apply-worker.service -f
```

## Optional API + Dashboard Service

Run backend API manually (or create your own unit):

```bash
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000
```

If serving dashboard via FastAPI static fallback, build frontend assets first:

```bash
npm --prefix dashboard run build
```
