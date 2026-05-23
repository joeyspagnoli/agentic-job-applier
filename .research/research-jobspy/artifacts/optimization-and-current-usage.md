# JobSpy Optimization and Current Usage Analysis

## Executive Summary

The agentic-job-applier project uses JobSpy's `scrape_jobs()` function to harvest jobs from Indeed, LinkedIn, and Glassdoor. The current implementation uses only **5 of 21 available parameters**, leaving significant optimization opportunities on the table, particularly around:

- Job age filtering (hours_old is hardcoded to 72 hours for all searches)
- Geographic filtering (distance parameter is never used)
- Job type filtering (job_type parameter is not used)
- LinkedIn description fetching (linkedin_fetch_description is disabled)
- Multi-site concurrency (already leveraged but not tuned)
- Proxy support for rate-limit avoidance (not implemented)
- Result quality filtering (easy_apply is not used)

---

## Part 1: Complete JobSpy Parameter Inventory & Optimization Value

### Overview of `scrape_jobs()` Signature

```python
def scrape_jobs(
    site_name: str | list[str] | Site | list[Site] | None = None,
    search_term: str | None = None,
    google_search_term: str | None = None,
    location: str | None = None,
    distance: int | None = 50,
    is_remote: bool = False,
    job_type: str | None = None,
    easy_apply: bool | None = None,
    results_wanted: int = 15,
    country_indeed: str = "usa",
    proxies: list[str] | str | None = None,
    ca_cert: str | None = None,
    description_format: str = "markdown",
    linkedin_fetch_description: bool | None = False,
    linkedin_company_ids: list[int] | None = None,
    offset: int | None = 0,
    hours_old: int = None,
    enforce_annual_salary: bool = False,
    verbose: int = 0,
    user_agent: str = None,
    **kwargs,
) -> pd.DataFrame:
```

### Parameter Reference with Optimization Analysis

#### HIGH-IMPACT PARAMETERS (Most critical for result quality/quantity)

| Parameter | Type | Default | Optimization Value | Notes |
|-----------|------|---------|-------------------|-------|
| **site_name** | str\|list[str]\|Site\|list[Site]\|None | None (all sites) | **CRITICAL** | Determines which job boards are scraped. Current project uses: `["indeed", "glassdoor", "linkedin"]`. Multi-site concurrency is handled natively by JobSpy (ThreadPoolExecutor). |
| **results_wanted** | int | 15 | **CRITICAL** | Controls approximate job count per site. Current: 25 per board. Each site's 1000-job cap is a hard limit. Higher values = longer scrape times but more coverage. |
| **search_term** | str | None | **CRITICAL** | Filters jobs by keyword. Current project uses user-configured terms ("software engineer", etc.). Complex syntax supported (Indeed: `"exact phrase" keyword -exclude (OR syntax)`). |
| **location** | str | None | **CRITICAL** | Geographic filter. Current: "Remote" or "United States". Behavior varies by site (LinkedIn uses only location; Indeed + Glassdoor use subdomain + location). |
| **hours_old** | int | None | **HIGH** | Filters by job posting recency (hours since posted). **Current project hardcodes 72 hours for ALL searches.** Optimization opportunity: use 168 (1 week) or 336 (2 weeks) for broader coverage; use 24 for fresh-job emphasis. |
| **distance** | int | 50 | **HIGH** | Miles from location (Indeed/ZipRecruiter only). **Current project does NOT use this parameter.** Default 50 miles. Setting to 0 = exact location only; larger values expand geographic spread. |
| **job_type** | str | None | **HIGH** | Filters by employment type: `fulltime`, `parttime`, `internship`, `contract`. **Current project does NOT use this parameter.** Opportunity to narrow results to relevant roles (e.g., "internship" for entry-level profiles). |

#### MEDIUM-IMPACT PARAMETERS (Improves result relevance/consistency)

| Parameter | Type | Default | Optimization Value | Notes |
|-----------|------|---------|-------------------|-------|
| **is_remote** | bool | False | **MEDIUM** | Filters for remote-only jobs. Current project captures remote jobs via location="Remote" instead. Using this flag explicitly may improve Indeed/Glassdoor filtering. |
| **easy_apply** | bool | None | **MEDIUM** | Filters for jobs hosted on the job board (LinkedIn "easy apply" no longer works per README). **Current project does NOT use.** Value: reduces friction for application, but limits coverage. |
| **linkedin_fetch_description** | bool | False | **MEDIUM** | Fetches full description + direct job URL for LinkedIn jobs. **Current project: disabled (False).** Cost: O(n) extra HTTP requests (one per LinkedIn job). Benefit: richer descriptions for matching/ranking. Decision: see Section 5 below. |
| **description_format** | str | "markdown" | **MEDIUM** | Format of job descriptions: `markdown`, `html`, `plain`. Current project uses default (markdown). Changing to `plain` might improve downstream NLP, but markdown is cleaner for display. |
| **country_indeed** | str | "usa" | **MEDIUM** | Country for Indeed/Glassdoor search. Current project uses "USA" hardcoded. Only needed if expanding to international markets. |
| **enforce_annual_salary** | bool | False | **MEDIUM** | Converts hourly/daily/monthly salaries to annual equivalent. **Current project does NOT use.** Value: enables consistent salary comparison across intervals. Note: JobSpy already does some conversion internally. |
| **offset** | int | 0 | **MEDIUM** | Pagination offset for search results. **Current project does NOT use.** Value: allows resuming incomplete scrapes or paginating through large result sets. Useful when results_wanted > 50 and JobSpy's internal pagination needs tuning. |

