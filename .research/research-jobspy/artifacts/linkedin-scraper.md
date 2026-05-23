# JobSpy LinkedIn Scraper - Technical Report

## Overview
The LinkedIn scraper is implemented as a class-based web scraper that extracts job postings from LinkedIn's guest job search API. It uses HTTP requests to fetch job listings and individual job details via HTML parsing.

---

## 1. HTTP Request Structure & Headers

### Session Configuration
**File: `__init__.py` lines 60-68**

- Session is created via `create_session()` utility with:
  - `proxies`: User-provided or None
  - `ca_cert`: Optional custom CA certificate
  - `is_tls=False`: Disables TLS certificate verification
  - `has_retry=True`: Enables automatic request retry logic
  - `delay=5`: Baseline delay between requests
  - `clear_cookies=True`: Clears cookies before each scrape session (prevents LinkedIn from tracking sessions)

### HTTP Headers
**File: `constant.py` lines 1-8**

The scraper uses a static header dictionary applied to all requests:

```
{
    "authority": "www.linkedin.com",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "max-age=0",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
```

These headers are designed to appear as a real Chrome browser on macOS 10.15.7.

### Authentication & Cookies
- **No explicit authentication**: The scraper uses LinkedIn's guest job search API, which requires no API key or login.
- **Cookie handling**: Cleared at session initialization via `clear_cookies=True` to avoid session/tracking cookies.
- **Session object**: Headers are applied via `self.session.headers.update(headers)` at line 68.

---

## 2. LinkedIn API Endpoints & Query Parameters

### Primary Search Endpoint
**File: `__init__.py` lines 119-123**

```
GET {base_url}/jobs-guest/jobs/api/seeMoreJobPostings/search?
```

Base URL: `https://www.linkedin.com` (class variable, line 48)

### Query Parameters
**File: `__init__.py` lines 95-117**

All parameters are constructed as a dict, with `None` values filtered out (line 117):

| Parameter | Source | Type | Values | Purpose |
|-----------|--------|------|--------|---------|
| `keywords` | `scraper_input.search_term` | string | User-provided | Job title/keyword search |
| `location` | `scraper_input.location` | string | User-provided | Geographic location filter |
| `distance` | `scraper_input.distance` | int | User-provided | Radius in miles from location |
| `f_WT` | `scraper_input.is_remote` | string | `"2"` if remote else None | Work type: 2 = Remote |
| `f_JT` | `scraper_input.job_type` | string | `"F"`, `"P"`, `"I"`, `"C"`, `"T"` | Job type code (see section 8) |
| `pageNum` | Hardcoded | int | `0` | Always 0 (pagination via `start` parameter) |
| `start` | Pagination loop | int | `0, 25, 50, 75, ...` | Result offset (25 jobs per page) |
| `f_AL` | `scraper_input.easy_apply` | string | `"true"` if True else None | Easy Apply filter |
| `f_C` | `scraper_input.linkedin_company_ids` | string | Comma-separated IDs | Filter by specific company LinkedIn IDs |
| `f_TPR` | `scraper_input.hours_old` | string | `"r{seconds_old}"` | Time posted filter (see section 7) |

**Examples:**
- Remote filter: `f_WT=2`
- Full-time filter: `f_JT=F`
- Easy Apply: `f_AL=true`
- Posted in last 24 hours: `f_TPR=r86400`
- Company filter: `f_C=1234,5678,9012`

### Timeout
- Request timeout: **10 seconds** (line 122)
- Applies to search API calls only

---

## 3. Pagination Logic

### Offset Calculation
**File: `__init__.py` lines 82, 88, 106, 168**

- Initial offset: `start = (scraper_input.offset // 10) * 10 if scraper_input.offset else 0`
  - Rounds down to nearest 10 (LinkedIn uses 10-result increments internally)
  - Line 82

- Pagination loop condition: `len(job_list) < scraper_input.results_wanted and start < 1000`
  - Line 88-89

