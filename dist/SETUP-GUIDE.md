# Job Aggregator — Setup & Support Guide

Reference doc for helping users get set up and answering their questions.

---

## Table of Contents

1. [Building & Packaging the Image](#1-building--packaging-the-image)
2. [Windows Setup (Step-by-Step)](#2-windows-setup-step-by-step)
3. [macOS Setup (Step-by-Step)](#3-macos-setup-step-by-step)
4. [Configuring Their Job Search](#4-configuring-their-job-search)
5. [Settings Page Reference](#5-settings-page-reference)
6. [How Filters Work (The Key Question)](#6-how-filters-work-the-key-question)
7. [Adding Companies to Track](#7-adding-companies-to-track)
8. [Common Questions & Troubleshooting](#8-common-questions--troubleshooting)
9. [Managing the System Day-to-Day](#9-managing-the-system-day-to-day)

---

## 1. Building & Packaging the Image

All builds run on your macOS dev machine. The `--platform` flag cross-compiles
for the target architecture so the image runs natively on the recipient's OS.

### Build for Windows (amd64)

```bash
cd /path/to/agentic-job-applier
docker build --platform linux/amd64 --target base -t job-aggregator:tier1 .
```

### Build for macOS Apple Silicon (arm64)

```bash
cd /path/to/agentic-job-applier
docker build --platform linux/arm64 --target base -t job-aggregator:tier1 .
```

### Build for macOS Intel (amd64)

Same as Windows — Intel Macs use x86_64:

```bash
cd /path/to/agentic-job-applier
docker build --platform linux/amd64 --target base -t job-aggregator:tier1 .
```

Build takes ~3-5 minutes. This creates a Linux image with the API, dashboard, and all fetchers — no AI/LaTeX/browser dependencies.

### Export for distribution

Use a platform-specific filename so it's clear which image is which:

```bash
# Windows image
docker save job-aggregator:tier1 | gzip > job-aggregator-tier1-windows.tar.gz

# macOS Apple Silicon image
docker save job-aggregator:tier1 | gzip > job-aggregator-tier1-mac-arm64.tar.gz

# macOS Intel image
docker save job-aggregator:tier1 | gzip > job-aggregator-tier1-mac-intel.tar.gz
```

Result is ~500MB-1GB.

### Package everything into a zip

```bash
# From the repo root — Windows example
cp job-aggregator-tier1-windows.tar.gz dist/job-aggregator-tier1.tar.gz
cd dist && zip -r ../job-aggregator-windows.zip . && cd ..
# Clean up
rm dist/job-aggregator-tier1.tar.gz
```

Send `job-aggregator-windows.zip` to the user. It contains:

```
job-aggregator-windows.zip
├── job-aggregator-tier1.tar.gz   ← Docker image
├── docker-compose.yml            ← Orchestration (pre-configured)
├── .env                          ← Environment config (edit this)
└── config/
    ├── companies.yaml            ← Where to find jobs (edit this)
    ├── filters.yaml              ← What to filter out (edit this)
    └── candidate_profile.yaml    ← Who they are (edit this)
```

---

## 2. Windows Setup (Step-by-Step)

### Prerequisites

- Docker Desktop installed and running (the whale icon should be in the system tray)
- That's it. No Python, no Node, no WSL required.

### Step-by-step

**1. Extract the zip**

Right-click `job-aggregator-dist.zip` → "Extract All..." → choose a location like `C:\job-aggregator`.

The folder should look like:

```
C:\job-aggregator\
├── job-aggregator-tier1.tar.gz
├── docker-compose.yml
├── .env
└── config\
    ├── companies.yaml
    ├── filters.yaml
    └── candidate_profile.yaml
```

**2. Load the Docker image**

Open PowerShell (right-click Start → "Windows PowerShell"):

```powershell
cd C:\job-aggregator
docker load -i job-aggregator-tier1.tar.gz
```

This takes 1-2 minutes. You'll see `Loaded image: job-aggregator:tier1`.

**3. Edit the config files**

Open the config files in Notepad or any text editor.

- `config\companies.yaml` — Add the companies you want to track (see [Section 7](#7-adding-companies-to-track))
- `config\filters.yaml` — Customize which jobs to keep/reject (see [Section 6](#6-how-filters-work-the-key-question))
- `config\candidate_profile.yaml` — Fill in your info (only needed if using the AI gate agent)

Or skip this and configure everything through the dashboard after starting (see step 5).

**4. Start it up**

```powershell
docker compose up -d
```

First time takes ~10-15 seconds. You'll see:

```
[+] Running 3/3
 ✔ Container job-aggregator-api-1        Healthy
 ✔ Container job-aggregator-discovery-1  Started
 ✔ Container job-aggregator-gate-1       Started
```

The gate container will show a warning about missing `OPENAI_API_KEY` and sleep — this is normal for Tier 1.

**5. Open the dashboard**

Open a browser and go to: **http://localhost:8000**

Jobs will start appearing after the first discovery cycle (~1-2 minutes for Greenhouse/Lever, up to 5 minutes for job boards).

All config files can also be edited from **Settings** (gear icon) in the dashboard.

### Windows-specific notes

- Docker Desktop must be running (check the system tray icon)
- If you get "port 8000 already in use" — change `API_PORT=8001` in `.env`
- Docker Desktop uses WSL2 under the hood but you never need to touch WSL
- Config file edits with Notepad are fine — YAML is read inside the Linux container

---

## 3. macOS Setup (Step-by-Step)

### Prerequisites

- Docker Desktop installed and running (the whale icon in the menu bar)

### Step-by-step

**1. Extract the zip**

Double-click `job-aggregator-dist.zip` or:

```bash
mkdir ~/job-aggregator && cd ~/job-aggregator
unzip /path/to/job-aggregator-dist.zip
```

**2. Load the Docker image**

```bash
docker load -i job-aggregator-tier1.tar.gz
```

**3. Edit config files**

```bash
open config/companies.yaml    # Opens in default text editor
```

At minimum, add the companies you want to track. Or skip and configure through the dashboard after starting.

**4. Start**

```bash
docker compose up -d
```

**5. Open dashboard**

Go to **http://localhost:8000** in a browser.

---

## 4. Configuring Their Job Search

Walk through this with the user when setting up. The goal is to customize three files in `config/`:

### Quick configuration via the dashboard (recommended after first start)

Once the system is running, everything can be edited through the dashboard at **http://localhost:8000** → **Settings** (gear icon). The UI writes back to the same YAML files. This is easier than editing YAML by hand.

### Config file overview

| File | What it controls | Must edit? |
|---|---|---|
| `companies.yaml` | Where to find jobs (which companies, which job boards) | **Yes** |
| `filters.yaml` | What to filter out (title patterns, job types, locations) | Recommended |
| `candidate_profile.yaml` | Who they are (used by gate agent if API key is set) | Only if using gate |
| `.env` | API keys, schedule, port | Only if adding API keys |

---

## 5. Settings Page Reference

The dashboard settings page has **3 top-level tabs**:

### Tab 1: General Settings

- **API Keys** — Add/remove API keys (OpenAI, etc). Keys are write-only (never displayed back). For Tier 1, only `OPENAI_API_KEY` (for gate agent) is relevant. Workday scraping is now built-in and free — no API token required.
- **Service Tier** — Shows current tier. For distributed users this will be `base`. Leave it.
- **Budget** — Monthly spending cap for AI API calls. Only relevant if gate agent is enabled.

### Tab 2: Candidate Profile & Resume

Two sections:

**Candidate Profile** (3 sub-tabs: Guided / Advanced YAML / File Actions)
- Who the user is: name, education, target roles, skills, hard dealbreakers, preferences
- The **Guided** tab has a nice form editor — use this
- Used by the gate agent to decide "should I apply to this job?"
- If no `OPENAI_API_KEY`, this is informational only (doesn't affect anything)

**Resume Editor**
- Locked on the `base` tier — users will see it grayed out
- Not relevant for Tier 1

### Tab 3: Company & Job Filters

This is the most important tab for Tier 1. Two sections:

**Filters** (Guided sub-tab) — controls `filters.yaml`
- Hard and soft filtering rules
- See [Section 6](#6-how-filters-work-the-key-question) for the full breakdown

**Company Sources** (Advanced YAML sub-tab) — controls `companies.yaml`
- Where jobs are fetched from
- See [Section 7](#7-adding-companies-to-track) for how to add companies

---

## 6. How Filters Work (The Key Question)

> "How do the filters on the Candidate tab differ from the Company & Job Filters tab?"

### Short answer

- **Candidate Profile** (Settings → Candidate Profile) = "Who am I?" — used by the **AI gate agent** to make nuanced decisions. Only matters if `OPENAI_API_KEY` is set.
- **Company & Job Filters** (Settings → Company & Job Filters → Filters) = "What do I definitely want/don't want?" — applied **automatically with code**, no AI involved.

### Detailed breakdown

There are **3 layers of filtering**, applied in order:

```
Layer 1: HARD FILTERS (filters.yaml → hard_filters)
   ↓  Applied during job fetching, BEFORE jobs enter the database
   ↓  Pure code — regex matching, substring checks, date math
   ↓  Jobs that fail are silently discarded (never appear anywhere)

Layer 2: SOFT FILTERS (filters.yaml → soft_filters)
   ↓  Applied after jobs enter the database
   ↓  Pure code — keyword matching
   ↓  Auto-classifies obvious cases without using the AI agent
   ↓  Saves API costs by skipping the gate for clear-cut jobs

Layer 3: GATE AGENT (candidate_profile.yaml → profile)
   ↓  Only runs if OPENAI_API_KEY is set
   ↓  AI reads the job description + your candidate profile
   ↓  Makes nuanced QUALIFY/REJECT decisions the filters can't
   ↓  e.g., "this says 'ML' but it's really a data entry role"
```

### Hard Filters — "Never show me these"

These are blunt, fast, and absolute. A job that hits a hard filter is **dropped before it's even saved**.

| Filter | What it does | Example |
|---|---|---|
| `exclude_job_types` | Drop jobs of these types | Exclude "Contract" and "Part-time" |
| `exclude_title_patterns` | Regex against job title — ANY match = rejected | `(?i)senior`, `(?i)manager` |
| `require_title_patterns` | Regex against job title — must match AT LEAST ONE (empty = allow all) | `intern`, `new.?grad` |
| `exclude_locations` | Substring match on location — ANY match = rejected | "China", "India" |
| `exclude_companies` | Exact company name match | "CompanyX" |
| `require_remote` | If true, only keep remote/hybrid jobs | true/false |
| `max_days_old` | Drop jobs posted more than N days ago | 30 |
| `min_salary_usd` / `max_salary_usd` | Salary bounds (only if job has salary data) | 50000 / 200000 |

### Soft Filters — "Skip the AI for obvious cases"

These run AFTER hard filters. They auto-classify jobs to save gate agent API costs.

| Filter | What it does | Example |
|---|---|---|
| `negative_keywords` | If job description contains ANY → auto-FILTER | "clearance required", "10+ years" |
| `positive_keywords` | If job description contains ALL → auto-QUALIFY | "intern" |
| `max_experience_years` | If job says "X+ years" and X > this → auto-FILTER | 3 |

### Candidate Profile — "Help the AI understand me"

The `hard_filters` and `preferences` inside `candidate_profile.yaml` are **plain English instructions** read by the AI agent. They're NOT code-executed rules.

| Field | What it does | Example |
|---|---|---|
| `profile.hard_filters` | English dealbreakers the AI enforces | "US roles only", "No defense/clearance roles" |
| `profile.preferences` | Soft preferences the AI weighs | "Prefer ML roles", "Prefer >= $25/hour" |
| `profile.target_roles` | What the user is looking for | "Software Engineer", "Data Scientist" |
| `profile.strongest_areas` | Key skills the AI matches against | "Python", "Machine learning" |

### When to use which

| Scenario | Use |
|---|---|
| "I never want to see senior roles" | Hard filter: `exclude_title_patterns: ["(?i)senior"]` |
| "I never want contract jobs" | Hard filter: `exclude_job_types: ["Contract"]` |
| "Skip anything requiring security clearance" | Soft filter: `negative_keywords: ["clearance required"]` |
| "I prefer ML roles but backend is ok too" | Candidate profile: `preferences` |
| "Only show me internships" | Hard filter: `require_title_patterns: ["intern", "co-op"]` |
| "I'm a Python dev with 2 years experience" | Candidate profile: `summary`, `strongest_areas` |

### Without OPENAI_API_KEY (Tier 1 default)

Only Layers 1 and 2 run. Jobs that pass hard and soft filters sit as `NEW` in the dashboard. The user manually reviews them. The candidate profile has no effect.

### With OPENAI_API_KEY added

All 3 layers run. The gate agent reads each `NEW` job + the candidate profile and marks it `QUALIFIED` or `REJECTED`. The dashboard then shows qualified jobs prominently.

---

## 7. Adding Companies to Track

### How to find a company's ATS type

Most companies use one of these systems. Check the company's careers page:

| URL pattern | ATS type | Config section |
|---|---|---|
| `boards.greenhouse.io/company` or `company.greenhouse.io` | Greenhouse | `greenhouse_companies` |
| `*.myworkdayjobs.com` | Workday | `workday_companies` (free, built-in) |
| `jobs.lever.co/company` | Lever | `lever_companies` |
| `jobs.ashbyhq.com/company` | Ashby | `ashby_companies` |
| Anything else | Career page watcher | `watched_pages` |

### Greenhouse (most common for tech)

Find the greenhouse_id from their careers URL:
- `https://boards.greenhouse.io/stripe` → `greenhouse_id: "stripe"`
- `https://boards.greenhouse.io/openai` → `greenhouse_id: "openai"`

Add to `companies.yaml`:

```yaml
greenhouse_companies:
  Stripe:
    greenhouse_id: "stripe"
    priority: 1

  OpenAI:
    greenhouse_id: "openai"
    priority: 1
```

### Workday (common for large enterprises / finance)

Free, built-in scraper — no API key needed. Hits the public Workday CXS JSON
endpoint directly. Find the Workday URL from a company's careers page (look for
the `*.myworkdayjobs.com` redirect).

87 companies are pre-seeded across 8 industries (pharma, healthcare, finance,
consulting, manufacturing, energy, retail HQ, government contractors). Edit
the `workday_companies` block in `companies.yaml` to add or remove entries.

```yaml
workday_companies:
  Goldman Sachs:
    workday_url: "https://gs.wd5.myworkdayjobs.com/External"
    industry: finance_banking
```

### Job boards (Indeed, Glassdoor)

These search across all companies. Customize search terms and locations:

```yaml
job_boards:
  Indeed:
    enabled: true
    search_terms:
      - "software engineer"
      - "data scientist"
    locations:
      - "Remote"
      - "New York, NY"
    results_wanted: 25
    priority: 2
```

### Lever

```yaml
lever_companies:
  Netflix:
    lever_id: "netflix"
    priority: 1
```

Find the lever_id from `https://jobs.lever.co/<lever_id>`.

### Ashby

```yaml
ashby_companies:
  Linear:
    board_id: "linear"
    priority: 2
```

Find the board_id from `https://jobs.ashbyhq.com/<board_id>`.

### Career page watchers (anything else)

For companies with custom careers pages:

```yaml
watched_pages:
  - company: Apple
    url: https://jobs.apple.com/en-us/search
    link_selector: "a[href*='/en-us/details/']"
```

### Through the dashboard

After the system is running, go to **Settings → Company & Job Filters → Company Sources** and edit the YAML directly in the browser. Click Save when done. Changes take effect on the next discovery cycle.

---

## 8. Common Questions & Troubleshooting

### "How do I start/stop it?"

```powershell
# Start (runs in background)
docker compose up -d

# Stop (keeps data and image)
docker compose down
```

### "How do I wipe the job database and start fresh?"

```powershell
# Removes containers + job database, keeps the image loaded
docker compose down -v
docker compose up -d
```

Jobs will be re-fetched on the next discovery cycle. Config files are untouched.

### "How do I remove everything completely and start from scratch?"

```powershell
# Remove containers, database, AND the Docker image
docker compose down -v
docker rmi job-aggregator:tier1
```

After this you'll need to `docker load -i job-aggregator-tier1.tar.gz` again before running `docker compose up -d`.

### "How do I see what's happening?"

```powershell
# All logs
docker compose logs -f

# Just discovery logs
docker compose logs -f discovery

# Just API logs
docker compose logs -f api
```

### "Jobs aren't appearing"

1. Check discovery is running: `docker compose logs discovery`
2. Look for errors in the output
3. If "Sleeping 30m until next run" — it's working, just waiting for the next cycle
4. First run takes 1-5 minutes depending on how many sources are configured
5. Check that `companies.yaml` actually has enabled sources

### "The gate container keeps restarting"

This is expected if `OPENAI_API_KEY` is not set. The gate logs a warning and sleeps. It won't crash-loop — it just sits idle. This is normal for Tier 1 without the API key.

### "Can I change how often it checks for new jobs?"

Edit `RUN_INTERVAL_MINUTES` in `.env`, then restart:

```powershell
docker compose down && docker compose up -d
```

### "How do I update the config after it's running?"

**Config files (`config/*.yaml`)** — take effect on the next discovery cycle (up to 30 min). No restart needed. To apply immediately:
```powershell
docker compose restart discovery
```

Via the dashboard: Settings → make changes → Save. Same behavior — next cycle picks them up.

**Environment variables (`.env`)** — require a full restart:
```powershell
docker compose down && docker compose up -d
```
This applies to any `.env` change: adding an API key, changing the port, changing `RUN_INTERVAL_MINUTES`, etc.

### "How do I add the gate agent later?"

1. Get an OpenAI API key from https://platform.openai.com/api-keys
2. Either:
   - Add it through the dashboard: Settings → General → API Keys → add `OPENAI_API_KEY`
   - Or edit `.env` and add: `OPENAI_API_KEY=sk-...`
3. Restart: `docker compose down && docker compose up -d`
4. Fill out the Candidate Profile in Settings → Candidate Profile
5. The gate worker will start classifying new jobs as QUALIFIED or REJECTED

### "How do I back up my data?"

The job database is in a Docker volume. To export it:

```powershell
docker compose cp api:/app/data/jobs.db ./jobs-backup.db
```

### "Can I access it from my phone?"

Yes — if Docker is running, go to `http://<computer-ip>:8000` from any device on the same network. Find the computer's IP:

- Windows: `ipconfig` → look for IPv4 Address
- macOS: System Settings → Network → Wi-Fi → Details → IP address

### "What does priority mean in companies.yaml?"

Priority (1-10) controls the order sources are checked. Priority 1 sources are fetched first. It doesn't affect filtering or display — just the order of the scan cycle.

### "Port 8000 is already in use"

Change `API_PORT` in `.env`:

```
API_PORT=8080
```

Then restart and access the dashboard at `http://localhost:8080`.

### "Docker Desktop says 'not enough memory'"

The system uses ~200-300MB of RAM. If Docker Desktop is limited, go to Docker Desktop → Settings → Resources → increase memory to at least 2GB.

---

## 9. Managing the System Day-to-Day

### Updating to a new version

When you send the user a new image:

```powershell
docker compose down
docker load -i job-aggregator-tier1-v2.tar.gz
docker compose up -d
```

Their config files and job data are preserved — only the application code changes.

### Checking system health

- Dashboard: http://localhost:8000 — if it loads, the API is healthy
- Logs: `docker compose logs --tail 50`
- Container status: `docker compose ps`

### Starting on boot (optional)

Docker Desktop can be set to start on login:
- Docker Desktop → Settings → General → "Start Docker Desktop when you sign in"

With `restart: unless-stopped` in the compose file, the containers auto-start when Docker starts.

---

## Quick Reference Card

| Action | Command |
|---|---|
| Start | `docker compose up -d` |
| Stop | `docker compose down` |
| View logs | `docker compose logs -f` |
| Restart after config change | `docker compose restart discovery` |
| Dashboard | http://localhost:8000 |
| Check status | `docker compose ps` |
| Backup database | `docker compose cp api:/app/data/jobs.db ./backup.db` |
