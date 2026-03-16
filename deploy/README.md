# Deployment Instructions for Linux Homeserver

## Runtime Model

- `job-discovery.timer` triggers `job-discovery.service` every 30 minutes.
- `job-agent-worker.service` runs continuously and drains NEW backlog from SQLite.
- `job-tailor-worker.service` runs continuously and drains QUALIFIED backlog.
- `job-review-worker.service` runs continuously and drains successful tailor runs.
- Handoff queues are SQLite-backed (`job_postings`, `tailor_runs`, `review_runs`).

## Prerequisites

1. Python 3.11+ installed
2. `uv` installed
3. Linux host with systemd
4. Project cloned on the host

## 1. Clone and Install

```bash
cd /opt
git clone <your-repo-url> agentic-job-applier
cd agentic-job-applier
uv sync
```

## 2. Configure Environment

```bash
cp .env.example .env
nano .env
```

Set at minimum:
- `OPENAI_API_KEY` for gate decisions
- `APIFY_API_TOKEN` (optional, Workday source)
- `NTFY_TOPIC` (optional, enables terminal failure alerts)

## 3. Preflight Checks

Check SQLite runtime used by Python:

```bash
uv run python -c "import sqlite3; print(sqlite3.sqlite_version)"
```

If your runtime is older than SQLite `3.52.0`, keep `SQLITE_JOURNAL_MODE=WAL` only if
you are comfortable with older WAL behavior, or set `SQLITE_JOURNAL_MODE=DELETE`
until your Python sqlite runtime is upgraded.

## 4. Manual Smoke Test

```bash
# One-shot end-to-end run: discovery then one gate batch.
uv run python -m scripts.run_pipeline_once --limit 25
```

## 5. Configure systemd Units

Edit placeholders in:
- `deploy/job-discovery.service`
- `deploy/job-agent-worker.service`
- `deploy/job-tailor-worker.service`
- `deploy/job-review-worker.service`
- `deploy/job-agent-alert@.service` (optional OnFailure alert hook)

Replace:
- `User=YOUR_USERNAME`
- `/path/to/agentic-job-applier`

## 6. Install and Enable Units

```bash
sudo cp deploy/job-discovery.service /etc/systemd/system/
sudo cp deploy/job-discovery.timer /etc/systemd/system/
sudo cp deploy/job-agent-worker.service /etc/systemd/system/
sudo cp deploy/job-tailor-worker.service /etc/systemd/system/
sudo cp deploy/job-review-worker.service /etc/systemd/system/
sudo cp deploy/job-agent-alert@.service /etc/systemd/system/

sudo systemctl daemon-reload

sudo systemctl enable --now job-discovery.timer
sudo systemctl enable --now job-agent-worker.service
sudo systemctl enable --now job-tailor-worker.service
sudo systemctl enable --now job-review-worker.service
```

## 7. Verify

```bash
systemctl status job-discovery.timer
systemctl status job-agent-worker.service
systemctl status job-tailor-worker.service
systemctl status job-review-worker.service

journalctl -u job-discovery.service -f
journalctl -u job-agent-worker.service -f
journalctl -u job-tailor-worker.service -f
journalctl -u job-review-worker.service -f
```

## Operational Playbook

Check terminal gate failures:

```bash
sqlite3 data/jobs.db "SELECT job_hash, title, agent_retry_count, agent_error, agent_failed_at FROM job_postings WHERE agent_failed_at IS NOT NULL ORDER BY agent_failed_at DESC LIMIT 20;"
```

Requeue one terminally failed job:

```bash
sqlite3 data/jobs.db "UPDATE job_postings SET status='NEW', agent_failed_at=NULL, agent_error=NULL, agent_retry_count=0, agent_next_retry_at=NULL, updated_at=CURRENT_TIMESTAMP WHERE job_hash='YOUR_JOB_HASH';"
```

Run one manual gate batch:

```bash
uv run python -m scripts.process_new_jobs --once --limit 25
```
