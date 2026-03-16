"""Unit tests for fetcher _parse_job and _normalize_salary methods.

Purpose:
    Validate field mapping, default handling, NaN coercion, and salary
    normalization logic in the Greenhouse, Apify, and JobSpy fetchers
    without making any network requests.
"""

from __future__ import annotations

import pytest

from src.fetchers.apify_fetcher import ApifyWorkdayFetcher
from src.fetchers.greenhouse_fetcher import GreenhouseFetcher
from src.fetchers.jobspy_fetcher import JobSpyFetcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_greenhouse() -> GreenhouseFetcher:
    """Create a GreenhouseFetcher instance for testing without HTTP setup.

    Purpose:
        Provide a minimal Greenhouse fetcher whose _parse_job can be called
        directly without an HTTP client or async context.
    Arg(s):
        None.
    Output:
        Returns a GreenhouseFetcher configured for 'TestCo'.
    """
    return GreenhouseFetcher(company_name="TestCo", greenhouse_id="testco")


def _make_apify() -> ApifyWorkdayFetcher:
    """Create an ApifyWorkdayFetcher instance for testing without API setup.

    Purpose:
        Provide a minimal Apify fetcher whose _parse_job can be called
        directly without an Apify client or async context.
    Arg(s):
        None.
    Output:
        Returns an ApifyWorkdayFetcher configured for 'TestCo'.
    """
    return ApifyWorkdayFetcher(
        company_name="TestCo",
        workday_url="https://testco.wd1.myworkdayjobs.com/careers",
    )


def _make_jobspy() -> JobSpyFetcher:
    """Create a JobSpyFetcher instance for testing without scraping.

    Purpose:
        Provide a minimal JobSpy fetcher whose _parse_job and _normalize_salary
        can be called directly without triggering scraping.
    Arg(s):
        None.
    Output:
        Returns a JobSpyFetcher configured for Indeed.
    """
    return JobSpyFetcher(
        site_name="indeed",
        search_term="software engineer",
        location="Remote",
    )


# ---------------------------------------------------------------------------
# Greenhouse tests
# ---------------------------------------------------------------------------


def test_greenhouse_parse_valid_response_maps_fields_correctly() -> None:
    """Verify _parse_job maps standard Greenhouse fields into JobPosting.

    Purpose:
        Validate that title, location, description, and source URL are
        correctly extracted from a representative Greenhouse API payload.
    """

    fetcher = _make_greenhouse()
    payload = {
        "title": "Staff Engineer",
        "absolute_url": "https://boards.greenhouse.io/testco/jobs/123",
        "location": {"name": "San Francisco, CA"},
        "content": "<p>We are looking for a <b>Staff Engineer</b>.</p>",
        "updated_at": "2024-01-15T10:00:00Z",
    }

    result = fetcher._parse_job(payload)

    assert result.title == "Staff Engineer"
    assert result.location == "San Francisco, CA"
    assert "Staff Engineer" in result.description
    assert "<b>" not in result.description
    assert result.source_url == "https://boards.greenhouse.io/testco/jobs/123"
    assert result.company == "TestCo"


def test_greenhouse_parse_missing_optional_fields_uses_defaults() -> None:
    """Verify _parse_job uses safe defaults when optional fields are absent.

    Purpose:
        Validate that missing salary, location, and description fields do not
        cause exceptions and fall back to expected defaults.
    """

    fetcher = _make_greenhouse()
    payload = {
        "title": "Unknown Role",
        "absolute_url": "https://boards.greenhouse.io/testco/jobs/999",
    }

    result = fetcher._parse_job(payload)

    assert result.title == "Unknown Role"
    assert result.location == ""
    assert result.description == ""
    assert result.salary_min is None
    assert result.salary_max is None
    assert result.salary_source == "not_listed"


# ---------------------------------------------------------------------------
# Apify tests
# ---------------------------------------------------------------------------


def test_apify_parse_valid_workday_item_maps_fields_correctly() -> None:
    """Verify _parse_job maps standard Apify Workday fields into JobPosting.

    Purpose:
        Validate that title, location, description, and URL are correctly
        extracted from a representative Apify dataset item.
    """

    fetcher = _make_apify()
    item = {
        "title": "Senior Data Engineer",
        "location": "Austin, TX",
        "description": "Build pipelines for large-scale data processing.",
        "url": "https://testco.wd1.myworkdayjobs.com/careers/job/Senior-Data-Engineer",
        "postedDate": "2024-02-01",
    }

    result = fetcher._parse_job(item)

    assert result.title == "Senior Data Engineer"
    assert result.location == "Austin, TX"
    assert "pipelines" in result.description
    assert result.source_url == "https://testco.wd1.myworkdayjobs.com/careers/job/Senior-Data-Engineer"
    assert result.company == "TestCo"


def test_apify_parse_alternative_field_names() -> None:
    """Verify _parse_job picks up jobTitle/jobLocation/jobDescription alternatives.

    Purpose:
        Validate that Apify items using the alternative field naming convention
        are normalized correctly without missing data.
    """

    fetcher = _make_apify()
    item = {
        "jobTitle": "ML Engineer",
        "jobLocation": "Remote",
        "jobDescription": "Train and deploy machine learning models.",
    }

    result = fetcher._parse_job(item)

    assert result.title == "ML Engineer"
    assert result.location == "Remote"
    assert "machine learning" in result.description


# ---------------------------------------------------------------------------
# JobSpy salary normalization tests
# ---------------------------------------------------------------------------


def test_jobspy_salary_normalization_hourly_to_annual_cents() -> None:
    """Verify _normalize_salary converts hourly rates to annual cents correctly.

    Purpose:
        Validate that a $50–$60/hour salary is converted to the correct annual
        cents value using the 2080-hour work year multiplier.
    """

    fetcher = _make_jobspy()

    min_cents, max_cents = fetcher._normalize_salary(50.0, 60.0, "hourly")

    assert min_cents == int(50.0 * 2080 * 100)
    assert max_cents == int(60.0 * 2080 * 100)


def test_jobspy_salary_normalization_monthly_to_annual_cents() -> None:
    """Verify _normalize_salary converts monthly rates to annual cents correctly.

    Purpose:
        Validate that a $5000–$6000/month salary is converted to the correct
        annual cents value using the 12-month multiplier.
    """

    fetcher = _make_jobspy()

    min_cents, max_cents = fetcher._normalize_salary(5000.0, 6000.0, "monthly")

    assert min_cents == int(5000.0 * 12 * 100)
    assert max_cents == int(6000.0 * 12 * 100)


def test_jobspy_handle_nan_values_in_description() -> None:
    """Verify _parse_job converts NaN description to empty string.

    Purpose:
        Validate that a pandas NaN float in the description field is coerced
        to an empty string rather than causing a crash or leaking 'nan'.
    """

    fetcher = _make_jobspy()
    row = {
        "title": "Backend Engineer",
        "company": "NanCo",
        "location": "Remote",
        "description": float("nan"),
        "job_url": "https://example.com/job/1",
        "min_amount": None,
        "max_amount": None,
        "currency": "USD",
        "interval": None,
    }

    result = fetcher._parse_job(row)

    assert result.description == ""
    assert result.title == "Backend Engineer"


def test_jobspy_salary_returns_none_when_both_amounts_none() -> None:
    """Verify _normalize_salary returns (None, None) when both amounts are None.

    Purpose:
        Validate that missing salary data is represented as a None tuple rather
        than zero cents or another sentinel value.
    """

    fetcher = _make_jobspy()

    min_cents, max_cents = fetcher._normalize_salary(None, None, "yearly")

    assert min_cents is None
    assert max_cents is None
