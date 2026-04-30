"""Behavioral tests for ``JobFilter._check_positive_keywords``.

These tests pin down the contract documented in the testing handoff:

- Empty ``positive_keywords`` configuration yields ``None``.
- A keyword present in the description yields
  ``(ACCEPT_QUALIFIED, "description contains positive keyword '{kw}'")``.
- A keyword absent from the description yields ``None``.
- With multiple configured keywords, the first match short-circuits and the
  reason names that exact keyword.
- Matching is case-insensitive (matches the rest of the soft-filter family).
- Non-string entries in the configured list are silently skipped — they must
  not raise.

The handoff explicitly flagged the ``all() → any()`` change as the bug fix
for users with non-software profiles whose descriptions never contained
every configured keyword. These tests assert the new behavior directly.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.filters.job_filter import FilterAction, JobFilter
from src.models.job_posting import JobPosting


def _build_filter(positive_keywords: list[Any]) -> JobFilter:
    """Construct a ``JobFilter`` whose only configured rule is the keyword list.

    Args:
        positive_keywords: Raw list to place under ``soft_filters.positive_keywords``.

    Returns:
        Initialized ``JobFilter`` with no hard rules and only the requested
        positive-keyword soft rule.
    """
    return JobFilter({"soft_filters": {"positive_keywords": positive_keywords}})


def _build_job(description: str) -> JobPosting:
    """Build a minimal valid ``JobPosting`` carrying the given description.

    Args:
        description: Raw description text the filter will scan.

    Returns:
        ``JobPosting`` with required fields populated and the supplied
        description.
    """
    return JobPosting(
        source="test",
        source_url="https://example.com/job",
        company="Acme",
        title="Engineer",
        description=description,
    )


def test_returns_none_when_positive_keywords_config_is_empty() -> None:
    # Arrange
    job_filter = _build_filter([])
    job = _build_job("we love python and react")

    # Act
    result = job_filter._check_positive_keywords(job)

    # Assert
    assert result is None


def test_returns_none_when_positive_keywords_key_is_missing() -> None:
    # Arrange
    job_filter = JobFilter({"soft_filters": {}})
    job = _build_job("anything at all")

    # Act
    result = job_filter._check_positive_keywords(job)

    # Assert
    assert result is None


def test_returns_accept_qualified_when_single_keyword_present() -> None:
    # Arrange
    job_filter = _build_filter(["python"])
    job = _build_job("Looking for a Python engineer with django experience.")

    # Act
    result = job_filter._check_positive_keywords(job)

    # Assert
    assert result == (
        FilterAction.ACCEPT_QUALIFIED,
        "description contains positive keyword 'python'",
    )


def test_returns_none_when_no_keyword_matches_description() -> None:
    # Arrange
    job_filter = _build_filter(["rust", "haskell"])
    job = _build_job("We use Python and Go on the backend.")

    # Act
    result = job_filter._check_positive_keywords(job)

    # Assert
    assert result is None


def test_returns_first_matching_keyword_when_multiple_configured_only_one_present() -> None:
    """Bug 5 fix: any() semantics — a single match short-circuits to qualified."""
    # Arrange
    job_filter = _build_filter(["rust", "kubernetes", "react"])
    job = _build_job("Frontend role; React experience required, no backend.")

    # Act
    result = job_filter._check_positive_keywords(job)

    # Assert
    assert result == (
        FilterAction.ACCEPT_QUALIFIED,
        "description contains positive keyword 'react'",
    )


def test_returns_first_keyword_in_config_order_when_multiple_match() -> None:
    """Reason string must name the FIRST keyword in the config that matches,
    not an arbitrary one — callers grep on this string for analytics."""
    # Arrange
    job_filter = _build_filter(["python", "react"])
    job = _build_job("We use Python AND React together every day.")

    # Act
    result = job_filter._check_positive_keywords(job)

    # Assert
    assert result == (
        FilterAction.ACCEPT_QUALIFIED,
        "description contains positive keyword 'python'",
    )


def test_match_is_case_insensitive() -> None:
    # Arrange
    job_filter = _build_filter(["PyThOn"])
    job = _build_job("python developer wanted")

    # Act
    result = job_filter._check_positive_keywords(job)

    # Assert
    assert result == (
        FilterAction.ACCEPT_QUALIFIED,
        "description contains positive keyword 'PyThOn'",
    )


def test_non_string_entries_in_config_are_skipped_silently() -> None:
    # Arrange
    job_filter = _build_filter([None, 42, "python"])
    job = _build_job("Senior python engineer")

    # Act
    result = job_filter._check_positive_keywords(job)

    # Assert
    assert result == (
        FilterAction.ACCEPT_QUALIFIED,
        "description contains positive keyword 'python'",
    )


def test_returns_none_when_only_non_string_entries_configured() -> None:
    # Arrange
    job_filter = _build_filter([None, 42, {}])
    job = _build_job("anything at all")

    # Act
    result = job_filter._check_positive_keywords(job)

    # Assert
    assert result is None


def test_empty_description_yields_none_even_with_keywords_configured() -> None:
    # Arrange
    job_filter = _build_filter(["python"])
    job = _build_job("")

    # Act
    result = job_filter._check_positive_keywords(job)

    # Assert
    assert result is None


@pytest.mark.parametrize(
    "description,keyword,expected_match",
    [
        ("loves python", "python", True),
        ("loves Python", "python", True),
        ("loves PYTHON", "python", True),
        ("loves py", "python", False),
        ("nothing relevant here", "kubernetes", False),
        ("kubernetes is great", "Kubernetes", True),
    ],
)
def test_substring_case_insensitive_matching_table(
    description: str,
    keyword: str,
    expected_match: bool,
) -> None:
    # Arrange
    job_filter = _build_filter([keyword])
    job = _build_job(description)

    # Act
    result = job_filter._check_positive_keywords(job)

    # Assert
    if expected_match:
        assert result is not None
        action, reason = result
        assert action is FilterAction.ACCEPT_QUALIFIED
        assert keyword in reason
    else:
        assert result is None