- **Hard limit: 1000 results maximum** (indicated by `start < 1000` check)
  - This is a LinkedIn API limitation

- Per-page results: **25 jobs per page** (class variable `jobs_per_page`, line 51)
  - Although `start` increments by the actual number of results returned (line 168)

### How `results_wanted` is Honored
**File: `__init__.py` lines 90, 161, 170**

1. Loop continues while `len(job_list) < scraper_input.results_wanted` (line 88)
2. Within the loop, jobs are added incrementally (line 160)
3. Early exit check: `if not continue_search(): break` (line 161-162)
4. Final truncation: `job_list = job_list[: scraper_input.results_wanted]` (line 170)
   - This ensures exactly `results_wanted` jobs are returned, not more

### Pagination Iteration Variables
- `start` variable increments by actual job card count returned: `start += len(job_cards)` (line 168)
- Allows handling pagination where fewer than 25 results are returned
- `request_count` tracks API calls made (line 91, 93)

---

## 4. Rate Limiting & Anti-Bot Handling

### Delay Logic
**File: `__init__.py` lines 49-50, 167**

- `delay = 3`: Base delay in seconds
- `band_delay = 4`: Random band, added to base delay
- Between pagination requests: `time.sleep(random.uniform(self.delay, self.delay + self.band_delay))`
  - This generates a random sleep between 3 and 7 seconds
  - Line 167

### When Delays Are Applied
- **After each successful page fetch** (inside pagination loop, line 167)
- Only if continuing to next page: `if continue_search():` (line 166)
- No delay on final iteration

### Retry Logic
- Managed by session configuration: `has_retry=True` (line 64)
- Retries are configured in `create_session()` utility function (not defined in these files)
- Likely uses exponential backoff

### HTTP Status Handling
**File: `__init__.py` lines 124-133**

```python
if response.status_code not in range(200, 400):
    if response.status_code == 429:
        err = "429 Response - Blocked by LinkedIn for too many requests"
    else:
        err = f"LinkedIn response status code {response.status_code}"
        err += f" - {response.text}"
    log.error(err)
    return JobResponse(jobs=job_list)
```

- Accepts responses in 200-399 range (success)
- **Rate limit status (429)**: Specifically caught and logged, returns accumulated results
- **Other failures**: Logged with status code and response text, returns accumulated results
- **No retry on failure**: Returns immediately with whatever jobs have been collected so far

### Exception Handling
**File: `__init__.py` lines 134-139**

```python
except Exception as e:
    if "Proxy responded with" in str(e):
        log.error(f"LinkedIn: Bad proxy")
    else:
        log.error(f"LinkedIn: {str(e)}")
    return JobResponse(jobs=job_list)
```

- Catches all exceptions during search API calls
- Specific handling for proxy errors
- Returns accumulated results on exception

---

## 5. How Job Details Are Fetched

### Two-Phase Approach

#### Phase 1: Bulk Search Results
**File: `__init__.py` lines 142-154**

- Single request to search API returns HTML with multiple job cards
- 25 jobs per page returned in one response
- Job IDs extracted from href attributes:
  - Location: `<a class="base-card__full-link">` href (line 147)
  - Extraction: `job_id = href.split("-")[-1]` (line 150)

#### Phase 2: Individual Job Details (Optional)
**File: `__init__.py` lines 157-158, 224-225**

- **Only if `linkedin_fetch_description=True`**
  - Controlled by `scraper_input.linkedin_fetch_description` (line 157)
  - Defaults to False (not fetching full details)

- **Per-job request**: `self._get_job_details(job_id)` (line 225)
  - Lines 249-302

### Job Details Fetch Implementation
**File: `__init__.py` lines 256-263**

```python
response = self.session.get(
    f"{self.base_url}/jobs/view/{job_id}", timeout=5
)
```

- Request URL: `https://www.linkedin.com/jobs/view/{job_id}`
- Timeout: **5 seconds** (shorter than search API)
- Catches exceptions and returns empty dict on failure
- Detects signup redirects: `if "linkedin.com/signup" in response.url:` (line 262)
  - Returns empty dict if redirected to signup (indicates blocked access)

