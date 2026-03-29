"""Pre-gate job filtering to reduce gate agent invocations.

This package applies user-configured hard and soft filters between the
deduplication step and database insertion, so only ambiguous jobs reach
the gate agent.
"""

from src.filters.job_filter import FilterAction, JobFilter

__all__ = [
    "FilterAction",
    "JobFilter",
]
