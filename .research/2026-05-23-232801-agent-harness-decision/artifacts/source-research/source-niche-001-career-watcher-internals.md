# source-niche-001: career_page_watcher.py Internals

**File:** `src/fetchers/career_page_watcher.py`

## Source URL Granularity

`CareerPageWatcher` produces **one `source_url` per individual job link**, NOT one per company. The flow:

1. Fetches the company career landing page (`page_url`) once per polling interval.
2. Extracts all matching job link URLs via CSS selector (default: `a[href*='/jobs/']`) or regex.
3. Diffs against `previous_urls` to find only newly discovered links.
4. Creates one `JobPosting` per new link, with `source_url = absolute_job_link_url`.

So the `source_url` field on a `JobPosting` from this fetcher is an individual job's URL (e.g., `https://company.com/jobs/software-engineer-1234`), not the career landing page.

## Title Extraction

Title is derived heuristically from the URL path: last segment, dashes/underscores → spaces, title-cased. Example: `software-engineer-backend` → `"Software Engineer Backend"`. No job description is fetched — the description field is a generic string: `"New job posting discovered on {company} career page"`.

## Key Fields in Produced JobPosting

| Field | Value |
|-------|-------|
| `source` | `career_page_{company_slug}` |
| `source_url` | Individual job page URL (extracted link) |
| `company_url` | The career page being monitored (`page_url`) |
| `title` | URL-path-derived heuristic |
| `description` | Generic fallback, not scraped |

## Implications for Apply Worker

The `source_url` delivered to the apply worker is a job-specific page, not a listing. However, **the page it points to may or may not have an apply form** — it could be:
- A direct Greenhouse/Lever embed → form present
- A company's custom job detail page that links to an ATS → requires further navigation
- A page that rendered client-side and needs JS → may need Playwright
- An expired/removed listing (404, redirected to listing page) → liveness check fails first
