"""Behavior tests for the digest category classifier and subscriber filters.

Covers the title-based classifier in ``src/digest/categorize.py`` and the
digest-side preference filters in ``src/digest/sender.py`` that depend on
it: strict field filtering, source-aware role-level matching, and the
Design field mapping.
"""

from __future__ import annotations

from typing import cast

import aiosqlite
import pytest

from src.digest.categorize import (
    CANONICAL_CATEGORY_ORDER,
    KNOWN_CATEGORIES,
    categorize_job,
)
from src.digest.sender import (
    _FIELD_TO_CATEGORY,
    _apply_preference_filters,
    _passes_category_filter,
    _passes_role_level_filter,
)


# ---------------------------------------------------------------------------
# Classifier: one representative title per category
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Software Engineer Intern", "Software"),
        ("Backend Developer Co-op", "Software"),
        ("Forward Deployed Engineer Intern", "Software"),
        ("Machine Learning Intern", "AI/ML/Data"),
        ("Data Science Intern", "AI/ML/Data"),
        ("ASIC Design Engineer New Grad", "Hardware"),
        ("Embedded Firmware Intern", "Hardware"),
        ("Product Designer Intern", "Design"),
        ("UX Design Intern", "Design"),
        ("Product Manager Intern", "Product"),
        ("Technical Program Manager Intern", "Product"),
        ("Quantitative Research Intern", "Quant"),
        ("Trading Analyst Intern", "Quant"),
        ("Investment Banking Summer Analyst", "Business"),
        ("Financial Analyst Entry Level", "Business"),
        ("Civil Engineering Intern", "Other"),
        ("Warranty Engineering Co-op", "Other"),
        ("Administrative Intern - Public Policy", "Other"),
    ],
)
def test_categorize_by_title(title: str, expected: str) -> None:
    assert categorize_job(title) == expected


# ---------------------------------------------------------------------------
# Classifier: rule-order and boundary behavior
# ---------------------------------------------------------------------------


def test_internal_audit_is_business_not_intern_noise() -> None:
    """'Internal Audit' bank roles must classify as Business, never Software."""
    assert categorize_job("Internal Audit Analyst") == "Business"


def test_business_intelligence_beats_business() -> None:
    """BI is data work even though the title contains 'business'."""
    assert categorize_job("Business Intelligence Intern") == "AI/ML/Data"


def test_bare_engineering_title_defaults_to_software() -> None:
    """Unqualified engineering titles keep Software recall high."""
    assert categorize_job("Engineering Intern") == "Software"


def test_sales_engineer_is_software_not_business() -> None:
    assert categorize_job("Sales Engineer Intern") == "Software"


def test_source_category_fallback_for_vague_title() -> None:
    """A curated source's label rescues titles no rule matches."""
    assert categorize_job("HLS Intern", "Software") == "Software"


def test_title_rules_override_source_category() -> None:
    """Simplify sometimes mislabels; the title wins when a rule matches."""
    assert categorize_job("Administrative Intern", "AI/ML/Data") == "Other"


def test_unknown_source_category_is_ignored() -> None:
    """Legacy board labels like 'Indeed' must not leak into categories."""
    assert categorize_job("Rotational Program Associate", "Indeed") == "Other"


def test_no_title_no_category_is_other() -> None:
    assert categorize_job(None) == "Other"
    assert categorize_job("") == "Other"


def test_field_map_targets_known_categories() -> None:
    """Every subscriber field chip maps to a canonical category."""
    assert set(_FIELD_TO_CATEGORY.values()) <= KNOWN_CATEGORIES
    assert "design" in _FIELD_TO_CATEGORY
    assert _FIELD_TO_CATEGORY["design"] == "Design"
    assert "Design" in CANONICAL_CATEGORY_ORDER


# ---------------------------------------------------------------------------
# Sender: strict category filter
# ---------------------------------------------------------------------------


def _job(title: str, raw_data: str | None = None, source: str = "x") -> aiosqlite.Row:
    """Minimal stand-in for an aiosqlite.Row job_postings record."""
    return cast(
        aiosqlite.Row, {"title": title, "raw_data": raw_data, "source": source}
    )


def test_category_filter_blocks_unselected_fields() -> None:
    """Uncategorized-source jobs no longer bypass the field filter."""
    banking_job = _job("Wealth Management Summer Analyst")
    assert not _passes_category_filter(banking_job, {"Software", "AI/ML/Data"})
    assert _passes_category_filter(banking_job, {"Business"})


def test_category_filter_passes_everything_without_selection() -> None:
    assert _passes_category_filter(_job("Wealth Management Summer Analyst"), set())


def test_category_filter_classifies_by_title_over_raw_label() -> None:
    """An Indeed SWE job with the legacy 'Indeed' label must reach SWE subscribers."""
    job = _job("Software Engineering Intern", raw_data='{"category": "Indeed"}')
    assert _passes_category_filter(job, {"Software"})


# ---------------------------------------------------------------------------
# Sender: role-level filter
# ---------------------------------------------------------------------------


def test_intern_filter_rejects_internal_audit() -> None:
    assert not _passes_role_level_filter("Internal Audit Analyst", "intern")


def test_intern_filter_accepts_word_bounded_variants() -> None:
    assert _passes_role_level_filter("Software Intern", "intern")
    assert _passes_role_level_filter("2027 Internship - Data", "intern")
    assert _passes_role_level_filter("Software Engineering Co-op", "intern")


def test_new_grad_source_rescues_plain_titles() -> None:
    """Simplify new-grad tracker listings count as new-grad without a marker."""
    assert _passes_role_level_filter(
        "Software Engineer",
        "new_grad",
        source="github_simplifyjobs_new-grad-positions",
    )
    assert not _passes_role_level_filter(
        "Software Engineer",
        "new_grad",
        source="greenhouse_stripe",
    )


def test_intern_source_rescues_plain_titles() -> None:
    assert _passes_role_level_filter(
        "Embedded Systems - Summer 2027",
        "intern",
        source="github_simplifyjobs_summer2027-internships",
    )


def test_new_grad_title_markers() -> None:
    assert _passes_role_level_filter("Graduate AI Engineer", "new_grad")
    assert _passes_role_level_filter("Entry-Level Software Engineer", "new_grad")
    assert not _passes_role_level_filter("Software Engineer 3", "new_grad")


def test_both_role_level_passes_everything() -> None:
    assert _passes_role_level_filter("Anything At All", "both")


# ---------------------------------------------------------------------------
# Sender: global senior-title screen
# ---------------------------------------------------------------------------


def test_senior_titles_never_reach_any_subscriber() -> None:
    """Legacy rows with senior markers are screened for every preference set."""
    prefs = {
        "role_level": "both",
        "allowed_categories": set(),
        "allowed_terms": set(),
        "location_preference": "both",
        "excluded_companies_lower": set(),
    }
    jobs = [
        cast(
            aiosqlite.Row,
            {
                "title": "Principal Packaging Engineer New Grad",
                "raw_data": None,
                "source": "github_simplifyjobs_new-grad-positions",
                "location": "Remote",
                "company": "Foundry",
            },
        ),
        cast(
            aiosqlite.Row,
            {
                "title": "Software Engineering Intern",
                "raw_data": None,
                "source": "greenhouse_stripe",
                "location": "Remote",
                "company": "Stripe",
            },
        ),
    ]
    kept = _apply_preference_filters(jobs, prefs)
    assert [j["title"] for j in kept] == ["Software Engineering Intern"]
