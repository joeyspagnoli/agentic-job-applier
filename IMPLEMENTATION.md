# Job Discovery System - Phase 1

### High-Level Overview

This system automatically discovers new job postings from multiple sources (Greenhouse API, Apify Workday scraper, JobSpy for job boards, and Firecrawl MCP for custom career pages), deduplicates them, stores them in a database, and runs on a 15-minute schedule.

What this accomplishes:

- Monitors 50+ target companies across multiple ATS platforms
- Aggregates jobs from Indeed, Glassdoor, and LinkedIn
- Deduplicates jobs using content-based hashing
- Stores structured job data for downstream processing
- Runs autonomously on your homeserver every 15 minutes
- Provides foundation for Google ADK agent workflow (Phase 2)

What this does NOT do (yet):

- Filter jobs by fit criteria (Phase 2)
- Tailor resumes (Phase 2)
- Auto-apply to jobs (Phase 2)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    SCHEDULED JOB MONITOR                        │
│                   (Runs every 30 minutes)                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    ┌────────┴────────┐
                    │  Main Orchestrator │
                    │   (main.py)        │
                    └────────┬────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        │                    │                    │
┌───────▼────────┐  ┌───────▼────────┐  ┌───────▼────────┐
│  Greenhouse    │  │  Apify Workday │  │  JobSpy        │
│  Fetcher       │  │  Fetcher       │  │  Fetcher       │
│  (FREE API)    │  │  (PAID API)    │  │  (FREE)        │
└───────┬────────┘  └───────┬────────┘  └───────┬────────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Job Normalizer  │
                    │  (Standardize)   │
                    └────────┬─────────┘
                             │
                    ┌────────▼────────┐
                    │  Deduplicator    │
                    │  (Hash-based)    │
                    └────────┬─────────┘
                             │
                    ┌────────▼────────┐
                    │  SQLite DB       │
                    │  (job_postings)  │
                    └──────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Logging System  │
                    │  (Stats & Errors)│
                    └──────────────────┘
```

---

## Questions Before Implementation

Please answer these to guide implementation details:

### Environment

1. Python version: What version are you running? (3.10+, 3.11, 3.12?)
2. Database choice: SQLite (simple, file-based) or PostgreSQL (more robust)?
3. OS: Linux, macOS, or Windows?
4. Scheduling method: cron, systemd timer, or Python scheduler (APScheduler)?

### Project Structure

1. Preferred structure:
   - Monorepo (all phases in one project)?
   - Separate repos (job-discovery separate from ADK agents)?
2. Configuration format: YAML, JSON, or .env files for company lists?

### Data Management

1. Job storage duration: Keep all jobs forever, or archive/delete after X days?
2. Duplicate handling: If same job found twice, update timestamp or ignore?
3. Data export: Need CSV/JSON export functionality for analysis?

### Rate Limiting & Proxies

1. Proxy usage: Do you have proxies? (JobSpy needs them for LinkedIn)
2. Rate limit strategy: Back off on errors, or skip source and continue?

### Monitoring & Alerting

1. Notification method: How do you want to be notified of errors? (email, Slack, Discord, logs only?)
2. Success metrics: Daily summary of jobs discovered? Real-time alerts?

### API Keys & Costs

1. Apify budget: Willing to pay \~$5-10/month for Workday scraping? Or skip for MVP?
2. Firecrawl: Skip custom career pages (Google, Apple, Microsoft) for MVP?

---

## Detailed Implementation Checklist

### Task 1: Project Setup

#### 1.1 Initialize Project Structure

```
job-discovery/
├── config/
│   ├── companies.yaml           # Company targets & metadata
│   └── search_criteria.yaml     # Job search parameters
├── src/
│   ├── fetchers/
│   │   ├── __init__.py
│   │   ├── base_fetcher.py      # Abstract base class
│   │   ├── greenhouse_fetcher.py
│   │   ├── apify_fetcher.py
│   │   └── jobspy_fetcher.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── job_posting.py       # Pydantic model
│   ├── database/
│   │   ├── __init__.py
│   │   ├── schema.sql
│   │   └── db_manager.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logger.py
│   │   └── deduplicator.py
│   └── main.py                  # Orchestrator
├── tests/
│   ├── test_fetchers.py
│   └── test_deduplicator.py
├── data/
│   └── jobs.db                  # SQLite database (gitignored)
├── logs/
│   └── job_monitor.log          # Logs (gitignored)
├── .env                         # API keys (gitignored)
├── pyproject.toml               # uv project config
└── README.md
```

Checklist:

- \[ \] Create directory structure
- \[ \] Initialize git repository
- \[ \] Create .gitignore (exclude .env, data/, logs/, \__pycache_\_/, .venv/)
- \[ \] Initialize uv project: uv init

#### 1.2 Install Dependencies

Recommended starting libraries:

```bash
uv add aiohttp httpx pydantic pyyaml aiosqlite jobspy apify-client apscheduler loguru pytest pytest-asyncio python-dotenv
```

What each does:

- aiohttp / httpx - Async HTTP requests
- pydantic - Data validation and models
- pyyaml - Parse YAML config files
- aiosqlite - Async SQLite database (or use asyncpg for PostgreSQL)
- jobspy - Job board scraper (Indeed, Glassdoor, LinkedIn)
- apify-client - Apify API client for Workday scraping
- apscheduler - Job scheduler (if not using cron/systemd)
- loguru - Better logging
- pytest / pytest-asyncio - Testing
- python-dotenv - Load environment variables

Checklist:

- \[ \] Run uv add command above
- \[ \] Verify installations: uv run python -c "import jobspy; import aiohttp; import pydantic"

#### 1.3 Environment Configuration

Create .env:

```bash
# API Keys
APIFY_API_TOKEN=your_apify_token_here  # Get from https://console.apify.com/account/integrations
# FIRECRAWL_API_KEY=your_key_here  # Optional for Phase 1

