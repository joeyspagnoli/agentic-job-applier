# Quick Start Guide

Get the Job Discovery System running in 5 minutes.

## Installation

```bash
# Clone the repo
git clone <your-repo-url>
cd agentic-job-applier

# Install dependencies
uv sync

# Test fetchers (optional)
uv run python -m scripts.test_fetchers
```

## Configuration

```bash
# Copy environment template
cp .env.example .env

# Optional: Add Apify token for Workday scraping
# Get token from: https://console.apify.com/account/integrations
nano .env
# Add: APIFY_API_TOKEN=your_token_here
```

## First Run

```bash
# Run one full pipeline cycle (discovery + gate worker batch)
uv run python -m scripts.run_pipeline_once --limit 25
```

Expected output:
```
============================================================
STARTING JOB DISCOVERY CYCLE
============================================================
Fetching from 20 Greenhouse companies...
Crawl complete: greenhouse/Stripe | Found: 549 | New: 549 | Duration: 0.93s
Crawl complete: greenhouse/Cloudflare | Found: 605 | New: 605 | Duration: 1.14s
...
============================================================
DISCOVERY CYCLE COMPLETE
  Total jobs discovered: 3847
  New jobs: 3847
  Duplicates: 0
  Sources succeeded: 22
  Sources failed: 0
  Total duration: 67.45s
============================================================
Database: 3847 total jobs, 3847 added today
```

## Check Status

```bash
# View dashboard
uv run python -m scripts.status
```

Output:
```
============================================================
JOB DISCOVERY STATUS
Time: 2026-01-22 15:30:45
============================================================

Total jobs in database: 3847
New jobs today: 3847
New jobs (last 7 days): 3847

Jobs by status:
  NEW: 3847

Jobs by source:
  greenhouse_cloudflare: 605
  greenhouse_stripe: 549
  greenhouse_databricks: 694
  ...

Top 10 companies:
  Databricks: 694
  Cloudflare: 605
  Stripe: 549
  ...
```

## Query Jobs

```bash
# Search by company
uv run python -m scripts.query_jobs --company Stripe

# Search by title
uv run python -m scripts.query_jobs --title "senior engineer"

# Remote jobs only
uv run python -m scripts.query_jobs --remote

# Today's jobs
uv run python -m scripts.query_jobs --new --limit 20
```

## Docker Stack Controls

When running with Docker Compose, use these host-level scripts:

```bash
./scripts/docker/start_stack.sh
./scripts/docker/stop_stack.sh
./scripts/docker/restart_stack.sh
```

If the dashboard is available, you can also use the TopBar power menu for
`Shut Down` and `Restart`.

## Resume Tailor (Pi-Mono)

1. Migrate your LaTeX resume into canonical YAML:

```bash
uv run python -m scripts.migrate_resume_tex_to_yaml \
  --tex-path ../resume/resume.tex \
  --yaml-out config/resume_content.yaml
```

2. Run one tailoring pass for a stored job:

```bash
uv run python -m scripts.run_resume_tailor \
  --job-hash <job_hash> \
  --resume-yaml-path config/resume_content.yaml \
  --pi-coding-agent-command "<your non-interactive pi-coding-agent command>"
```

3. Inspect resulting artifacts:

```bash
ls data/tailored_resumes/<job_hash>/
uv run python -m scripts.resume_tailor_tools get-page-count \
  --pdf-path data/tailored_resumes/<job_hash>/resume_tailored.pdf
```

## Customize

### Add/Remove Companies

Edit `config/companies.yaml`:

```yaml
greenhouse_companies:
  YourCompany:
    greenhouse_id: "yourcompany"
    priority: 1
```

To find a Greenhouse ID:
1. Visit the company's careers page
2. Look for URLs like `boards.greenhouse.io/{company_id}`
3. Use that ID in the config

### Change Search Terms

Edit `config/companies.yaml` under `job_boards`:

```yaml
job_boards:
  Indeed:
    enabled: true
    search_terms:
      - "your custom search"
      - "another search term"
    locations:
      - "Remote"
      - "Your City"
    results_wanted: 25
```

## Autonomous Runtime

### On Linux (systemd) — Ubuntu Server LTS

