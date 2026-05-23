# JobSpy Core API & Model Analysis

## Executive Summary

JobSpy is a production-grade multi-site job scraping library that aggregates job postings from 8 different job boards (LinkedIn, Indeed, Glassdoor, Google, ZipRecruiter, Bayt, Naukri, BDJobs) using concurrent scraping with ThreadPoolExecutor. The library provides a single entry point (`scrape_jobs()`) that orchestrates site-specific scrapers and returns a normalized pandas DataFrame.

**Key characteristics:**
- Python 3.10+ minimum (enforced in pyproject.toml)
- Pydantic v2.3.0+ for data validation
- Concurrent threading with per-site error isolation
- Result deduplication via DataFrames
- Salary extraction from both direct data and job descriptions
- Multi-country support (140+ countries via Indeed/Glassdoor mapping)
- Proxy rotation with round-robin strategy
- TLS fingerprinting support for anti-bot evasion

---

## 1. Complete `scrape_jobs()` Function Signature

**Location:** `/home/claude-code/Projects/agentic-job-applier/reference-repos/jobspy/jobspy/__init__.py` lines 31-53

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
) -> pd.DataFrame
```

### Parameter Reference Table

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `site_name` | str \| list[str] \| Site \| list[Site] \| None | None | Job boards to scrape. Can be single string/enum or list. If None, scrapes ALL sites in SCRAPER_MAPPING (line 58-67). String values are converted via `map_str_to_site()` (line 74-80). |
| `search_term` | str \| None | None | Primary search query passed to all scrapers. Required for most boards (not for Google). |
| `google_search_term` | str \| None | None | **Google-only** parameter. Separate from `search_term`. Google requires specific syntax matching browser search box filters. |
| `location` | str \| None | None | Geographic filter (city/state/region). Interpreted differently by each scraper. |
| `distance` | int \| None | 50 | Search radius in miles. Default 50 miles. May be ignored by some scrapers (e.g., international sites). |
| `is_remote` | bool | False | Filters for remote-only positions. Note: README states Indeed limitation - cannot use with `job_type` or `easy_apply`. |
| `job_type` | str \| None | None | Job classification filter. Must be value from JobType enum (fulltime, parttime, internship, contract, etc.). Converted to enum via `get_enum_from_value()` line 69. |
| `easy_apply` | bool \| None | None | Filters for easy-apply postings (hosted on job board). LinkedIn easy apply filter documented as non-functional in README. Indeed limitation applies. |
| `results_wanted` | int | 15 | Target number of results **per site**. Each scraper aims for this count independently. |
| `country_indeed` | str | "usa" | Country code/name for Indeed and Glassdoor. Converted to Country enum via `Country.from_string()` line 84. Supports 140+ countries. |
| `proxies` | list[str] \| str \| None | None | Proxy URLs for round-robin rotation. Formats: `"user:pass@host:port"`, `"host:port"`, `"http://..."`, `"socks5://..."`. Single proxy converted to list in RotatingProxySession.__init__() (line 34-35). |
| `ca_cert` | str \| None | None | Path to CA certificate file for SSL verification with proxies. Passed to session.verify (line 130). |
| `description_format` | str | "markdown" | Format for job descriptions: "markdown", "html", or "plain". Converted to DescriptionFormat enum. Different converters in util.py (lines 154-167). |
| `linkedin_fetch_description` | bool \| None | False | **LinkedIn-only**. Fetches full job description and direct URL. Documented as O(n) increase in requests. README limitation: cannot use with `hours_old` or `easy_apply`. |
| `linkedin_company_ids` | list[int] \| None | None | **LinkedIn-only**. Filter jobs by company LinkedIn IDs. |
| `offset` | int \| None | 0 | Pagination offset. Starts search from Nth result. Default 0 (start from beginning). |
| `hours_old` | int | None | Filters jobs posted within N hours. ZipRecruiter/Glassdoor round up to next day. README limitations: Indeed cannot use with `job_type`, `is_remote`, or `easy_apply`. LinkedIn cannot use with `easy_apply` or `linkedin_fetch_description`. |
| `enforce_annual_salary` | bool | False | Converts non-annual salaries to annual equivalent. Uses conversion factors: hourly × 2080 (line 313), monthly × 12 (line 316), weekly × 52 (line 319), daily × 260 (line 322). Applied to both direct compensation and extracted salary (lines 162-168, 176-179). |
| `verbose` | int | 0 | Logging level: 0=ERROR, 1=WARNING, 2=INFO. Maps in `set_logger_level()` (line 144). |
| `user_agent` | str | None | Custom User-Agent header. Passed to all scraper instances (line 106). |
| `**kwargs` | dict | None | Captured but unused in base function. Allows future extension. |

### Return Type
- **Returns:** `pd.DataFrame` with normalized job columns across all sites
- **Empty fallback:** Returns `pd.DataFrame()` if no results from any site (line 221)

---

## 2. Pydantic Models & Field Reference

### 2.1 JobPost (Primary Model)

**Location:** `/home/claude-code/Projects/agentic-job-applier/reference-repos/jobspy/jobspy/model.py` lines 239-281

**Purpose:** Core data model for a single job posting. Converted to dict at line 133 for DataFrame construction.

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `id` | str \| None | None | Unique posting ID (site-specific, may be URL hash) |
| `title` | str | *required* | Job position title |
| `company_name` | str \| None | None | Employer name. Renamed to `company` in DataFrame (line 136) |
| `job_url` | str | *required* | Canonical job posting URL |
| `job_url_direct` | str \| None | None | Direct company URL (bypasses board redirects). Populated for LinkedIn when `linkedin_fetch_description=True` |
| `location` | Location | *required* | Nested model: country, city, state. Converted to string via `display_location()` (line 148) |
| `description` | str \| None | None | Full job description. Format controlled by `description_format` parameter. May be HTML, Markdown, or plain text. |
| `company_url` | str \| None | None | Company website root URL |
| `company_url_direct` | str \| None | None | Direct company URL (non-board-hosted) |
| `job_type` | list[JobType] \| None | None | List of JobType enums. Converted to comma-separated string (line 138) |
| `compensation` | Compensation \| None | None | Nested model: interval, min_amount, max_amount, currency. Exploded to separate columns in DataFrame (lines 151-160) |
| `date_posted` | date \| None | None | Python date object for post creation |
| `emails` | list[str] \| None | None | Contact email addresses extracted from description. Joined as comma-separated string (line 143) |
| `is_remote` | bool \| None | None | Boolean remote work indicator |
| `listing_type` | str \| None | None | Classification (e.g., "featured", "sponsored") |
| `job_level` | str \| None | None | **LinkedIn-specific** (e.g., "entry-level", "mid-level", "senior") |
| `company_industry` | str \| None | None | **LinkedIn & Indeed** (e.g., "Software Development") |
| `company_addresses` | str \| None | None | **Indeed-specific** CSV of company office locations |
| `company_num_employees` | str \| None | None | **Indeed-specific** Employee count bracket (e.g., "1001-5000") |
| `company_revenue` | str \| None | None | **Indeed-specific** Annual revenue bracket |
| `company_description` | str \| None | None | **Indeed-specific** Company profile text |
| `company_logo` | str \| None | None | **Indeed-specific** Logo image URL |
| `banner_photo_url` | str \| None | None | **Indeed-specific** Job posting banner image |
| `job_function` | str \| None | None | **LinkedIn-specific** (e.g., "Engineering", "Sales") |
| `skills` | list[str] \| None | None | **Naukri-specific** Required skills. Joined to comma-separated string (line 190) |
| `experience_range` | str \| None | None | **Naukri-specific** (e.g., "2-5 years") |
| `company_rating` | float \| None | None | **Naukri-specific** Company rating (from AmbitionBox data) |
| `company_reviews_count` | int \| None | None | **Naukri-specific** Number of company reviews |
| `vacancy_count` | int \| None | None | **Naukri-specific** Open positions for this role |
| `work_from_home_type` | str \| None | None | **Naukri-specific** WFH classification (e.g., "Hybrid", "Remote", "Office") |

### 2.2 Location

**Location:** `model.py` lines 181-205

```python
class Location(BaseModel):
    country: Country | str | None = None
    city: Optional[str] = None
    state: Optional[str] = None