---

## 6. Field Extraction & JobPost Model Mapping

### From Search Results (HTML Parsing)

#### Title
- **Source**: `<span class="sr-only">` (line 192)
- **Extraction**: `title_tag.get_text(strip=True)` (line 193)
- **Fallback**: "N/A" if not found
- **Mapping**: `JobPost.title`

#### Company
- **Source**: `<h4 class="base-search-card__subtitle">` → `<a>` element (lines 195-202)
- **Extraction**: `company_a_tag.get_text(strip=True)` (line 202)
- **Fallback**: "N/A"
- **Mapping**: `JobPost.company_name`

#### Company URL
- **Source**: Same `<a>` href attribute (line 198)
- **Processing**: URL is parsed and query string removed:
  ```python
  urlunparse(urlparse(company_a_tag.get("href"))._replace(query=""))
  ```
- **Fallback**: Empty string
- **Mapping**: `JobPost.company_url`

#### Location
- **Source**: `<div class="base-search-card__metadata">` → `<span class="job-search-card__location">` (lines 204, 312-315)
- **Processing**: `_get_location()` method (lines 304-328)
  - Text split by ", " to parse city, state, country
  - 2 parts: city, state (country = scraper.country, defaults to "worldwide")
  - 3 parts: city, state, country
- **Mapping**: `JobPost.location` (Location object with city, state, country)

#### Date Posted
- **Source**: `<time class="job-search-card__listdate">` or `<time class="job-search-card__listdate--new">` (lines 207-215)
- **Attribute**: `datetime` attribute (line 218)
- **Format**: ISO format YYYY-MM-DD (line 220)
- **Fallback**: None if parsing fails
- **Mapping**: `JobPost.date_posted`

#### Salary/Compensation
- **Source**: `<span class="job-search-card__salary-info">` (line 176)
- **Processing** (lines 180-190):
  - Split by "-" to get min and max
  - Currency parser applied to each value
  - Currency extracted from first character of text (special case: "$" → "USD")
  - Both converted to int
- **Mapping**: `JobPost.compensation` (Compensation object: min_amount, max_amount, currency)
- **Fallback**: None if salary tag not present

#### Job ID
- **Source**: Last segment of href after splitting by "-" (line 150)
- **Example**: `/jobs/view/3816857619` → job_id = "3816857619"
- **Mapping**: `JobPost.id` = f"li-{job_id}"

#### Job URL
- **Source**: Constructed from job_id (line 237)
- **Format**: `https://www.linkedin.com/jobs/view/{job_id}`
- **Mapping**: `JobPost.job_url`

### From Individual Job Details (If Fetched)

#### Description
- **Source**: `<div class="show-more-less-html__markup">` (line 266-267)
- **Processing** (lines 271-276):
  - HTML attributes stripped via `remove_attributes()`
  - Prettified to HTML
  - Converted based on `scraper_input.description_format`:
    - MARKDOWN: via `markdown_converter()`
    - PLAIN: via `plain_converter()`
    - Default (HTML): left as-is
- **Mapping**: `JobPost.description`

#### Job Function
- **Source**: H3 with text containing "Job function" → next sibling `<span class="description__job-criteria-text">` (lines 277-287)
- **Processing**: `.text.strip()`
- **Mapping**: `JobPost.job_function`

#### Company Logo
- **Source**: `<img class="artdeco-entity-image">` → `data-delayed-url` attribute (lines 289-293)
- **Processing**: Uses walrus operator to get image URL directly
- **Mapping**: `JobPost.company_logo` (URL string)

#### Job Level (Seniority)
- **Source**: Extracted via `parse_job_level(soup)` utility (line 296)
- **Parsing** (util.py lines 42-62):
  - H3 with text containing "Seniority level"
  - Next sibling `<span class="description__job-criteria-text description__job-criteria-text--criteria">`
  - `.get_text(strip=True)`