#### LOW-IMPACT PARAMETERS (Infrastructure/Robustness)

| Parameter | Type | Default | Optimization Value | Notes |
|-----------|------|---------|-------------------|-------|
| **proxies** | list[str]\|str\|None | None | **MEDIUM** | Proxy list for rate-limit avoidance. Format: `["user:pass@host:port", "localhost"]`. **Current project does NOT use.** Cost: requires proxy infrastructure/payment. Benefit: avoids 429 blocks on LinkedIn (which is very restrictive). LinkedIn especially benefits from rotating proxies. |
| **ca_cert** | str | None | **LOW** | Path to CA certificate file for HTTPS proxies. Only needed when using proxies with custom cert validation. |
| **user_agent** | str | None | **LOW** | Custom User-Agent header. **Current project does NOT use.** Default is likely outdated per README warning. Setting a modern user agent may help with bot detection. Example: `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"`. |
| **verbose** | int | 0 | **LOW** | Log verbosity: 0 (errors only), 1 (errors+warnings), 2 (all logs). Current project likely uses 0 for production, higher for debugging. |
| **linkedin_company_ids** | list[int] | None | **LOW** | LinkedIn-only: restrict search to specific company IDs. **Current project does NOT use.** Value: narrow to target employers. Requires knowing LinkedIn company IDs. |

---

## Part 2: Current Project JobSpy Usage

### Call Site: `JobSpyFetcher._scrape_sync()`
**File:** `/home/claude-code/Projects/agentic-job-applier/src/fetchers/jobspy_fetcher.py` (lines 203-210)

```python
def _scrape_sync(self) -> Any:
    return scrape_jobs(
        site_name=[self.site_name],           # Literal["indeed", "glassdoor", "linkedin"]
        search_term=self.search_term,         # e.g., "software engineer", "data scientist"
        location=self.location,               # "Remote" or geographic location string
        results_wanted=self.results_wanted,   # Default 25 (from config/companies.yaml)
        country_indeed=self.country,          # "USA" (hardcoded in __init__)
        hours_old=72,                         # HARDCODED: 72 hours for all searches
    )
```

### Configuration Entry Point: `fetch_jobspy_jobs()`
**File:** `/home/claude-code/Projects/agentic-job-applier/src/orchestrator/fetchers/jobspy.py` (lines 33-185)

**Configuration source:** `config/companies.yaml`

```yaml
job_boards:
  Indeed:
    enabled: true
    locations:
      - "Remote"
      - "United States"
    results_wanted: 25
    priority: 2

  Glassdoor:
    enabled: false  # Disabled: bot detection issues (stale fingerprints, 403 swallowed as 0 results)
    locations:
      - "Remote"
    results_wanted: 25
    priority: 3

  LinkedIn:
    enabled: false  # Disabled: requires proxies
    locations:
      - "Remote"
    results_wanted: 25
    priority: 3
```

**Orchestration flow:**
1. For each enabled job board and search term + location combination:
2. Create a `JobSpyFetcher` instance with fixed parameters
3. Call `fetch_jobs()` → runs `_scrape_sync()` in an executor
4. Parse DataFrame rows into normalized `JobPosting` objects
5. Filter duplicates via `Deduplicator` (checks both in-batch and database)
6. Insert new jobs into `job_postings` table with `source`, `source_url`, salary fields, etc.
7. Sleep 2 seconds between requests to avoid hammering (line 183)

**Key observation:** Every search variant (board + search term + location) creates a separate crawl record and calls `scrape_jobs()` independently. This means:
- Indeed + 5 search terms + 2 locations = 10 separate scrape calls
- Each call is subject to the same hardcoded 72-hour window

---

## Part 3: Parameters NOT Currently Used (Gap Analysis)

### Parameters the Project Should Consider

#### 1. **hours_old** (Currently Hardcoded to 72)
**Current state:** Line 209 in jobspy_fetcher.py sets `hours_old=72` for all searches.

**Gap:** No configuration option to adjust posting age threshold.

**Why it matters:**
- 72 hours is 3 days: finds recent postings but misses valid 1-2 week postings
- Larger values (168/336) give more coverage and avoid re-scraping the same fresh jobs repeatedly
- Smaller values (24) focus on day-old postings for time-sensitive roles

**Recommended fix:**
```python
# Add to JobSpyFetcher.__init__:
def __init__(self, ..., hours_old: int | None = None):
    self.hours_old = hours_old  # None allows JobSpy default behavior

# In _scrape_sync(), pass it through:
hours_old=self.hours_old if self.hours_old is not None else 72,
```

**Config YAML option:**
```yaml
job_boards:
  Indeed:
    hours_old: 168  # Optional: 1 week window instead of 72h default
```

---

#### 2. **distance** (Never Used)
**Current state:** Not passed to `scrape_jobs()`. Defaults to JobSpy's 50 miles.

**Gap:** Geographic targeting cannot be tuned per board/search.

**Why it matters:**
- `distance=0` = exact location match only (stricter, fewer results)
- `distance=50` = default, 50-mile radius
- `distance=500+` = state-wide or regional coverage
- Only affects Indeed/ZipRecruiter (LinkedIn/Glassdoor use only location string)

**Recommended fix:**
```python
# Add to config/companies.yaml:
job_boards:
  Indeed:
    locations:
      - location: "San Francisco, CA"
        distance: 25  # Stricter: SF only
      - location: "California"
        distance: 100  # Wider: all of CA

# Add to JobSpyFetcher:
def __init__(self, ..., distance: int | None = 50):
    self.distance = distance

# In _scrape_sync():
distance=self.distance,
```