```

**Method:** `display_location() -> str`
- Constructs human-readable location string
- Order: city → state → country
- Country enum names handled specially: "usa"→"USA", "uk"→"UK", others title-cased
- Filters out internal enums (US_CANADA, WORLDWIDE)

### 2.3 CompensationInterval

**Location:** `model.py` lines 208-224

```python
class CompensationInterval(Enum):
    YEARLY = "yearly"
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    DAILY = "daily"
    HOURLY = "hourly"
```

**Method:** `get_interval(pay_period: str) -> str | None`
- Maps string representations to enum values
- Special mappings: "YEAR"→YEARLY, "HOUR"→HOURLY
- Falls back to enum member lookup

### 2.4 Compensation

**Location:** `model.py` lines 227-231

```python
class Compensation(BaseModel):
    interval: Optional[CompensationInterval] = None
    min_amount: float | None = None
    max_amount: float | None = None
    currency: Optional[str] = "USD"
```

**Notes:**
- `interval` is enum-typed but stored as CompensationInterval in model
- At DataFrame output, converted to string value (line 154)
- Default currency "USD" applied if not provided
- min/max amounts are floats (allow decimals for hourly rates)

### 2.5 JobType

**Location:** `model.py` lines 10-57

```python
class JobType(Enum):
    FULL_TIME = (multiple localized strings...)
    PART_TIME = (...)
    CONTRACT = (...)
    TEMPORARY = ("temporary",)
    INTERNSHIP = (...)
    PER_DIEM = ("perdiem",)
    NIGHTS = ("nights",)
    OTHER = ("other",)
    SUMMER = ("summer",)
    VOLUNTEER = ("volunteer",)
```

**Tuple Structure:** Each enum value is a tuple of alternate strings in multiple languages
- **FULL_TIME:** 29 variants (English, Spanish, German, Mandarin, Hebrew, Finnish, Greek, Hungarian, Italian, Swedish, Polish, Korean, Thai, Turkish, Ukrainian, Vietnamese, etc.)
- **PART_TIME:** 4 variants
- **CONTRACT:** 2 variants
- **INTERNSHIP:** 5 variants including "ojt(onthejobtraining)"

**Conversion:** `get_enum_from_job_type(job_type_str)` iterates all enums checking if string is in tuple (line 177-185)

### 2.6 Country

**Location:** `model.py` lines 60-178

```python
class Country(Enum):
    ARGENTINA = ("argentina", "ar", "com.ar")
    ...
    USA = ("usa,us,united states", "www:us", "com")
    ...
