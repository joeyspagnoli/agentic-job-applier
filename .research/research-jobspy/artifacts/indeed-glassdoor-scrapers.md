# Technical Report: Indeed and Glassdoor Scrapers in JobSpy

**Date**: 2026-05-19  
**Scope**: Exhaustive analysis of HTTP request structures, endpoints, filtering, pagination, and data extraction for Indeed and Glassdoor job scrapers

---

## INDEED SCRAPER

### 1. HTTP Request Structure

#### Protocol & Authentication
- **API Type**: GraphQL (not REST or HTML parsing)
- **Base Endpoint**: `https://apis.indeed.com/graphql` (line 48, indeed/__init__.py)
- **Method**: POST with JSON payload
- **Session Type**: Custom session with TLS disabled (`is_tls=False`, line 39, indeed/__init__.py)
- **Proxy Support**: Optional proxies and custom CA certificates supported (line 31, indeed/__init__.py)

#### Headers
**Source**: Lines 100-109, indeed/constant.py

```
Host: apis.indeed.com
content-type: application/json
indeed-api-key: 161092c2017b5bbab13edb12461a62d5a833871e7cad6d9d475304573de67ac8
accept: application/json
indeed-locale: en-US
accept-language: en-US,en;q=0.9
user-agent: Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Indeed App 193.1
indeed-app-info: appv=193.1; appid=com.indeed.jobsearch; osv=16.6.1; os=ios; dtype=phone
```

**Header Dynamics**:
- `indeed-api-key` is hardcoded (potential security concern)
- `indeed-locale` defaults to `en-US` but can be overridden (line 59, indeed/__init__.py)
- `indeed-co` header added dynamically from country code (line 60, indeed/__init__.py)
- User-Agent spoofs an iOS Indeed app (version 193.1)

### 2. Endpoint URLs & Query Parameters

#### GraphQL Query Structure
**Source**: Lines 1-98, indeed/constant.py

The scraper uses a single GraphQL query template `job_search_query` with variable substitution:

```graphql
query GetJobData {
    jobSearch(
        {what}
        {location}
        limit: 100
        {cursor}
        sort: RELEVANCE
        {filters}
    ) {
        pageInfo {
            nextCursor
        }
        results {
            trackingKey
            job { ... }
        }
    }
}
```

#### Query Variable Injection
**Source**: Lines 92-107, indeed/__init__.py

1. **Search Term** (`what`): 
   - Wrapped as `what: "search_term"` if provided
   - Escaped for GraphQL (line 93): `search_term.replace('"', '\\"')`
   - Can be empty string if no search term

2. **Location** (`location`):
   - Format: `location: {where: "location_string", radius: distance_miles, radiusUnit: MILES}`
   - Example: `location: {where: "New York, NY", radius: 25, radiusUnit: MILES}`
   - Omitted if no location specified

3. **Cursor** (`cursor`):
   - Format: `cursor: "next_cursor_value"`
   - Enables pagination (details in section 3)

4. **Filters** (`filters`):
   - Complex structure, see section 7

5. **Date Filter**:
   - `dateOnIndeed` parameter (line 104): hours in past (integer)
   - Passed directly to GraphQL query

#### Request Payload Structure
**Source**: Lines 108-119, indeed/__init__.py

```python
payload = {
    "query": query,
}
response = self.session.post(
    self.api_url,
    headers=api_headers_temp,
    json=payload,
    timeout=10,
    verify=False,
)
```

- Single JSON payload with `query` key containing formatted GraphQL string
- 10-second timeout
- SSL verification disabled (`verify=False`)
- POST request via session (requests library)

### 3. Pagination Logic & Limits

**Source**: Lines 62-81, indeed/__init__.py

#### Pagination Mechanism
- **Cursor-based pagination** (not offset-based)
- Initial cursor is `None` (line 64)
- Each response contains `data["data"]["jobSearch"]["pageInfo"]["nextCursor"]` (line 127)
- Cursor is passed to next request: `cursor: "next_cursor_value"`

#### Pagination Loop
```python
while len(self.seen_urls) < scraper_input.results_wanted + scraper_input.offset:
    jobs, cursor = self._scrape_page(cursor)
    if not jobs:
        break
```

**Logic**:
- Continues until total unique job URLs seen >= (results_wanted + offset)
- Breaks if a page returns empty jobs
- Loops via `page` counter for logging (line 75)

#### Per-Page Limit
- **Hard-coded**: 100 jobs per page (line 42: `self.jobs_per_page = 100`)
- **GraphQL limit**: 100 (line 6 in constant.py: `limit: 100`)
- Offset handling: Applied post-fetch (lines 77-80)
  ```python
  return JobResponse(
      jobs=job_list[scraper_input.offset : scraper_input.offset + scraper_input.results_wanted]
  )
  ```

#### Seen URLs Tracking
- **Purpose**: Prevent duplicates across pages
- **Data Structure**: Set (`self.seen_urls`, line 44)
- **Key Format**: `https://domain.indeed.com/viewjob?jk=job_key` (line 201)
- **Check**: Line 202-203: Skip job if URL already in set

### 4. Rate Limiting / Anti-Bot / CAPTCHA Handling

**Status**: Minimal explicit handling found.

#### Response Validation
- **Source**: Lines 120-124, indeed/__init__.py
- **Check**: `if not response.ok` (HTTP status check)
- **Failure Mode**: Logs warning and returns empty jobs, breaks pagination
- **No retry logic** in main scraper