# Database
DATABASE_PATH=data/jobs.db  # SQLite
# DATABASE_URL=postgresql://user:pass@localhost/jobs  # If using PostgreSQL

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/job_monitor.log

# Scheduler
RUN_INTERVAL_MINUTES=30
```

Checklist:

- \[ \] Create .env file
- \[ \] Get Apify API token (if using Workday scraper)
- \[ \] Set database path
- \[ \] Configure log settings

---

### Task 2: Database Design

#### 2.1 Database Schema

File: src/database/schema.sql

```sql
-- Main table for job postings
CREATE TABLE IF NOT EXISTS job_postings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_hash TEXT UNIQUE NOT NULL,  -- MD5 hash for deduplication

    -- Source metadata
    source TEXT NOT NULL,            -- 'greenhouse_stripe', 'apify_workday', 'jobspy_indeed'
    source_url TEXT NOT NULL,        -- Original URL
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Company info
    company TEXT NOT NULL,
    company_url TEXT,

    -- Job details
    title TEXT NOT NULL,
    location TEXT,
    is_remote BOOLEAN,
    job_type TEXT,                   -- 'Full-time', 'Part-time', 'Contract', etc.

    -- Compensation
    salary_min INTEGER,              -- In cents to avoid float issues
    salary_max INTEGER,
    salary_currency TEXT DEFAULT 'USD',
    salary_source TEXT,              -- 'direct', 'parsed_from_description', 'not_listed'

    -- Content
    description TEXT,
    requirements TEXT,

    -- Dates
    posted_date TEXT,                -- As provided by source (may be relative like "2 days ago")
    posted_date_parsed TIMESTAMP,    -- Converted to actual timestamp if possible

    -- Processing status
    status TEXT DEFAULT 'NEW',       -- NEW, FILTERED, QUALIFIED, APPLIED, REJECTED

    -- Raw data for debugging
    raw_data JSON,                   -- Complete original API response

    -- Timestamps
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes for fast queries
    CHECK (status IN ('NEW', 'FILTERED', 'QUALIFIED', 'APPLIED', 'REJECTED'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_job_hash ON job_postings(job_hash);
CREATE INDEX IF NOT EXISTS idx_status ON job_postings(status);
CREATE INDEX IF NOT EXISTS idx_company ON job_postings(company);
CREATE INDEX IF NOT EXISTS idx_fetched_at ON job_postings(fetched_at);
CREATE INDEX IF NOT EXISTS idx_source ON job_postings(source);

-- Crawl history tracking
CREATE TABLE IF NOT EXISTS crawl_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,            -- 'greenhouse', 'apify_workday', 'jobspy'
    company TEXT,                    -- Specific company if applicable
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT DEFAULT 'IN_PROGRESS',  -- IN_PROGRESS, SUCCESS, FAILED
    jobs_found INTEGER DEFAULT 0,
    jobs_new INTEGER DEFAULT 0,      -- How many were actually new
    error_message TEXT,

    CHECK (status IN ('IN_PROGRESS', 'SUCCESS', 'FAILED'))
);

CREATE INDEX IF NOT EXISTS idx_crawl_source ON crawl_history(source);
CREATE INDEX IF NOT EXISTS idx_crawl_started ON crawl_history(started_at);

-- Daily statistics
CREATE TABLE IF NOT EXISTS daily_stats (
    date TEXT PRIMARY KEY,           -- YYYY-MM-DD
    total_jobs_discovered INTEGER DEFAULT 0,
    jobs_new INTEGER DEFAULT 0,
    jobs_duplicate INTEGER DEFAULT 0,
    sources_crawled INTEGER DEFAULT 0,
    sources_failed INTEGER DEFAULT 0
);
```

Checklist:

- \[ \] Create schema.sql
- \[ \] Decide on database choice (SQLite vs PostgreSQL)
- \[ \] Test schema creation: sqlite3 data/jobs.db < src/database/schema.sql

#### 2.2 Database Manager Implementation

File: src/database/db_manager.py

What it needs to do:

- \[ \] Initialize database connection (async)
- \[ \] Create tables if not exist
- \[ \] Insert new job (with duplicate check via hash)
- \[ \] Update existing job
- \[ \] Query jobs by status
- \[ \] Record crawl history
- \[ \] Update daily stats
- \[ \] Close connection properly

Key methods to implement:

```python
class DatabaseManager:
    async def connect(self):
        """Initialize DB connection"""

    async def create_tables(self):
        """Run schema.sql"""

    async def insert_job(self, job_data: dict) -> bool:
        """Insert job, return True if new, False if duplicate"""

    async def get_job_by_hash(self, job_hash: str) -> Optional[dict]:
        """Check if job exists"""

    async def update_job_status(self, job_hash: str, status: str):
        """Update processing status"""

    async def start_crawl(self, source: str, company: str = None) -> int:
        """Log crawl start, return crawl_id"""

    async def complete_crawl(self, crawl_id: int, jobs_found: int, jobs_new: int, error: str = None):
        """Log crawl completion"""

    async def update_daily_stats(self, date: str, jobs_discovered: int, jobs_new: int):
        """Update stats table"""

    async def close(self):
        """Clean shutdown"""
```

Checklist:

- \[ \] Implement DatabaseManager class
- \[ \] Handle SQLite/PostgreSQL differences (if supporting both)
- \[ \] Add proper error handling
- \[ \] Test CRUD operations

---

### Task 3: Data Models

#### 3.1 Job Posting Model

File: src/models/job_posting.py

```python
from pydantic import BaseModel, Field, validator
from typing import Optional, Literal
from datetime import datetime
import hashlib
import json

class JobPosting(BaseModel):
    """Standardized job posting model"""

    # Source
    source: str
    source_url: str

    # Company
    company: str
    company_url: Optional[str] = None

    # Job details
    title: str
    location: Optional[str] = None
    is_remote: Optional[bool] = None
    job_type: Optional[Literal['Full-time', 'Part-time', 'Contract', 'Internship']] = None

    # Compensation
    salary_min: Optional[int] = None  # In cents
    salary_max: Optional[int] = None
    salary_currency: str = 'USD'
    salary_source: Optional[Literal['direct', 'parsed', 'not_listed']] = 'not_listed'

    # Content
    description: str = ""
    requirements: str = ""

    # Dates
    posted_date: Optional[str] = None

    # Raw data
    raw_data: dict = Field(default_factory=dict)

    @property
    def job_hash(self) -> str:
        """Generate unique hash for deduplication"""
        # Hash based on company + title + description snippet
        unique_string = f"{self.company.lower()}|{self.title.lower()}|{self.description[:500]}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    @validator('is_remote', pre=True, always=True)
    def detect_remote(cls, v, values):
        """Auto-detect remote from location if not explicitly set"""
        if v is not None:
            return v

        location = values.get('location', '').lower()
        remote_keywords = ['remote', 'anywhere', 'work from home', 'wfh']
        return any(keyword in location for keyword in remote_keywords)

    def to_db_dict(self) -> dict:
        """Convert to database-compatible dict"""
        return {
            'job_hash': self.job_hash,
            'source': self.source,
            'source_url': self.source_url,
            'company': self.company,
            'company_url': self.company_url,
            'title': self.title,
            'location': self.location,
            'is_remote': self.is_remote,
            'job_type': self.job_type,
            'salary_min': self.salary_min,
            'salary_max': self.salary_max,
            'salary_currency': self.salary_currency,
            'salary_source': self.salary_source,
            'description': self.description,
            'requirements': self.requirements,
            'posted_date': self.posted_date,
            'raw_data': json.dumps(self.raw_data)
        }
```

Checklist:

- \[ \] Create JobPosting model with Pydantic
- \[ \] Implement job_hash property
- \[ \] Add validators for data normalization
- \[ \] Test serialization/deserialization

---

### Task 4: Company Configuration

#### 4.1 Company Targets File

File: config/companies.yaml

```yaml
greenhouse_companies:
  Stripe:
    greenhouse_id: "stripe"
    priority: 1 # 1-10, 1 = highest priority

  Plaid:
    greenhouse_id: "plaid"
    priority: 1

  Cloudflare:
    greenhouse_id: "cloudflare"
    priority: 2

  Databricks:
    greenhouse_id: "databricks"
    priority: 2

  Snowflake:
    greenhouse_id: "snowflake"
    priority: 2

  Datadog:
    greenhouse_id: "datadog"
    priority: 3

  MongoDB:
    greenhouse_id: "mongodb"
    priority: 3

  Confluent:
    greenhouse_id: "confluent"
    priority: 3

  HashiCorp:
    greenhouse_id: "hashicorp"
    priority: 3

  Vercel:
    greenhouse_id: "vercel"
    priority: 3

workday_companies:
  "Goldman Sachs":
    workday_url: "https://gs.wd5.myworkdayjobs.com/en-US/GSCareers"
    priority: 1

  "JPMorgan Chase":
    workday_url: "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001"
    priority: 1

  "Morgan Stanley":
    workday_url: "https://morganstanley.tal.net/vx/lang-en-GB/mobile-0/appcentre-1/brand-2/xf-91c0e92d74a1/candidate/jobboard/vacancy/1/adv/"
    priority: 1

  "Bank of America":
    workday_url: "https://careers.bankofamerica.com/en-us/job-search-results"
    priority: 2

  # Add more as needed...

job_boards:
  Indeed:
    enabled: true
    search_terms:
      - "senior software engineer"
      - "staff software engineer"
    locations:
      - "Remote"
      - "San Francisco, CA"
    priority: 2

  Glassdoor:
    enabled: true
    search_terms:
      - "senior software engineer"
    locations:
      - "Remote"
    priority: 3

  LinkedIn:
    enabled: false # Requires proxies, enable later
    priority: 3
```

Checklist:

- \[ \] Create companies.yaml
- \[ \] Fill in your 50 target companies
- \[ \] Verify Greenhouse IDs (test API: <https://boards-api.greenhouse.io/v1/boards/{id}/jobs>)
- \[ \] Verify Workday URLs
- \[ \] Set priority levels

#### 4.2 Search Criteria Configuration

File: config/search_criteria.yaml

```yaml
# Job titles to search for
target_titles:
  - "Software Engineer"
  - "Senior Software Engineer"
  - "Staff Software Engineer"
  - "Backend Engineer"
  - "Full Stack Engineer"
  - "Machine Learning Engineer"

# Titles to exclude (regex matching)
exclude_title_patterns:
  - "(?i)intern"
  - "(?i)junior"
  - "(?i)manager" # Unless you want management roles
  - "(?i)director"
  - "(?i)vp|vice president"

# Location preferences
locations:
  remote_preference: "remote_only" # or "hybrid_ok", "any"
  acceptable_cities:
    - "San Francisco"
    - "New York"
    - "Austin"
    - "Seattle"
    - "Remote"

# Salary (for filtering in Phase 2)
salary:
  min: 150000
  max: 300000
  currency: "USD"

# Experience level
experience:
  min_years: 3
  max_years: 10
```

Checklist:

- \[ \] Create search_criteria.yaml
- \[ \] Define your target titles
- \[ \] Set exclusion patterns
- \[ \] Configure location preferences

---

### Task 5: Fetcher Implementations

#### 5.1 Base Fetcher (Abstract Class)

File: src/fetchers/base_fetcher.py

What it defines:

```python
from abc import ABC, abstractmethod
from typing import List
from src.models.job_posting import JobPosting

class BaseFetcher(ABC):
    """Abstract base class for all job fetchers"""

    def __init__(self, config: dict):
        self.config = config
        self.source_name = self.get_source_name()

    @abstractmethod
    async def fetch_jobs(self) -> List[JobPosting]:
        """Fetch jobs from source and return standardized JobPosting objects"""
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """Return identifier for this source (e.g., 'greenhouse_stripe')"""
        pass

    async def __aenter__(self):
        """Support async context manager"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup on context exit"""
        pass
```

Checklist:

- \[ \] Create BaseFetcher abstract class
- \[ \] Define required methods
- \[ \] Add type hints
- \[ \] Support async context manager

#### 5.2 Greenhouse Fetcher

File: src/fetchers/greenhouse_fetcher.py

What it needs to do:

- \[ \] Accept company name + greenhouse_id
- \[ \] Make GET request to <https://boards-api.greenhouse.io/v1/boards/{greenhouse_id}/jobs>
- \[ \] Parse JSON response
- \[ \] Convert each job to JobPosting model
- \[ \] Handle pagination (if Greenhouse API has it - check docs)
- \[ \] Handle rate limiting (429 errors)
- \[ \] Handle network errors gracefully
- \[ \] Return list of JobPosting objects

API Response Structure (for reference):

```json
{
  "jobs": [
    {
      "id": 123456,
      "title": "Senior Software Engineer",
      "updated_at": "2025-01-20T10:30:00Z",
      "absolute_url": "https://jobs.lever.co/company/job-id",
      "location": {
        "name": "San Francisco, CA"
      },
      "content": "<p>Job description HTML...</p>",
      "departments": [{ "name": "Engineering" }]
    }
  ]
}
```

Key implementation points:

```python
class GreenhouseFetcher(BaseFetcher):
    def __init__(self, company_name: str, greenhouse_id: str):
        self.company_name = company_name
        self.greenhouse_id = greenhouse_id
        super().__init__(config={'company': company_name, 'id': greenhouse_id})

    def get_source_name(self) -> str:
        return f"greenhouse_{self.company_name.lower().replace(' ', '_')}"

    async def fetch_jobs(self) -> List[JobPosting]:
        # Implementation here
        pass
```

Checklist:

- \[ \] Implement GreenhouseFetcher
- \[ \] Test with 3-5 companies
- \[ \] Handle HTML in description (strip or keep?)
- \[ \] Parse location for remote detection
- \[ \] Extract salary from description if present (regex)
- \[ \] Log errors without crashing

#### 5.3 Apify Fetcher (Workday)

File: src/fetchers/apify_fetcher.py

What it needs to do:

- \[ \] Initialize Apify client with API token
- \[ \] Call Workday actor: gooyer.co/myworkdayjobs
- \[ \] Pass company Workday URL as input
- \[ \] Wait for actor to complete
- \[ \] Fetch results from dataset
- \[ \] Convert to JobPosting objects
- \[ \] Handle errors (actor failures, timeouts)

Implementation notes:

```python
from apify_client import ApifyClient

class ApifyFetcher(BaseFetcher):
    def __init__(self, company_name: str, workday_url: str):
        self.company_name = company_name
        self.workday_url = workday_url
        self.client = ApifyClient(os.getenv('APIFY_API_TOKEN'))
        super().__init__(config={'company': company_name, 'url': workday_url})

    async def fetch_jobs(self) -> List[JobPosting]:
        # Run actor
        run = self.client.actor("gooyer.co/myworkdayjobs").call(
            run_input={
                "startUrls": [self.workday_url],
                "maxItems": 100  # Adjust based on needs
            }
        )

        # Fetch results
        dataset_items = self.client.dataset(run["defaultDatasetId"]).list_items().items

        # Convert to JobPosting
        # ...
```

Checklist:

- \[ \] Implement ApifyFetcher
- \[ \] Test with 1-2 Workday companies
- \[ \] Handle Apify credit limits
- \[ \] Parse Apify's response format
- \[ \] Handle actor timeouts
- \[ \] Consider cost per run (log this)

#### 5.4 JobSpy Fetcher

File: src/fetchers/jobspy_fetcher.py

What it needs to do:

- \[ \] Use JobSpy library to scrape Indeed, Glassdoor
- \[ \] Accept search parameters (search_term, location, results_wanted)
- \[ \] Call scrape_jobs() for each configured job board
- \[ \] Convert JobSpy's JobPost objects to our JobPosting model
- \[ \] Handle rate limiting (especially LinkedIn)
- \[ \] Retry logic for failed scrapes

Implementation notes:

```python
from jobspy import scrape_jobs

class JobSpyFetcher(BaseFetcher):
    def __init__(self, site_name: str, search_term: str, location: str):
        self.site_name = site_name  # 'indeed', 'glassdoor', 'linkedin'
        self.search_term = search_term
        self.location = location
        super().__init__(config={'site': site_name, 'term': search_term})

    async def fetch_jobs(self) -> List[JobPosting]:
        # JobSpy is synchronous, run in executor
        import asyncio
        loop = asyncio.get_event_loop()

        jobs_df = await loop.run_in_executor(
            None,
            scrape_jobs,
            [self.site_name],  # site_name as list
            self.search_term,
            self.location,
            50,  # results_wanted
            'USA'  # country_indeed
        )

        # Convert DataFrame to JobPosting objects
        # jobs_df has columns: title, company, location, description, etc.
        # ...
```

Checklist:

- \[ \] Implement JobSpyFetcher
- \[ \] Test with Indeed (most reliable)
- \[ \] Test with Glassdoor
- \[ \] Skip LinkedIn for MVP (requires proxies)
- \[ \] Handle pandas DataFrame → JobPosting conversion
- \[ \] Log scrape statistics

---

### Task 6: Deduplication System

File: src/utils/deduplicator.py

What it needs to do:

- \[ \] Generate consistent hashes for jobs
- \[ \] Compare new jobs against database
- \[ \] Return list of truly new jobs
- \[ \] Update existing jobs if needed (e.g., new posting date)

Implementation approach:

```python
class Deduplicator:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def filter_new_jobs(self, jobs: List[JobPosting]) -> List[JobPosting]:
        """Return only jobs not already in database"""
        new_jobs = []

        for job in jobs:
            existing = await self.db.get_job_by_hash(job.job_hash)

            if existing is None:
                new_jobs.append(job)
            else:
                # Job exists - optionally update timestamp
                # await self.db.update_job_timestamp(job.job_hash)
                pass

        return new_jobs
```

Checklist:

- \[ \] Implement Deduplicator class
- \[ \] Test hash consistency (same job = same hash)
- \[ \] Test hash uniqueness (different jobs = different hashes)
- \[ \] Decide: update existing jobs or ignore completely?
- \[ \] Log duplicate statistics

---

### Task 7: Logging System

File: src/utils/logger.py

What it needs to do:

- \[ \] Configure loguru logger
- \[ \] Log to both file and console
- \[ \] Different log levels (DEBUG, INFO, WARNING, ERROR)
- \[ \] Structured logging for stats
- \[ \] Rotation policy (e.g., 10 MB per file, keep 5 files)

Implementation:

```python
from loguru import logger
import sys

def setup_logger(log_file: str = "logs/job_monitor.log", level: str = "INFO"):
    """Configure application logger"""

    # Remove default logger
    logger.remove()

    # Console logger (colored)
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=level
    )

    # File logger (with rotation)
    logger.add(
        log_file,
        rotation="10 MB",
        retention="5 files",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=level
    )

    return logger
