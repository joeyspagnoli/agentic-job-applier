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

    -- Agent workflow metadata
    agent_processed_at TIMESTAMP,    -- Successful gate processing timestamp
    agent_result TEXT,               -- Serialized GateRunResult payload
    agent_failed_at TIMESTAMP,       -- Failure marker to stop infinite retries
    agent_error TEXT,                -- Last recorded gate-processing error
    agent_retry_count INTEGER NOT NULL DEFAULT 0,  -- Number of retry attempts
    agent_next_retry_at TIMESTAMP,   -- Next scheduled retry timestamp (UTC)
    agent_claim_token TEXT,          -- Worker claim token for atomic queueing
    agent_claimed_at TIMESTAMP,      -- Timestamp when worker claimed this row

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
CREATE INDEX IF NOT EXISTS idx_agent_processed ON job_postings(agent_processed_at);
CREATE INDEX IF NOT EXISTS idx_agent_failed ON job_postings(agent_failed_at);
CREATE INDEX IF NOT EXISTS idx_agent_retry_ready
    ON job_postings(status, agent_failed_at, agent_processed_at, agent_next_retry_at);
CREATE INDEX IF NOT EXISTS idx_agent_claimed_at ON job_postings(agent_claimed_at);

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

-- Resume tailor run tracking
CREATE TABLE IF NOT EXISTS tailor_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING, SUCCESS, FAILED
    artifact_yaml_path TEXT,
    artifact_tex_path TEXT,
    artifact_pdf_path TEXT,
    page_count INTEGER,
    error TEXT,
    next_retry_at TIMESTAMP,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    claim_token TEXT,
    CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED'))
);
CREATE INDEX IF NOT EXISTS idx_tailor_runs_job_hash ON tailor_runs(job_hash);
CREATE INDEX IF NOT EXISTS idx_tailor_runs_status ON tailor_runs(status);
CREATE INDEX IF NOT EXISTS idx_tailor_runs_started_at ON tailor_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_tailor_runs_job_status ON tailor_runs(job_hash, status);

-- Resume review run tracking
CREATE TABLE IF NOT EXISTS review_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_hash TEXT NOT NULL,
    tailor_run_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING, SUCCESS, FAILED
    verdict TEXT,  -- PASS, TAILORED, BASE, FAIL
    selected_yaml_path TEXT,
    selected_tex_path TEXT,
    selected_pdf_path TEXT,
    review_report_json TEXT,
    agent_stdout TEXT,
    agent_stderr TEXT,
    error TEXT,
    next_retry_at TIMESTAMP,
    fallback_base_yaml_path TEXT,
    fallback_base_tex_path TEXT,
    fallback_base_pdf_path TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    claim_token TEXT,
    CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED')),
    CHECK (verdict IS NULL OR verdict IN ('PASS', 'TAILORED', 'BASE', 'FAIL'))
);
CREATE INDEX IF NOT EXISTS idx_review_runs_job_hash ON review_runs(job_hash);
CREATE INDEX IF NOT EXISTS idx_review_runs_status ON review_runs(status);
CREATE INDEX IF NOT EXISTS idx_review_runs_started_at ON review_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_review_runs_tailor_run_id ON review_runs(tailor_run_id);
CREATE INDEX IF NOT EXISTS idx_review_runs_tailor_status
    ON review_runs(tailor_run_id, status);