```

**Tuple Structure:** (display_name, indeed_subdomain[:api_code], glassdoor_tld[:subdomain])

**Supported Countries:** 71 country enums (lines 67-143)
- **Indeed value:** Element [1], optionally with ":" separator for API code override
- **Glassdoor value:** Element [2], optionally with ":" separator for subdomain override
- **Internal variants:** US_CANADA, WORLDWIDE (for LinkedIn)

**Key Methods:**

| Method | Purpose | Implementation |
|--------|---------|-----------------|
| `indeed_domain_value` | Returns (subdomain, api_code) tuple | Splits element [1] on ":", defaults subdomain to full value and api_code to uppercase |
| `glassdoor_domain_value` | Returns full domain like "www.glassdoor.de" | Partitions element [2] on ":", constructs domain URL |
| `get_glassdoor_url()` | Returns full HTTPS URL | `f"https://{glassdoor_domain_value}/"` |
| `from_string(country_str)` | Convert string to enum | Case-insensitive lookup in comma-separated name list, raises ValueError if not found |

### 2.7 JobResponse

**Location:** `model.py` lines 283-284

```python
class JobResponse(BaseModel):
    jobs: list[JobPost] = []
```

**Purpose:** Wrapper returned by all scraper implementations. Contains list of JobPost objects. Mutated in __init__.py line 127.

### 2.8 Site

**Location:** `model.py` lines 287-295

```python
class Site(Enum):
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    ZIP_RECRUITER = "zip_recruiter"
    GLASSDOOR = "glassdoor"
    GOOGLE = "google"
    BAYT = "bayt"
    NAUKRI = "naukri"
    BDJOBS = "bdjobs"
```

**Usage:** Enum keys map to SCRAPER_MAPPING dict (line 58-67). Values used for DataFrame "site" column (line 135).

### 2.9 SalarySource

**Location:** `model.py` lines 298-300

```python
class SalarySource(Enum):
    DIRECT_DATA = "direct_data"
    DESCRIPTION = "description"
```

**Values:** 
- `DIRECT_DATA` = salary from structured job posting fields
- `DESCRIPTION` = salary extracted via regex from job description text

**Assignment Logic:** (lines 161, 180, 182-186)
- Set to DIRECT_DATA if compensation object exists
- Set to DESCRIPTION if salary extracted from text (USA only, line 170)
- Set to None if no salary found (line 182-186)

### 2.10 ScraperInput

**Location:** `model.py` lines 303-322

```python
class ScraperInput(BaseModel):
    site_type: list[Site]
    search_term: str | None = None
    google_search_term: str | None = None
    location: str | None = None
    country: Country | None = Country.USA
    distance: int | None = None
    is_remote: bool = False
    job_type: JobType | None = None
    easy_apply: bool | None = None
    offset: int = 0
    linkedin_fetch_description: bool = False
    linkedin_company_ids: list[int] | None = None
    description_format: DescriptionFormat | None = DescriptionFormat.MARKDOWN
    request_timeout: int = 60
    results_wanted: int = 15
    hours_old: int | None = None
```

**Purpose:** Data class passed to all scraper.scrape() implementations. Constructed at lines 86-102.

**Fields not in scrape_jobs() signature:**
- `request_timeout: int = 60` - HTTP timeout in seconds (not exposed as parameter)
- `description_format` typed as enum internally (passed as string to scrape_jobs)

### 2.11 DescriptionFormat

**Location:** `model.py` lines 234-237

```python
class DescriptionFormat(Enum):
    MARKDOWN = "markdown"
    HTML = "html"
    PLAIN = "plain"
```

### 2.12 Scraper (Abstract Base Class)

**Location:** `model.py` lines 325-335

```python
class Scraper(ABC):
    def __init__(
        self, 
        site: Site, 
        proxies: list[str] | None = None, 
        ca_cert: str | None = None, 
        user_agent: str | None = None
    ):
        self.site = site
        self.proxies = proxies
        self.ca_cert = ca_cert
        self.user_agent = user_agent

    @abstractmethod
    def scrape(self, scraper_input: ScraperInput) -> JobResponse: ...
```

**Subclasses:** LinkedIn, Indeed, ZipRecruiter, Glassdoor, Google, BaytScraper, Naukri, BDJobs (imported at lines 8-14)

---

## 3. Multi-Site Scraping Architecture

### Concurrency Model

**Location:** `/home/claude-code/Projects/agentic-job-applier/reference-repos/jobspy/jobspy/__init__.py` lines 120-127

```python
with ThreadPoolExecutor() as executor:
    future_to_site = {
        executor.submit(worker, site): site for site in scraper_input.site_type
    }
    
    for future in as_completed(future_to_site):
        site_value, scraped_data = future.result()
        site_to_jobs_dict[site_value] = scraped_data
