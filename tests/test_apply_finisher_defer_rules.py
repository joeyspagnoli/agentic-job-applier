"""Behavioral tests for DeferRules / load_defer_rules.

Covers every Tier-3 label category from the gap-synthesis and all Tier-2
essay patterns, plus bypass-type handling and never_defer_overrides logic.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.agents.apply_finisher.defer_rules import DeferRules, load_defer_rules


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def default_rules(tmp_path: Path) -> DeferRules:
    """Load the real config/defer_rules.yaml from the project root."""
    project_root = Path(__file__).parent.parent
    return load_defer_rules(project_root / "config" / "defer_rules.yaml")


@pytest.fixture()
def rules_with_salary_override(tmp_path: Path) -> DeferRules:
    """Rules where 'salary range' is whitelisted out of Tier 3."""
    yaml_content = {
        "always_defer_labels": [
            {"regex": "(?i)salary|compensation|desired pay"},
        ],
        "draft_and_flag_labels": [],
        "bypass_field_types": ["file", "hidden"],
        "never_defer_overrides": [
            {"regex": "(?i)^salary range$"},
        ],
    }
    rules_file = tmp_path / "defer_rules.yaml"
    rules_file.write_text(yaml.safe_dump(yaml_content), encoding="utf-8")
    return load_defer_rules(rules_file)


# ---------------------------------------------------------------------------
# Tier 3 — sponsorship
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label",
    [
        "Will you now or in the future require sponsorship?",
        "Do you require visa sponsorship?",
        "Authorize to sponsor immigration",
    ],
)
def test_sponsorship_labels_are_tier3(label: str, default_rules: DeferRules) -> None:
    """Sponsorship-related labels must always classify as tier3."""
    assert default_rules.classify(label, "select") == "tier3"


# ---------------------------------------------------------------------------
# Tier 3 — EEO / demographics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label",
    [
        "Gender",
        "Race/Ethnicity",
        "Veteran Status",
        "disability status",
        "Please self-identify your ethnicity",
        "Do you self identify as Hispanic?",
    ],
)
def test_eeo_labels_are_tier3(label: str, default_rules: DeferRules) -> None:
    """EEO demographic labels must always classify as tier3."""
    assert default_rules.classify(label, "select") == "tier3"


# ---------------------------------------------------------------------------
# Tier 3 — salary / compensation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label",
    [
        "Desired salary",
        "Compensation expectations",
        "Expected desired pay",
        "What is your salary expectation?",
    ],
)
def test_salary_labels_are_tier3(label: str, default_rules: DeferRules) -> None:
    """Salary/compensation labels must always classify as tier3."""
    assert default_rules.classify(label, "text") == "tier3"


# ---------------------------------------------------------------------------
# Tier 3 — start date
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label",
    [
        "Start date",
        "When can you start?",
        "Earliest start date",
        "What is your earliest start?",
    ],
)
def test_start_date_labels_are_tier3(label: str, default_rules: DeferRules) -> None:
    """Start-date labels must always classify as tier3."""
    assert default_rules.classify(label, "date") == "tier3"


# ---------------------------------------------------------------------------
# Tier 2 — essay / motivation questions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label",
    [
        "Why are you interested in this role?",
        "Why this position?",
        "Why do you want to join us?",
        "Why this company?",
        "Tell us about your experience",
        "Describe your experience with Python",
        "What was the hardest problem you've solved?",
        "Cover letter",
    ],
)
def test_essay_labels_are_tier2(label: str, default_rules: DeferRules) -> None:
    """Essay / motivation labels must classify as tier2."""
    assert default_rules.classify(label, "textarea") == "tier2"


# ---------------------------------------------------------------------------
# Tier 1 — unmatched labels
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label",
    [
        "LinkedIn URL",
        "Phone number",
        "How did you hear about us?",
        "Country",
    ],
)
def test_neutral_labels_are_tier1(label: str, default_rules: DeferRules) -> None:
    """Labels not matching any rule must classify as tier1."""
    assert default_rules.classify(label, "text") == "tier1"


# ---------------------------------------------------------------------------
# bypass_field_types
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field_type", ["file", "hidden", "submit", "button"])
def test_bypass_field_types_are_skipped(
    field_type: str, default_rules: DeferRules
) -> None:
    """should_bypass must return True for every configured bypass type."""
    assert default_rules.should_bypass(field_type) is True


def test_text_field_is_not_bypassed(default_rules: DeferRules) -> None:
    """should_bypass must return False for a normal text input."""
    assert default_rules.should_bypass("text") is False


# ---------------------------------------------------------------------------
# never_defer_overrides — whitelist beats Tier 3
# ---------------------------------------------------------------------------


def test_exact_salary_range_is_not_tier3_when_overridden(
    rules_with_salary_override: DeferRules,
) -> None:
    """'salary range' (exact) must fall through to tier1 when whitelisted."""
    # The always_defer_labels regex matches "salary range" …
    # … but never_defer_overrides regex (?i)^salary range$ removes Tier 3.
    # No draft_and_flag_labels are configured, so it lands on tier1.
    result = rules_with_salary_override.classify("salary range", "text")
    assert result == "tier1"


def test_salary_expectation_still_tier3_when_not_exactly_overridden(
    rules_with_salary_override: DeferRules,
) -> None:
    """'What is your salary expectation?' must stay tier3 (override is ^salary range$)."""
    result = rules_with_salary_override.classify(
        "What is your salary expectation?", "text"
    )
    assert result == "tier3"