```

Checklist:

- \[ \] Implement logger setup
- \[ \] Test file rotation
- \[ \] Add structured logging for:
  - Crawl start/end
  - Jobs discovered/new/duplicate
  - Errors with stack traces
- \[ \] Log timing metrics

---

### Task 8: Main Orchestrator

File: src/main.py

What it orchestrates:

1. Load configuration (companies, search criteria)
2. Initialize database
3. For each source:
   - Create appropriate fetcher
   - Fetch jobs
   - Normalize to JobPosting
   - Deduplicate
   - Store new jobs
   - Log statistics
4. Update daily stats
5. Handle errors gracefully (don't crash entire run if one source fails)

High-level flow:

```python
async def run_job_discovery():
    """Main orchestration function"""

    logger.info("Starting job discovery cycle")

    # Initialize
    db = DatabaseManager(os.getenv('DATABASE_PATH'))
    await db.connect()
    await db.create_tables()

    deduplicator = Deduplicator(db)

    total_discovered = 0
    total_new = 0

    # Load configs
    companies = load_yaml('config/companies.yaml')

    # Fetch from Greenhouse
    for company, config in companies['greenhouse_companies'].items():
        crawl_id = await db.start_crawl('greenhouse', company)
        try:
            async with GreenhouseFetcher(company, config['greenhouse_id']) as fetcher:
                jobs = await fetcher.fetch_jobs()
                new_jobs = await deduplicator.filter_new_jobs(jobs)

                for job in new_jobs:
                    await db.insert_job(job.to_db_dict())

                total_discovered += len(jobs)
                total_new += len(new_jobs)

                await db.complete_crawl(crawl_id, len(jobs), len(new_jobs))
                logger.info(f"{company}: {len(new_jobs)}/{len(jobs)} new jobs")

        except Exception as e:
            logger.error(f"Error fetching {company}: {e}")
            await db.complete_crawl(crawl_id, 0, 0, str(e))

    # Fetch from Apify (Workday)
    # ...

    # Fetch from JobSpy
    # ...

    # Update stats
    await db.update_daily_stats(
        date=datetime.now().strftime('%Y-%m-%d'),
        jobs_discovered=total_discovered,
        jobs_new=total_new
    )

    logger.info(f"Cycle complete: {total_new} new jobs discovered")

    await db.close()