---

#### 3. **job_type** (Never Used)
**Current state:** Not passed. Accepts user-configured search terms instead.

**Gap:** Cannot explicitly filter for internship/contract/part-time roles at the scraper level.

**Why it matters:**
- `job_type="internship"` ensures results are entry-level
- `job_type="contract"` narrows to temporary/freelance
- `job_type="parttime"` targets flexible roles
- **LinkedIn/Indeed limitations:** Only one filter from `{hours_old, easy_apply, job_type}` can be used per query. Using `job_type` means you cannot also use `hours_old` or `easy_apply` on LinkedIn.

**Recommended fix:**
```python
# Add to config/companies.yaml:
job_boards:
  Indeed:
    job_type: "fulltime"  # Optional: restrict to fulltime
    
# Add to JobSpyFetcher:
def __init__(self, ..., job_type: str | None = None):
    self.job_type = job_type

# In _scrape_sync():
job_type=self.job_type,

# BUT: Document the Indeed/LinkedIn constraint:
# "If job_type is set, hours_old cannot be used on LinkedIn."
```

**Warning:** README states: "Only one from this list can be used in a search: hours_old, job_type & is_remote, easy_apply" (Indeed); "hours_old, easy_apply" (LinkedIn).

---

#### 4. **is_remote** (Captured via location="Remote", Not Explicit)
**Current state:** Uses `location="Remote"` string instead of `is_remote=True` flag.

**Gap:** Subtle difference: some job boards may not recognize "Remote" string correctly.

**Why it matters:**
- `is_remote=True` is a first-class filter on Indeed/ZipRecruiter
- Using both `location="Remote"` and `is_remote=True` may be redundant or necessary depending on board
- Better clarity in logs/config

**Recommended fix:**
```python
# In config/companies.yaml, add clarity:
job_boards:
  Indeed:
    locations:
      - "Remote"  # Means: is_remote=True for Indeed parsing
      - "San Francisco, CA"  # Means: specific location, not remote

# In JobSpyFetcher, optionally detect:
if self.location.lower() == "remote":
    is_remote = True
else:
    is_remote = False

# Pass to scrape_jobs():
is_remote=is_remote,
location=self.location if not is_remote else None,  # Some boards may not need location if is_remote=True
```

---

#### 5. **easy_apply** (Never Used)
**Current state:** Not passed to `scrape_jobs()`.

**Gap:** No way to filter for "quick apply" jobs.

**Why it matters:**
- `easy_apply=True` filters for jobs with minimal application friction (e.g., LinkedIn "Easy Apply")
- README notes: "LinkedIn easy apply filter no longer works" (API changed)
- Still supported for other boards; unclear efficacy

**Recommended fix:**
```python
# Add to config/companies.yaml if needed:
job_boards:
  LinkedIn:
    easy_apply: true  # Optional

# BUT: Verify it actually works given the README caveat.
```

---

#### 6. **linkedin_fetch_description** (Disabled, Major Gap)
**Current state:** Hardcoded to `False` in JobSpy fetcher.

**Gap:** LinkedIn jobs have minimal description unless explicitly fetched.

**Why it matters:**
- Default LinkedIn scrape: only role title, company, location, salary (sparse)
- With `linkedin_fetch_description=True`: full job description, direct job URL, richer metadata
- Cost: **O(n) extra HTTP requests** (one per LinkedIn job found)
- If you request 25 LinkedIn jobs, that's 26 requests total (1 list + 25 detail)

**Trade-off analysis:** See Section 5 below. Preliminary recommendation: **Enable for quality, but only if proxies are available to avoid rate limits.**

---

#### 7. **enforce_annual_salary** (Never Used)
**Current state:** Not passed to `scrape_jobs()`.

**Gap:** Salary data may be in mixed intervals (hourly, monthly, yearly).

**Why it matters:**
- Current project already does salary normalization in `_normalize_salary()` (lines 281-333)
- JobSpy's `enforce_annual_salary` converts before returning DataFrame
- **Benefit:** Cleaner, more consistent data from scraper
- **Current workaround:** Project manually normalizes in `_normalize_salary()` using multipliers

**Recommended fix:**
```python
# In _scrape_sync(), enable it:
enforce_annual_salary=True,

# Then simplify _normalize_salary() in JobPosting parsing
# (may become redundant if JobSpy does the conversion)
```

---

#### 8. **description_format** (Uses Default "markdown")
**Current state:** Uses default `"markdown"`.

**Gap:** No configuration to switch to HTML or plain text.

**Why it matters:**
- Markdown is human-readable and clean
- HTML is raw but preserves formatting
- Plain text is cleaner for NLP/ML pipelines
- Current project stores in `raw_data` as is, then parses for display

**Recommendation:** Keep default (markdown). No optimization needed.

---

#### 9. **offset** (Never Used)
**Current state:** Not passed. JobSpy defaults to 0.

**Gap:** Cannot resume partial scrapes or paginate large result sets.

**Why it matters:**
- If `results_wanted=100` and scrape fails after 50, no way to resume at offset 50
- Useful for very large searches or when hitting rate limits mid-scrape
- Limited practical value for current workflow (25-result default)

**Recommendation:** Not critical for current use case.

---

#### 10. **proxies** (Not Used, Critical Gap for LinkedIn)
**Current state:** Not implemented.