```

**Key characteristics:**
- **ThreadPoolExecutor()** with default worker count (= CPU count on Python 3.5+)
- **as_completed()** iterator returns futures as they finish (non-blocking)
- **No timeout** set on executor.submit() or future.result()
- **Per-site isolation:** Each site in separate thread. Exception in one site's scraper does NOT kill other threads
- **site_to_jobs_dict** accumulates results: key = site.value string (e.g., "linkedin"), value = JobResponse object

### Worker Function

**Location:** lines 116-118

```python
def worker(site):
    site_val, scraped_info = scrape_site(site)
    return site_val, scraped_info
```

Wrapper that calls `scrape_site(site)` which:
1. Instantiates scraper class (line 105): `scraper_class(proxies=proxies, ca_cert=ca_cert, user_agent=user_agent)`
2. Calls `scraper.scrape(scraper_input)` (line 107)
3. Returns (site.value string, JobResponse object)

### Error Isolation

**Uncaught Exceptions:**
- If a scraper raises an exception, `future.result()` at line 126 will propagate it
- Exception terminates the entire scrape_jobs() call
- **No fallback mechanism** - no try/except around future_to_site loop
- Individual site failures are NOT isolated at the library level (but scrapers may have internal error handling)

### Scraper Order

- **No guaranteed order.** ThreadPoolExecutor.as_completed() returns futures in completion order, not submission order
- Sites are scraped in parallel, not sequentially

---

## 4. Deduplication & Result Merging

### Deduplication Strategy

**Location:** `/home/claude-code/Projects/agentic-job-applier/reference-repos/jobspy/jobspy/__init__.py` lines 201-219

**NO explicit deduplication logic.** Results are merged via DataFrame concatenation without duplicate removal:

```python
jobs_dfs: list[pd.DataFrame] = []

for site, job_response in site_to_jobs_dict.items():
    for job in job_response.jobs:
        job_data = job.dict()
        # ... transform job_data ...
        job_df = pd.DataFrame([job_data])
        jobs_dfs.append(job_df)

if jobs_dfs:
    filtered_dfs = [df.dropna(axis=1, how="all") for df in jobs_dfs]
    jobs_df = pd.concat(filtered_dfs, ignore_index=True)
```

**Findings:**
- Each JobPost converted to DataFrame row (lines 133-198)
- Sites may return duplicate postings for the same job (not prevented)
- No call to `.drop_duplicates()` on the final DataFrame
- **Implication:** Same job appearing on multiple sites will appear as multiple rows

### Result Merging

**Process:**
1. **Per-site transformation** (lines 131-199): Each job from each site converted to dict, job_url used to uniquely identify posting (line 134, not enforced)
2. **Column normalization** (lines 209-214):
   - Drop all-NA columns from individual DataFrames (line 203)
   - Add missing columns from `desired_order` as None (lines 209-211)
   - Reindex to `desired_order` column list
3. **Sorting** (lines 217-219): Sort by site (A-Z), then date_posted (newest first)

### Column Order (desired_order)

**Location:** `/home/claude-code/Projects/agentic-job-applier/reference-repos/jobspy/jobspy/util.py` lines 327-363

```python
desired_order = [
    "id", "site", "job_url", "job_url_direct",
    "title", "company", "location", "date_posted",
    "job_type", "salary_source", "interval", "min_amount", "max_amount", "currency",
    "is_remote", "job_level", "job_function", "listing_type", "emails", "description",
    "company_industry", "company_url", "company_logo", "company_url_direct",
    "company_addresses", "company_num_employees", "company_revenue", "company_description",
    "skills", "experience_range", "company_rating", "company_reviews_count", "vacancy_count", "work_from_home_type",
]
```

30 columns total. Site-specific fields (e.g., `company_logo`) will be None for non-matching sites.

---

## 5. Proxy Handling

### Proxy Format & Parsing

**Location:** `/home/claude-code/Projects/agentic-job-applier/reference-repos/jobspy/jobspy/util.py` lines 32-52

```python
class RotatingProxySession:
    def __init__(self, proxies=None):
        if isinstance(proxies, str):
            self.proxy_cycle = cycle([self.format_proxy(proxies)])
        elif isinstance(proxies, list):
            self.proxy_cycle = (
                cycle([self.format_proxy(proxy) for proxy in proxies])
                if proxies
                else None
            )
        else:
            self.proxy_cycle = None

    @staticmethod
    def format_proxy(proxy):
        if proxy.startswith("http://") or proxy.startswith("https://"):
            return {"http": proxy, "https": proxy}
        if proxy.startswith("socks5://"):
            return {"http": proxy, "https": proxy}
        return {"http": f"http://{proxy}", "https": f"http://{proxy}"}
```

**Accepted formats:**
- `"user:pass@host:port"` → Converted to `{"http": "http://user:pass@host:port", "https": "http://user:pass@host:port"}`
- `"host:port"` → Converted to `{"http": "http://host:port", "https": "http://host:port"}`
- `"http://..."` → Passed as-is
- `"https://..."` → Passed as-is
- `"socks5://..."` → Passed as-is (treated as both http & https proxy)

**Output:** Dictionary with "http" and "https" keys pointing to proxy URL

### Proxy Rotation Strategy

**Round-robin cycling:**

```python
self.proxy_cycle = cycle([...])  # itertools.cycle for infinite looping
next_proxy = next(self.proxy_cycle)  # Get next proxy in rotation
```

- Single proxy: creates 1-element list, cycles it (same proxy every request)
- Multiple proxies: rotates through list in order
- Loop resets when end of list reached (itertools.cycle behavior)

### Proxy Application

**RequestsRotating (lines 55-86):**

```python
def request(self, method, url, **kwargs):
    if self.clear_cookies:
        self.cookies.clear()
    
    if self.proxy_cycle:
        next_proxy = next(self.proxy_cycle)
        if next_proxy["http"] != "http://localhost":
            self.proxies = next_proxy
        else:
            self.proxies = {}  # localhost = no proxy
    return requests.Session.request(self, method, url, **kwargs)
