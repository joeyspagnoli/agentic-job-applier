# JobSpy Google Jobs & ZipRecruiter Scrapers: Technical Analysis

## Executive Summary

This report provides an exhaustive technical analysis of JobSpy's two job scrapers:
1. **Google Jobs Scraper** - Uses Google's async callback API with structured JSON parsing
2. **ZipRecruiter Scraper** - Uses ZipRecruiter's official API with mobile-spoofing headers

Both scrapers employ distinct pagination strategies, anti-bot measures, and field extraction approaches. The Google scraper achieves pagination through cursor tokens; ZipRecruiter uses continue tokens. ZipRecruiter provides richer structured data; Google requires aggressive JSON parsing from HTML responses.

---

## SECTION 1: GOOGLE JOBS SCRAPER

### 1.1 Request Architecture & Endpoints

#### Primary Endpoints (google/__init__.py)
- **Initial Search URL**: `https://www.google.com/search` (line 38)
- **Async Callback URL**: `https://www.google.com/async/callback:550` (line 39)
  - Used exclusively for pagination and job fetching

#### Session Configuration (line 50-52)
```python
self.session = create_session(
    proxies=self.proxies, ca_cert=self.ca_cert, is_tls=False, has_retry=True
)
```
- **Key Detail**: `is_tls=False` - Disables TLS validation (suggests reliance on proxy/CA cert handling)
- **Retry Logic**: Enabled via `has_retry=True`

### 1.2 Initial Request Query Construction (lines 86-124)

#### Search Query Building
The scraper builds a human-readable query string by concatenating filters:

```python
query = f"{self.scraper_input.search_term} jobs"
```

Then conditionally appends:
1. **Job Type** (lines 100-108):
   - Mapping: `FULL_TIME` → "Full time", `PART_TIME` → "Part time", `INTERNSHIP` → "Internship", `CONTRACT` → "Contract"
   - Single job type per search (concatenated into query string)

2. **Location** (lines 110-111):
   - Format: `near {location}`
   - Appended directly to query

3. **Hours Old Filter** (lines 90-98, 113-115):
   - Conversion logic in `get_time_range()`:
     - `≤24 hours` → "since yesterday"
     - `≤72 hours` → "in the last 3 days"
     - `≤168 hours` → "in the last week"
     - `>168 hours` → "in the last month"
   - **Limitation**: Only 4 preset ranges; no granular date filtering

4. **Remote Filter** (lines 117-118):
   - Appends "remote" string to query

5. **Google Search Term Override** (lines 120-121):
   - If `scraper_input.google_search_term` provided, entire query is replaced
   - Allows direct control over Google search syntax

#### Initial Request Parameters (lines 123-124)
```python
params = {"q": query, "udm": "8"}
response = self.session.get(self.url, headers=headers_initial, params=params)
```