- **Processing**: Lowercased at JobPost level (line 240)
- **Mapping**: `JobPost.job_level`

#### Job Type (Employment Type)
- **Source**: Extracted via `parse_job_type(soup)` utility (line 298)
- **Parsing** (util.py lines 17-39):
  - H3 with text containing "Employment type"
  - Next sibling span with class `description__job-criteria-text description__job-criteria-text--criteria`
  - `.get_text(strip=True)` then `.lower()` and replace "-" with ""
  - Converted to JobType enum via `get_enum_from_job_type()`
- **Output**: Returns list of JobType enums
- **Mapping**: `JobPost.job_type`

#### Company Industry
- **Source**: Extracted via `parse_company_industry(soup)` utility (line 297)
- **Parsing** (util.py lines 65-85):
  - H3 with text containing "Industries"
  - Next sibling span with class `description__job-criteria-text description__job-criteria-text--criteria`
  - `.get_text(strip=True)`
- **Mapping**: `JobPost.company_industry`

#### Direct Job URL
- **Source**: `<code id="applyUrl">` element (line 337)
- **Processing** (lines 339-343):
  - Regex search for pattern: `(?<=\?url=)[^"]+` (line 71)
  - Extracts URL-encoded value after `?url=`
  - URL-decoded via `unquote()`
- **Purpose**: External application URL if job has apply button
- **Mapping**: `JobPost.job_url_direct`

#### Emails
- **Source**: Description text (line 244)
- **Processing**: `extract_emails_from_text(description)` utility
- **Mapping**: `JobPost.emails` (list of email strings)

#### Is Remote
- **Source**: Composite of title, description, location (line 227)
- **Processing** (util.py lines 88-96):
  - Function `is_job_remote(title, description, location)`
  - Checks for keywords: "remote", "work from home", "wfh"
  - Case-insensitive search across title + description + location display
  - Returns boolean
- **Mapping**: `JobPost.is_remote`

### Field Mapping Summary Table

| JobPost Field | Source | Line | Optional | Processing |
|---------------|--------|------|----------|------------|
| id | href split | 150 | No | f"li-{job_id}" |
| title | sr-only span | 192 | No | text.strip() |
| company_name | subtitle h4 > a | 195 | No | text.strip() |
| company_url | subtitle h4 > a href | 198 | No | URL parsed, query removed |
| location | location span | 312 | No | split and parse |
| is_remote | title+desc+location | 227 | No | keyword search |
| date_posted | time datetime attr | 218 | Yes | strptime "%Y-%m-%d" |
| job_url | constructed | 237 | No | f"{base_url}/jobs/view/{job_id}" |
| compensation | salary-info span | 176 | Yes | split, parse, create Compensation |
| job_type | job details | 239 | Yes | parse_job_type() |
| job_level | job details | 240 | Yes | parse_job_level().lower() |
| company_industry | job details | 241 | Yes | parse_company_industry() |
| description | show-more-less div | 266 | Yes | format conversion |
| job_url_direct | code#applyUrl | 337 | Yes | regex + unquote |
| emails | description | 244 | Yes | extract_emails_from_text() |
| company_logo | img data-delayed-url | 289 | Yes | direct URL |
| job_function | h3 "Job function" | 277 | Yes | next sibling span text |

---

## 7. Hours Old Filtering

### Parameter Construction
**File: `__init__.py` lines 84-115**

```python
seconds_old = (
    scraper_input.hours_old * 3600 if scraper_input.hours_old else None
)
...
if seconds_old is not None:
    params["f_TPR"] = f"r{seconds_old}"
```

- User provides `hours_old` as integer (hours)
- Converted to seconds by multiplying by 3600
- Only added to params if not None

### API Parameter Format
- **Parameter name**: `f_TPR`
- **Format**: `r{seconds}` (prefix "r" + total seconds)
- **Examples**:
  - Last 24 hours: `f_TPR=r86400` (24 × 3600)
  - Last 7 days: `f_TPR=r604800` (7 × 24 × 3600)
  - Last 30 days: `f_TPR=r2592000` (30 × 24 × 3600)