#### Headers That May Bypass Detection
- iOS app user-agent (spoofs mobile Indeed app)
- `indeed-app-info` header mimics app metadata
- `indeed-api-key` header (pre-authentication, bypasses typical bot detection)

#### No Explicit Handling For
- CAPTCHA detection or solving
- Rate limit headers (429, Retry-After)
- Exponential backoff or retry delays
- Request throttling between pages
- User-Agent rotation

#### Known Constraints
- 10-second timeout per request (potential for timeout errors)
- No proxy rotation logic shown (though proxies accepted)

### 5. Job Details Fetching

**Strategy**: Inline in search results (no separate detail requests)

**Source**: Line 126, indeed/__init__.py
```python
jobs = data["data"]["jobSearch"]["results"]
```

All job details are included in the single GraphQL response. The query requests the following fields inline:

#### Inline Fields Retrieved
**Source**: Lines 17-94, indeed/constant.py

- `source.name`
- `key` (unique job ID)
- `title`
- `datePublished` (timestamp in milliseconds)
- `dateOnIndeed` (days published)
- `description.html` (full HTML description)
- `location.*` (city, state, country, postal code, street address, formatted)
- `compensation.*` (salary ranges, currency, estimated vs. posted)
- `attributes[]` (job type, remote status)
- `employer.*` (company name, logo, industry, employee count, revenue, description, CEO info)
- `recruit.*` (direct job URL, work schedule, detailed salary)

**No separate detail page requests are made** - everything is fetched in one GraphQL call per page.

### 6. Field Extraction → JobPost Mapping

**Source**: Lines 195-260, indeed/__init__.py

| JobPost Field | Source Key | Transformation |
|---|---|---|
| `id` | `job["key"]` | `f'in-{job_key}'` (prefix with "in-") |
| `title` | `job["title"]` | Passthrough |
| `description` | `job["description"]["html"]` | HTML→Markdown conversion if requested (line 207) |
| `company_name` | `job["employer"]["name"]` | Passthrough or None if no employer |
| `company_url` | `job["employer"]["relativeCompanyPageUrl"]` | Prepend base_url to relative path (line 220) |
| `company_url_direct` | `job["employer"]["dossier"]["links"]["corporateWebsite"]` | Passthrough (corporate website URL) |
| `location.city` | `job["location"]["city"]` | Passthrough |
| `location.state` | `job["location"]["admin1Code"]` | Passthrough (state/province code) |
| `location.country` | `job["location"]["countryCode"]` | Passthrough (ISO 2-letter code) |
| `job_type` | `job["attributes"][]` | Parse labels; map to JobType enum (line 209) |
| `compensation` | `job["compensation"]` | Complex parsing (see section 6a) |
| `date_posted` | `job["datePublished"]` | Milliseconds → seconds → date string (line 210-211): `datetime.fromtimestamp(timestamp_seconds).strftime("%Y-%m-%d")` |
| `job_url` | `job["key"]` | `https://domain.indeed.com/viewjob?jk={key}` |
| `job_url_direct` | `job["recruit"]["viewJobUrl"]` | Passthrough (external applicant URL) |
| `emails` | `description` | Regex extraction from description text (line 236) |
| `is_remote` | `job` + `description` | Multi-source check (see section 6b) |
| `company_addresses` | `employer["dossier"]["employerDetails"]["addresses"][0]` | First address only (line 239-240) |
| `company_industry` | `employer["dossier"]["employerDetails"]["industry"]` | Clean: remove "Iv1", replace "_" with space, title-case (lines 243-250) |
| `company_num_employees` | `employer["dossier"]["employerDetails"]["employeesLocalizedLabel"]` | Passthrough (localized string like "10-50" or "201-500") |
| `company_revenue` | `employer["dossier"]["employerDetails"]["revenueLocalizedLabel"]` | Passthrough (localized string) |
| `company_description` | `employer["dossier"]["employerDetails"]["briefDescription"]` | Passthrough (plain text description) |
| `company_logo` | `employer["images"]["squareLogoUrl"]` | Passthrough (URL to square logo) |

#### 6a. Compensation Parsing
**Source**: Lines 20-49, indeed/util.py

```python
def get_compensation(compensation: dict) -> Compensation | None:
    if not compensation["baseSalary"] and not compensation["estimated"]:
        return None
    
    comp = compensation["baseSalary"] if compensation["baseSalary"] else compensation["estimated"]["baseSalary"]
    if not comp:
        return None
    
    interval = get_compensation_interval(comp["unitOfWork"])
    min_range = comp["range"].get("min")
    max_range = comp["range"].get("max")
    
    return Compensation(
        interval=interval,
        min_amount=int(min_range),
        max_amount=int(max_range),
        currency=compensation["estimated"]["currencyCode"] or compensation["currencyCode"]
    )
```

**Logic**:
- **Precedence**: `baseSalary` > `estimated.baseSalary` (source of truth)
- **Fallback**: Uses estimated salary if posted salary not available
- **Interval Mapping** (lines 72-83):
  - `DAY` → `DAILY`
  - `YEAR` → `YEARLY`
  - `HOUR` → `HOURLY`
  - `WEEK` → `WEEKLY`
  - `MONTH` → `MONTHLY`
  - Raises `ValueError` if unsupported interval
- **Currency**: From estimated if available, else from baseSalary
- **Range**: Converted to integers

#### 6b. Remote Detection
**Source**: Lines 52-68, indeed/util.py