```

Checklist:

- \[ \] Implement run_job_discovery() function
- \[ \] Load all configs at start
- \[ \] Iterate through all sources
- \[ \] Handle errors per-source (don't crash entire run)
- \[ \] Log comprehensive statistics
- \[ \] Ensure proper cleanup (close DB, etc.)
- \[ \] Make it async throughout

---

### Task 9: Scheduler Setup

#### Option A: systemd Timer (Linux - Recommended)

File: /etc/systemd/system/job-discovery.service

```ini
[Unit]
Description=Job Discovery Service
After=network.target

[Service]
Type=oneshot
User=your-username
WorkingDirectory=/path/to/job-discovery
Environment="PATH=/path/to/job-discovery/.venv/bin"
ExecStart=/path/to/job-discovery/.venv/bin/uv run python src/main.py

[Install]
WantedBy=multi-user.target
```

File: /etc/systemd/system/job-discovery.timer

```ini
[Unit]
Description=Run Job Discovery Every 30 Minutes
Requires=job-discovery.service

[Timer]
OnCalendar=*:0/30
Persistent=true

[Install]
WantedBy=timers.target
```

Commands:

```bash
sudo systemctl daemon-reload
sudo systemctl enable job-discovery.timer
sudo systemctl start job-discovery.timer
sudo systemctl status job-discovery.timer
```

Checklist:

- \[ \] Create service file
- \[ \] Create timer file
- \[ \] Update paths to match your setup
- \[ \] Enable and start timer
- \[ \] Test with sudo systemctl start job-discovery.service
- \[ \] Check logs with journalctl -u job-discovery.service

#### Option B: Cron (macOS/Linux)

Crontab entry:

```bash
# Run every 30 minutes
*/30 * * * * cd /path/to/job-discovery && /path/to/.venv/bin/uv run python src/main.py >> logs/cron.log 2>&1
```

Commands:

```bash
crontab -e  # Edit crontab
crontab -l  # List cron jobs
```

Checklist:

- \[ \] Edit crontab
- \[ \] Add entry
- \[ \] Verify with crontab -l
- \[ \] Test by setting to run every minute temporarily
- \[ \] Check logs/cron.log

#### Option C: APScheduler (Python - Cross-platform)

File: src/scheduler.py

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.main import run_job_discovery
import asyncio

async def main():
    scheduler = AsyncIOScheduler()

    # Run every 30 minutes
    scheduler.add_job(
        run_job_discovery,
        'interval',
        minutes=30,
        id='job_discovery',
        replace_existing=True
    )

    scheduler.start()

    # Keep running
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
```