### LinkedIn's Time Range Interpretation
- The `r` prefix indicates a "relative time" filter
- LinkedIn interprets this as "posted within the last N seconds"
- No client-side filtering; filtering happens server-side at API level

---

## 8. Job Type Filtering

### Job Type Code Mapping
**File: `util.py` lines 7-14**

```python
def job_type_code(job_type_enum: JobType) -> str:
    return {
        JobType.FULL_TIME: "F",
        JobType.PART_TIME: "P",
        JobType.INTERNSHIP: "I",
        JobType.CONTRACT: "C",
        JobType.TEMPORARY: "T",
    }.get(job_type_enum, "")
```

### API Parameter
**File: `__init__.py` lines 100-103**

```python
"f_JT": (
    job_type_code(scraper_input.job_type)
    if scraper_input.job_type
    else None
),
```

- **Parameter name**: `f_JT`
- **Mapping to API codes**:
  - Full-time → "F"
  - Part-time → "P"
  - Internship → "I"
  - Contract → "C"
  - Temporary → "T"

### Usage
- Only added to query params if `scraper_input.job_type` is not None
- Single string value per request (no multi-select in search)
- If user wants multiple job types, multiple searches required

---

## 9. Location & Distance Handling

### Location Parameter
**File: `__init__.py` lines 96-98**

```python
"keywords": scraper_input.search_term,
"location": scraper_input.location,
"distance": scraper_input.distance,
```

- **Parameter**: `location` (string, user-provided)
- **Parameter**: `distance` (integer, user-provided)
- Both passed directly to LinkedIn API with no processing
- Examples: location="New York", distance=25

### Location Parsing (From Results)
**File: `__init__.py` lines 304-328**

```python
def _get_location(self, metadata_card: Optional[Tag]) -> Location:
    location = Location(country=Country.from_string(self.country))
    if metadata_card is not None:
        location_tag = metadata_card.find(
            "span", class_="job-search-card__location"
        )
        location_string = location_tag.text.strip() if location_tag else "N/A"
        parts = location_string.split(", ")
        if len(parts) == 2:
            city, state = parts
            location = Location(
                city=city,
                state=state,
                country=Country.from_string(self.country),
            )
        elif len(parts) == 3:
            city, state, country = parts
            country = Country.from_string(country)
            location = Location(city=city, state=state, country=country)
    return location
```

### Parsing Logic
- **Default country**: `self.country` (initialized to "worldwide" at line 70)
- **2 parts** (e.g., "San Francisco, CA"): Assumes US location with scraper's country
- **3 parts** (e.g., "Toronto, ON, Canada"): Parses country from third part
- **No parts or 1 part**: Returns default location with country only

### Remote Work Handling
**File: `__init__.py` lines 99**

```python
"f_WT": 2 if scraper_input.is_remote else None,
```

- **Parameter**: `f_WT` (work type)
- **Remote filter value**: `"2"`
- Only added if `scraper_input.is_remote` is True

---

## 10. LinkedIn-Specific Parameters

### All LinkedIn Query Parameters Used

| Parameter | Value Type | Source | Purpose | LinkedIn Feature |
|-----------|-----------|--------|---------|------------------|
| `keywords` | string | search_term | Job search query | Standard search |
| `location` | string | location | Geographic filter | Location-based search |
| `distance` | int | distance | Radius from location | Distance radius |
| `f_WT` | "2" | is_remote boolean | Remote work filter | Work type: 2=Remote |
| `f_JT` | "F"/"P"/"I"/"C"/"T" | job_type enum | Employment type filter | Job type: F=FT, P=PT, I=Intern, C=Contract, T=Temp |
| `f_AL` | "true" | easy_apply boolean | Easy Apply enabled | Easy Apply filter |
| `f_C` | comma-separated IDs | linkedin_company_ids | Filter by company | Company IDs |
| `f_TPR` | "r{seconds}" | hours_old integer | Posted recency | Time posted filter |
| `pageNum` | 0 | hardcoded | Pagination page number | Always 0 |
| `start` | 0, 25, 50, ... | pagination logic | Result offset | Pagination offset |