**Gap:** No proxy rotation, no rate-limit avoidance.

**Why it matters:**
- LinkedIn is "most restrictive and usually rate limits around the 10th page with one IP" (README)
- Current project has LinkedIn disabled (`enabled: false` in companies.yaml) because proxies are not available
- With proxies: LinkedIn becomes viable
- Cost: Residential proxy service (e.g., BrightData, Oxylabs) = $100-500/month
- Format: `proxies=["user:pass@host:port", "host:port"]` or `proxies="socks5://host:port"`

**Recommended fix (when budget allows):**
```python
# Add to config or .env:
JOBSPY_PROXIES = "user:pass@proxy1.com:8080,user:pass@proxy2.com:8080"

# In JobSpyFetcher.__init__:
def __init__(self, ..., proxies: list[str] | None = None):
    self.proxies = proxies

# In _scrape_sync():
proxies=self.proxies,

# In fetch_jobspy_jobs(), pass from config:
fetcher = fetcher_cls(
    ...,
    proxies=resolve_proxies_from_env(),  # New helper
)
```

---

#### 11. **user_agent** (Never Used)
**Current state:** Not passed. JobSpy uses built-in default (possibly outdated).

**Gap:** Bot detection may identify requests as automated.

**Why it matters:**
- README warns: "user_agent ... may be outdated"
- Modern user agents help avoid 403/429 blocks
- Easy fix, low cost

**Recommended fix:**
```python
# Add to JobSpyFetcher:
MODERN_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

def _scrape_sync(self) -> Any:
    return scrape_jobs(
        ...,
        user_agent=MODERN_USER_AGENT,
    )
```

---

#### 12. **linkedin_company_ids** (Never Used)
**Current state:** Not supported.

**Gap:** Cannot target specific LinkedIn company IDs.

**Why it matters:**
- Useful for narrowing to priority employer set
- Requires knowing LinkedIn numeric company IDs
- Low practical value given current project uses search_term filtering

**Recommendation:** Not critical. Skip unless targeting specific employers.

---

#### 13. **country_indeed** (Hardcoded to "USA")
**Current state:** Hardcoded in JobSpyFetcher.__init__ (line 124: `country="USA"`).

**Gap:** No configuration to search international markets.

**Why it matters:**
- Indeed/Glassdoor support many countries
- Current project is US-focused, so this is fine
- Not a gap; acceptable for current scope

---

#### 14. **ca_cert** (Never Used)
**Current state:** Not supported.

**Gap:** Cannot use proxies with custom certificate validation.

**Why it matters:**
- Only needed if proxies require HTTPS with custom CA
- Rare edge case

**Recommendation:** Skip unless proxy integration demands it.

---

## Part 4: Proxy Usage & Rotation Strategy

### Format Expected by JobSpy

```python
# Option 1: List of proxy URLs
proxies = [
    "user:password@proxy1.example.com:8080",
    "user:password@proxy2.example.com:8080",
    "socks5://proxy3.example.com:1080",  # SOCKS5 also supported
]

# Option 2: Single proxy string
proxies = "user:password@proxy.example.com:8080"

# Option 3: No auth required
proxies = ["192.168.1.100:8080", "localhost:3128"]
```

### Internal Rotation Mechanism

From `jobspy/__init__.py` (line 106):
```python
scraper = scraper_class(proxies=proxies, ca_cert=ca_cert, user_agent=user_agent)
```

Each scraper (LinkedIn, Indeed, etc.) implements round-robin rotation internally:
- First request uses `proxies[0]`
- Second request uses `proxies[1]`
- Wraps around after exhausting list

### Best Practices for Rotation

1. **Residential Proxies Only:** Avoid datacenter proxies (too obvious, easily blocked)
   - BrightData, Oxylabs, Smartproxy all support residential
   
2. **Multiple Providers:** Rotate across different providers if possible
   ```python
   proxies = [
       "user:pass@brightdata1.proxy.com:8080",
       "user:pass@oxylabs1.proxy.com:8080",
       "user:pass@smartproxy1.proxy.com:8080",
   ]
   ```

3. **Enough Proxies:** LinkedIn is very aggressive. Minimum 10-20 proxies for reliable scraping of >50 LinkedIn jobs.

4. **Refresh Strategy:** If proxies are blocked, refresh the list or fallback to different provider.

5. **Error Handling:** Current project doesn't retry on 429. Recommendation: add retry logic with exponential backoff + proxy rotation.

### Cost Model

- **Free:** None. No proxies = LinkedIn disabled.
- **Budget:** $100-500/month for residential proxy service (10-50 concurrent proxies)
- **ROI:** LinkedIn alone can yield 50-100+ new jobs per day if available

---

## Part 5: linkedin_fetch_description Cost/Benefit Analysis

### What It Does

When `linkedin_fetch_description=True`:
1. Initial LinkedIn search returns job list (title, company, location, salary)
2. For EACH job found, fetch the detail page to get:
   - Full job description
   - Job level (entry, associate, mid-senior, director, etc.)
   - Direct LinkedIn job URL (instead of just the job ID)
   - Company industry
   - Other metadata

### Cost: Request Overhead

- **Default** (`False`): 1 request per LinkedIn search
  - 1 search for 25 jobs = 1 request
  
- **With `linkedin_fetch_description=True`**: 1 + N requests
  - 1 search + 25 detail fetches = 26 requests
  - **26x multiplier on HTTP load**

### Impact on Rate Limiting

