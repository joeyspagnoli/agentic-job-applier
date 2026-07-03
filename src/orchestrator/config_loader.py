"""Config-loading helpers shared by the orchestrator entry points.

Keeps YAML reading, list/integer normalization, and the candidate-profile
specific Workday helpers in one place so the discovery loop in
``src.orchestrator.discovery`` stays focused on coordination.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from src.filters.job_filter import JobFilter

# Industry tags whose Workday tenants tend to host EE-relevant intern roles.
# Used to relax the strict title-domain requirement: titles like "Engineering
# Intern" or "Process Engineering Intern" should pass at semiconductor /
# aerospace / automotive employers even though the candidate's target_roles
# don't include "process".
EE_FRIENDLY_INDUSTRIES: frozenset[str] = frozenset({
    "semiconductor",
    "aerospace_defense",
    "automotive",
    "manufacturing_automotive",
    "hardware",
})

# Workday CXS anonymous queries return only ~40 default-sorted results when
# ``searchText`` is empty. Using one of these tokens (drawn from the
# candidate's own target_roles) typically expands a tenant's surfaced jobs
# from 40 to several hundred. Order matters: more specific tokens first.
_WORKDAY_SEARCH_TOKEN_PRIORITY: tuple[str, ...] = (
    "intern",
    "co-op",
    "new grad",
    "junior",
    "early career",
)

# Generic entry-level alternation used by ``_build_loose_filter`` to relax
# the strict "domain + intern" require_title_pattern down to "intern (any
# kind)" for Workday tenants tagged with an EE-friendly industry. Kept in
# lockstep with ``deriveRequireTitlePatterns`` in OnboardingPage.tsx.
_LOOSE_INTERN_REQUIRE_PATTERN = (
    r"(?i)\b(?:intern(ship)?|co-?op|new\s+grad(uate)?"
    r"|early\s+career|junior|jr\.?|entry[\s-]level)\b"
)


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML file and return the parsed mapping.

    Purpose:
        Centralize YAML loading so the orchestrator can read repo config files
        without repeating file-handling logic.
    Args:
        path: Filesystem path to the YAML file that should be parsed.
    Output:
        Returns the parsed YAML content as a dictionary.
    """

    # The orchestrator relies on YAML configs for source definitions, so this
    # helper keeps parsing behavior consistent anywhere config is loaded.
    with open(path) as f:
        loaded = yaml.safe_load(f)
        if isinstance(loaded, dict):
            return loaded
        return {}