```python
def is_job_remote(job: dict, description: str) -> bool:
    remote_keywords = ["remote", "work from home", "wfh"]
    
    is_remote_in_attributes = any(
        any(keyword in attr["label"].lower() for keyword in remote_keywords)
        for attr in job["attributes"]
    )
    is_remote_in_description = any(
        keyword in description.lower() for keyword in remote_keywords
    )
    is_remote_in_location = any(
        keyword in job["location"]["formatted"]["long"].lower()
        for keyword in remote_keywords
    )
    
    return is_remote_in_attributes or is_remote_in_description or is_remote_in_location
```

**Multi-source Detection**:
1. Attributes labels (e.g., "Remote" tag)
2. Job description text
3. Location formatted string

**Keywords**: `["remote", "work from home", "wfh"]` (case-insensitive)

#### 6c. Job Type Parsing
**Source**: Lines 5-17, indeed/util.py

```python
def get_job_type(attributes: list) -> list[JobType]:
    job_types = []
    for attribute in attributes:
        job_type_str = attribute["label"].replace("-", "").replace(" ", "").lower()
        job_type = get_enum_from_job_type(job_type_str)
        if job_type:
            job_types.append(job_type)
    return job_types
```

**Process**:
- Iterates attributes (from GraphQL response)
- Normalizes label: remove dashes, spaces; lowercase
- Maps to JobType enum via utility function
- Returns list of matching job types

### 7. Filters: job_type, hours_old, location, distance, remote, salary, easy_apply

**Source**: Lines 137-193, indeed/__init__.py

#### Filter Logic Decision Tree

```
IF hours_old is set:
    - Only apply date filter (composite filters conflict with date in Indeed API)
ELSE IF easy_apply is set:
    - Filter for Indeed-apply scope only
ELSE IF job_type OR is_remote is set:
    - Use composite filters for attributes
ELSE:
    - No filters (empty string)
```

**Reason for Logic** (line 139 comment): "If hours_old is provided, composite filter for job_type/is_remote is not possible."

#### 7a. Date Filter (hours_old)
**Source**: Lines 144-152, indeed/__init__.py

```graphql
filters: {
    date: {
        field: "dateOnIndeed",
        start: "{start}h"
    }
}
```

- `start` value: hours in past (e.g., `24h`, `168h`)
- Applied to `dateOnIndeed` field
- Mutually exclusive with other filter types

#### 7b. Easy Apply Filter
**Source**: Lines 154-162, indeed/__init__.py

```graphql
filters: {
    keyword: {
        field: "indeedApplyScope",
        keys: ["DESKTOP"]
    }
}
```

- Field: `indeedApplyScope`
- Value: `["DESKTOP"]` (indicates Indeed-hosted apply form)
- Matches jobs with Indeed's apply button, not external links

#### 7c. Job Type + Remote Filters (Composite)
**Source**: Lines 163-192, indeed/__init__.py

```graphql
filters: {
    composite: {
        filters: [{
            keyword: {
                field: "attributes",
                keys: ["key1", "key2", ...]
            }
        }]
    }
}
```

**Job Type to Key Mapping** (lines 164-168):
| JobType Enum | Indeed Key |
|---|---|
| FULL_TIME | `CF3CP` |
| PART_TIME | `75GKK` |
| CONTRACT | `NJXCK` |
| INTERNSHIP | `VDTG7` |

**Remote Key**: `DSQF7` (line 177)

**Logic** (lines 171-192):
- Build `keys` list from job_type and is_remote
- Only generate filters if `keys` is non-empty
- Keys joined as: `["key1", "key2", ...]` (line 180)

#### 7d. Location & Distance Handling
**Source**: Lines 99-102, indeed/__init__.py

```python
location=(
    f'location: {{where: "{self.scraper_input.location}", radius: {self.scraper_input.distance}, radiusUnit: MILES}}'
    if self.scraper_input.location
    else ""
)
```

- **Location**: String (city, state, country, zip code)
- **Distance**: Integer in miles (radius)
- **Unit**: Hardcoded to `MILES`
- **Omitted**: If no location specified (entire location block skipped)

#### 7e. Salary Filtering
**Status**: NOT IMPLEMENTED

The scraper does not support filtering by salary range. The compensation data is extracted post-fetch.

### 8. Country/Locale Handling

**Source**: Lines 56-60, indeed/__init__.py

```python
domain, self.api_country_code = self.scraper_input.country.indeed_domain_value
self.base_url = f"https://{domain}.indeed.com"
self.headers = api_headers.copy()
self.headers["indeed-co"] = self.scraper_input.country.indeed_domain_value
```

**Country Config Expected**:
- `scraper_input.country.indeed_domain_value` → Tuple of (domain, country_code)
- Example: `("us", "US")` → domain `us.indeed.com`, country code `US`
- Header `indeed-co` updated per country

**Headers Affected**:
- `indeed-co`: Dynamic per country (line 60, 112)
- `indeed-locale`: Dynamic per country (line 105, not shown in this file but expected in country config)

**URL Construction**: Domain embedded in base_url (line 58)

### 9. Undocumented Parameters & Implementation Details

1. **Hardcoded API Key** (line 103, constant.py):
   - Value: `161092c2017b5bbab13edb12461a62d5a833871e7cad6d9d475304573de67ac8`
   - Public in source code (security risk)
   - Likely a shared/demo key for the app

2. **Sort Parameter**:
   - Hardcoded to `RELEVANCE` (line 8, constant.py)
   - No user-configurable sort option exposed

3. **App Metadata in Headers**:
   - Simulates Indeed iOS app (version 193.1)
   - `appid`: `com.indeed.jobsearch`
   - `dtype`: `phone` (mobile device)

