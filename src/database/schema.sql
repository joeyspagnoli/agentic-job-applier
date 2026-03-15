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