Run as background service:

```bash
nohup uv run python src/scheduler.py &
```

Checklist:

- \[ \] Create scheduler.py
- \[ \] Test scheduler
- \[ \] Set up process manager (supervisord, PM2, or systemd)
- \[ \] Ensure it restarts on crash

---

### Task 10: Testing

#### 10.1 Unit Tests

File: tests/test_fetchers.py

```python
import pytest
from src.fetchers.greenhouse_fetcher import GreenhouseFetcher

@pytest.mark.asyncio
async def test_greenhouse_fetcher():
    """Test Greenhouse API fetching"""
    fetcher = GreenhouseFetcher("Stripe", "stripe")
    jobs = await fetcher.fetch_jobs()

    assert len(jobs) > 0
    assert all(job.company == "Stripe" for job in jobs)
    assert all(job.source.startswith("greenhouse") for job in jobs)
```

Checklist:

- \[ \] Write tests for each fetcher
- \[ \] Test deduplication logic
- \[ \] Test database operations
- \[ \] Test job hash generation
- \[ \] Run with: uv run pytest tests/

#### 10.2 Integration Test

File: tests/test_integration.py

```python
@pytest.mark.asyncio
async def test_full_pipeline():
    """Test complete discovery pipeline"""
    # Run discovery
    await run_job_discovery()

    # Check database
    db = DatabaseManager('data/test_jobs.db')
    await db.connect()

    jobs = await db.get_jobs_by_status('NEW')
    assert len(jobs) > 0

    await db.close()
```