4. **TLS Disabled**:
   - Session created with `is_tls=False` (line 39)
   - Unusual for production API calls; may indicate proxy bypass

5. **Tracking Key**:
   - Retrieved but not used: `trackingKey` in response (line 15, constant.py)
   - Likely for analytics but not extracted to JobPost

6. **Recruit Fields**:
   - `recruit.detailedSalary`: Requested but not extracted
   - `recruit.workSchedule`: Requested but not extracted
   - Could be used for future salary/schedule filtering

7. **Worker Threads**:
   - `self.num_workers = 10` (line 43) - set but never used in code
   - No parallel job processing visible

### 10. Known Failure Modes

1. **HTTP Error Handling** (lines 120-124):
   - Non-200 status codes logged but silently fail (return empty jobs)
   - No retry mechanism
   - User must manually retry

2. **Timeout** (line 117):
   - 10-second timeout may be insufficient for slow/distant servers
   - Times out → returns empty jobs, breaks pagination

3. **API Key Expiration**:
   - Hardcoded key could be revoked by Indeed
   - No fallback mechanism

4. **Country Config Missing**:
   - If `scraper_input.country.indeed_domain_value` not configured, will raise AttributeError

5. **Missing Location Type**:
   - If location provided but location type not recognized, GraphQL may return unexpected results

6. **Description Parsing**:
   - HTML→Markdown conversion may fail on malformed HTML
   - No error handling shown

7. **Compensation Parsing Edge Cases**:
   - If `range` dict missing `min` or `max`, `get()` returns None, int(None) raises TypeError
   - Undocumented: behavior if both `baseSalary` and `estimated.baseSalary` are empty dicts

8. **Remote Detection**:
   - Keyword matching is simple substring search (case-insensitive)
   - Could match "remove" or "remotely" but not "partially remote"

---

## GLASSDOOR SCRAPER

### 1. HTTP Request Structure

#### Protocol & Authentication
- **API Type**: GraphQL (not REST or HTML parsing)
- **Base Endpoint**: `{base_url}/graph` (e.g., `https://www.glassdoor.com/graph`, line 115, glassdoor/__init__.py)
- **Method**: POST with JSON payload
- **Session Type**: Standard requests session with optional retry logic (line 64)
- **Proxy Support**: Optional proxies, CA certificates, custom user-agent supported (line 37)

#### CSRF Token Requirement
**Source**: Lines 152-162, glassdoor/__init__.py

```python
def _get_csrf_token(self):
    res = self.session.get(f"{self.base_url}/Job/computer-science-jobs.htm")
    pattern = r'"token":\s*"([^"]+)"'
    matches = re.findall(pattern, res.text)
    token = None
    if matches:
        token = matches[0]
    return token
```

**Token Retrieval**:
- GETs a dummy job search page (`/Job/computer-science-jobs.htm`)
- Regex extracts token from HTML: pattern `"token": "([^"]+)"`
- Falls back to hardcoded token if regex fails (line 67)

#### Headers
**Source**: Lines 1-17, glassdoor/constant.py

```
authority: www.glassdoor.com
accept: */*
accept-language: en-US,en;q=0.9
apollographql-client-name: job-search-next
apollographql-client-version: 4.65.5
content-type: application/json
origin: https://www.glassdoor.com
referer: https://www.glassdoor.com/
sec-ch-ua: "Chromium";v="118", "Google Chrome";v="118", "Not=A?Brand";v="99"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "macOS"
sec-fetch-dest: empty
sec-fetch-mode: cors
sec-fetch-site: same-origin
user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36
gd-csrf-token: <dynamic token>
```

**Header Notes**:
- Apollo GraphQL client headers (job-search-next v4.65.5)
- Chrome browser user-agent (Chrome 138)
- CSRF token injected dynamically (line 67)
- Optional user-agent override (lines 68-69)

### 2. Endpoint URLs & Query Parameters

#### Job Search Endpoint
**Source**: Lines 114-118, glassdoor/__init__.py

```python
response = self.session.post(
    f"{self.base_url}/graph",
    timeout_seconds=15,
    data=payload,
)
```

- **URL**: `{base_url}/graph` (single GraphQL endpoint)
- **Base URL**: Determined by country (line 61): `self.scraper_input.country.get_glassdoor_url()`
  - Example: `https://www.glassdoor.com` (US), `https://www.glassdoor.ca` (Canada)
- **Timeout**: 15 seconds

#### Job Description Endpoint
**Source**: Lines 220-256, glassdoor/__init__.py

Separate GraphQL query for fetching individual job descriptions:

```python
url = f"{self.base_url}/graph"
body = [
    {
        "operationName": "JobDetailQuery",
        "variables": {
            "jl": job_id,
            "queryString": "q",
            "pageTypeEnum": "SERP",
        },
        "query": """
            query JobDetailQuery($jl: Long!, $queryString: String, $pageTypeEnum: PageTypeEnum) {
                jobview: jobView(
                    listingId: $jl
                    contextHolder: {queryString: $queryString, pageTypeEnum: $pageTypeEnum}
                ) {
                    job {
                        description
                        __typename
                    }
                    __typename
                }
            }
        """
    }
]
res = requests.post(url, json=body, headers=headers)
```

**Details**:
- Uses `requests.post()` directly, not session (bypasses session retry logic)
- Variables: `jl` (job listing ID), `queryString` (hardcoded "q"), `pageTypeEnum` (hardcoded "SERP")
- Requests only `job.description` field

#### Location Lookup Endpoint
**Source**: Lines 258-284, glassdoor/__init__.py