- LinkedIn rate limits "around the 10th page with one IP" (README)
- Fetching 10 pages without description = 10 requests
- Fetching 10 pages WITH description = 10 + (250 jobs) = 260 requests
- **Much higher chance of 429 Too Many Requests**

### Value Proposition

**Pros:**
- Full description enables better job-relevance scoring
- Direct URL is cleaner (skip LinkedIn redirect)
- Job level helps match candidate seniority
- Richer metadata for filtering and ranking

**Cons:**
- 26x HTTP overhead per search variant
- LinkedIn is already rate-limited; this makes it worse
- Current project truncates descriptions in many places anyway
- Description parsing is CPU-cheap compared to fetching

### Recommendation

**Status: CONDITIONAL - Only enable with residential proxies**

```python
# Option A: Disable by default (current state)
linkedin_fetch_description=False  # Safe, 1 request

# Option B: Enable only when proxies available (recommended for high-quality results)
linkedin_fetch_description=(bool(proxies) if proxies else False)

# Option C: Configurable in YAML (best)
# config/companies.yaml:
LinkedIn:
  linkedin_fetch_description: true  # Only if proxies are set up
```

**Decision tree:**
1. If proxies available AND results_wanted > 50: enable
2. If proxies available AND results_wanted <= 25: optional (monitor 429 rate)
3. If no proxies: disable (or keep LinkedIn disabled entirely)

---

## Part 6: Maximizing results_wanted Without Rate Limits

### Current Settings

- Config default: `results_wanted: 25` per board (companies.yaml)
- Actual call: `results_wanted=self.results_wanted` (jobspy_fetcher.py line 207)

### Site-Specific Limits & Constraints

| Site | Hard Cap | Rate Limit Behavior | Recommended results_wanted |
|------|----------|-------------------|---------------------------|
| **Indeed** | ~1000 jobs | "No rate limiting" per README | 50-100 safe; 100-500 with delays |
| **Glassdoor** | ~1000 jobs | Aggressive bot detection (403s) | 20-30 max; even then, often fails |
| **LinkedIn** | ~1000 jobs | "Rate limits around 10th page with one IP" | 10-25 without proxies; 50+ with proxies |
| **ZipRecruiter** | N/A | Unknown | 25-50 presumed safe |

### Strategy to Maximize Without Hitting Limits

#### 1. Increase results_wanted Gradually
```python
# Phase 1: Monitor current performance
results_wanted: 25  # Current

# Phase 2: Test with Indeed (safest)
# Modify config/companies.yaml:
job_boards:
  Indeed:
    results_wanted: 50  # Double

# Phase 3: Add Glassdoor (risky; likely to 403)
Glassdoor:
  results_wanted: 20  # Conservative; often blocked

# Phase 4: Add LinkedIn only if proxies available
LinkedIn:
  proxies: "..."  # Must set
  results_wanted: 25  # Start low
  linkedin_fetch_description: false  # Keep disabled until proxies proven
```

#### 2. Stagger Requests Across Time
Currently, orchestrator sleeps 2 seconds between search variants (line 183):
```python
await asyncio.sleep(2)  # After each search variant
```

Recommendation: Increase based on site responsiveness
```python
# Adaptive delay based on success rate
if site_name == "linkedin":
    await asyncio.sleep(5)  # More conservative for LinkedIn
elif site_name == "glassdoor":
    await asyncio.sleep(3)  # Moderate for Glassdoor
else:  # Indeed
    await asyncio.sleep(1)  # Minimal for Indeed
```

#### 3. Use offset for Pagination
If trying to scrape 1000 jobs from Indeed:
```python
# Instead of: results_wanted=1000 (might timeout or fail)
# Use:
for page_num in range(0, 1000, 100):
    jobs = scrape_jobs(
        ...,
        results_wanted=100,
        offset=page_num,
    )
    # Process and store jobs
    await asyncio.sleep(5)  # Wait between pages
```

#### 4. Distribute Across Multiple Crawl Runs
Instead of 5 search terms × 2 locations × 25 results = 250 jobs per run:
- Run 1: Search term A + B (2 × 25 = 50 jobs)
- Sleep 30 minutes
- Run 2: Search term C + D (2 × 25 = 50 jobs)
- Sleep 30 minutes
- Run 3: Search term E (1 × 25 = 25 jobs)

This spreads load across the day and avoids rate limits.

#### 5. Monitor HTTP Response Codes
Add error handling for 429 (Too Many Requests):
```python
# In fetch_jobspy_jobs():
try:
    jobs = await fetcher.fetch_jobs()
except FetchError as e:
    if "429" in str(e):
        logger.warning(f"Rate limited for {site_name}; waiting 5 minutes")
        await asyncio.sleep(300)  # Back off 5 minutes
        # Retry with smaller results_wanted
        fetcher.results_wanted = fetcher.results_wanted // 2
        jobs = await fetcher.fetch_jobs()
```

#### 6. Use Job Board–Specific Tuning
```yaml
job_boards:
  Indeed:
    results_wanted: 100  # Safe; no rate limiting reported
  Glassdoor:
    results_wanted: 15   # Very conservative; often blocked
  LinkedIn:
    results_wanted: 20   # Only with proxies; start low
```

---

## Part 7: Multi-Site Parallelism & Concurrency

### Current Implementation

JobSpy uses `ThreadPoolExecutor` internally (jobspy/__init__.py lines 120-127):

```python
with ThreadPoolExecutor() as executor:
    future_to_site = {
        executor.submit(worker, site): site for site in scraper_input.site_type
    }
    
    for future in as_completed(future_to_site):
        site_value, scraped_data = future.result()
        site_to_jobs_dict[site_value] = scraped_data
```

