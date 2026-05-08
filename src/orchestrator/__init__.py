"""Job discovery orchestration package.

Splits the discovery cycle into config loading, the insert pipeline, and per-
fetcher entry points so each piece stays focused and testable.  The public
API mirrors the legacy ``main.py`` symbols that scripts and tests already
depend on.
"""

from src.orchestrator.discovery import run_job_discovery

__all__ = ["run_job_discovery"]