#### Prerequisites

```bash
# Install TeX Live and latexmk (required for resume tailor worker)
sudo apt-get update
sudo apt-get install -y texlive-full latexmk

# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone <your-repo-url>
cd agentic-job-applier
uv sync

# Copy and edit environment
cp .env.example .env
nano .env
# Set at minimum: DATABASE_PATH, PI_CODING_AGENT_COMMAND (or ensure 'pi' is in PATH)
# Set NTFY_TOPIC for operational alerts
# Set API keys as needed (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)
```

#### Deploy all services

```bash
# Edit paths in ALL service files (replace /path/to/ and YOUR_USERNAME)
nano deploy/job-discovery.service
nano deploy/job-agent-worker.service
nano deploy/job-tailor-worker.service

# Install service units
sudo cp deploy/job-discovery.service /etc/systemd/system/
sudo cp deploy/job-discovery.timer /etc/systemd/system/
sudo cp deploy/job-agent-worker.service /etc/systemd/system/
sudo cp deploy/job-tailor-worker.service /etc/systemd/system/
sudo cp deploy/job-agent-alert@.service /etc/systemd/system/
sudo systemctl daemon-reload

# Enable discovery + gate worker
sudo systemctl enable --now job-discovery.timer
sudo systemctl enable --now job-agent-worker.service

# Enable resume tailor worker
# NOTE: PI_CODING_AGENT_COMMAND must be set in .env (or 'pi' in PATH)
# NOTE: latexmk must be installed (texlive-full)
sudo systemctl enable --now job-tailor-worker.service

# Check status
systemctl status job-discovery.timer
systemctl status job-agent-worker.service
systemctl status job-tailor-worker.service
journalctl -u job-tailor-worker.service -f
```

#### Cost controls and shutdown

```bash
# Stop the tailor worker (most expensive — runs pi-mono coding agent)
sudo systemctl stop job-tailor-worker.service

# Stop the gate worker (moderate — runs ADK model calls)
sudo systemctl stop job-agent-worker.service

# Stop everything (discovery still runs but nothing processes)
sudo systemctl stop job-tailor-worker.service job-agent-worker.service

# Disable to prevent restart on reboot
sudo systemctl disable job-tailor-worker.service

# Monitor costs: check how many runs happened today
sqlite3 data/jobs.db "SELECT status, COUNT(*) FROM tailor_runs WHERE started_at >= date('now') GROUP BY status;"

# Check which jobs were tailored
sqlite3 data/jobs.db "SELECT job_hash, status, started_at, completed_at FROM tailor_runs ORDER BY started_at DESC LIMIT 20;"
```

### On macOS (cron)

```bash
# Open crontab
crontab -e

# Add two lines (discovery + gate worker one-shot)
*/30 * * * * cd /path/to/agentic-job-applier && /path/to/.venv/bin/python main.py >> logs/cron.log 2>&1
*/5 * * * * cd /path/to/agentic-job-applier && /path/to/.venv/bin/python -m scripts.process_new_jobs --once --limit 25 >> logs/cron.log 2>&1
```

## Troubleshooting

### "No jobs found" for a company

The Greenhouse ID might be wrong. Check:
- Visit `https://boards.greenhouse.io/{company_id}`
- If 404, search for the company's actual careers page
- Update `companies.yaml` with correct ID

### Rate limiting errors

JobSpy/Indeed may rate limit. Solutions:
- Reduce `results_wanted` in config
- Increase delay in main.py (line 203: `await asyncio.sleep(5)`)
- Space out runs (run every hour instead of 30 min)

### Permission errors

```bash
# Ensure directories exist and are writable
mkdir -p data logs
chmod 755 data logs
```

## Next Steps

1. Edit `config/candidate_profile.yaml` for your own background and role targets
2. Configure `NTFY_TOPIC` in `.env` to receive terminal gate failure alerts
3. Run opt-in live E2E tests: `uv run pytest -q --run-live-agent-e2e -m live_agent_e2e`

See [README.md](README.md) for complete documentation.

## Support

- File issues on GitHub
- Check logs in `logs/job_monitor.log`
- Run with `LOG_LEVEL=DEBUG` for detailed output
