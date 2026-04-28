"""Fuzzy deduplication for job postings.

Inspired by career-ops' dedup-tracker.mjs. Supplements the existing
SHA-256 hash dedup with company name normalization and role title
token-overlap matching to catch near-duplicates from different sources.
"""

from __future__ import annotations

import re
import unicodedata

ROLE_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "for", "in", "at", "to",
    "with", "is", "on", "by", "as", "-", "&", "/", "|",
})

# Minimum overlap thresholds for fuzzy role matching.
MIN_TOKEN_OVERLAP = 2
MIN_OVERLAP_RATIO = 0.6


def normalize_company_name(name: str) -> str:
    """Normalize a company name for fuzzy matching.

    Strips punctuation, lowercases, removes common suffixes (Inc, Ltd,
    Corp, LLC, etc.), and collapses whitespace.

    Args:
        name: Raw company name from a job posting.

    Returns:
        A normalized company string suitable for dedup grouping.
    """
    if not name:
        return ""

    # Normalize unicode (accented chars → ASCII equivalents).
    normalized = unicodedata.normalize("NFKD", name)
    normalized = normalized.encode("ascii", errors="ignore").decode("ascii")

    # Lowercase and strip punctuation.
    normalized = normalized.lower().strip()
    normalized = re.sub(r"[^\w\s]", "", normalized)

    # Remove common corporate suffixes.
    suffixes = (
        r"\b(inc|incorporated|corp|corporation|ltd|limited|llc|llp|"
        r"gmbh|ag|sa|sas|plc|co|company|group|holdings)\b"
    )
    normalized = re.sub(suffixes, "", normalized)

    # Collapse whitespace.
    return re.sub(r"\s+", " ", normalized).strip()


def _tokenize_role(title: str) -> set[str]:
    """Split a role title into meaningful tokens for overlap matching.

    Args:
        title: Job title string.

    Returns:
        A set of lowercase non-stopword tokens.
    """
    words = re.findall(r"[a-zA-Z0-9]+", title.lower())
    return {w for w in words if w not in ROLE_STOPWORDS and len(w) > 1}


def roles_are_similar(title_a: str, title_b: str) -> bool:
    """Check if two role titles are similar enough to be duplicates.

    Uses token-overlap matching: at least MIN_TOKEN_OVERLAP shared tokens
    and at least MIN_OVERLAP_RATIO overlap with the smaller token set.

    Args:
        title_a: First role title.
        title_b: Second role title.

    Returns:
        True if the roles are considered similar.
    """
    tokens_a = _tokenize_role(title_a)
    tokens_b = _tokenize_role(title_b)

    if not tokens_a or not tokens_b:
        return False

    overlap = tokens_a & tokens_b
    if len(overlap) < MIN_TOKEN_OVERLAP:
        return False

    smaller_set_size = min(len(tokens_a), len(tokens_b))
    if smaller_set_size == 0:
        return False

    ratio = len(overlap) / smaller_set_size
    return ratio >= MIN_OVERLAP_RATIO


def is_fuzzy_duplicate(
    *,
    new_company: str,
    new_title: str,
    existing_company: str,
    existing_title: str,
) -> bool:
    """Check if a new job posting is a fuzzy duplicate of an existing one.

    Combines normalized company matching with fuzzy role similarity.

    Args:
        new_company: Company name from the new posting.
        new_title: Job title from the new posting.
        existing_company: Company name from an existing posting.
        existing_title: Job title from an existing posting.

    Returns:
        True if the posting is likely a duplicate.
    """
    norm_new_company = normalize_company_name(new_company)
    norm_existing_company = normalize_company_name(existing_company)

    if norm_new_company != norm_existing_company:
        return False

    return roles_are_similar(new_title, existing_title)
