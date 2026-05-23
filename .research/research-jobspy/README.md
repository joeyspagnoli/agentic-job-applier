# JobSpy Library Research

**Date:** 2026-05-19  
**Mode:** Research  
**Goal:** Understand JobSpy's full API surface and per-site scraper internals to identify optimization opportunities for the agentic-job-applier discovery layer.

## What Was Researched

JobSpy is the multi-site scraping library powering the `src/fetchers/` layer. At research time the project used only **5 of 21 available `scrape_jobs()` parameters**, leaving significant capability untapped.

Six artifacts were produced:

| Artifact | Covers |
|----------|--------|
| `core-api-model.md` | Full `scrape_jobs()` signature, parameter reference, data model, threading model, deduplication |
| `linkedin-scraper.md` | HTTP session setup, header strategy, guest API endpoints, pagination, description fetching |
| `indeed-glassdoor-scrapers.md` | Country mapping, GraphQL queries, HTML parsing, salary extraction |
| `google-ziprecruiter-scrapers.md` | Google search term construction, ZipRecruiter auth flow and pagination |
| `naukri-bdjobs-bayt-scrapers.md` | Regional board scrapers (Naukri, BDJobs, Bayt) — headers, endpoints, field mapping |
| `optimization-and-current-usage.md` | Gap analysis between current usage and available parameters; prioritized recommendations |

## Key Findings

- **`hours_old`** is hardcoded to 72 h for all searches — tuning per-source would reduce stale listings.
- **`distance`** is never passed — adding it would tighten geographic relevance for location-specific searches.
- **`job_type`** is unused — passing `"internship"` would push filtering upstream to the source instead of relying on post-fetch title patterns.
- **`linkedin_fetch_description`** is disabled — enabling it adds a second HTTP round-trip per listing but yields full descriptions for LinkedIn jobs.
- **Proxy support** is available but not wired — rate-limit headroom is currently zero.
- **`easy_apply`** filter is unused — could reduce low-signal listings.

## Status

Research only — no code changes were made. Use `optimization-and-current-usage.md` as the implementation reference when tuning the fetcher layer.