```

- Applied at **every request** (rotates per HTTP call)
- Special case: `"localhost"` disables proxy

**TLSRotating (lines 89-103):**

```python
def execute_request(self, *args, **kwargs):
    if self.proxy_cycle:
        next_proxy = next(self.proxy_cycle)
        if next_proxy["http"] != "http://localhost":
            self.proxies = next_proxy
        else:
            self.proxies = {}
    response = tls_client.Session.execute_request(self, *args, **kwargs)
    response.ok = response.status_code in range(200, 400)
    return response
```

Same logic for tls_client.

### Session Creation

**Location:** lines 106-132

```python
def create_session(
    *,
    proxies: dict | str | None = None,
    ca_cert: str | None = None,
    is_tls: bool = True,
    has_retry: bool = False,
    delay: int = 1,
    clear_cookies: bool = False,
) -> requests.Session
```

**Parameters:**
- `is_tls=True` → Uses TLSRotating (tls_client with random fingerprint order)
- `is_tls=False` → Uses RequestsRotating (standard requests.Session with optional retry)
- `ca_cert` → Sets `session.verify` to certificate path (line 130)

**Retry logic** (lines 65-74):
- 3 retries for connection, status, and network errors
- Status codes retried: 500, 502, 503, 504, 429 (rate limits)
- Exponential backoff with `backoff_factor=delay`

### CA Certificate Handling

**Location:** line 43 (scrape_jobs signature), line 106 (instantiation), line 130 (application)

- Passed as filesystem path string
- Applied to session.verify attribute
- Disables InsecureRequestWarning (line 16): `urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)`

---

## 6. Exception Hierarchy

**Location:** `/home/claude-code/Projects/agentic-job-applier/reference-repos/jobspy/jobspy/exception.py`

```python
class LinkedInException(Exception):
    def __init__(self, message=None):
        super().__init__(message or "An error occurred with LinkedIn")

class IndeedException(Exception):
    def __init__(self, message=None):
        super().__init__(message or "An error occurred with Indeed")

class ZipRecruiterException(Exception):
    def __init__(self, message=None):
        super().__init__(message or "An error occurred with ZipRecruiter")

class GlassdoorException(Exception):
    def __init__(self, message=None):
        super().__init__(message or "An error occurred with Glassdoor")

class GoogleJobsException(Exception):
    def __init__(self, message=None):
        super().__init__(message or "An error occurred with Google Jobs")

class BaytException(Exception):
    def __init__(self, message=None):
        super().__init__(message or "An error occurred with Bayt")

class NaukriException(Exception):
    def __init__(self, message=None):
        super().__init__(message or "An error occurred with Naukri")

class BDJobsException(Exception):
    def __init__(self, message=None):
        super().__init__(message or "An error occurred with BDJobs")