```python
url = f"{self.base_url}/findPopularLocationAjax.htm?maxLocationsToReturn=10&term={location}"
res = self.session.get(url)
```

**Endpoint**: `/findPopularLocationAjax.htm` (REST, not GraphQL)

**Query Parameters**:
- `maxLocationsToReturn`: Hardcoded to 10 (line 261)
- `term`: Location search string (city, state, country)

**Response**: JSON array of location objects with `locationId`, `locationType`

### 3. Pagination Logic & Limits

**Source**: Lines 81-97, glassdoor/__init__.py

#### Page-Based Pagination
- **Mechanism**: Page numbers (not cursors)
- **Per-page limit**: 30 jobs (line 49: `self.jobs_per_page = 30`)
- **Max pages**: 30 (line 50: `self.max_pages = 30`)
- **Absolute max results**: 900 (line 60): `self.scraper_input.results_wanted = min(900, scraper_input.results_wanted)`

#### Pagination Loop
```python
range_start = 1 + (scraper_input.offset // self.jobs_per_page)
tot_pages = (scraper_input.results_wanted // self.jobs_per_page) + 2
range_end = min(tot_pages, self.max_pages + 1)

for page in range(range_start, range_end):
    log.info(f"search page: {page} / {range_end - 1}")
    try:
        jobs, cursor = self._fetch_jobs_page(
            scraper_input, location_id, location_type, page, cursor
        )
        job_list.extend(jobs)
        if not jobs or len(job_list) >= scraper_input.results_wanted:
            job_list = job_list[: scraper_input.results_wanted]
            break
    except Exception as e:
        log.error(f"Glassdoor: {str(e)}")
        break
```

