"""Behavioral tests for AnswerCache / load_answer_cache.

Covers exact-hash hits, fuzzy hits, misses, $COMPANY substitution,
per-company vs. anonymized priority, and append_entry round-trips.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.agents.apply_finisher.answer_cache import (
    load_answer_cache,
    normalize,
    substitute_company,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_yaml_file(tmp_path: Path, entries: list[dict[str, object]]) -> Path:
    """Write a minimal answer_cache.yaml and return the path."""
    data = {"schema_version": 1, "entries": entries}
    cache_file = tmp_path / "answer_cache.yaml"
    cache_file.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return cache_file


def _make_entry_dict(
    question_text: str,
    answer: str,
    *,
    category: str = "general",
    company_specific: bool = False,
    company: str | None = None,
) -> dict[str, object]:
    """Build a raw YAML entry dict (what load_answer_cache reads)."""
    return {
        "question_text": question_text,
        "question_normalized": normalize(question_text),
        "answer": answer,
        "category": category,
        "company_specific": company_specific,
        "company": company,
    }


# ---------------------------------------------------------------------------
# normalize()
# ---------------------------------------------------------------------------


def test_normalize_strips_punctuation_and_lowercases() -> None:
    """normalize() removes punctuation, lowercases, and collapses whitespace."""
    assert normalize("Why $COMPANY?!") == "why company"


def test_normalize_collapses_whitespace() -> None:
    """normalize() collapses internal whitespace to single spaces."""
    assert normalize("  Tell us,  about yourself. ") == "tell us about yourself"


def test_normalize_replaces_company_token() -> None:
    """normalize() replaces $COMPANY so fuzzy matching is company-agnostic."""
    result = normalize("At $COMPANY we value this.")
    assert "company" in result
    assert "$" not in result


# ---------------------------------------------------------------------------
# substitute_company()
# ---------------------------------------------------------------------------


def test_substitute_company_replaces_placeholder() -> None:
    """substitute_company() replaces $COMPANY with the provided name."""
    result = substitute_company("I love $COMPANY's mission.", "Stripe")
    assert result == "I love Stripe's mission."


def test_substitute_company_noop_when_no_placeholder() -> None:
    """substitute_company() returns the answer unchanged if no $COMPANY present."""
    result = substitute_company("I love engineering.", "Stripe")
    assert result == "I love engineering."


# ---------------------------------------------------------------------------
# Exact-hash hit (case + punctuation differ, normalize to same value)
# ---------------------------------------------------------------------------


def test_exact_hash_hit_ignores_case_and_punctuation(tmp_path: Path) -> None:
    """lookup() returns a hit when normalized forms match exactly."""
    # Arrange
    cache_file = _make_yaml_file(
        tmp_path,
        [
            _make_entry_dict(
                "why do you want to work here",
                "Because I value impact.",
                category="motivation",
                company_specific=False,
            )
        ],
    )
    cache = load_answer_cache(cache_file)

    # Act — query with different casing and punctuation
    hit = cache.lookup("Why do you want to work here?", company="Acme")

    # Assert
    assert hit is not None
    assert hit.score == 100.0
    assert hit.entry.answer == "Because I value impact."


# ---------------------------------------------------------------------------
# Fuzzy hit (ratio ~90, one word different)
# ---------------------------------------------------------------------------


def test_fuzzy_hit_at_ratio_90(tmp_path: Path) -> None:
    """lookup() returns a hit when token_set_ratio is at or above threshold."""
    cache_file = _make_yaml_file(
        tmp_path,
        [
            _make_entry_dict(
                "Why are you excited about this position",
                "I love building things.",
                category="motivation",
                company_specific=False,
            )
        ],
    )
    cache = load_answer_cache(cache_file)

    # "role" instead of "position" — close enough for token_set_ratio
    hit = cache.lookup("Why are you excited about this role", company="Acme")

    assert hit is not None
    assert hit.score >= 85.0


# ---------------------------------------------------------------------------
# No hit at ratio ~70
# ---------------------------------------------------------------------------


def test_no_hit_when_ratio_below_threshold(tmp_path: Path) -> None:
    """lookup() returns None when the best fuzzy score is below threshold."""
    cache_file = _make_yaml_file(
        tmp_path,
        [
            _make_entry_dict(
                "Tell me about a time you led a team",
                "I managed a squad of five engineers.",
                category="leadership",
                company_specific=False,
            )
        ],
    )
    cache = load_answer_cache(cache_file)

    # Totally different question — should not match.
    hit = cache.lookup("What is your GPA?", company="Acme")

    assert hit is None


# ---------------------------------------------------------------------------
# $COMPANY round-trip
# ---------------------------------------------------------------------------


def test_company_token_substituted_on_retrieval(tmp_path: Path) -> None:
    """$COMPANY in stored answers is replaced with the real company on lookup."""
    cache_file = _make_yaml_file(
        tmp_path,
        [
            _make_entry_dict(
                "Why do you want to work here",
                "At $COMPANY I would thrive.",
                category="motivation",
                company_specific=False,
            )
        ],
    )
    cache = load_answer_cache(cache_file)

    hit = cache.lookup("Why do you want to work here", company="Stripe")

    assert hit is not None
    assert hit.entry.answer == "At Stripe I would thrive."
    assert hit.was_anonymized is True


# ---------------------------------------------------------------------------
# Per-company beats anonymized at equal scores
# ---------------------------------------------------------------------------


def test_per_company_entry_beats_anonymized_at_equal_score(tmp_path: Path) -> None:
    """Per-company entries take precedence over anonymized at equal scores."""
    question = "Why do you want to work here"
    cache_file = _make_yaml_file(
        tmp_path,
        [
            _make_entry_dict(
                question,
                "Generic anonymized answer.",
                category="motivation",
                company_specific=False,
            ),
            _make_entry_dict(
                question,
                "Stripe-specific answer.",
                category="motivation",
                company_specific=True,
                company="Stripe",
            ),
        ],
    )
    cache = load_answer_cache(cache_file)

    hit = cache.lookup(question, company="Stripe")

    assert hit is not None
    assert hit.entry.answer == "Stripe-specific answer."
    assert hit.was_anonymized is False


# ---------------------------------------------------------------------------
# append_entry round-trip
# ---------------------------------------------------------------------------


def test_append_entry_persists_and_is_findable(tmp_path: Path) -> None:
    """append_entry() writes to YAML and the entry is found in a fresh load."""
    cache_file = _make_yaml_file(tmp_path, [])
    cache = load_answer_cache(cache_file)

    # Act
    cache.append_entry(
        "How did you hear about us",
        "LinkedIn",
        category="source",
        company_specific=False,
    )

    # Assert — reload from disk to confirm persistence.
    fresh_cache = load_answer_cache(cache_file)
    hit = fresh_cache.lookup("How did you hear about us", company="Acme")

    assert hit is not None
    assert hit.entry.answer == "LinkedIn"


def test_append_entry_company_specific_round_trip(tmp_path: Path) -> None:
    """Company-specific entries are persisted and only match the correct company."""
    cache_file = _make_yaml_file(tmp_path, [])
    cache = load_answer_cache(cache_file)

    cache.append_entry(
        "Why Stripe?",
        "I love Stripe's developer focus.",
        category="motivation",
        company_specific=True,
        company="Stripe",
    )

    fresh_cache = load_answer_cache(cache_file)

    # Should find for Stripe.
    hit = fresh_cache.lookup("Why Stripe?", company="Stripe")
    assert hit is not None

    # Should NOT find for a different company.
    miss = fresh_cache.lookup("Why Stripe?", company="Acme")
    assert miss is None


def test_append_entry_raises_when_company_specific_without_company(
    tmp_path: Path,
) -> None:
    """append_entry() raises ValueError if company_specific=True but company=None."""
    cache_file = _make_yaml_file(tmp_path, [])
    cache = load_answer_cache(cache_file)

    with pytest.raises(ValueError, match="company must be provided"):
        cache.append_entry(
            "Why this role?",
            "I enjoy the challenge.",
            category="motivation",
            company_specific=True,
            company=None,
        )


# ---------------------------------------------------------------------------
# First-run bootstrap: missing cache file creates an empty cache on disk
# ---------------------------------------------------------------------------


def test_load_answer_cache_creates_empty_file_when_missing(tmp_path: Path) -> None:
    """First finisher run on a fresh checkout: ``answer_cache.yaml`` does not
    yet exist. ``load_answer_cache`` must seed an empty file instead of
    raising ``FileNotFoundError``, otherwise the finisher crashes before the
    first LLM call and every apply lands NEEDS_REVIEW.
    """
    cache_file = tmp_path / "subdir" / "answer_cache.yaml"
    assert not cache_file.exists()
    assert not cache_file.parent.exists()

    cache = load_answer_cache(cache_file)

    # File and parent dir created.
    assert cache_file.exists(), "load_answer_cache should seed the file on first run"
    assert cache_file.parent.is_dir()
    # Seeded content is a valid, parseable empty cache.
    assert cache_file.read_text(encoding="utf-8").strip() == "entries: []"
    # Lookups against the empty cache return None, never raise.
    assert cache.lookup("anything at all", company="Acme") is None

    # Re-loading the just-seeded file works (catches a regression where the
    # seed produces YAML the loader cannot parse).
    reloaded = load_answer_cache(cache_file)
    assert reloaded.lookup("anything at all", company="Acme") is None


def test_load_answer_cache_tolerates_empty_yaml_file(tmp_path: Path) -> None:
    """An empty file (``touch answer_cache.yaml`` with no content) should load
    as an empty cache, not crash on ``raw.get`` against ``None``.
    """
    cache_file = tmp_path / "answer_cache.yaml"
    cache_file.write_text("", encoding="utf-8")

    cache = load_answer_cache(cache_file)

    assert cache.lookup("any question", company="Acme") is None
