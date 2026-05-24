"""Module-level constants and compiled patterns for the API surface.

This module centralizes configuration constants used by FastAPI routers and
service helpers — paths to dashboard assets, settings YAML files, system
scripts, tailored-resume artifacts, regex patterns, and pagination defaults.
Importing constants from here keeps `api.main` focused on app construction.
"""

from __future__ import annotations

import re
from typing import Literal

from src.utils.paths import resolve_repo_root

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
DEFAULT_POLLING_SECONDS = 30

SYSTEM_ACTION_STOP = "stop"
SYSTEM_ACTION_RESTART = "restart"
SYSTEM_ACTION_FETCH_JOBS = "fetch_jobs"
SYSTEM_ACTION_STATUS_ACCEPTED = "accepted"

DASHBOARD_DIST_DIR = resolve_repo_root() / "dashboard" / "dist"
DASHBOARD_ASSETS_DIR = DASHBOARD_DIST_DIR / "assets"
DASHBOARD_INDEX_FILE = DASHBOARD_DIST_DIR / "index.html"

SETTINGS_RESUME_PATH = resolve_repo_root() / "config" / "resume.tex"
SETTINGS_PROFILE_PATH = resolve_repo_root() / "config" / "candidate_profile.yaml"
SETTINGS_FILTERS_PATH = resolve_repo_root() / "config" / "filters.yaml"
SETTINGS_COMPANIES_PATH = resolve_repo_root() / "config" / "companies.yaml"
SETTINGS_BACKUPS_DIR = resolve_repo_root() / "config" / "backups"
SETTINGS_ENV_PATH = resolve_repo_root() / ".env"

SYSTEM_STOP_SCRIPT_PATH = resolve_repo_root() / "scripts" / "docker" / "stop_stack.sh"
SYSTEM_RESTART_SCRIPT_PATH = (
    resolve_repo_root() / "scripts" / "docker" / "restart_stack.sh"
)
SYSTEM_FETCH_JOBS_SCRIPT_PATH = (
    resolve_repo_root() / "scripts" / "docker" / "restart_discovery.sh"
)

TAILORED_RESUME_DIR = resolve_repo_root() / "data" / "tailored_resumes"
TAILORED_RESUME_FILENAME = "resume_tailored.pdf"
TAILORED_RESUME_TOKEN_ENV_KEY = "TAILORED_RESUME_DOWNLOAD_TOKEN"
TAILORED_RESUME_TOKEN_HEADER = "x-tailored-resume-token"
LOCAL_TAILORED_RESUME_CLIENT_HOSTS = frozenset(
    {
        "127.0.0.1",
        "::1",
        "localhost",
        "testclient",
    }
)

JOB_HASH_PATTERN = re.compile(r"^[a-f0-9]{32,64}$")
SETTINGS_BACKUP_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
SETTINGS_BACKUP_FILE_LIMIT = 10

WORK_AUTH_STATUS_YES: Literal["yes"] = "yes"
WORK_AUTH_STATUS_NO: Literal["no"] = "no"
WORK_AUTH_STATUS_UNKNOWN: Literal["unknown"] = "unknown"
COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")

TEX_SECTION_HEADER_PATTERN = re.compile(r"\\section\{\\textbf\{(?P<heading>[^}]+)\}\}")
TEX_SECTION_HEADING_ALIASES: dict[str, str] = {
    "work experience": "Experience",
    "professional experience": "Experience",
    "employment": "Experience",
    "internships": "Experience",
    "project experience": "Projects",
    "selected projects": "Projects",
    "technical projects": "Projects",
    "skills": "Skills and Achievements",
    "technical skills": "Skills and Achievements",
    "skills and technologies": "Skills and Achievements",
    "education & coursework": "Education",
    "academic background": "Education",
}
REQUIRED_TEX_SECTION_HEADINGS: tuple[str, ...] = (
    "Education",
    "Experience",
    "Projects",
    "Skills and Achievements",
)
PERSONAL_NAME_PATTERN = re.compile(r"\\bfseries\s+([^}]+)\}\\\\")
PERSONAL_CONTACT_PATTERN = re.compile(
    r"\{\\normalsize\s*(.+?)\}\s*\\end\{center\}",
    flags=re.DOTALL,
)

# Valid API key names that the settings UI may read/write. The current API
# only writes OPENAI_API_KEY (see issue #35), but the wider set is kept here
# so future BYOK work can reuse the same .env helper without churn.
ALLOWED_API_KEY_NAMES: frozenset[str] = frozenset(
    {
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_BASE_URL",
        "ADZUNA_APP_ID",
        "ADZUNA_APP_KEY",
    }
)

# Valid service tier identifiers.
ALLOWED_SERVICE_TIERS: frozenset[str] = frozenset({"base", "latex", "full"})