**Logic**:
- **Start page**: 1 + (offset // 30) - skips pages based on offset
- **Total pages to fetch**: (results_wanted // 30) + 2 (buffer for partial pages)
- **Capped**: min(tot_pages, max_pages + 1) - max 30 pages
- **Break conditions**:
  - No jobs returned on page
  - Total jobs >= results_wanted
  - Exception raised
- **Final slice**: Trim to exact `results_wanted` count (line 92)

#### Cursor Token Mechanism
**Source**: Lines 148-150, glassdoor/__init__.py, and lines 39-42, glassdoor/util.py

```python
def get_cursor_for_page(pagination_cursors, page_num):
    for cursor_data in pagination_cursors:
        if cursor_data["pageNumber"] == page_num:
            return cursor_data["cursor"]
```

- API response includes `paginationCursors` array (line 149)
- Each cursor object has `pageNumber` and `cursor` fields
- Function looks up cursor for next page number

**Usage**: `cursor` passed to next page request (line 312)

#### Seen URLs Tracking
- **Data Structure**: Set (`self.seen_urls`, line 51)
- **Key Format**: `https://{base_url}/job-listing/j?jl={job_id}` (line 169)
- **Check**: Lines 170-171: Skip if URL already seen

### 4. Rate Limiting / Anti-Bot / CAPTCHA Handling

**Status**: Limited explicit handling.

#### 429 Response Detection
**Source**: Lines 264-272, glassdoor/__init__.py

```python
if res.status_code == 429:
    err = f"429 Response - Blocked by Glassdoor for too many requests"
    log.error(err)
    return None, None
else:
    err = f"Glassdoor response status code {res.status_code}"
    err += f" - {res.text}"
    log.error(f"Glassdoor response status code {res.status_code}")
    return None, None
```

**Handling**:
- Detects 429 (Too Many Requests) specifically
- Returns (None, None) tuple, breaking pagination
- Logs error but does not retry or wait

#### Retry Logic
**Source**: Line 64, glassdoor/__init__.py

```python
self.session = create_session(
    proxies=self.proxies, ca_cert=self.ca_cert, has_retry=True
)
```

- `has_retry=True` flag passed to session creation
- Likely implements automatic retries for transient failures (implementation in util module)

#### Other Anti-Bot Measures
- Chrome user-agent (not suspicious)
- CSRF token requirement (standard web security)
- No explicit rate limit headers parsed
- No exponential backoff visible

#### No Explicit Handling For
- CAPTCHA detection or solving
- Request throttling between pages
- User-Agent rotation
- Proxy rotation (though proxies accepted)

### 5. Job Details Fetching

**Strategy**: Hybrid - job list inline, but descriptions fetched separately

**Source**: Lines 134-150, glassdoor/__init__.py

#### Job List Fields (Inline)
Retrieved in main `_fetch_jobs_page` GraphQL query:

```python
jobs_data = res_json["data"]["jobListings"]["jobListings"]
```

Query fields (from constant.py lines 117-182): `JobView` fragment includes:
- `jobview.header.*` (all header data)
- `jobview.job.*` (title, ID, but NOT description)
- `jobview.overview.*` (logo)
- `jobview.jobListingAdminDetails.*`

#### Description Fetching (Separate Request)
**Source**: Lines 191-193, glassdoor/__init__.py

```python
try:
    description = self._fetch_job_description(job_id)
except:
    description = None
```

**Separate GraphQL Request** (lines 220-256):
- POST to `/graph` with `JobDetailQuery` operation
- Variables: `jl` (job ID), `queryString`, `pageTypeEnum`
- Queries only `job.description` field
- Called in parallel via ThreadPoolExecutor (line 136)

#### Parallelization
**Source**: Lines 136-146, glassdoor/__init__.py

```python
with ThreadPoolExecutor(max_workers=self.jobs_per_page) as executor:
    future_to_job_data = {
        executor.submit(self._process_job, job): job for job in jobs_data
    }
    for future in as_completed(future_to_job_data):
        try:
            job_post = future.result()
            if job_post:
                jobs.append(job_post)
```

**Details**:
- ThreadPoolExecutor with max_workers = 30 (jobs_per_page)
- Each job processed concurrently
- `_process_job` method (which calls `_fetch_job_description`) runs in thread pool
- Descriptions fetched in parallel with job list parsing

### 6. Field Extraction → JobPost Mapping

**Source**: Lines 164-218, glassdoor/__init__.py

| JobPost Field | Source Key | Transformation |
|---|---|---|
| `id` | `job_data["jobview"]["job"]["listingId"]` | `f"gd-{job_id}"` (prefix with "gd-") |
| `title` | `job["header"]["jobTitleText"]` | Passthrough |
| `company_name` | `job["header"]["employerNameFromSearch"]` | Passthrough |
| `company_url` | `company_id` | `f"{base_url}/Overview/W-EI_IE{company_id}.htm"` (constructed URL) |
| `date_posted` | `job["header"]["ageInDays"]` | Convert days ago to date: `datetime.now() - timedelta(days=age_in_days)` (line 181) |
| `job_url` | `job_id` | `f"{base_url}/job-listing/j?jl={job_id}"` (line 169) |
| `location` | `job["header"]["locationName"]` | Parse via `parse_location()` (see section 6a) |
| `is_remote` | `job["header"]["locationType"]` | `True` if `locationType == "S"` (line 184) |
| `compensation` | `job["header"]` | Parse via `parse_compensation()` (see section 6b) |
| `description` | Separate fetch | `_fetch_job_description(job_id)` result (line 191) |
| `emails` | `description` | Regex extraction from description (line 215) |
| `company_logo` | `job_data["jobview"]["overview"]["squareLogoUrl"]` | Passthrough or None (line 196) |
| `listing_type` | `job["header"]["adOrderSponsorshipLevel"]` | Lowercase (line 202) |

**Fields Not Extracted** (present in response but unused):
- `employer.id`, `employer.name`, `employer.shortName` (company info available)
- `jobCountryId`, `goc`, `gocId` (geographic/classification data)
- `adOrderId`, `sponsored` (ad metadata)
- `jobResultTrackingKey` (tracking)
- `savedJobId` (user state)

#### 6a. Location Parsing
**Source**: Lines 32-36, glassdoor/util.py

```python
def parse_location(location_name: str) -> Location | None:
    if not location_name or location_name == "Remote":
        return
    city, _, state = location_name.partition(", ")
    return Location(city=city, state=state)
```

**Logic**:
- Returns None if location_name is empty or "Remote"
- Splits on ", " (comma-space separator)
- Example: "New York, NY" → Location(city="New York", state="NY")
- Assumes 2-part format; if more parts, state is third part after second ", "

#### 6b. Compensation Parsing
**Source**: Lines 4-23, glassdoor/util.py

```python
def parse_compensation(data: dict) -> Compensation | None:
    pay_period = data.get("payPeriod")
    adjusted_pay = data.get("payPeriodAdjustedPay")
    currency = data.get("payCurrency", "USD")
    
    if not pay_period or not adjusted_pay:
        return None
    
    interval = None
    if pay_period == "ANNUAL":
        interval = CompensationInterval.YEARLY
    elif pay_period:
        interval = CompensationInterval.get_interval(pay_period)
    
    min_amount = int(adjusted_pay.get("p10") // 1)
    max_amount = int(adjusted_pay.get("p90") // 1)
    
    return Compensation(
        interval=interval,
        min_amount=min_amount,
        max_amount=max_amount,
        currency=currency,
    )
```

**Details**:
- **Pay Period**: Required field; returns None if missing
- **Adjusted Pay**: Percentile-based range (p10, p90)
- **Interval Mapping**:
  - `"ANNUAL"` → `CompensationInterval.YEARLY`
  - Other pay_period values → `CompensationInterval.get_interval(pay_period)` (utility function)
- **Currency**: Defaults to "USD" if missing
- **Range Calculation**: p10 (10th percentile) as min, p90 (90th percentile) as max
  - Division by 1 oddity (line 16): `int(adjusted_pay.get("p10") // 1)` - likely redundant integer conversion

### 7. Filters: job_type, hours_old, location, distance, remote, salary, easy_apply

**Source**: Lines 286-322, glassdoor/__init__.py

#### Filter Implementation
Filters are built as `filterParams` array in GraphQL variables:

```python
filter_params = []
if self.scraper_input.easy_apply:
    filter_params.append({"filterKey": "applicationType", "values": "1"})
if fromage:
    filter_params.append({"filterKey": "fromAge", "values": str(fromage)})
if self.scraper_input.job_type:
    filter_params.append(
        {"filterKey": "jobType", "values": self.scraper_input.job_type.value[0]}
    )
```

#### 7a. Easy Apply Filter
**Source**: Lines 297-298, glassdoor/__init__.py

```python
if self.scraper_input.easy_apply:
    filter_params.append({"filterKey": "applicationType", "values": "1"})
```

- **Filter Key**: `applicationType`
- **Value**: `"1"` (hardcoded string, likely means Glassdoor's easy apply)
- Appended only if `easy_apply` is True

#### 7b. Date Filter (hours_old)
**Source**: Lines 293-300, glassdoor/__init__.py

```python
fromage = None
if self.scraper_input.hours_old:
    fromage = max(self.scraper_input.hours_old // 24, 1)

filter_params = []
# ...
if fromage:
    filter_params.append({"filterKey": "fromAge", "values": str(fromage)})
```

- **Conversion**: Hours → days (divide by 24)
- **Minimum**: 1 day (max ensures no zero or negative values)
- **Filter Key**: `fromAge`
- **Value**: String representation of days

#### 7c. Job Type Filter
**Source**: Lines 318-321, glassdoor/__init__.py

```python
if self.scraper_input.job_type:
    payload["variables"]["filterParams"].append(
        {"filterKey": "jobType", "values": self.scraper_input.job_type.value[0]}
    )
```

- **Filter Key**: `jobType`
- **Value**: `self.scraper_input.job_type.value[0]` (first element of JobType enum value)
- Example: If job_type is JobType.FULL_TIME, value might be "fulltime"

#### 7d. Location & Distance Handling
**Source**: Lines 72-74, 258-284, glassdoor/__init__.py

```python
location_id, location_type = self._get_location(
    scraper_input.location, scraper_input.is_remote
)
```

**Location Resolution** (lines 258-284):
```python
def _get_location(self, location: str, is_remote: bool) -> (int, str):
    if not location or is_remote:
        return "11047", "STATE"  # remote options
    
    url = f"{self.base_url}/findPopularLocationAjax.htm?maxLocationsToReturn=10&term={location}"
    res = self.session.get(url)
    
    items = res.json()
    if not items:
        raise ValueError(f"Location '{location}' not found on Glassdoor")
    
    location_type = items[0]["locationType"]
    if location_type == "C":
        location_type = "CITY"
    elif location_type == "S":
        location_type = "STATE"
    elif location_type == "N":
        location_type = "COUNTRY"
    
    return int(items[0]["locationId"]), location_type
```

**Details**:
- If no location or is_remote=True: Default to remote location ID "11047" with type "STATE"
- Otherwise: Query `/findPopularLocationAjax.htm` with location term
- Takes first result from API
- Maps location type codes: C→CITY, S→STATE, N→COUNTRY
- Raises ValueError if location not found

**Distance**: NOT EXPLICITLY SUPPORTED

**Payload Variables** (lines 308-310):
```python
"locationType": location_type,
"locationId": int(location_id),
"parameterUrlInput": f"IL.0,12_I{location_type}{location_id}",
```

- `parameterUrlInput`: Constructed URL parameter for internal use (format: `IL.0,12_ILOCATION_TYPE{location_id}`)

#### 7e. Remote Handling
**Source**: Line 259, glassdoor/__init__.py

```python
if not location or is_remote:
    return "11047", "STATE"  # remote options
```

- If `is_remote=True`: Returns hardcoded location ID "11047" (Glassdoor's remote location)
- Location string becomes irrelevant if is_remote=True

#### 7f. Salary Filtering
**Status**: NOT IMPLEMENTED

No salary range filter in `filter_params`. Compensation data is extracted post-fetch.

### 8. Country/Locale Handling

**Source**: Lines 61, glassdoor/__init__.py

```python
self.base_url = self.scraper_input.country.get_glassdoor_url()
```

**Country Config Expected**:
- `scraper_input.country.get_glassdoor_url()` → Base URL string
- Example: `https://www.glassdoor.com` (US), `https://www.glassdoor.ca` (Canada)

**Affected Components**:
- All endpoint URLs (job search, location lookup, job details)
- Cookie/session handling (per-country)
- CSRF token fetched per-country

**No explicit locale header** - locale determined by domain

### 9. Undocumented Parameters & Implementation Details

1. **Hardcoded Fallback CSRF Token** (line 184, constant.py):
   - Value: `Ft6oHEWlRZrxDww95Cpazw:0pGUrkb2y3TyOpAIqF2vbPmUXoXVkD3oEGDVkvfeCerceQ5-n8mBg3BovySUIjmCPHCaW0H2nQVdqzbtsYqf4Q:wcqRqeegRUa9MVLJGyujVXB7vWFPjdaS1CtrrzJq-ok`
   - Used if regex extraction fails (line 67)
   - Token format: `auth:payload:signature` pattern

2. **Apollo GraphQL Client Headers**:
   - `apollographql-client-name`: `job-search-next` (hardcoded)
   - `apollographql-client-version`: `4.65.5` (hardcoded)
   - Identifies client library/version

3. **Hardcoded Query Parameters**:
   - `maxLocationsToReturn`: 10 (line 261)
   - `queryString`: "q" in JobDetailQuery (line 230)
   - `pageTypeEnum`: "SERP" in JobDetailQuery (line 231)

4. **Pay Period Percentiles**:
   - Uses p10 (10th percentile) and p90 (90th percentile) for salary range
   - Not min/max but statistical percentiles (more conservative estimate)

5. **Location Type Codes**:
   - API returns single-character codes: C, S, N
   - Mapped to enum-like strings: CITY, STATE, COUNTRY

6. **Pagination Cursor Array**:
   - Response includes array of cursor objects with pageNumber and cursor
   - Must match page numbers to find correct cursor (not sequential)

7. **Listing Type**:
   - `adOrderSponsorshipLevel` field indicates sponsored/promoted listings
   - Lowercased before storing (line 202)
   - Possible values: unknown (not documented)

8. **Company ID Construction**:
   - Employer ID from response (line 176)
   - Company URL format: `/Overview/W-EI_IE{company_id}.htm` (line 194)
   - "EI_IE" prefix standard for Glassdoor company pages

9. **No User-Agent Override by Default**:
   - User-agent only updated if custom one provided (lines 68-69)
   - Default is Chrome 138 on macOS (header.py lines 16)

10. **ThreadPoolExecutor Exception Handling**:
    - Blanket catch of all exceptions in thread results (line 146)
    - Raises `GlassdoorException` with generic message
    - Could mask individual job processing failures

### 10. Known Failure Modes

1. **CSRF Token Extraction Failure**:
   - Regex may fail if HTML structure changes
   - Falls back to hardcoded token (may be expired)
   - No validation that token is valid

2. **Location Not Found**:
   - Raises ValueError if location string not found (line 276)
   - Breaks entire scrape job (no fallback to "all locations")

3. **HTTP Error Handling**:
   - 429 (rate limit) returns (None, None), breaking pagination
   - Other non-200 status codes logged but parsing continues (may raise KeyError on missing fields)
   - No retry mechanism for transient errors

4. **Timeout**:
   - 15-second timeout may fail on slow servers
   - Returns (None, None), breaks pagination

5. **Description Fetch Failures**:
   - Bare except clause (line 192): catches all exceptions, sets description to None
   - Network errors, malformed responses silently fail

6. **Parallel Description Fetching**:
   - `requests.post()` used directly, not session with retry logic (line 249)
   - No error handling if description fetch fails in thread
   - Could result in jobs with null descriptions

7. **Date Calculation Edge Case**:
   - If `ageInDays` is None (line 181): `timedelta(days=None)` raises TypeError
   - date_posted becomes None (line 182) - could be handled but not validated

8. **Max Results Truncation**:
   - Hard limit of 900 results (line 60)
   - No warning to user if more results requested

9. **Missing Location Type in API Response**:
   - If `locationType` not in location object from API, KeyError raised
   - No validation of API response structure

10. **Page Calculation Logic**:
    - `range_start = 1 + (scraper_input.offset // self.jobs_per_page)` - assumes offset is rough approximation
    - If offset not divisible by 30, exact offset position not guaranteed

---

## COMPARATIVE ANALYSIS

| Aspect | Indeed | Glassdoor |
|---|---|---|
| **API Type** | GraphQL (single `/graphql` endpoint) | GraphQL (`/graph` endpoint) |
| **Authentication** | Hardcoded API key in headers | CSRF token (dynamic + fallback) |
| **Pagination** | Cursor-based (opaque token strings) | Page-number + cursor tokens |
| **Per-Page Jobs** | 100 | 30 |
| **Max Results** | Unlimited | 900 |
| **Job Details** | Inline in search response | Separate request per job (parallel fetching) |
| **Parallelization** | None visible (sequential) | ThreadPoolExecutor for description fetching |
| **Location Support** | String input + radius (miles) | Lookup endpoint required, no radius |
| **Remote Handling** | Filter key + keyword detection | Special location ID "11047" |
| **Rate Limiting** | Silent failure on HTTP error | 429 detection + session-level retry |
| **Salary Filtering** | Not supported | Not supported |
| **Date Filtering** | Conflicts with other filters | Compatible with all filters |
| **Job Type Keys** | Hardcoded attribute keys (e.g., CF3CP) | JobType enum values |
| **Country Support** | Domain + country code in headers | Domain only (via base_url) |
| **Timeout** | 10 seconds | 15 seconds |
| **Error Recovery** | Log + return empty jobs | Log + break pagination |
| **Session Retry** | Not explicitly enabled | Enabled with `has_retry=True` |

---

## CRITICAL SECURITY & MAINTENANCE CONCERNS

### Indeed
1. **Public API Key**: Hardcoded in source (line 103, constant.py) - likely shared/demo key but still a security risk
2. **Disabled SSL Verification**: `verify=False` (line 118) - accepts invalid certificates
3. **TLS Disabled**: `is_tls=False` (line 39) - unusual for API client
4. **Hard-coded Sort**: Only "RELEVANCE" sort available (not user-configurable)

### Glassdoor
1. **Fallback Token**: Hardcoded token used if extraction fails (line 67) - may be expired
2. **Direct requests.post()**: Description fetching bypasses session retry logic (line 249)
3. **Broad Exception Handling**: Bare except clauses (line 192) hide real errors
4. **Limited Offset Precision**: Offset calculation may not guarantee exact starting position (line 81)

### Both
1. **No Exponential Backoff**: No automatic retry delay on rate limiting
2. **No CAPTCHA Handling**: No detection or solving mechanism
3. **User-Agent Spoofing**: Both spoof mobile/browser clients (privacy implications)
4. **Limited Salary Support**: Neither supports salary range filtering
5. **Regex-Based Remote Detection**: Indeed uses simple keyword matching (could have false positives)

---

## IMPLEMENTATION RECOMMENDATIONS FOR AGENTIC JOB APPLIER

1. **Connection Pooling**: Both scrapers create fresh sessions per scrape; consider reusing sessions
2. **Retry Strategy**: Implement exponential backoff for transient failures (both scrapers)
3. **CSRF Token Caching**: Glassdoor token could be cached across scrapes (if expiry unknown)
4. **Parallel Detail Fetching**: Indeed could benefit from parallel description fetching (currently unavailable)
5. **Salary Filtering**: Post-process results client-side if salary filtering needed
6. **Rate Limiting**: Implement client-side token bucket or similar to avoid 429 responses
7. **Logging**: Add structured logging (job ID, status, timing) for debugging
8. **Validation**: Validate required fields before constructing JobPost objects
9. **Offset Handling**: Glassdoor offset logic may skip/duplicate results with pagination; verify behavior
10. **Timeout Tuning**: 10-15 second timeouts may be too aggressive for poor network conditions