def load_optional_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML mapping when present, otherwise return an empty mapping.

    Purpose:
        Support optional configuration files while keeping discovery resilient
        when users have not created every optional config artifact yet.
    Args:
        path: Filesystem path to the YAML file that may or may not exist.
    Output:
        Returns the parsed YAML mapping when available, otherwise `{}`.
    """

    if not path.exists():
        return {}
    return load_yaml(path)


def normalize_string_list(
    value: Any,
    *,
    field_name: str,
    source_name: str,
) -> list[str]:
    """Normalize config values into a non-empty list of strings.

    Purpose:
        Protect fan-out loops from malformed YAML values such as a scalar
        string or mixed-type lists that would otherwise create noisy failures.
    Args:
        value: Raw config value to normalize.
        field_name: Human-readable field name for warning logs.
        source_name: Config section label used in warning logs.
    Output:
        Returns a list of non-empty trimmed strings.
    """

    if value is None:
        return []

    if not isinstance(value, list):
        logger.warning(
            "Expected list for {}.{}; got {}. Ignoring value.",
            source_name,
            field_name,
            type(value).__name__,
        )
        return []

    normalized_values: list[str] = []
    for item in value:
        normalized_item = str(item).strip()
        if normalized_item:
            normalized_values.append(normalized_item)
    return normalized_values


def normalize_positive_int(
    value: Any,
    *,
    field_name: str,
    source_name: str,
    default_value: int,
) -> int:
    """Normalize a positive integer config value with fallback behavior.

    Purpose:
        Keep numeric crawl configuration deterministic even when YAML values
        are missing, malformed, or non-positive.
    Args:
        value: Raw config value to normalize.
        field_name: Human-readable field name for warning logs.
        source_name: Config section label used in warning logs.
        default_value: Fallback value when normalization fails.
    Output:
        Returns a positive integer.
    """

    if value is None:
        return default_value

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        logger.warning(
            "Expected integer for {}.{}; got {!r}. Using default {}.",
            source_name,
            field_name,
            value,
            default_value,
        )
        return default_value

    if parsed <= 0:
        logger.warning(
            "Expected positive integer for {}.{}; got {}. Using default {}.",
            source_name,
            field_name,
            parsed,
            default_value,
        )
        return default_value
    return parsed


def resolve_job_board_default_search_terms(
    *,
    search_criteria_config: dict[str, Any],
    candidate_profile_config: dict[str, Any],
) -> list[str]:
    """Resolve default board search terms from profile and search criteria.

    Purpose:
        Keep discovery targeting config-driven and agnostic by deriving fallback
        query terms from user-owned config rather than hardcoded role strings.
    Args:
        search_criteria_config: Parsed `config/search_criteria.yaml` mapping.
        candidate_profile_config: Parsed `config/candidate_profile.yaml` mapping.
    Output:
        Returns an ordered list of unique default search terms.
    """

    search_defaults = candidate_profile_config.get("search_defaults", {})
    if not isinstance(search_defaults, dict):
        search_defaults = {}

    defaults_from_profile = normalize_string_list(
        search_defaults.get("job_board_search_terms"),
        field_name="search_defaults.job_board_search_terms",
        source_name="candidate_profile",
    )
    defaults_from_criteria = normalize_string_list(
        search_criteria_config.get("target_titles"),
        field_name="target_titles",
        source_name="search_criteria",
    )

    combined_defaults = defaults_from_profile + defaults_from_criteria

    unique_terms: list[str] = []
    seen_terms: set[str] = set()
    for term in combined_defaults:
        normalized_term = str(term).strip()
        if not normalized_term:
            continue
        dedup_key = normalized_term.casefold()
        if dedup_key in seen_terms:
            continue
        seen_terms.add(dedup_key)
        unique_terms.append(normalized_term)

    return unique_terms


def build_loose_filter(filters_config: dict[str, Any]) -> JobFilter | None:
    """Build a relaxed-title-requirement clone of the user's JobFilter.

    Purpose:
        At semiconductor/aerospace/automotive Workday tenants, the strict
        ``domain + intern`` title requirement (derived from the candidate's
        target_roles) misses EE-relevant titles like "Engineering Intern"
        and "Process Engineering Intern" because their domain word is not
        in the candidate's role list. For these EE-friendly employers we
        accept any entry-level title; the company's industry already
        signals role-relevance.
    Args:
        filters_config: Parsed ``filters.yaml`` mapping. The clone preserves
            every other hard/soft filter (excludes, salary, locations,
            keywords) and only relaxes ``require_title_patterns``.
    Output:
        Returns a ``JobFilter`` with the relaxed patterns, or ``None`` when
        the input config is empty (no filtering at all should apply).
    """

    if not filters_config:
        return None
    relaxed_config: dict[str, Any] = {
        "hard_filters": {
            **(filters_config.get("hard_filters") or {}),
            "require_title_patterns": [_LOOSE_INTERN_REQUIRE_PATTERN],
        },
        "soft_filters": filters_config.get("soft_filters") or {},
    }
    return JobFilter(relaxed_config)


def build_curated_filter(filters_config: dict[str, Any]) -> JobFilter | None:
    """Build a JobFilter clone with no title requirement at all.

    Purpose:
        Community internship/new-grad trackers (the ``github_repos``
        section) are already curated to early-career roles, but most of
        their listings carry plain titles — the Simplify new-grad repo is
        full of "Software Engineer" and "Entry-Level Software Engineer"
        entries with no "new grad" marker. Running those through the
        strict ``require_title_patterns`` gate silently dropped the
        majority of the tracker's listings, making the digest worse than
        the free board it ingests. This clone keeps every other hard/soft
        filter (excluded locations, excluded companies, seniority title
        excludes, max age) and removes only the title requirement.
    Args:
        filters_config: Parsed ``filters.yaml`` mapping.
    Output:
        Returns a ``JobFilter`` with ``require_title_patterns`` cleared,
        or ``None`` when the input config is empty.
    """

    if not filters_config:
        return None
    curated_config: dict[str, Any] = {
        "hard_filters": {
            **(filters_config.get("hard_filters") or {}),
            "require_title_patterns": [],
        },
        "soft_filters": filters_config.get("soft_filters") or {},
    }
    return JobFilter(curated_config)


def resolve_workday_search_text(
    candidate_profile_config: dict[str, Any],
) -> str:
    """Pick a single Workday ``searchText`` token from candidate target_roles.

    Purpose:
        Expand Workday CXS anonymous query results from the default ~40 per
        tenant to the hundreds of intern listings actually published, by
        forwarding the candidate's strongest entry-level signal as a free-
        text search.
    Args:
        candidate_profile_config: Parsed ``candidate_profile.yaml`` mapping.
            May be empty when onboarding has not yet run.
    Output:
        Returns the highest-priority token found in target_roles, or an
        empty string when no entry-level signal is detected (the legacy
        default-results behavior is preserved for senior-track candidates).
    """

    profile = candidate_profile_config.get("profile") or {}
    target_roles = profile.get("target_roles") or []
    if not isinstance(target_roles, list):
        return ""
    haystack = " ".join(str(role) for role in target_roles).lower()
    for token in _WORKDAY_SEARCH_TOKEN_PRIORITY:
        if token in haystack:
            return token
    return ""