```

**Hierarchy Structure:**
- All inherit directly from Python's base `Exception` (no custom parent)
- Each exception takes optional `message` parameter
- Falls back to generic default message if not provided (e.g., "An error occurred with LinkedIn")
- No exception chaining or context preservation
- **Total of 8 exceptions** - one per job board

**Patterns in exception usage:**
- Likely raised by individual scraper classes (imported but not shown in provided files)
- Not caught by library entry point (line 125-127 has no try/except)

---

## 7. Hidden/Undocumented Parameters

### In scrape_jobs() Signature

**`**kwargs` (line 52):**
- Captured but NOT used in function body
- No passing to scrapers or utility functions
- Allows forward compatibility (future parameters won't break existing calls)
- Consumers cannot rely on arbitrary kwargs being processed

### In ScraperInput Model

**`request_timeout: int = 60` (line 319):**
- NOT exposed as scrape_jobs() parameter
- Not mentioned in README
- Hard-coded default of 60 seconds
- Must be accessed via scraper-level configuration (not implemented in this API)
- Intended for HTTP request socket timeout

### In util.py Functions

**`clear_cookies` parameter in RequestsRotating (line 56, 59):**
- NOT exposed in scrape_jobs()
- Can clear browser cookies before each request
- Defaults to False
- Only used by RequestsRotating, not TLSRotating

**`has_retry` & `delay` in RequestsRotating (line 56, 62-74):**
- NOT exposed in scrape_jobs()
- Enables/configures exponential backoff retry logic
- Only applies to RequestsRotating (standard requests), not TLSRotating
- Retry on 429 (rate limit) not controlled by scrape_jobs() caller

### In extract_salary() Function

**`lower_limit`, `upper_limit`, `hourly_threshold`, `monthly_threshold` (lines 211-217):**

```python
def extract_salary(
    salary_str,
    lower_limit=1000,
    upper_limit=700000,
    hourly_threshold=350,
    monthly_threshold=30000,
    enforce_annual_salary=False,
):
```

- Thresholds for salary validation and interval detection
- `lower_limit=1000` → Reject salaries below $1000 annual
- `upper_limit=700000` → Reject salaries above $700k annual
- `hourly_threshold=350` → Assume hourly if < $350/unit
- `monthly_threshold=30000` → Assume monthly if < $30k/unit
- NOT exposed via scrape_jobs(), only via direct util.py call
- Hardcoded defaults apply to all USA-based salary extraction

---

## 8. Shared Utility Helpers (util.py)

**Location:** `/home/claude-code/Projects/agentic-job-applier/reference-repos/jobspy/jobspy/util.py`

### Logger & Logging

**`create_logger(name: str) -> logging.Logger` (lines 19-29)**
- Creates named logger: `f"JobSpy:{name}"`
- Sets `propagate=False` (doesn't bubble to root logger)
- Only adds handler if not already present (idempotent)
- Formats as: `"%(asctime)s - %(levelname)s - %(name)s - %(message)s"`
- Returns logger ready to use

**`set_logger_level(verbose: int)` (lines 135-151)**
- Maps verbose int to logging level name:
  - `0` → ERROR
  - `1` → WARNING
  - `2` → INFO (default)
  - Other → INFO
- Applies to all loggers starting with "JobSpy:"
- Raises ValueError if invalid level_name

### Session & Proxy Management

**`RotatingProxySession` (lines 32-52)** - Abstract base
- Converts proxy strings to session-compatible format
- Sets up itertools.cycle for round-robin rotation
- format_proxy() handles http, https, socks5 schemes

**`RequestsRotating(lines 55-86)` - Mixin of RotatingProxySession + requests.Session**
- **setup_session(has_retry, delay)** - Optional exponential backoff config
- **request()** - Override to rotate proxy per request
- Supports cookie clearing between requests

**`TLSRotating(lines 89-103)` - Mixin of RotatingProxySession + tls_client.Session**
- Uses tls-client library for TLS fingerprint randomization
- **execute_request()** - Override to rotate proxy
- Sets `response.ok` property based on status code range (200-399)

**`create_session()` (lines 106-132)**
- Factory function
- Parameters: proxies, ca_cert, is_tls, has_retry, delay, clear_cookies
- Returns RequestsRotating or TLSRotating based on is_tls flag

### Description Format Conversion

**`markdown_converter(description_html: str) -> str` (lines 154-158)**
- Uses markdownify library to convert HTML to Markdown
- Strips leading/trailing whitespace
- Returns None if input is None

**`plain_converter(decription_html: str) -> str` (lines 160-167)**
- Uses BeautifulSoup to extract plain text from HTML
- Joins text with single space separator
- Collapses multiple whitespace to single space with regex
- Returns None if input is None
- Note: Parameter spelled "decription_html" (typo in source)

### Email & Job Type Parsing

**`extract_emails_from_text(text: str) -> list[str] | None` (lines 170-174)**
- Regex: `r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"`
- Returns list of matching email addresses
- Returns None if text is None or no matches

**`get_enum_from_job_type(job_type_str: str) -> JobType | None` (lines 177-185)**
- Searches all JobType enum values (tuples)
- Returns first enum where job_type_str is in tuple
- Returns None if no match

**`extract_job_type(description: str) -> list[JobType] | None` (lines 281-297)**
- Regex patterns for full_time, part_time, internship, contract
- Case-insensitive search
- Returns list of matching JobType enums
- Returns None if no matches

### Currency & Salary Processing

**`currency_parser(cur_str) -> float` (lines 188-202)**
- Removes non-numeric characters except '.', ',', '-'
- Handles thousands separators (',' or '.')
- Returns numpy-rounded float (2 decimals)
- Assumes last 3 characters contain decimal point/comma

**`extract_salary(salary_str, lower_limit=1000, upper_limit=700000, hourly_threshold=350, monthly_threshold=30000, enforce_annual_salary=False)` (lines 211-278)**

**Logic:**
1. Searches for pattern: `$MIN[k?] - $MAX[k?]` (line 227)
2. Extracts min/max values, handles 'k' suffix for thousands
3. **Interval detection** (lines 249-264):
   - `< hourly_threshold` (350) → HOURLY
   - `< monthly_threshold` (30000) → MONTHLY
   - `else` → YEARLY
4. **Conversion to annual** (lines 249-264):
   - Hourly × 2080 (2080 working hours/year)
   - Monthly × 12
   - Yearly = as-is
5. **Validation** (lines 269-273):
   - Both annual min/max must be between lower_limit and upper_limit
   - Annual min must be < annual max
6. **Return value selection** (lines 274-277):
   - If enforce_annual_salary → return annual values
   - Else → return original min/max with detected interval
7. Returns (interval, min_amount, max_amount, currency) or (None, None, None, None)

**Example:** "$50k - $80k" → (HOURLY, 104000, 166400, USD) if enforce_annual_salary=True

### Enum Conversion

**`map_str_to_site(site_name: str) -> Site` (lines 300-301)**
- Converts string to Site enum via `Site[site_name.upper()]`
- Raises KeyError if invalid site name

