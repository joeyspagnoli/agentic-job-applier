"""Apply user-configured hard and soft filters to fetched job postings.

Hard filters reject jobs outright (they never enter the database).
Soft filters auto-categorize obvious matches so the gate agent only
processes genuinely ambiguous postings.

Typical usage:
    from src.filters.job_filter import JobFilter

    job_filter = JobFilter(config)
    action, reason = job_filter.filter_job(job)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from loguru import logger

from src.models.job_posting import JobPosting

# Experience-requirement pattern: "N+ years" or "N years" in description text.
_EXPERIENCE_YEARS_PATTERN = re.compile(
    r"(\d{1,2})\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)",
    re.IGNORECASE,
)

# Salary values are stored in cents; convert annual USD to cents for comparison.
CENTS_PER_DOLLAR = 100


class FilterAction(Enum):
    """Outcome of running a job through the pre-gate filter pipeline.

    Attributes:
        ACCEPT_NEW: Job passes all filters and should enter the gate agent queue.
        ACCEPT_QUALIFIED: Soft filters auto-qualified the job; skip the gate agent.
        REJECT: Hard filter matched; do not insert the job at all.
        REJECT_FILTERED: Soft filter matched; insert with status FILTERED.
    """

    ACCEPT_NEW = "ACCEPT_NEW"
    ACCEPT_QUALIFIED = "ACCEPT_QUALIFIED"
    REJECT = "REJECT"
    REJECT_FILTERED = "REJECT_FILTERED"


class JobFilter:
    """Evaluate jobs against user-configured hard and soft filter rules.

    Attributes:
        _hard: Parsed hard-filter configuration mapping.
        _soft: Parsed soft-filter configuration mapping.
        _exclude_title_compiled: Pre-compiled exclude title regex patterns.
        _require_title_compiled: Pre-compiled require title regex patterns.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Load and compile filter rules from the parsed filters.yaml config.

        Args:
            config: Parsed contents of ``config/filters.yaml``.
        """
        self._hard: dict[str, Any] = config.get("hard_filters", {})
        self._soft: dict[str, Any] = config.get("soft_filters", {})

        self._exclude_title_compiled = self._compile_patterns(
            self._hard.get("exclude_title_patterns", []),
            label="exclude_title_patterns",
        )
        self._require_title_compiled = self._compile_patterns(
            self._hard.get("require_title_patterns", []),
            label="require_title_patterns",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def filter_job(self, job: JobPosting) -> tuple[FilterAction, str]:
        """Run a job through the full hard → soft filter pipeline.

        Args:
            job: A normalized job posting from any fetcher.

        Returns:
            A ``(FilterAction, reason)`` tuple describing the decision.
        """
        # Hard filters run first — any match rejects the job immediately.
        hard_result = self._apply_hard_filters(job)
        if hard_result is not None:
            return hard_result

        # Soft filters auto-categorize obvious matches.
        soft_result = self._apply_soft_filters(job)
        if soft_result is not None:
            return soft_result

        # No filter matched — the job is ambiguous and needs the gate agent.
        return FilterAction.ACCEPT_NEW, "no filter matched"

    # ------------------------------------------------------------------
    # Hard filters
    # ------------------------------------------------------------------

    def _apply_hard_filters(
        self,
        job: JobPosting,
    ) -> tuple[FilterAction, str] | None:
        """Run all hard-filter checks in priority order.

        Args:
            job: The job posting to evaluate.

        Returns:
            A ``(REJECT, reason)`` tuple on the first match, or ``None``
            if no hard filter triggers.
        """
        result = self._check_exclude_job_type(job)
        if result is not None:
            return result

        result = self._check_exclude_title(job)
        if result is not None:
            return result

        result = self._check_require_title(job)
        if result is not None:
            return result

        result = self._check_exclude_location(job)
        if result is not None:
            return result

        result = self._check_require_remote(job)
        if result is not None:
            return result

        result = self._check_exclude_company(job)
        if result is not None:
            return result

        result = self._check_max_days_old(job)
        if result is not None:
            return result

        result = self._check_salary_bounds(job)
        if result is not None:
            return result

        return None

    def _check_exclude_job_type(
        self,
        job: JobPosting,
    ) -> tuple[FilterAction, str] | None:
        """Reject jobs whose normalized job_type is in the exclude list."""
        exclude_types = self._hard.get("exclude_job_types", [])
        if not exclude_types or not job.job_type:
            return None

        exclude_lower = {t.lower() for t in exclude_types if isinstance(t, str)}
        if job.job_type.lower() in exclude_lower:
            return FilterAction.REJECT, f"job_type '{job.job_type}' excluded"
        return None

    def _check_exclude_title(
        self,
        job: JobPosting,
    ) -> tuple[FilterAction, str] | None:
        """Reject jobs whose title matches any exclude pattern."""
        for pattern in self._exclude_title_compiled:
            if pattern.search(job.title):
                return FilterAction.REJECT, f"title matches exclude pattern '{pattern.pattern}'"
        return None

    def _check_require_title(
        self,
        job: JobPosting,
    ) -> tuple[FilterAction, str] | None:
        """Reject jobs whose title does not match any require pattern."""
        if not self._require_title_compiled:
            return None

        for pattern in self._require_title_compiled:
            if pattern.search(job.title):
                return None

        return FilterAction.REJECT, "title does not match any require pattern"

    def _check_exclude_location(
        self,
        job: JobPosting,
    ) -> tuple[FilterAction, str] | None:
        """Reject jobs whose location contains an excluded substring."""
        exclude_locations = self._hard.get("exclude_locations", [])
        if not exclude_locations or not job.location:
            return None

        location_lower = job.location.lower()
        for loc in exclude_locations:
            if isinstance(loc, str) and loc.lower() in location_lower:
                return FilterAction.REJECT, f"location contains excluded '{loc}'"
        return None

    def _check_require_remote(
        self,
        job: JobPosting,
    ) -> tuple[FilterAction, str] | None:
        """Reject non-remote jobs when require_remote is enabled."""
        if not self._hard.get("require_remote", False):
            return None

        if job.is_remote:
            return None

        return FilterAction.REJECT, "job is not remote (require_remote enabled)"

    def _check_exclude_company(
        self,
        job: JobPosting,
    ) -> tuple[FilterAction, str] | None:
        """Reject jobs from blocklisted companies."""
        exclude_companies = self._hard.get("exclude_companies", [])
        if not exclude_companies:
            return None

        exclude_lower = {c.lower() for c in exclude_companies if isinstance(c, str)}
        if job.company.lower() in exclude_lower:
            return FilterAction.REJECT, f"company '{job.company}' excluded"
        return None

    def _check_max_days_old(
        self,
        job: JobPosting,
    ) -> tuple[FilterAction, str] | None:
        """Reject jobs older than the configured max_days_old threshold."""
        max_days = self._hard.get("max_days_old", 0)
        if not max_days or not job.posted_date:
            return None

        parsed_date = self._try_parse_date(job.posted_date)
        if parsed_date is None:
            return None

        age_days = (datetime.now(tz=timezone.utc) - parsed_date).days
        if age_days > max_days:
            return FilterAction.REJECT, f"job is {age_days} days old (max {max_days})"
        return None

    def _check_salary_bounds(
        self,
        job: JobPosting,
    ) -> tuple[FilterAction, str] | None:
        """Reject jobs whose salary falls outside configured bounds."""
        min_salary = self._hard.get("min_salary_usd", 0)
        max_salary = self._hard.get("max_salary_usd", 0)

        if not min_salary and not max_salary:
            return None

        # Only filter when the job actually reports salary data.
        if job.salary_min is None and job.salary_max is None:
            return None

        min_cents = min_salary * CENTS_PER_DOLLAR if min_salary else 0
        max_cents = max_salary * CENTS_PER_DOLLAR if max_salary else 0

        if min_cents and job.salary_max is not None and job.salary_max < min_cents:
            return FilterAction.REJECT, f"salary_max below minimum ${min_salary}"

        if max_cents and job.salary_min is not None and job.salary_min > max_cents:
            return FilterAction.REJECT, f"salary_min above maximum ${max_salary}"

        return None

    # ------------------------------------------------------------------
    # Soft filters
    # ------------------------------------------------------------------

    def _apply_soft_filters(
        self,
        job: JobPosting,
    ) -> tuple[FilterAction, str] | None:
        """Run soft-filter checks that auto-categorize obvious matches.

        Args:
            job: The job posting to evaluate.

        Returns:
            A ``(REJECT_FILTERED, reason)`` or ``(ACCEPT_QUALIFIED, reason)``
            tuple on the first match, or ``None`` if no soft filter triggers.
        """
        result = self._check_negative_keywords(job)
        if result is not None:
            return result

        result = self._check_experience_years(job)
        if result is not None:
            return result

        result = self._check_positive_keywords(job)
        if result is not None:
            return result

        return None

    def _check_negative_keywords(
        self,
        job: JobPosting,
    ) -> tuple[FilterAction, str] | None:
        """Auto-filter jobs whose description contains negative keywords."""
        negative_keywords = self._soft.get("negative_keywords", [])
        if not negative_keywords:
            return None

        description_lower = job.description.lower()
        for keyword in negative_keywords:
            if isinstance(keyword, str) and keyword.lower() in description_lower:
                return (
                    FilterAction.REJECT_FILTERED,
                    f"description contains negative keyword '{keyword}'",
                )
        return None

    def _check_experience_years(
        self,
        job: JobPosting,
    ) -> tuple[FilterAction, str] | None:
        """Auto-filter jobs requiring more experience than the configured max."""
        max_exp = self._soft.get("max_experience_years", 0)
        if not max_exp:
            return None

        matches = _EXPERIENCE_YEARS_PATTERN.findall(job.description)
        for years_str in matches:
            try:
                years = int(years_str)
            except ValueError:
                continue

            if years > max_exp:
                return (
                    FilterAction.REJECT_FILTERED,
                    f"requires {years}+ years experience (max {max_exp})",
                )

        return None

    def _check_positive_keywords(
        self,
        job: JobPosting,
    ) -> tuple[FilterAction, str] | None:
        """Auto-qualify jobs whose description contains any positive keyword.

        Using ``any`` rather than ``all`` means a job is fast-tracked once a
        single domain-relevant skill from the user's profile appears in the
        description, reducing gate-agent load without sacrificing relevance.

        Args:
            job: The job posting to evaluate.

        Returns:
            An ``(ACCEPT_QUALIFIED, reason)`` tuple on the first matching
            keyword, or ``None`` if no keyword appears.
        """
        positive_keywords = self._soft.get("positive_keywords", [])
        if not positive_keywords:
            return None

        description_lower = job.description.lower()
        matched = next(
            (kw for kw in positive_keywords if isinstance(kw, str) and kw.lower() in description_lower),
            None,
        )
        if matched is not None:
            return (
                FilterAction.ACCEPT_QUALIFIED,
                f"description contains positive keyword '{matched}'",
            )
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compile_patterns(
        patterns: list[str],
        *,
        label: str,
    ) -> list[re.Pattern[str]]:
        """Compile a list of regex pattern strings, skipping invalid ones.

        Args:
            patterns: Raw regex strings from the YAML config.
            label: Config field name used in warning logs for bad patterns.

        Returns:
            A list of compiled regex pattern objects.
        """
        compiled: list[re.Pattern[str]] = []
        for raw in patterns:
            if not isinstance(raw, str):
                continue
            try:
                compiled.append(re.compile(raw, re.IGNORECASE))
            except re.error as exc:
                logger.warning(
                    "Invalid regex in {}: {!r} — {}",
                    label,
                    raw,
                    exc,
                )
        return compiled

    @staticmethod
    def _try_parse_date(date_str: str) -> datetime | None:
        """Best-effort parse of a date string into a timezone-aware datetime.

        Args:
            date_str: Raw date string from a fetcher (ISO 8601 or similar).

        Returns:
            A timezone-aware ``datetime`` on success, or ``None`` when the
            string cannot be parsed.
        """
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                continue

        # Unix timestamp (SimplifyJobs uses epoch seconds).
        try:
            epoch = float(date_str)
            return datetime.fromtimestamp(epoch, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            pass

        return None
