"""Per-fetcher orchestrator entry points.

Each module exports a ``fetch_<source>_jobs`` coroutine that wraps the
matching fetcher class from ``src.fetchers``: it manages the crawl-history
row, runs jobs through the dedup + filter + insert pipeline, and returns
the four-element accounting tuple expected by ``run_job_discovery``.
"""

from src.orchestrator.crawl_runners.adzuna import fetch_adzuna_jobs
from src.orchestrator.crawl_runners.ashby import fetch_ashby_jobs
from src.orchestrator.crawl_runners.career_pages import fetch_career_page_jobs
from src.orchestrator.crawl_runners.github_repos import fetch_github_repo_jobs
from src.orchestrator.crawl_runners.greenhouse import fetch_greenhouse_jobs
from src.orchestrator.crawl_runners.icims import fetch_icims_jobs
from src.orchestrator.crawl_runners.jobspy import fetch_jobspy_jobs
from src.orchestrator.crawl_runners.lever import fetch_lever_jobs
from src.orchestrator.crawl_runners.linkedin import fetch_linkedin_jobs
from src.orchestrator.crawl_runners.taleo import fetch_taleo_jobs
from src.orchestrator.crawl_runners.workday import fetch_workday_jobs

__all__ = [
    "fetch_adzuna_jobs",
    "fetch_ashby_jobs",
    "fetch_career_page_jobs",
    "fetch_github_repo_jobs",
    "fetch_greenhouse_jobs",
    "fetch_icims_jobs",
    "fetch_jobspy_jobs",
    "fetch_lever_jobs",
    "fetch_linkedin_jobs",
    "fetch_taleo_jobs",
    "fetch_workday_jobs",
]