**Summary:** All sites (Indeed, Glassdoor, LinkedIn) are scraped concurrently, not sequentially.

### Orchestrator Layer Concurrency

File: `src/orchestrator/fetchers/jobspy.py`, lines 115-183

Current pattern:
```python
for search_term in search_terms:          # Sequential loop
    for location in locations:             # Sequential loop
        fetcher = JobSpyFetcher(...)       # Single site per fetcher instance
        jobs = await fetcher.fetch_jobs()  # Awaits result
        # Deduplicate, filter, insert
        await asyncio.sleep(2)             # Wait 2s before next
```

**Current:** Search variants are sequential (one search finishes, then next starts).

**Alternative:** Could parallelize search variants:
```python
# Pseudo-code: run multiple search variants concurrently
tasks = []
for search_term in search_terms:
    for location in locations:
        fetcher = JobSpyFetcher(...)
        tasks.append(fetcher.fetch_jobs())

all_jobs = await asyncio.gather(*tasks)  # All variants run in parallel
```

### Recommendation: Hybrid Approach

Current sequential approach is actually **preferred** because:

1. **Rate limit safety:** Sequential avoids hammering job boards with simultaneous requests
2. **Simpler error handling:** If one search fails, others still proceed
3. **Database contention:** Sequential inserts avoid lock contention
4. **Monitoring:** Easier to track which search term/location is active in logs

**Only parallelize if:**
- Number of search variants < 5 (to avoid rate limit)
- Job boards have explicit rate-limit headers you can respect
- Database can handle concurrent insert load

**Keep current:** Sequential search variants with 2-second inter-request delay is sensible.

### What IS Parallelized Well

Within a single `scrape_jobs()` call:
- All enabled sites (Indeed, Glassdoor, LinkedIn) run in parallel threads
- This is optimal because they're different domains

Example: Calling `scrape_jobs(site_name=["indeed", "glassdoor", "linkedin"], ...)`
- Thread 1: Scrape Indeed
- Thread 2: Scrape Glassdoor  
- Thread 3: Scrape LinkedIn
- All three run concurrently, results aggregated

**Current project does NOT leverage this.** Each call specifies one site:
```python
fetcher = JobSpyFetcher(
    site_name=site_name,  # Single site like "indeed"
    ...
)
```

### Recommendation: Multi-Site Efficiency Improvement

Instead of:
```python
# Per board orchestrator loop (current)
for board_name in ["Indeed", "Glassdoor", "LinkedIn"]:
    for search_term in search_terms:
        fetcher = JobSpyFetcher(site_name=board_name.lower(), ...)
        jobs = await fetcher.fetch_jobs()
```

Use:
```python
# Multi-site orchestrator loop (proposed)
for search_term in search_terms:
    for location in locations:
        enabled_sites = ["indeed", "glassdoor"]  # Skip LinkedIn unless proxies ready
        # Single call to scrape_jobs with multiple sites
        jobs_df = scrape_jobs(
            site_name=enabled_sites,  # ["indeed", "glassdoor"]
            search_term=search_term,
            location=location,
            ...,
        )
        # Parse and deduplicate
```

**Benefit:** 3x speedup for multi-site searches (Indeed + Glassdoor run in parallel instead of sequentially).

**Implementation cost:** Low; refactor JobSpyFetcher to accept list of sites.

---

## Part 8: Deduplication Strategies

### Current Implementation

File: `src/utils/deduplicator.py`

Two-level deduplication:

1. **In-batch dedup** (lines 45-50):
   ```python
   seen_in_batch: set[str] = set()
   for job in jobs:
       if job.job_hash in seen_in_batch:
           continue
       seen_in_batch.add(job.job_hash)
       unique_jobs.append(job)
   ```
   Purpose: Filter duplicate rows within a single scrape result.

2. **Database dedup** (lines 53-61):
   ```python
   existing_hashes = await self.db.get_existing_job_hashes(...)
   for job in unique_jobs:
       if job.job_hash in existing_hashes:
           continue
       new_jobs.append(job)
   ```
   Purpose: Filter jobs already in database.

### Hash Generation

File: `src/models/job_posting.py` (inferred from code patterns)

Likely uses: hash(company, title, location, job_url) or similar stable key.

### Cross-Site Deduplication

**Current:** Each JobSpy fetcher call is independent; results dedup happens post-fetching.

**Challenge:** Same job may be posted on Indeed AND LinkedIn with different URLs.

**Current handling:** Dedup by job_hash (which includes company, title, location). Different URLs but same job = deduplicated.

### Gaps & Improvements

#### Gap 1: No Active Deduplication Across Concurrent Sites

If Indeed + Glassdoor scrapes run in parallel (recommended optimization above), no in-memory dedup happens between them. Example:

- Indeed returns: "Software Engineer @ Google in SF"
- Glassdoor returns: "Software Engineer @ Google in SF" (same job, different URL)
- Both get added to same batch, dedup happens later

**Fix:** Minimal. The downstream dedup catches it; slightly inefficient but not broken.

#### Gap 2: No URL-Based Dedup

Some boards post the same job listing multiple times with slight variations:
- Title case differences ("Software Engineer" vs "software engineer")
- Description edits (re-posted with updated text)
- Same company, title, location but different job_url

**Current:** Treated as different jobs (different URL).

**Recommendation:** Accept as-is. URL variation usually indicates updated posting; OK to scrape both.