### Unsupported/Missing LinkedIn Filters
The scraper does NOT currently support:
- Experience level filter (`f_E`)
- Salary range filter
- Industry filter
- Company size filter
- Date posted specificity (only relative time via `f_TPR`)
- Job function filter
- Skills filter

---

## 11. Known Failure Modes & Exception Handling

### Search API Failures

#### HTTP Status Code 429 (Rate Limited)
**File: `__init__.py` lines 125-128**
- Explicitly detected
- Returns accumulated job list
- Logs: "429 Response - Blocked by LinkedIn for too many requests"
- No retry attempt; scraping halts

#### Other HTTP Errors (4xx, 5xx)
**File: `__init__.py` lines 129-133**
- Any status code outside 200-399 range
- Logs full response text
- Returns accumulated results

#### Network/Connection Exceptions
**File: `__init__.py` lines 134-139**
- Generic exception catch
- Proxy errors detected: checks for "Proxy responded with" in error string
- Logs error message
- Returns accumulated results

### Job Details Fetch Failures

#### All Failures Return Empty Dict
**File: `__init__.py` lines 256-261**
```python
try:
    response = self.session.get(...)
    response.raise_for_status()
except:
    return {}
```
- Timeout or network error → {}
- HTTP error → {}
- All exceptions caught, no logging

#### LinkedIn Signup Redirect Detection
**File: `__init__.py` lines 262-263**
```python
if "linkedin.com/signup" in response.url:
    return {}
```
- Detects if LinkedIn redirected to signup (access blocked)
- Returns empty dict, no error raised

### Duplicate Job Filtering
**File: `__init__.py` lines 152-154**
```python
if job_id in seen_ids:
    continue
seen_ids.add(job_id)
```
- Tracks seen job IDs across pages
- Prevents duplicate entries
- Silent skip if duplicate found

### Job Card Parsing Failures
**File: `__init__.py` lines 163-164**
```python
except Exception as e:
    raise LinkedInException(str(e))
```
- Individual job parsing errors wrapped in LinkedInException
- Stops entire scraping operation (not caught upstream in scrape())

### HTML Parsing Fallbacks
Multiple fallbacks throughout parsing:

| Field | Fallback |
|-------|----------|
| title | "N/A" |
| company | "N/A" |
| company_url | "" (empty) |
| location | Location with only country |
| date_posted | None |
| compensation | None |
| salary currency | "USD" if "$" symbol |

---

## 12. Constants File Insights - LinkedIn's Taxonomy

### Headers Analysis
**File: `constant.py`**

The single constant dictionary reveals:

1. **User-Agent Strategy**
   - Masquerades as specific Chrome version (120.0.0.0)
   - macOS 10.15.7 (Catalina, released 2019)
   - Desktop browser (not mobile)

2. **Accept Headers Strategy**
   - Accepts HTML, XHTML, XML with varying quality factors
   - Accepts modern image formats (avif, webp)
   - Signed exchange support (q=0.7, lower priority)
   - Shows sophisticated browser compatibility

3. **Security Headers**
   - `upgrade-insecure-requests: 1` → prefers HTTPS
   - `cache-control: max-age=0` → forces fresh content from server

4. **Language**
   - `accept-language: en-US,en;q=0.9` → English preference

### What This Reveals
- LinkedIn expects and may block non-browser user-agents
- Rotation of user-agents may be beneficial (but not currently implemented)
- Static headers could be detected as a bot signature over time
- LinkedIn uses standard HTTP mechanisms (no custom X-* headers required)

