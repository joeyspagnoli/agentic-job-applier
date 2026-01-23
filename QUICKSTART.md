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
uv run python scripts/test_fetchers.py
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
# Run discovery cycle (takes 2-5 minutes)
uv run python main.py
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
uv run python scripts/status.py
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
uv run python scripts/query_jobs.py --company Stripe

# Search by title
uv run python scripts/query_jobs.py --title "senior engineer"

# Remote jobs only
uv run python scripts/query_jobs.py --remote

# Today's jobs
uv run python scripts/query_jobs.py --new --limit 20
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

## Schedule Automated Runs

### On Linux (systemd)

```bash
# Edit paths in service file
nano deploy/job-discovery.service

# Install
sudo cp deploy/job-discovery.service /etc/systemd/system/
sudo cp deploy/job-discovery.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable job-discovery.timer
sudo systemctl start job-discovery.timer

# Check status
systemctl status job-discovery.timer
```

### On macOS (cron)

```bash
# Open crontab
crontab -e

# Add line (runs every 30 minutes):
*/30 * * * * cd /path/to/agentic-job-applier && /path/to/.venv/bin/python main.py >> logs/cron.log 2>&1
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

1. **Phase 2**: Add intelligent filtering to auto-qualify jobs
2. **Phase 3**: Automate applications with resume customization
3. **Customize**: Add your own job sources/fetchers

See [README.md](README.md) for complete documentation.

## Support

- File issues on GitHub
- Check logs in `logs/job_monitor.log`
- Run with `LOG_LEVEL=DEBUG` for detailed output
