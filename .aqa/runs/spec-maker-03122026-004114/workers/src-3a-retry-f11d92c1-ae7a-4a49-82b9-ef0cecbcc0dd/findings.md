# Worker Findings

- Worker: src-3a-retry
- Completed: 2026-03-12T04:44:32.542Z
- Task: Retry src-3 scope A (models/db/utils/config)

## Summary
Reviewed the job model (`src/models/job_posting.py:10-103`), database schema (`src/database/schema.sql:1-89`), deduplication helper (`src/utils/deduplicator.py:1-59`), logging setup (`src/utils/logger.py:1-91`), fetcher package init (`src/fetchers/__init__.py:1-13`), search criteria config (`config/search_criteria.yaml:4-85`), environment template (`.env.example:1-21`), project manifest (`pyproject.toml:1-21`), and repo ignores (`.gitignore:1-22`) to understand the `models/db/utils/config` surface area.

## Findings
- `JobPosting.salary_source` is constrained to `["direct", "parsed", "not_listed"]`, but the database schema comments refer to `'parsed_from_description'`, so values written via `to_db_dict()` will never match the schema comment and could confuse downstream consumers that expect `'parsed_from_description'` in the `salary_source` column (`src/models/job_posting.py:27-101`, `src/database/schema.sql:21-25`).
- The deduplication utility queries `job_hash` for every job and the schema enforces a unique constraint plus an index on `job_hash` (and adds supporting indexes on status/company), so the schema aligns with the deduplication strategy to keep hash lookups performant (`src/utils/deduplicator.py:17-59`, `src/database/schema.sql:3-53`, `src/utils/logger.py:9-91`).
- Search criteria, env template, project metadata, and ignores document the expected configuration surface for fetchers and agents, showing remote preferences, salary/experience bands, required API keys, logging/db paths, and dependency expectations (`config/search_criteria.yaml:4-85`, `.env.example:1-21`, `pyproject.toml:1-21`, `.gitignore:1-22`).

## Evidence
1. `src/models/job_posting.py:27-101` defines `salary_source` allowed values and `to_db_dict()` content, while `src/database/schema.sql:21-25` comments describe `salary_source` values including `'parsed_from_description'`, revealing the schema/model mismatch.
2. `src/utils/deduplicator.py:17-59` repeatedly calls `get_job_by_hash`, and `src/database/schema.sql:3-53` establishes a unique constraint and indexes on `job_hash`, status, company, and source, supporting efficient deduplication checks; `src/utils/logger.py:9-91` complements this flow with structured logging around cycles and crawls.
3. `config/search_criteria.yaml:4-85`, `.env.example:1-21`, `pyproject.toml:1-21`, and `.gitignore:1-22` respectively describe filtering rules, required secrets/resources, dependencies, and ignored artifacts, documenting the configuration ecosystem the models and utilities rely on.

## Recommendations
- Normalize `salary_source` values between the model and schema—either expand the `JobPosting` literal to include `'parsed_from_description'` or map `'parsed'` to `'parsed_from_description'` before persisting—so downstream consumers reading the database see the expected canonical string (`src/models/job_posting.py:27-101`, `src/database/schema.sql:21-25`).
- No action needed for deduplication or logging: the schema’s unique/index constraints on `job_hash` and supporting columns already align with the deduplicator’s async hash lookups, and the logging helpers provide structured summaries to monitor each discovery cycle (`src/utils/deduplicator.py:17-59`, `src/database/schema.sql:3-53`, `src/utils/logger.py:9-91`).