Checklist:

- \[ \] Test full pipeline end-to-end
- \[ \] Verify database entries
- \[ \] Check log files
- \[ \] Validate job data quality

#### 10.3 Manual Testing Checklist

- \[ \] Run discovery once manually: uv run python src/main.py
- \[ \] Check logs/job_monitor.log
- \[ \] Query database: sqlite3 data/jobs.db "SELECT COUNT(\*) FROM job_postings;"
- \[ \] Verify jobs from at least 3 different sources
- \[ \] Check for duplicates: SELECT job_hash, COUNT(\*) FROM job_postings GROUP BY job_hash HAVING COUNT(\*) > 1;
- \[ \] Test error handling (temporarily break API key, bad URL, etc.)

---

### Task 11: Monitoring & Maintenance

#### 11.1 Create Status Dashboard (Optional but Recommended)

Simple script to check system health:

File: scripts/status.py

```python
import sqlite3
from datetime import datetime, timedelta

def print_status():
    db = sqlite3.connect('data/jobs.db')
    cursor = db.cursor()

    # Total jobs
    total = cursor.execute("SELECT COUNT(*) FROM job_postings").fetchone()[0]

    # New jobs today
    today = datetime.now().strftime('%Y-%m-%d')
    new_today = cursor.execute(
        "SELECT COUNT(*) FROM job_postings WHERE DATE(fetched_at) = ?",
        (today,)
    ).fetchone()[0]

    # Jobs by source
    sources = cursor.execute(
        "SELECT source, COUNT(*) FROM job_postings GROUP BY source"
    ).fetchall()

    # Recent crawls
    recent = cursor.execute(
        "SELECT source, status, jobs_found, started_at FROM crawl_history ORDER BY started_at DESC LIMIT 10"
    ).fetchall()

    print(f"=== Job Discovery Status ===")
    print(f"Total jobs in database: {total}")
    print(f"New jobs today: {new_today}")
    print(f"\nJobs by source:")
    for source, count in sources:
        print(f"  {source}: {count}")
    print(f"\nRecent crawls:")
    for source, status, found, started in recent:
        print(f"  {started} | {source} | {status} | {found} jobs")

    db.close()

if __name__ == '__main__':
    print_status()
```

Run: uv run python scripts/status.py

Checklist:

- \[ \] Create status script
- \[ \] Add to daily routine
- \[ \] Set up alerts for failures (email/Slack)

#### 11.2 Backup Strategy

Checklist:

- \[ \] Set up daily DB backups: cp data/jobs.db backups/jobs\_$(date +%Y%m%d).db
- \[ \] Keep backups for 30 days
- \[ \] Test restore process

#### 11.3 Maintenance Tasks

Weekly:

- \[ \] Review error logs
- \[ \] Check if any sources are consistently failing
- \[ \] Verify new companies are being scraped

Monthly:

- \[ \] Update company list if needed
- \[ \] Check Apify credits usage
- \[ \] Review duplicate rate (high rate = hash function issue)
- \[ \] Archive old jobs (optional)

---

## Success Criteria

You'll know Phase 1 is complete when:

- \[ \] System runs automatically every 30 minutes
- \[ \] Database contains jobs from at least 20 companies
- \[ \] Jobs are properly deduplicated (< 5% duplicate rate)
- \[ \] All 3 source types working (Greenhouse, Apify, JobSpy)
- \[ \] Logs show clear success/failure status
- \[ \] No crashes for 48 hours of continuous operation
- \[ \] Can query database and see structured job data
