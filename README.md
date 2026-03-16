# Agentic Job Applier - Phase 1: Job Discovery System

Automated job discovery system that monitors multiple sources (Greenhouse, Workday, Indeed, Glassdoor) and stores opportunities in a SQLite database.

## Features

- **Multi-source job fetching**:
  - Greenhouse API (free, no auth required)
  - Workday via Apify scraper (requires API token)
  - Indeed, Glassdoor via JobSpy library
- **Intelligent deduplication** based on content hashing
- **SQLite database** for persistent storage
- **Comprehensive logging** with rotation
- **Autonomous runtime** via systemd timer + continuous worker (Linux)
- **Status dashboard** script for monitoring
- **YAML-canonical resume tailoring pipeline** with 1-page enforcement

## Installation

### Prerequisites

- Python 3.11+
- `uv` package manager ([installation instructions](https://github.com/astral-sh/uv))

### Setup

1. Clone the repository:
```bash
git clone <your-repo-url>
cd agentic-job-applier
```

2. Install dependencies:
```bash
uv sync
```

3. Configure environment:
```bash
cp .env.example .env
# Edit .env with your configuration
nano .env
```

Required environment variables:
- `APIFY_API_TOKEN`: Get from [Apify Console](https://console.apify.com/account/integrations) (optional, for Workday scraping)
- `DATABASE_PATH`: Path to SQLite database (default: `data/jobs.db`)
- `LOG_FILE`: Path to log file (default: `logs/job_monitor.log`)
- `LOG_LEVEL`: Logging level (default: `INFO`)
- `OPENAI_API_KEY`: Required for the `gpt-5-mini` apply/skip gate

Agent workflow environment variables:
- `AGENT_BATCH_SIZE`: Max NEW jobs processed per run
- `AGENT_POLL_INTERVAL_SECONDS`: Poll interval when running `--loop`
- `AGENT_MAX_RETRIES`: Retry attempts before terminal failure (default: 3)
- `AGENT_RETRY_BACKOFF_SECONDS`: Base retry delay in seconds (default: 300)
- `AGENT_RETRY_BACKOFF_MULTIPLIER`: Retry backoff multiplier (default: 3)
- `NTFY_TOPIC`: Enable ntfy terminal-failure alerts when set
- `NTFY_SERVER`: ntfy endpoint (default: `https://ntfy.sh`)
- `NTFY_TOKEN`: Optional bearer token for ntfy auth
- `NTFY_PRIORITY`: ntfy priority header (default: `default`)
- `CANDIDATE_PROFILE_PATH`: Optional profile config path override
- `SQLITE_JOURNAL_MODE`: Optional journal mode override (`WAL` default)
- `PI_CODING_AGENT_COMMAND`: Optional command override for the pi-coding-agent resume tailor runner

4. Configure companies and search criteria:
   - Edit `config/companies.yaml` to add/remove target companies
   - Edit `config/search_criteria.yaml` to customize search terms and filters
   - Edit `config/candidate_profile.yaml` to tune gate context and default internship targeting

## Usage

### Manual Run

Run a single discovery cycle:

```bash
uv run python main.py
```

### Check Status

View current system status and statistics:

```bash
uv run python -m scripts.status
```

This displays:
- Total jobs in database
- New jobs today/this week
- Jobs by status and source
- Top companies
- Recent crawl history
- Failed crawls
- Daily statistics

### Run The Apply/Skip Gate

Process pending `NEW` jobs through the local-first decider:

```bash
uv run python -m scripts.process_new_jobs --limit 25
```

Run one full pipeline cycle (discovery then one gate batch):

```bash
uv run python -m scripts.run_pipeline_once --limit 25
```

Inspect one stored job with the exact same gate logic:

```bash
uv run python -m scripts.decide_job --job-hash <job_hash>
uv run python -m scripts.decide_job --job-hash <job_hash> --save
```

### Run Resume Tailor (Pi-Mono, YAML Canonical)

Migrate your existing LaTeX resume to canonical YAML (one-time or whenever your base resume changes):

```bash
uv run python -m scripts.migrate_resume_tex_to_yaml \
  --tex-path ../resume/resume.tex \
  --yaml-out config/resume_content.yaml
```

Use the tool surface directly (useful for debugging or integrating with custom pi prompts):

```bash
uv run python -m scripts.resume_tailor_tools db-get-job-context --job-hash <job_hash>
uv run python -m scripts.resume_tailor_tools load-resume-yaml --path config/resume_content.yaml
uv run python -m scripts.resume_tailor_tools render-resume-tex \
  --yaml-path config/resume_content.yaml \
  --tex-out data/tailored_resumes/manual/resume.tex
uv run python -m scripts.resume_tailor_tools compile-resume \
  --tex-path data/tailored_resumes/manual/resume.tex \
  --pdf-out data/tailored_resumes/manual/resume.pdf
uv run python -m scripts.resume_tailor_tools get-page-count \
  --pdf-path data/tailored_resumes/manual/resume.pdf
```

Run the full one-page-enforced tailor loop for one stored job:

```bash
uv run python -m scripts.run_resume_tailor \
  --job-hash <job_hash> \
  --resume-yaml-path config/resume_content.yaml \
  --pi-coding-agent-command "<your non-interactive pi-coding-agent command>"
```

Optional branch isolation per tailoring run:

```bash
uv run python -m scripts.run_resume_tailor \
  --job-hash <job_hash> \
  --create-git-branch \
  --branch-prefix resume-tailor \
  --pi-coding-agent-command "<your non-interactive pi-coding-agent command>"
```

### Automated Scheduling (Linux)

Recommended autonomous runtime on Linux homeserver:
- `job-discovery.timer`: discovery producer every 30 minutes
- `job-agent-worker.service`: continuous consumer draining NEW backlog

1. Edit systemd service files:
```bash
cd deploy
nano job-discovery.service
nano job-agent-worker.service
# Update User, WorkingDirectory, and ExecStart paths in both files
```

2. Install systemd service:
```bash
sudo cp job-discovery.service /etc/systemd/system/
sudo cp job-discovery.timer /etc/systemd/system/
sudo cp job-agent-worker.service /etc/systemd/system/
sudo cp job-agent-alert@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now job-discovery.timer
sudo systemctl enable --now job-agent-worker.service
```

3. Verify:
```bash
# Check timer + worker status
systemctl status job-discovery.timer
systemctl status job-agent-worker.service

# View logs
journalctl -u job-discovery.service -f
journalctl -u job-agent-worker.service -f
```

See [deploy/README.md](deploy/README.md) for detailed deployment instructions.

## Configuration

### Companies Configuration

Edit `config/companies.yaml` to manage target companies:

```yaml
greenhouse_companies:
  Stripe:
    greenhouse_id: "stripe"
    priority: 1

workday_companies:
  Goldman Sachs:
    workday_url: "https://gs.wd5.myworkdayjobs.com/en-US/GSCareers"
    priority: 1

job_boards:
  Indeed:
    enabled: true
    search_terms:
      - "senior software engineer"
    locations:
      - "Remote"
    results_wanted: 25
```

### Search Criteria

Edit `config/search_criteria.yaml` to customize filtering (used in Phase 2):

```yaml
target_titles:
  - "Software Engineer"
  - "Senior Software Engineer"
  - "Backend Engineer"

locations:
  remote_preference: "remote_only"
  acceptable_cities:
    - "San Francisco"
    - "New York"
    - "Remote"

salary:
  min: 150000
  max: 400000
```

## Architecture

### Project Structure

```
agentic-job-applier/
├── config/                    # Configuration files
│   ├── companies.yaml        # Target companies
│   ├── search_criteria.yaml  # Search criteria
│   └── resume_content.yaml   # YAML-canonical resume source of truth
├── src/
│   ├── database/             # Database layer
│   │   ├── db_manager.py    # SQLite manager
│   │   └── schema.sql       # Database schema
│   ├── agents/
│   │   ├── root_apply_decider/   # ADK apply/skip gate
│   │   └── resume_tailor_pi/     # pi-mono resume tailor runtime + tools
│   ├── fetchers/             # Job fetchers
│   │   ├── base_fetcher.py  # Abstract base
│   │   ├── greenhouse_fetcher.py
│   │   ├── apify_fetcher.py
│   │   └── jobspy_fetcher.py
│   ├── models/               # Data models
│   │   └── job_posting.py   # Pydantic model
│   └── utils/                # Utilities
│       ├── deduplicator.py  # Deduplication logic
│       └── logger.py        # Logging setup
├── scripts/
│   ├── status.py                 # Status dashboard
│   ├── run_resume_tailor.py      # End-to-end tailor runner
│   ├── resume_tailor_tools.py    # Tool surface for pi-coding-agent
│   └── migrate_resume_tex_to_yaml.py # LaTeX->YAML migration utility
├── deploy/                   # Deployment files
│   ├── job-discovery.service
│   ├── job-discovery.timer
│   └── README.md
├── data/                     # SQLite database (gitignored)
├── logs/                     # Log files (gitignored)
└── main.py                  # Main orchestrator
```

### Data Flow

1. **Orchestrator** (main.py) loads configuration and initializes database
2. **Fetchers** scrape jobs from various sources:
   - GreenhouseFetcher: Direct API calls
   - ApifyWorkdayFetcher: Apify actor for Workday scraping
   - JobSpyFetcher: JobSpy library for job boards
3. **Deduplicator** filters out duplicate jobs using content hashing
4. **Database Manager** stores new jobs in SQLite
5. **Logger** records all activity with rotation

### Database Schema

- `job_postings`: Main table storing job details
- `crawl_history`: Tracks each source fetch attempt
- `daily_stats`: Aggregated daily statistics

## Troubleshooting

### Common Issues

**No jobs found from Greenhouse companies**

Some company IDs in the default config may be incorrect. Check the Greenhouse board URL:
- Visit `https://boards.greenhouse.io/{company_id}`
- If 404, search for the company's career page and find their correct ID

**Apify token errors**

Make sure `APIFY_API_TOKEN` is set in `.env`. Get your token from [Apify Console](https://console.apify.com/account/integrations).

**JobSpy rate limiting**

Indeed/Glassdoor may rate limit requests. The system includes 2-second delays between requests. If issues persist, reduce `results_wanted` in config.

**Permission errors**

Ensure the user running the service has write permissions to:
- `data/` directory (for SQLite database)
- `logs/` directory (for log files)

### Logs

Application logs are stored in `logs/job_monitor.log` with automatic rotation (10MB max, 1 week retention).

For systemd service logs:
```bash
journalctl -u job-discovery.service --since "1 hour ago"
```

## Development

### Running Tests

```bash
uv run --group dev pytest tests/
```

Live model E2E tests are opt-in:

```bash
uv run pytest -q --run-live-agent-e2e -m live_agent_e2e
```

### Adding a New Fetcher

1. Create a new fetcher class inheriting from `BaseFetcher`
2. Implement `fetch_jobs()` and `get_source_name()` methods
3. Return list of `JobPosting` objects
4. Add configuration to `companies.yaml`
5. Update main.py orchestrator to include the new fetcher

Example:
```python
class CustomFetcher(BaseFetcher):
    async def fetch_jobs(self) -> List[JobPosting]:
        # Your scraping logic here
        return [JobPosting(...), ...]

    def get_source_name(self) -> str:
        return "custom_source"
```

## Roadmap

- [x] **Phase 1: Job Discovery** (Current)
  - Multi-source job fetching
  - Deduplication and storage
  - Automated scheduling

- [x] **Phase 2: Intelligent Filtering**
  - Root apply/skip decider workflow
  - Agent-result persistence and status mapping
  - Retry/failure tracking for agent processing

- [ ] **Phase 3: Application Automation**
  - Resume customization (YAML-canonical pi-mono tailor loop now available)
  - Cover letter generation
  - Form filling automation

## License

MIT

## Contributing

Issues and pull requests welcome!
