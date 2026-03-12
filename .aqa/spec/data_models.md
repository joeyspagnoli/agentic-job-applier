# Data Models

## JobPosting (Pydantic)
- Fields: source, source_url, company/company_url, title, location, is_remote, job_type (Full-time|Part-time|Contract|Internship), salary_min/max (cents), salary_currency, salary_source, description, requirements, posted_date, raw_data [src/models/job_posting.py:10-41](src/models/job_posting.py:10-41).
- Behaviors: job_hash (company+title+description slice MD5) for dedup; remote auto-detect from location; job_type normalization; `to_db_dict()` for DB insertion; extra fields ignored [src/models/job_posting.py:43-103](src/models/job_posting.py:43-103).

## Database Schema (SQLite)
- **job_postings**: id PK, job_hash UNIQUE, source/source_url, company/company_url, title, location, is_remote, job_type, salary_min/max/currency/source, description, requirements, posted_date, posted_date_parsed, status (NEW|FILTERED|QUALIFIED|APPLIED|REJECTED), raw_data JSON, updated_at [src/database/schema.sql:1-46](src/database/schema.sql:1-46).
- **Indexes**: job_hash, status, company, fetched_at, source [src/database/schema.sql:48-53](src/database/schema.sql:48-53).
- **crawl_history**: source, company, started_at/completed_at, status (IN_PROGRESS|SUCCESS|FAILED), jobs_found, jobs_new, error_message + indexes [src/database/schema.sql:55-71](src/database/schema.sql:55-71).
- **daily_stats**: date PK, totals for discovered/new/duplicate, sources_crawled/failed [src/database/schema.sql:73-81](src/database/schema.sql:73-81).
- **Agent fields**: agent_processed_at, agent_result, agent_failed_at, agent_error added via runtime migration [src/database/db_manager.py:251-305](src/database/db_manager.py:251-305).

## Candidate Profile (Agent Input)
- Loaded from `CANDIDATE_PROFILE_PATH` (YAML/JSON/text), parsed into dict; fallback placeholder if missing [scripts/process_new_jobs.py:41-74](scripts/process_new_jobs.py:41-74).
- Combined with job payload (core fields) to form ADK runner input JSON in `_build_prompt` [scripts/process_new_jobs.py:77-94](scripts/process_new_jobs.py:77-94).

## Agent Output
- **RootApplyDeciderOutput**: decision (APPLY|SKIP), confidence [0,1], reasons[], matched_skills[], missing_skills[] [src/agents/root_apply_decider.py:24-43](src/agents/root_apply_decider.py:24-43).
- Persisted via `record_agent_decision` into job_postings agent_result/status fields [src/database/db_manager.py:251-280](src/database/db_manager.py:251-280).