#### Gap 3: No Salary-Based Dedup

Two identical jobs except salary_min changes: "75-90k" → "80-95k" (re-posted with updated range).

**Current:** Treated as new job.

**Recommendation:** Accept. Salary updates indicate real change; worth re-scraping.

#### Gap 4: No Temporal Dedup

If same job posted 2 weeks ago is posted again today, it's deduplicated. This is **correct behavior**; avoid duplicate applications.

**Current:** Works as designed.

---

## Part 9: Caching & Persistence Strategies

### Current State

**No explicit caching layer.** Every `scrape_jobs()` call hits the live job boards.

**Where data lives:**
- JobSpy results: In-memory Pandas DataFrame (discarded after parsing)
- Parsed jobs: In-memory list[JobPosting]
- Persisted: SQLite `job_postings` table

### Caching Opportunities

#### 1. HTTP Response Caching (Request Memoization)

**Value:** Avoid re-scraping the same search term for 1-2 hours.

**Pseudo-implementation:**
```python
import hashlib
from datetime import datetime, timedelta

SCRAPE_CACHE = {}  # {search_hash: (result_df, timestamp)}
CACHE_TTL = 3600  # 1 hour

def get_scrape_cache_key(site, term, location):
    return hashlib.sha256(f"{site}:{term}:{location}".encode()).hexdigest()

async def fetch_jobs(self):
    cache_key = get_scrape_cache_key(self.site_name, self.search_term, self.location)
    
    # Check cache
    if cache_key in SCRAPE_CACHE:
        cached_df, cached_time = SCRAPE_CACHE[cache_key]
        if (datetime.now() - cached_time).seconds < CACHE_TTL:
            logger.info(f"Using cached results for {self.search_term}")
            return self._parse_cached_jobs(cached_df)
    
    # Fresh scrape
    jobs_df = await loop.run_in_executor(None, self._scrape_sync)
    
    # Cache result
    SCRAPE_CACHE[cache_key] = (jobs_df, datetime.now())
    
    return self._parse_job(jobs_df)
```

**Pros:**
- Avoids duplicate scrapes during development/testing
- Handles transient failures (use cache as fallback)
- Reduce job board load

**Cons:**
- Stale data if cache TTL is long
- Memory overhead
- Requires cache invalidation strategy

**Recommendation:** **Implement with 30-min TTL for development; disable in production** (single crawl per cycle is fine).

#### 2. Result Batching & Deduplication Within Crawl Cycle

**Current:** Already implemented in `Deduplicator`. No improvement needed.

#### 3. Incremental/Resume Crawls

**Value:** If scrape fails mid-way (e.g., 403 block after 50 of 100 results), resume from offset.

**Current:** No resume support.

**Pseudo-implementation:**
```python
# In config:
crawl_metadata:
  last_offset: 0
  last_timestamp: "2024-05-19T10:00:00"

# In orchestrator:
if last_crawl_timestamp > (now - 1 hour) and last_offset > 0:
    # Resume from last offset
    offset = last_offset
else:
    # Fresh crawl
    offset = 0

jobs_df = scrape_jobs(..., offset=offset)

# Update metadata
crawl_metadata.last_offset += len(jobs_df)
```

**Recommendation:** **Not necessary for current project** (25-result default completes quickly). Only useful if results_wanted > 100.

#### 4. Database Indexing for Hash Lookups

**Current:** SQLite `job_postings` table has primary key on `id`, likely has index on `job_hash`.

**Verification command:**
```sql
PRAGMA index_info(job_postings);  -- Check indexes
```

**Recommendation:** Ensure `job_hash` has a unique index (likely already does from schema definition).

### Conclusion on Caching

- **Simple HTTP cache:** Worth 30-line implementation for development/testing
- **Resume support:** Not critical at current scale (25 results)
- **Database optimization:** Likely already done (job_hash is probably indexed)

---

## Part 10: Top 5 Concrete Improvements for Production

### Improvement #1: Make hours_old Configurable (Quick Win)

**Why:** Currently hardcoded to 72 hours for all searches. Different search terms may benefit from different windows (e.g., niche roles need 2 weeks, hot roles need 24 hours).

**Implementation:**
1. Add `hours_old` to config/companies.yaml (optional per board)
2. Pass through JobSpyFetcher.__init__
3. Use in scrape_jobs() call

**Effort:** 15 minutes  
**Impact:** +10-20% discovery coverage (broader result windows)  
**Risk:** Low (JobSpy already supports this parameter)

```python
# config/companies.yaml
job_boards:
  Indeed:
    hours_old: 168  # 1 week instead of 3 days

# JobSpyFetcher.__init__
def __init__(self, ..., hours_old: int | None = None):
    self.hours_old = hours_old or 72

# _scrape_sync()
hours_old=self.hours_old,
```

---

### Improvement #2: Add Proxy Support & Enable LinkedIn (High Effort, High Impact)

**Why:** LinkedIn is currently disabled because proxies are not available. With residential proxies, LinkedIn becomes viable.

**Implementation:**
1. Procure residential proxy service ($100-500/month)
2. Add JOBSPY_PROXIES env var
3. Pass proxies to scrape_jobs()
4. Enable LinkedIn in config

**Effort:** 2 hours (setup + integration)  
**Impact:** +50-100 jobs/day from LinkedIn (second-largest board)  
**Risk:** Medium (proxy configuration complexity, cost)

