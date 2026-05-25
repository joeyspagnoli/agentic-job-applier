# source-niche-002: github_repo_fetcher.py Internals

**File:** `src/fetchers/github_repo_fetcher.py`

## What This Fetcher Does

`GitHubRepoFetcher` is designed specifically for the **SimplifyJobs ecosystem** — repos like `SimplifyJobs/Summer2026-Internships` that store job listings in a structured JSON file (`.github/scripts/listings.json` on the `dev` branch). It fetches this JSON from `raw.githubusercontent.com` (not the GitHub API, to avoid rate limits).

## Source URL Assignment

```python
source_url=entry.get("url", ""),
```

The `url` field in SimplifyJobs' `listings.json` is **the apply URL for that job** — typically a direct ATS link (Greenhouse, Lever, Workday, Ashby, etc.) or occasionally a company careers page. It is NOT a GitHub URL.

**Critical finding: this is NOT a "GitHub repo with markdown job listings" scenario.** The fetcher:
1. Reads a machine-readable JSON file from GitHub as a data source.
2. Extracts the `url` field per listing, which is the actual job apply URL.
3. Sets that external URL as `source_url`.

The `source_url` from `GitHubRepoFetcher` is an external ATS URL, not a GitHub page.

## SimplifyJobs Listing Schema Fields Used

| Field | Mapped To |
|-------|-----------|
| `url` | `source_url` (the apply URL) |
| `company_name` | `company` |
| `company_url` | `company_url` |
| `title` | `title` |
| `locations` | `location` |
| `date_posted` | `posted_date` (epoch → ISO 8601) |
| `active` | Filter: skipped if `False` |
| `is_visible` | Filter: skipped if `False` |
| `category` | Optional filter |

## Implications

- Source URLs from this fetcher are ATS-hosted apply forms or company pages — same as any other fetcher.
- They will NOT be raw GitHub markdown URLs.
- The GitHub URL is only used to fetch the JSON data file; it never appears as `source_url`.
- The "GitHub README job list with mailto / no-form links" anti-pattern does NOT apply to this fetcher as currently implemented.

## Residual Risk

If a listing in the JSON has `url: ""` (empty) or a malformed/mailto URL, `source_url` will be empty or invalid. The liveness check should catch this at the pre-flight stage.