### Implied LinkedIn Capabilities
- LinkedIn's guest job API accepts query parameters for filtering
- No authentication required for job search (publicly browsable)
- Results returned as HTML with CSS classes for parsing
- Job detail pages require full page loads (no JSON endpoint for individual jobs)

---

## Technical Implementation Details

### Class Structure
**File: `__init__.py` lines 47-72**

```python
class LinkedIn(Scraper):
    base_url = "https://www.linkedin.com"
    delay = 3
    band_delay = 4
    jobs_per_page = 25
    
    def __init__(self, proxies, ca_cert, user_agent):
        # Session initialization
```

- Inherits from `Scraper` base class
- Class variables define timing and limits
- Instance methods handle scraping workflow

### Regular Expression for URL Extraction
**File: `__init__.py` line 71**

```python
self.job_url_direct_regex = re.compile(r'(?<=\?url=)[^"]+')
```

- Uses positive lookbehind: `(?<=\?url=)`
- Captures everything up to closing quote: `[^"]+`
- Purpose: Extract actual external URL from LinkedIn's apply wrapper
- Example: `?url=https%3A%2F%2Fcompany.example.com%2Fjob` → captures encoded URL

### Session Retry Configuration
**File: `__init__.py` lines 60-67**

- Retry is enabled via `create_session()` call
- Implementation details hidden in utility module
- Likely uses urllib3's Retry class
- `delay=5` suggests initial retry delay

---

## Summary of Key Insights

### Strengths
1. **Clean separation**: Search and details in distinct methods
2. **Flexible filtering**: Supports most LinkedIn job search filters
3. **Graceful degradation**: Returns partial results on failure
4. **Duplicate prevention**: Tracks seen job IDs
5. **Format flexibility**: Description format conversion (HTML/Markdown/Plain)

### Potential Optimizations
1. **Parallel requests**: Could fetch multiple job details concurrently
2. **User-agent rotation**: Currently static, easily blocked by LinkedIn
3. **Header rotation**: All requests identical, creates bot signature
4. **Smarter retries**: 429 errors could trigger exponential backoff + retry
5. **Batch job detail requests**: Currently sequential per-job requests
6. **Result size negotiation**: Hard limit of 1000 could be pushed via pagination tricks

### Anti-Bot Detection Risks
1. **Consistent user-agent**: Same across all requests
2. **Regular delays**: Predictable 3-7 second intervals
3. **No header variation**: Same headers every request
4. **Rapid pagination**: Could hit 25 jobs/second if no rate limiting
5. **No JavaScript execution**: Can't handle dynamic content (low concern for job listings)

### LinkedIn API Quirks
1. **No JSON endpoint**: Must parse HTML from search results
2. **10-result pagination internally**: Rounding to 10 in offset calculation
3. **Hard 1000 result limit**: Can't scrape beyond 1000 positions
4. **Query string handling**: Company URLs have query strings stripped
5. **Time filter format**: Requires seconds with "r" prefix, not standard time format
6. **Lazy-loaded images**: Company logo uses `data-delayed-url` not `src`

---

## Appendix: File References

### /home/claude-code/Projects/agentic-job-applier/reference-repos/jobspy/jobspy/linkedin/__init__.py
- Primary scraper implementation
- Lines 1-45: Imports and setup
- Lines 47-171: LinkedIn class and main scrape() method
- Lines 173-247: _process_job() parsing logic
- Lines 249-302: _get_job_details() job detail fetching
- Lines 304-328: _get_location() location parsing
- Lines 330-345: _parse_job_url_direct() URL extraction

### /home/claude-code/Projects/agentic-job-applier/reference-repos/jobspy/jobspy/linkedin/constant.py
- HTTP headers constant

### /home/claude-code/Projects/agentic-job-applier/reference-repos/jobspy/jobspy/linkedin/util.py
- Lines 7-14: job_type_code() mapping function
- Lines 17-39: parse_job_type() parsing function
- Lines 42-62: parse_job_level() parsing function
- Lines 65-85: parse_company_industry() parsing function
- Lines 88-96: is_job_remote() detection function