**`get_enum_from_value(value_str) -> JobType` (lines 304-308)**
- Searches JobType enums for matching value string
- Raises Exception if not found

### HTML Utilities

**`remove_attributes(tag) -> tag` (lines 205-208)**
- Removes all attributes from BeautifulSoup tag in-place
- Returns modified tag

### Salary Conversion

**`convert_to_annual(job_data: dict)` (lines 311-324)**
- Modifies job_data dict in-place
- Multipliers:
  - hourly × 2080
  - monthly × 12
  - weekly × 52
  - daily × 260
- Sets interval to "yearly" after conversion

### Column Ordering

**`desired_order` list (lines 327-363)**
- Defines DataFrame column output order
- 30 total columns (see section 4)
- Used in scrape_jobs() to reorder final DataFrame

---

## 9. Dependencies & Python Version Requirements

**Location:** `/home/claude-code/Projects/agentic-job-applier/reference-repos/jobspy/pyproject.toml`

### Build System
```toml
[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

### Python Version
```toml
python = "^3.10"
```
- **Minimum:** Python 3.10
- **Constraint:** ^3.10 = >= 3.10.0, < 4.0.0
- **Enforced:** Blocks Python 3.9 and earlier

### Core Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `requests` | ^2.31.0 | HTTP client (>= 2.31.0) |
| `beautifulsoup4` | ^4.12.2 | HTML parsing (>= 4.12.2) |
| `pandas` | ^2.1.0 | DataFrame operations (>= 2.1.0) |
| `numpy` | >=1.26.0 | Numerical operations (>= 1.26.0, no upper bound) |
| `pydantic` | ^2.3.0 | Data validation (>= 2.3.0, < 3.0.0) |
| `tls-client` | ^1.0.1 | TLS fingerprint evasion (>= 1.0.1) |
| `markdownify` | ^1.1.0 | HTML-to-Markdown conversion (>= 1.1.0) |
| `regex` | ^2024.4.28 | Advanced regex support (>= 2024.4.28) |

### Development Dependencies
```toml
[tool.poetry.group.dev.dependencies]
jupyter = "^1.0.0"
black = "*"
pre-commit = "*"
```

### Packaging Metadata
```toml
name = "python-jobspy"
version = "1.1.82"
description = "Job scraper for LinkedIn, Indeed, Glassdoor, ZipRecruiter & Bayt"
authors = ["Cullen Watson <cullen@cullenwatson.com>", "Zachary Hampton <zachary@zacharysproducts.com>"]
keywords = ["jobs-scraper", "linkedin", "indeed", "glassdoor", "ziprecruiter", "bayt", "naukri"]
```

### Code Style
```toml
[tool.black]
line-length = 88
```

---

## 10. Key Implementation Patterns & Edge Cases

### DataFrame Construction

**Lines 129-199:** Each JobPost individually converted and appended as DataFrame:

```python
jobs_dfs: list[pd.DataFrame] = []

for site, job_response in site_to_jobs_dict.items():
    for job in job_response.jobs:
        job_data = job.dict()
        # Transform job_data...
        job_df = pd.DataFrame([job_data])
        jobs_dfs.append(job_df)
```

**Inefficiency:** Creates N DataFrames then concatenates (O(n) concatenations). Better to collect dicts then create single DataFrame.

### Compensation Handling

**Lines 151-160:** Special handling for compensation object:

```python
compensation_obj = job_data.get("compensation")
if compensation_obj and isinstance(compensation_obj, dict):
    job_data["interval"] = compensation_obj.get("interval").value if compensation_obj.get("interval") else None
    job_data["min_amount"] = compensation_obj.get("min_amount")
    job_data["max_amount"] = compensation_obj.get("max_amount")
    job_data["currency"] = compensation_obj.get("currency", "USD")
    job_data["salary_source"] = SalarySource.DIRECT_DATA.value
```

- Flattens nested Compensation object to multiple DataFrame columns
- Calls `.value` on interval enum to convert to string
- **Assumes dict format** (not Pydantic model) - only true after job.dict() conversion

### Salary Extraction (USA Only)

**Lines 170-180:**

```python
if country_enum == Country.USA:
    (interval, min_amount, max_amount, currency) = extract_salary(...)
    job_data["salary_source"] = SalarySource.DESCRIPTION.value
```

- **Only extracts salary from description for USA searches**
- Non-USA countries never have salary_source set to DESCRIPTION
- If enforce_annual_salary=True, salary is converted before tuple unpacking

### Site Name Normalization

**Lines 108-110:**

```python
cap_name = site.value.capitalize()
site_name = "ZipRecruiter" if cap_name == "Zip_recruiter" else cap_name
site_name = "LinkedIn" if cap_name == "Linkedin" else cap_name
```

- Converts enum value to title case
- Special cases for multi-word site names with underscores
- Applied to logging output, not DataFrame (DataFrame uses raw site.value)

### Job Type List Handling

**Lines 137-140:**

```python
job_data["job_type"] = (
    ", ".join(job_type.value[0] for job_type in job_data["job_type"])
    if job_data["job_type"]
    else None
)
```

- Assumes job_type is list of JobType enums
- Joins first element of each enum's tuple (primary language)
- Comma-separated string in DataFrame

### Email Extraction

**Lines 142-144:**

```python
job_data["emails"] = (
    ", ".join(job_data["emails"]) if job_data["emails"] else None
)
```

- Assumes emails already extracted as list
- Joins to comma-separated string

### Location String Conversion

**Lines 145-148:**

```python
if job_data["location"]:
    job_data["location"] = Location(
        **job_data["location"]
    ).display_location()