**Critical Parameters**:
- `q` = constructed query string (job search with filters embedded as text)
- `udm` = "8" (Google's **udm parameter** = Universal Database Mode 8, specific to Jobs vertical)

#### Headers Strategy (constant.py)

**headers_initial** (lines 1-27):
- Mimics browser navigation: `sec-fetch-dest: document`, `sec-fetch-mode: navigate`
- **User-Agent**: `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36...Chrome/130.0.0.0`
- **Client Hints** (SEC-CH headers): Reveal Chrome v130, macOS 10.15.7, arm64 architecture
- **Referer**: `https://www.google.com/`
- **No custom authentication** - relies on browser impersonation

**headers_jobs** (lines 29-50):
- Mimics XHR/CORS request: `sec-fetch-dest: empty`, `sec-fetch-mode: cors`
- Same user-agent and client hints (maintains consistency)
- Generic `Accept: */*`

### 1.3 Cursor Token Extraction (lines 126-128)

```python
pattern_fc = r'<div jsname="Yust4d"[^>]+data-async-fc="([^"]+)"'
match_fc = re.search(pattern_fc, response.text)
data_async_fc = match_fc.group(1) if match_fc else None
```

**Mechanism**:
- Regex extracts `data-async-fc` attribute from a specific `<div>` with `jsname="Yust4d"`
- This attribute is a forward cursor token for pagination
- **If no match**: Returns `None` (line 54-57), suggesting ≤10 initial results only

### 1.4 Initial Page Job Parsing (lines 129-135)

```python
jobs_raw = find_job_info_initial_page(response.text)
for job_raw in jobs_raw:
    job_post = self._parse_job(job_raw)
    if job_post:
        jobs.append(job_post)
```

#### find_job_info_initial_page() in util.py (lines 26-41)

Uses regex pattern to extract JSON arrays from HTML:
```python
pattern = f'520084652":(' + r"\[.*?\]\s*])\s*}\s*]\s*]\s*]\s*]\s*]"
```

**What this regex does**:
- Searches for literal string `"520084652":` followed by a JSON array
- **520084652** is a hidden constant (likely internal Google Jobs ID)
- Extracts everything matching the nested bracket structure
- Parses extracted JSON and yields individual job arrays

### 1.5 Pagination Mechanism (lines 137-165)

#### Next Page Request Structure (lines 137-139)
```python
def _get_jobs_next_page(self, forward_cursor: str) -> Tuple[list[JobPost], str]:
    params = {"fc": [forward_cursor], "fcv": ["3"], "async": [async_param]}
    response = self.session.get(self.jobs_url, headers=headers_jobs, params=params)
```

**Parameters**:
- `fc` = forward cursor (pagination token, array value)
- `fcv` = "3" (cursor format version, array value)
- `async` = `async_param` from constant.py (giant encoded string, likely base64 metadata)

**async_param Details** (constant.py lines 52):
- 1000+ character encoded string
- Contains: `_basejs:/xjs/_/js/...`, `_basecss:/xjs/_/ss/...`, `_basecomb:/xjs/_/js/...`
- Appears to be resource manifest/cache buster for JavaScript/CSS dependencies
- **Purpose**: Likely included to match browser requests exactly

#### Pagination Loop Logic (lines 62-78)
```python
while (
    len(self.seen_urls) < scraper_input.results_wanted + scraper_input.offset
    and forward_cursor
):
    jobs, forward_cursor = self._get_jobs_next_page(forward_cursor)
    if not jobs:
        log.info(f"found no jobs on page: {page}")
        break
    job_list += jobs
    page += 1
```

**Key Behaviors**:
- Continues until: (1) seen_urls reaches desired count OR (2) forward_cursor is None
- Breaks early if a page yields no jobs
- **Deduplication**: Uses `seen_urls` set keyed by job URL
- **Result Capping** (line 48): Max results hardcoded to 900 (`scraper_input.results_wanted = min(900, scraper_input.results_wanted)`)

#### Response Parsing for Pages (lines 142-165)
```python
def _parse_jobs(self, job_data: str) -> Tuple[list[JobPost], str]:
    start_idx = job_data.find("[[[")
    end_idx = job_data.rindex("]]]") + 3
    s = job_data[start_idx:end_idx]
    parsed = json.loads(s)[0]
```

**Extraction Strategy**:
- Finds first occurrence of `[[[` and last occurrence of `]]]`
- Extracts JSON array and parses first element `[0]`
- Iterates through array: `for array in parsed: _, job_data = array`
- Recursively calls `find_job_info()` on each job_data element

**find_job_info() in util.py (lines 8-23)**:
- Recursive dict/list traversal
- Searches for specific key `"520084652"` (same ID as initial parsing)
- Returns first match where key maps to a list

### 1.6 Field Extraction & JobPost Mapping (lines 167-202)

#### Raw Data Structure (job_info list indices)
The scraper treats job data as a fixed-index list:

| Index | Field | Usage |
|-------|-------|-------|
| 0 | Title | Job title |
| 1 | Company | Company name |
| 2 | Location | Full location string |
| 3 | [0][0] | Job URL (nested) |
| 12 | Days Posted | Recency string (e.g., "10 days ago") |
| 19 | Description | Full HTML description |
| 28 | Job ID | Unique identifier |

#### Location Parsing (lines 175-178)
```python
location = city = job_info[2]
state = country = date_posted = None
if location and "," in location:
    city, state, *country = [*map(lambda x: x.strip(), location.split(","))]
```

**Logic**:
- Splits location by comma
- First segment: city
- Second segment: state
- Remaining segments: country (potentially multi-word, stored as list)
- **Assumes format**: "City, State, Country" (e.g., "San Francisco, CA, United States")

#### Date Parsing (lines 180-184)
```python
days_ago_str = job_info[12]
if type(days_ago_str) == str:
    match = re.search(r"\d+", days_ago_str)
    days_ago = int(match.group()) if match else None
    date_posted = (datetime.now() - timedelta(days=days_ago)).date()
```

**Approach**:
- Expects string like "10 days ago" or "3 days ago"
- Extracts first integer with regex `\d+`
- Calculates date by subtracting days from current date
- **Limitation**: Non-numeric dates (e.g., "Just now") return None

#### Remote Detection (line 197)
```python
is_remote="remote" in description.lower() or "wfh" in description.lower()
```

**Simple keyword matching**:
- Searches description for "remote" or "wfh"
- **False negatives**: Misses variations like "work from home", "distributed", etc.

#### JobPost Construction (lines 188-201)
```python
job_post = JobPost(
    id=f"go-{job_info[28]}",  # Prefixed with "go-"
    title=title,
    company_name=company_name,
    location=Location(city=city, state=state, country=country[0] if country else None),
    job_url=job_url,
    date_posted=date_posted,
    is_remote=is_remote,  # Boolean
    description=description,
    emails=extract_emails_from_text(description),
    job_type=extract_job_type(description),  # From description parsing
)
```

**Extracted Fields**:
- **ID**: Format "go-{internal_id}"
- **Job Type**: Inferred from description text (not from structured field)
- **Emails**: Regex extraction from description
- **Compensation**: Not extracted (always None)
- **Listing Type**: Not extracted

### 1.7 Anti-Bot & Rate Limiting Measures

**Observations**:

1. **No explicit rate limiting**: No `time.sleep()` between requests (unlike ZipRecruiter's 5s delay)
2. **Proxy support**: Accepts proxy list at initialization (line 25)
3. **CA Certificate handling**: Supports custom CA certs (line 25)
4. **TLS disabled**: `is_tls=False` in session creation (line 51)
5. **Retry mechanism**: Built into session (`has_retry=True`)
6. **Browser impersonation**: Extensive client hints and realistic headers
7. **Request volume limit**: Hard cap at 900 results (line 48)

**Likely Detection Vectors**:
- Missing/wrong `udm=8` parameter
- Absence of client hint headers
- Invalid async_param format
- Request sequencing (no natural pacing)

---

## SECTION 2: ZIPRECRUITER SCRAPER

### 2.1 Request Architecture & Endpoints

#### Primary Endpoints (ziprecruiter/__init__.py)
- **Base URL**: `https://www.ziprecruiter.com` (line 37)
- **API URL**: `https://api.ziprecruiter.com` (line 38)
- **Jobs API**: `https://api.ziprecruiter.com/jobs-app/jobs` (line 99)
- **Event API**: `https://api.ziprecruiter.com/jobs-app/event` (line 218)

#### Session Configuration (lines 48-51)
```python
self.session = create_session(proxies=proxies, ca_cert=ca_cert)
self.session.headers.update(headers)
self._get_cookies()
```

**Flow**:
1. Creates session with optional proxies
2. Updates session headers with default headers
3. Calls `_get_cookies()` to establish API session

### 2.2 Mobile Spoofing & Header Strategy

#### headers (constant.py lines 1-10)

```python
headers = {
    "Host": "api.ziprecruiter.com",
    "accept": "*/*",
    "x-zr-zva-override": "100000000;vid:ZT1huzm_EQlDTVEc",
    "x-pushnotificationid": "0ff4983d38d7fc5b3370297f2bcffcf4b3321c418f5c22dd152a0264707602a0",
    "x-deviceid": "D77B3A92-E589-46A4-8A39-6EF6F1D86006",
    "user-agent": "Job Search/87.0 (iPhone; CPU iOS 16_6_1 like Mac OS X)",
    "authorization": "Basic YTBlZjMyZDYtN2I0Yy00MWVkLWEyODMtYTI1NDAzMzI0YTcyOg==",
    "accept-language": "en-US,en;q=0.9",
}
```

**Strategic Headers**:
- **User-Agent**: iOS app ("Job Search/87.0" on iPhone, iOS 16.6.1)
- **Authorization**: Basic auth (base64-encoded credentials)
  - Decoded: `a0ef32d6-7b4c-41ed-a283-a25403324a72:` (UUID format, likely hardcoded API key)
- **Custom Headers**:
  - `x-zr-zva-override`: Contains "vid:" (visitor ID) hash
  - `x-pushnotificationid`: Push notification token (hardcoded)
  - `x-deviceid`: Device UUID (hardcoded across all requests)

**Purpose**: Mimics official iOS app to bypass bot detection

### 2.3 Cookie/Session Initialization

#### _get_cookies() Method (lines 214-219)
```python
def _get_cookies(self):
    url = f"{self.api_url}/jobs-app/event"
    self.session.post(url, data=get_cookie_data)
```

**No response handling** - fires POST to `/jobs-app/event` with device telemetry

#### get_cookie_data (constant.py lines 12-29)

Fixed list of tuples sent as POST data:
```python
get_cookie_data = [
    ("event_type", "session"),
    ("logged_in", "false"),
    ("number_of_retry", "1"),
    ("property", "model:iPhone"),
    ("property", "os:iOS"),
    ("property", "locale:en_us"),
    ("property", "app_build_number:4734"),
    ("property", "app_version:91.0"),
    ("property", "manufacturer:Apple"),
    ("property", "timestamp:2025-01-12T12:04:42-06:00"),
    ("property", "screen_height:852"),
    ("property", "os_version:16.6.1"),
    ("property", "source:install"),
    ("property", "screen_width:393"),
    ("property", "device_model:iPhone 14 Pro"),
    ("property", "brand:Apple"),
]
```

**Telemetry Sent**:
- Session event type (not logged in)
- Device properties: iPhone 14 Pro, iOS 16.6.1, screen 852x393
- App version: 91.0 (build 4734)
- Hardcoded timestamp: `2025-01-12T12:04:42-06:00` (always this value!)
- Locale: en_us

**Anti-Detection Measure**: Registers device fingerprint before scraping

### 2.4 Query Parameter Construction

#### add_params() Function (ziprecruiter/util.py lines 4-24)

```python
def add_params(scraper_input) -> dict[str, str | int]:
    params: dict[str, str | int] = {
        "search": scraper_input.search_term,
        "location": scraper_input.location,
    }
```

**Base Parameters**:
- `search`: Raw search term string
- `location`: Location string (no parsing)

**Conditional Parameters**:

1. **Hours Old Filter** (lines 9-10):
   ```python
   if scraper_input.hours_old:
       params["days"] = max(scraper_input.hours_old // 24, 1)
   ```
   - Converts hours to days (integer division)
   - Minimum 1 day
   - **API parameter name**: "days"

2. **Job Type Filter** (lines 12-15):
   ```python
   job_type_map = {JobType.FULL_TIME: "full_time", JobType.PART_TIME: "part_time"}
   if scraper_input.job_type:
       job_type = scraper_input.job_type
       params["employment_type"] = job_type_map.get(job_type, job_type.value[0])
   ```
   - Maps to: FULL_TIME → "full_time", PART_TIME → "part_time"
   - Fallback: Uses first character of enum value
   - **Only 2 mapped types** (internships, contracts ignored)

3. **Easy Apply** (lines 17-18):
   ```python
   if scraper_input.easy_apply:
       params["zipapply"] = 1
   ```
   - **API parameter**: "zipapply" (boolean as 1)

4. **Remote Filter** (lines 19-20):
   ```python
   if scraper_input.is_remote:
       params["remote"] = 1
   ```
   - Simple binary flag

5. **Distance/Radius** (lines 21-22):
   ```python
   if scraper_input.distance:
       params["radius"] = scraper_input.distance
   ```
   - Distance in miles (assumed)

**Final Step** (line 24): Removes None values
```python
return {k: v for k, v in params.items() if v is not None}
```

### 2.5 Pagination Mechanism

#### Main Pagination Loop (lines 57-83)

```python
max_pages = math.ceil(scraper_input.results_wanted / self.jobs_per_page)  # 20 per page
for page in range(1, max_pages + 1):
    if len(job_list) >= scraper_input.results_wanted:
        break
    if page > 1:
        time.sleep(self.delay)  # 5 second delay
    log.info(f"search page: {page} / {max_pages}")
    jobs_on_page, continue_token = self._find_jobs_in_page(
        scraper_input, continue_token
    )
```

**Key Behaviors**:
- **Jobs per page**: 20 (line 54)
- **Rate limiting**: 5 second `time.sleep()` between pages (line 72, delay=5)
- **Early termination**: Breaks if enough results collected or no continue_token

#### API Request (lines 85-114)

```python
def _find_jobs_in_page(
    self, scraper_input: ScraperInput, continue_token: str | None = None
) -> tuple[list[JobPost], str | None]:
    params = add_params(scraper_input)
    if continue_token:
        params["continue_from"] = continue_token
    
    res = self.session.get(f"{self.api_url}/jobs-app/jobs", params=params)
    if res.status_code not in range(200, 400):
        if res.status_code == 429:
            err = "429 Response - Blocked by ZipRecruiter for too many requests"
        else:
            err = f"ZipRecruiter response status code {res.status_code}..."
        log.error(err)
        return jobs_list, ""
```

**Endpoint**: `https://api.ziprecruiter.com/jobs-app/jobs`

**Parameters**:
- All parameters from `add_params()` (search, location, days, remote, etc.)
- If paginating: `continue_from={token}` (line 97)

**Error Handling**:
- **429 (Too Many Requests)**: Returns empty list with error message (line 101-102)
- **Other errors**: Checks for proxy-related messages (line 109)
- Returns empty job list + empty string (falsy token) to break loop

#### Response Parsing (lines 115-122)

```python
res_data = res.json()
jobs_list = res_data.get("jobs", [])
next_continue_token = res_data.get("continue", None)

with ThreadPoolExecutor(max_workers=self.jobs_per_page) as executor:
    job_results = [executor.submit(self._process_job, job) for job in jobs_list]

job_list = list(filter(None, (result.result() for result in job_results)))
return job_list, next_continue_token
```

**JSON Response Structure**:
```json
{
  "jobs": [...],
  "continue": "next_page_token"
}
```

**Parallel Processing**:
- Uses `ThreadPoolExecutor` with `max_workers=20` (jobs_per_page)
- Submits each job to `_process_job()` concurrently
- Filters out None results (failed parses or duplicates)

### 2.6 Field Extraction & JobPost Mapping

#### _process_job() Method (lines 124-177)

Raw data comes as dict with keys:

| Key | Field | Processing |
|-----|-------|------------|
| "name" | Job title | Direct assignment |
| "listing_key" | Job ID | URL construction + ID prefix |
| "job_description" | HTML description | Markdown conversion optional |
| "buyer_type" | Listing type | Direct assignment |
| "hiring_company" | Company info | Extract nested "name" |
| "job_country" | Country code | "US" → "usa", else "canada" |
| "job_city" | City | Direct assignment |
| "job_state" | State | Direct assignment |
| "employment_type" | Job type | Via get_job_type_enum() |
| "posted_time" | Date | ISO format, strip 'Z' |
| "compensation_interval" | Comp period | "annual" → "yearly" |
| "compensation_min" | Min salary | Integer conversion |
| "compensation_max" | Max salary | Integer conversion |
| "compensation_currency" | Currency | Direct assignment (USD/CAD) |

#### URL Construction (line 129)
```python
job_url = f"{self.base_url}/jobs//j?lvk={job['listing_key']}"
```

**Format**: `https://www.ziprecruiter.com/jobs//j?lvk={listing_key}`
- Note: Double slash `//j` in path (unusual but intentional)
- `lvk` parameter = "listing value key"

#### Location Parsing (lines 145-147)
```python
country_value = "usa" if job.get("job_country") == "US" else "canada"
country_enum = Country.from_string(country_value)

location = Location(
    city=job.get("job_city"), state=job.get("job_state"), country=country_enum
)
```

**Logic**:
- Binary: US → "usa", everything else → "canada"
- **Limitation**: No other countries supported
- Converts string to enum via `Country.from_string()`

#### Job Type Extraction (lines 148-150)
```python
job_type = get_job_type_enum(
    job.get("employment_type", "").replace("_", "").lower()
)
```

**Transformations**:
1. Get "employment_type" (default empty string)
2. Remove underscores: "full_time" → "fulltime"
3. Lowercase
4. Pass to `get_job_type_enum()` lookup

#### get_job_type_enum() Function (ziprecruiter/util.py lines 27-31)

```python
def get_job_type_enum(job_type_str: str) -> list[JobType] | None:
    for job_type in JobType:
        if job_type_str in job_type.value:
            return [job_type]
    return None
```

**Matching Strategy**:
- Iterates through JobType enum
- Checks if input string is **substring of** enum.value tuple
- Returns list containing matching type or None

**Example matches**:
- "fulltime" matches JobType.FULL_TIME (value contains "fulltime")
- "parttime" matches JobType.PART_TIME

#### Date Parsing (line 151)
```python
date_posted = datetime.fromisoformat(job["posted_time"].rstrip("Z")).date()
```

**Process**:
1. Strip trailing 'Z' from ISO string
2. Parse via `fromisoformat()` (assumes ISO 8601 format)
3. Extract `.date()` component

**Example**: "2025-01-12T14:30:00Z" → 2025-01-12

#### Compensation Parsing (lines 152-156)
```python
comp_interval = job.get("compensation_interval")
comp_interval = "yearly" if comp_interval == "annual" else comp_interval
comp_min = int(job["compensation_min"]) if "compensation_min" in job else None
comp_max = int(job["compensation_max"]) if "compensation_max" in job else None
comp_currency = job.get("compensation_currency")
```

**Transformations**:
- Interval: "annual" → "yearly" (normalize)
- Min/Max: Convert to integers if present
- Currency: Direct assignment (USD, CAD expected)

**Compensation Object** (line 165-170):
```python
compensation=Compensation(
    interval=comp_interval,
    min_amount=comp_min,
    max_amount=comp_max,
    currency=comp_currency,
)
```

#### Full Description via Direct Fetch (line 157)
```python
description_full, job_url_direct = self._get_descr(job_url)
```

**Trigger**: After API job extract, fetches job page HTML for enriched description

### 2.7 Description Enrichment via Web Scrape

#### _get_descr() Method (lines 179-212)

```python
def _get_descr(self, job_url):
    res = self.session.get(job_url, allow_redirects=True)
    if res.ok:
        soup = BeautifulSoup(res.text, "html.parser")
        job_descr_div = soup.find("div", class_="job_description")
        company_descr_section = soup.find("section", class_="company_description")
```

**HTML Parsing**:
- Fetches job page with redirects enabled
- Extracts two elements:
  1. `<div class="job_description">` - Job duties
  2. `<section class="company_description">` - Company info

#### Description Cleaning (lines 186-196)
```python
job_description_clean = (
    remove_attributes(job_descr_div).prettify(formatter="html")
    if job_descr_div
    else ""
)
company_description_clean = (
    remove_attributes(company_descr_section).prettify(formatter="html")
    if company_descr_section
    else ""
)
description_full = job_description_clean + company_description_clean
```

**Process**:
1. Removes HTML attributes from elements (via `remove_attributes()`)
2. Prettifies output (adds newlines, indentation)
3. Concatenates job + company descriptions

#### JSON Embedded Direct URL Extraction (lines 198-207)
```python
try:
    script_tag = soup.find("script", type="application/json")
    if script_tag:
        job_json = json.loads(script_tag.string)
        job_url_val = job_json["model"].get("saveJobURL", "")
        m = re.search(r"job_url=(.+)", job_url_val)
        if m:
            job_url_direct = m.group(1)
except:
    job_url_direct = None
```

**Strategy**:
- Searches for `<script type="application/json">` tag
- Parses JSON and navigates to `["model"]["saveJobURL"]`
- Extracts query parameter value after `job_url=`
- **Purpose**: Gets direct application URL (bypasses ZipRecruiter tracking)

**Example URL structure**: `...?job_url=https%3A%2F%2Fcompany.com%2Fapply`

#### Description Format Conversion (lines 209-210)
```python
if self.scraper_input.description_format == DescriptionFormat.MARKDOWN:
    description_full = markdown_converter(description_full)
```

**Optional markdown conversion** using `markdown_converter()` utility

#### Final JobPost Construction (lines 159-177)
```python
return JobPost(
    id=f'zr-{job["listing_key"]}',
    title=title,
    company_name=company,
    location=location,
    job_type=job_type,  # List[JobType]
    compensation=compensation,
    date_posted=date_posted,
    job_url=job_url,  # ZipRecruiter URL
    description=description_full if description_full else description,
    emails=extract_emails_from_text(description) if description else None,
    job_url_direct=job_url_direct,  # Direct company URL
    listing_type=listing_type,
)
```

**Key Fields**:
- **ID**: Format "zr-{listing_key}"
- **job_url**: Tracked ZipRecruiter link
- **job_url_direct**: Direct application URL (extracted from page)
- **job_type**: Returns list (unlike Google which returns None/extracted)

### 2.8 Anti-Bot & Rate Limiting Measures

#### Explicit Rate Limiting
- **5-second delay** between pagination requests (line 72)
- Only applies after page 1

#### Mobile Spoofing
- iOS app user-agent with version
- Hardcoded device IDs, push notification tokens
- Device telemetry matching iPhone 14 Pro

#### Authentication
- Basic auth header with hardcoded UUID
- Device fingerprinting via event API call

#### Error Handling
- **429 Response**: Gracefully breaks pagination loop
- Proxy error detection and logging

#### Deduplication
- Tracks `seen_urls` set (line 55) by constructed URL
- Skips duplicates in response

---

## SECTION 3: COMPARATIVE ANALYSIS

### 3.1 Request Strategy Comparison

| Aspect | Google | ZipRecruiter |
|--------|--------|--------------|
| **Request Type** | Browser navigation + XHR | Mobile app API |
| **Query Format** | Natural language search string | Structured params |
| **Initial Setup** | Single request to search page | POST to event API for telemetry |
| **Pagination Token** | Forward cursor (data-async-fc) | Continue token |
| **Jobs Per Page** | 10 | 20 |
| **Results Cap** | 900 | Unlimited (by API) |
| **Rate Limit** | None explicit | 5s delay + 429 handling |

### 3.2 Data Extraction Comparison

| Aspect | Google | ZipRecruiter |
|--------|--------|--------------|
| **API Response Format** | Custom JSON structure | Standard JSON |
| **Parsing Strategy** | Recursive dict traversal | Direct dict access |
| **Parallel Processing** | No | ThreadPoolExecutor (20 workers) |
| **Job Title Source** | Structured list[0] | Direct JSON key |
| **Company Source** | Structured list[1] | Nested dict |
| **Location** | Single string (parsed) | Separate fields (city, state) |
| **Description** | API response | API + HTML web scrape |
| **Date Format** | "X days ago" string | ISO 8601 |
| **Compensation** | Not extracted | Full extraction (min, max, currency, interval) |

### 3.3 Field Coverage Comparison

| Field | Google | ZipRecruiter |
|-------|--------|--------------|
| Title | ✓ | ✓ |
| Company | ✓ | ✓ |
| Location | ✓ (parsed) | ✓ (structured) |
| URL | ✓ | ✓ + direct |
| Description | ✓ | ✓ (enhanced via web scrape) |
| Date Posted | ✓ | ✓ |
| Remote | ✓ (keyword search) | ✓ (filter only) |
| Job Type | Partial (inferred) | ✓ (2 types mapped) |
| Salary | ✗ | ✓ (min, max, currency) |
| Emails | ✓ (extracted) | ✓ (extracted) |
| ID | ✓ | ✓ |

### 3.4 Filter Capability Comparison

| Filter | Google | ZipRecruiter | Notes |
|--------|--------|--------------|-------|
| Search Term | ✓ | ✓ | Google supports custom syntax |
| Location | ✓ | ✓ | Google: "near {loc}", ZR: direct param |
| Job Type | ✓ (4 types) | ✓ (2 types) | Google: FT, PT, Int, Contract; ZR: FT, PT |
| Hours Old | ✓ (4 ranges) | ✓ (days) | Google: discrete; ZR: granular |
| Remote | ✓ | ✓ | Google: text query; ZR: binary param |
| Distance | ✗ | ✓ | ZipRecruiter supports radius |
| Easy Apply | ✗ | ✓ | ZipRecruiter only |

### 3.5 Known Failure Modes & Limitations

#### Google Scraper
1. **No initial cursor**: Returns empty if <10 results on first page
2. **Date parsing failure**: "Just now" or non-numeric dates return None
3. **Remote detection**: Simplistic keyword matching (misses variations)
4. **Job type extraction**: Always inferred from description, never exact
5. **No compensation data**: Always None
6. **No distance filtering**: Only location string
7. **Hardcoded 900 result limit**: Cannot get more
8. **Location format assumption**: Expects "City, State, Country" structure

#### ZipRecruiter Scraper
1. **Country limitation**: Binary US/Canada only
2. **Job type mapping**: Only FULL_TIME and PART_TIME explicitly mapped
3. **Hardcoded timestamp**: Device event always uses same datetime
4. **Web scrape dependency**: Extra latency for each job (per-job HTML fetch)
5. **Device hardcoding**: All requests use identical device ID/push token
6. **No salary in API response**: Requires parsing after fetch?
   - **Note**: Actually includes comp_min/max in API response (lines 154-155)
   - Compensation IS in API response, not additional scrape

### 3.6 Anti-Detection Sophistication Ranking

**Google**: 
- Browser-grade headers (extensive client hints)
- TLS bypass (is_tls=False)
- Realistic async parameter manifest
- No device fingerprinting

**ZipRecruiter**:
- Mobile app spoofing (iOS specific)
- Device fingerprint registration
- Hardcoded authorization token
- Device telemetry tracking

**Winner**: ZipRecruiter (more detailed spoofing profile)

---

## SECTION 4: CONSTANTS & INTERNAL API TAXONOMY

### 4.1 Google Constants

#### async_param (constant.py line 52)
Encoded resource manifest, contains paths to:
- `_basejs`: Base JavaScript bundle paths
- `_basecss`: Base CSS stylesheet paths
- `_basecomb`: Combined resource paths
- Versioned with hashes (e.g., `k=xjs.s.en_US.JwveA-JiKmg.2018.O`)

**Implication**: Google provides resource cache-buster to ensure up-to-date client code

#### Job ID Constant: 520084652 (util.py lines 12, 27)
- Hardcoded in two places (initial page + pagination)
- Treated as magic key in recursive JSON traversal
- Likely internal Google Jobs product code or feature flag

#### Headers Version
- Chrome v130.0.0.0
- macOS 10.15.7 (Catalina)
- arm64 architecture

### 4.2 ZipRecruiter Constants

#### Authorization Token
`a0ef32d6-7b4c-41ed-a283-a25403324a72:` (base64 decoded)
- UUID format suggests API key tied to app installation

#### Device ID
`D77B3A92-E589-46A4-8A39-6EF6F1D86006` (UUID)
- Used for session tracking across requests
- Same for all scraper instances (not randomized)

#### VID (Visitor ID)
`ZT1huzm_EQlDTVEc` (in x-zr-zva-override header)
- Hash-like format, persistent across sessions
- Possibly derived from device ID

#### Device Fingerprint
- iPhone 14 Pro
- iOS 16.6.1
- Screen: 852x393
- App version: 91.0 (build 4734)
- Hardcoded timestamp: `2025-01-12T12:04:42-06:00`

**Implication**: All instances use identical device fingerprint (vulnerability to account-level blocking)

#### Job Type Enum Mapping
```python
FULL_TIME: ["fulltime", "full-time", "full_time"]  # (assumed)
PART_TIME: ["parttime", "part-time", "part_time"]  # (assumed)
```

Substring matching allows flexible input parsing

---

## SECTION 5: CRITICAL IMPLEMENTATION DETAILS

### 5.1 Google Scraper Edge Cases

1. **Duplicate handling**: Seen URLs tracked globally, persists across pagination
2. **Job data is fixed-position list**: Refactoring list indices would break scraper
3. **Nested URL access**: job_info[3][0][0] suggests deeply nested structure vulnerability
4. **Async param is critical**: Omitting/wrong format likely causes 403/429

### 5.2 ZipRecruiter Scraper Edge Cases

1. **Per-job web fetch**: Every job triggers HTTP request (20 per page by default)
   - **Performance**: N+1 problem for description enrichment
   - **Total requests**: 1 (event) + 1 (API search) + 20 (per-job) = 22 per page
2. **ThreadPoolExecutor with max_workers=20**: Parallel processing of jobs
   - **Implication**: I/O bound bottleneck at 20 concurrent requests
3. **No retry logic in _get_descr()**: HTML fetch failures silently return empty description
4. **Markdown conversion**: Applied to both API description AND web-scraped description

### 5.3 Rate Limiting Reality Check

**Google**:
- No sleep between requests
- Session retries enabled (could be exponential backoff)
- High risk of IP blocking without proxies

**ZipRecruiter**:
- 5 second hardcoded delay
- Explicit 429 handling (breaks pagination)
- More resilient to rate limits

---

## SECTION 6: INTEGRATION WITH JOBSPY FRAMEWORK

### 6.1 Shared Interfaces

Both inherit from `Scraper` base class:
```python
class Scraper:
    def scrape(self, scraper_input: ScraperInput) -> JobResponse
```

**ScraperInput fields used**:
- `search_term`: Required
- `location`: Optional
- `job_type`: Optional
- `hours_old`: Optional
- `is_remote`: Optional
- `distance`: ZipRecruiter only
- `easy_apply`: ZipRecruiter only
- `google_search_term`: Google only
- `results_wanted`: Both
- `offset`: Google only
- `description_format`: ZipRecruiter only

**JobResponse**: List of JobPost objects with optional errors

### 6.2 Utility Function Dependencies

**Common utilities** (jobspy/util.py):
- `extract_emails_from_text()` - Regex email extraction
- `extract_job_type()` - Infer JobType from text
- `create_session()` - Setup HTTP session with proxies/retries
- `markdown_converter()` - HTML to Markdown (ZR only)
- `remove_attributes()` - Strip HTML attributes (ZR only)
- `create_logger()` - Consistent logging

**ZipRecruiter specific**:
- `get_job_type_enum()` - Mapping employment_type to JobType
- `add_params()` - Query parameter construction

---

## SECTION 7: SECURITY & DETECTION RISKS

### 7.1 Google Scraper Risks

1. **TLS disabled**: Susceptible to MITM if not using trustworthy proxy
2. **async_param hardcoded**: Version mismatch could trigger bot detection
3. **No randomization**: Same behavior signature across all instances
4. **List indexing fragile**: Changes to response structure (e.g., new fields) break parsing

### 7.2 ZipRecruiter Scraper Risks

1. **Hardcoded credentials**: Single API key shared across all users
   - **Impact**: Account-level rate limits affect all instances
   - **Mitigation**: API key could be easily revoked if discovered
2. **Identical device fingerprints**: All scrapers look identical to ZipRecruiter
   - **Risk**: Blocking one user blocks all
3. **Hardcoded timestamp**: `2025-01-12T12:04:42-06:00` never changes
   - **Detection vector**: Device event timestamp older than current date
4. **Per-job fetches**: Linear scaling of requests (performance vulnerability)

---

## SECTION 8: FUTURE MAINTENANCE RISKS

### 8.1 Google Scraper

- **async_param**: Likely needs monthly updates (Chrome version bumps)
- **520084652 constant**: May change if Google refactors Jobs UI
- **Header format**: Client hints spec evolving; future Chrome versions may add/remove fields
- **Query string parsing**: Relies on natural language integration; format changes break filtering

### 8.2 ZipRecruiter Scraper

- **API version**: Currently hits `/jobs-app/jobs` endpoint (v1 implied)
- **Device event endpoint**: `/jobs-app/event` could be deprecated
- **HTML structure parsing**: `<div class="job_description">` and `<section class="company_description">` hard-coded
- **JSON extraction from script tag**: Relies on `["model"]["saveJobURL"]` path

---

## CONCLUSION

**Google Scraper**: Uses undocumented async callback API with minimal structured data extraction. Requires aggressive JSON parsing, fixed-position list access, and maintains browser impersonation. No rate limiting; high detection risk without proxies. Hardcoded 900 result limit. No compensation data.

**ZipRecruiter Scraper**: Uses official mobile app API with rich JSON responses. Implements explicit rate limiting and device fingerprinting spoofing. Enriches results via per-job web scraping. Risks account-level blocking due to hardcoded credentials and device fingerprints. More resilient but more complex (N+1 fetch pattern).

Both lack production-grade error recovery, rely on magic constants, and have fragile parsing logic vulnerable to site structure changes.