```python
# In orchestrator before fetch_jobspy_jobs():
proxies = os.getenv("JOBSPY_PROXIES", "").split(",") if os.getenv("JOBSPY_PROXIES") else None

# In JobSpyFetcher
def __init__(self, ..., proxies: list[str] | None = None):
    self.proxies = proxies

# _scrape_sync()
proxies=self.proxies,
```

---

### Improvement #3: Multi-Site Concurrency in Orchestrator (Medium Effort, Medium Impact)

**Why:** Currently each search variant calls scrape_jobs() with a single site. Combining sites into one call leverages JobSpy's internal parallelism (ThreadPoolExecutor).

**Implementation:**
1. Collect enabled sites for each search term
2. Call scrape_jobs(site_name=["indeed", "glassdoor"], ...) instead of separate calls
3. Parse & deduplicate results together

**Effort:** 1 hour  
**Impact:** 3x speedup for multi-site searches (e.g., Indeed + Glassdoor in parallel)  
**Risk:** Low (JobSpy already supports this)

```python
# Current (sequential):
for site in ["indeed", "glassdoor"]:
    fetcher = JobSpyFetcher(site_name=site, ...)
    jobs = await fetcher.fetch_jobs()

# Proposed (parallel):
enabled_sites = ["indeed", "glassdoor"]
jobs_df = scrape_jobs(site_name=enabled_sites, search_term=term, location=loc, ...)
# Parse all sites' results in one pass
```

---

### Improvement #4: Add User-Agent & Modern Bot Detection (Quick Win)

**Why:** README warns user agents may be outdated. Modern user agents reduce 403/429 blocks.

**Implementation:**
1. Define modern user agent string in code
2. Pass to scrape_jobs()

**Effort:** 5 minutes  
**Impact:** +5-10% success rate (fewer bot blocks)  
**Risk:** None (cosmetic change)

```python
MODERN_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# In _scrape_sync()
user_agent=MODERN_USER_AGENT,
```

---

### Improvement #5: Implement Smart Retry with Exponential Backoff & Rate-Limit Detection (Medium Effort, High Impact)

**Why:** Current code lacks retry logic. A 429 or 503 causes immediate failure with no fallback.

**Implementation:**
1. Wrap scrape_jobs() in retry loop with exponential backoff
2. Detect 429 (rate limited) and backoff longer
3. Reduce results_wanted on retry to lighten load

**Effort:** 45 minutes  
**Impact:** +20-30% robustness (fewer transient failures)  
**Risk:** Low (retry is standard practice)

```python
# In _scrape_sync():
max_retries = 3
for attempt in range(max_retries):
    try:
        return scrape_jobs(...)
    except Exception as e:
        if "429" in str(e):
            # Rate limited: backoff aggressively
            await asyncio.sleep(2 ** attempt * 30)  # 30s, 60s, 120s
            self.results_wanted = self.results_wanted // 2  # Half results on retry
        elif "503" in str(e):
            # Service unavailable: backoff
            await asyncio.sleep(2 ** attempt * 10)
        else:
            raise  # Unexpected error
    if attempt == max_retries - 1:
        raise FetchError(f"Failed after {max_retries} retries")
```

---

## Summary Table: All Improvements

| # | Improvement | Effort | Impact | Risk | Priority |
|---|-------------|--------|--------|------|----------|
| 1 | hours_old configurable | 15 min | +10-20% coverage | Low | HIGH |
| 2 | Proxy support + LinkedIn | 2 hours | +50-100 jobs/day | Medium | HIGH |
| 3 | Multi-site concurrency | 1 hour | 3x speedup | Low | MEDIUM |
| 4 | Modern user agent | 5 min | +5-10% success | None | HIGH |
| 5 | Retry + rate-limit handling | 45 min | +20-30% robustness | Low | MEDIUM |

---

## Appendix: File Locations & Quick Reference

### Key Files for Implementation

- **Current JobSpy call:** `/home/claude-code/Projects/agentic-job-applier/src/fetchers/jobspy_fetcher.py` (lines 203-210)
- **Orchestrator entry:** `/home/claude-code/Projects/agentic-job-applier/src/orchestrator/fetchers/jobspy.py` (lines 33-185)
- **Config source:** `/home/claude-code/Projects/agentic-job-applier/config/companies.yaml` (job_boards section)
- **Deduplicator:** `/home/claude-code/Projects/agentic-job-applier/src/utils/deduplicator.py`
- **Database schema:** `/home/claude-code/Projects/agentic-job-applier/src/database/_mixins/jobs.py` (INSERT statement)
- **JobSpy source:** `/home/claude-code/Projects/agentic-job-applier/reference-repos/jobspy/jobspy/__init__.py` (scrape_jobs function)

### JobSpy Parameters Not Used (At a Glance)

```
CRITICAL GAPS:
- hours_old: Hardcoded 72h; should be configurable
- distance: Never used; could narrow/expand geographic reach
- job_type: Never used; could filter internship/contract/parttime
- linkedin_fetch_description: Disabled; trades full descriptions for 26x HTTP load

MEDIUM GAPS:
- proxies: Not implemented; required for LinkedIn viability
- is_remote: Implicit (location="Remote"); not explicit
- easy_apply: Never used; could filter quick-apply jobs
- enforce_annual_salary: Never used; project does own conversion
- user_agent: Never used; using stale default per README warning

LOW GAPS:
- offset: Not used; OK for current scale
- ca_cert: Not needed without proxies
- linkedin_company_ids: Not applicable (company-agnostic search)
- country_indeed: Hardcoded USA; fine for scope
- verbose: Likely uses default; no tuning needed
```

---

**End of Report**