```

- Reconstructs Location model from dict
- Calls display_location() to convert to readable string
- Results in formatted location like "San Francisco, CA, USA"

### Missing Column Addition

**Lines 209-211:**

```python
for column in desired_order:
    if column not in jobs_df.columns:
        jobs_df[column] = None
```

- Adds columns not present in any scraper's results
- Fills with None values
- Ensures DataFrame has all expected columns for output stability

### Empty Result Handling

**Line 221:**

```python
else:
    return pd.DataFrame()
```

- Returns empty DataFrame if no jobs found across all sites
- No columns defined (caller must handle empty DataFrame structure)

---

## 11. README Limitations & Constraints

**Location:** `/home/claude-code/Projects/agentic-job-applier/reference-repos/jobspy/README.md` lines 123-134

### Indeed Limitations

Cannot use these in combination:
- `hours_old` + (`job_type` OR `is_remote`)
- `easy_apply` + anything else

### LinkedIn Limitations

Cannot use these in combination:
- `hours_old` + `easy_apply`
- `hours_old` + `linkedin_fetch_description`
- `easy_apply` + (`hours_old` OR `linkedin_fetch_description`)

### Site-Specific Features

- **LinkedIn easy apply:** Documented as no longer functional (line 88)
- **Google:** Requires very specific syntax in google_search_term (lines 202-203)
- **ZipRecruiter/Glassdoor:** hours_old rounded up to next day (line 101)
- **Rate limiting:** LinkedIn most restrictive, Indeed has no rate limiting (lines 179-181)

---

## 12. Critical Implementation Notes for Production Use

### Threading Without Error Isolation

**Risk:** Single scraper failure crashes entire operation. No fallback to partial results.

**Mitigation:** Wrap scrape_jobs() in try/except at caller level.

### No Deduplication

**Risk:** Same job from multiple sites creates duplicate rows. Job-level deduplication must be implemented downstream.

**Detection:** Check job_url for duplicates.

### Salary Extraction Only for USA

**Risk:** Non-USA jobs never have salary_source set, even if salary data present in description.

**Workaround:** Apply extract_salary() to non-USA descriptions manually if needed.

### Proxy Rotation Per Request

**Risk:** Proxy load not evenly distributed across all requests. First request always gets first proxy.

**Pattern:** Linear rotation through proxy list, resets at list end.

### Concurrency Gotcha

**Risk:** No explicit timeout on futures. A stuck scraper can hang the entire operation indefinitely.

**Workaround:** Use timeout context manager at caller level or configure ThreadPoolExecutor timeout.

### DataFrame Column Order Instability

**Risk:** If desired_order list changes, output schema changes. No schema versioning.

**Mitigation:** Pin desired_order in code; communicate breaking changes.

### Salary Validation Thresholds

**Risk:** Hardcoded thresholds (hourly_threshold=350) may not apply to all job markets.

**Impact:** Mis-categorized salary intervals for high-paying roles or low-paying markets.

---

## Files Reference

| File | Lines | Purpose |
|------|-------|---------|
| `jobspy/__init__.py` | 31-221 | scrape_jobs() main entry point, threading, result assembly |
| `jobspy/model.py` | 10-335 | Pydantic models: JobPost, Location, Compensation, Country, Site, JobResponse, ScraperInput |
| `jobspy/exception.py` | 9-45 | Exception hierarchy (8 site-specific exceptions) |
| `jobspy/util.py` | 19-363 | Session management, salary extraction, format conversion, logging, helper enums |
| `README.md` | 1-261 | Documentation, parameter descriptions, supported countries, limitations |
| `pyproject.toml` | 1-33 | Python 3.10+, Pydantic 2.3.0+, requests, beautifulsoup4, pandas 2.1.0+, tls-client 1.0.1+ |

---

## Summary Table: Key API Contracts

| Aspect | Value | Notes |
|--------|-------|-------|
| **Min Python** | 3.10 | Enforced in pyproject.toml |
| **Concurrency** | ThreadPoolExecutor | Per-site threads, as_completed |
| **Sites Supported** | 8 | LinkedIn, Indeed, Glassdoor, Google, ZipRecruiter, Bayt, Naukri, BDJobs |
| **Countries Supported** | 71 + 2 special | Via Country enum, Indeed/Glassdoor use country parameter |
| **Deduplication** | None | Duplicates not removed |
| **Salary Extraction** | USA only (description) | Via extract_salary() regex |
| **Result Format** | pandas.DataFrame | Sorted by site, date_posted |
| **Proxy Format** | host:port, user:pass@host:port, http://, https://, socks5:// | Round-robin rotation |
| **Exception Handling** | No isolation | Single scraper failure crashes entire operation |
| **Timeout Default** | None | Could hang indefinitely |
| **Rate Limiting** | Per-scraper | Handled at scraper level, not library |
| **Description Formats** | markdown, html, plain | Via markdownify and BeautifulSoup |

