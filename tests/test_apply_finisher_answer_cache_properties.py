"""Property-based and edge-case coverage for ``AnswerCache``.

Complements ``test_apply_finisher_answer_cache.py`` (which covers concrete
hit / miss scenarios) by stressing the normalize / substitute round-trip
under arbitrary inputs and locking in the per-company-vs-anonymized
selection on equal scores.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.agents.apply_finisher.answer_cache import (
    load_answer_cache,
    normalize,
    substitute_company,
)


# ---------------------------------------------------------------------------
# Property: normalize is idempotent
# ---------------------------------------------------------------------------


_SAFE_TEXT = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd", "Zs", "Po"),
        whitelist_characters=" \t\n",
    ),
    min_size=0,
    max_size=200,
)


@given(_SAFE_TEXT)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_normalize_is_idempotent(value: str) -> None:
    """``normalize(normalize(x)) == normalize(x)`` for arbitrary safe text."""

    once = normalize(value)
    twice = normalize(once)
    assert once == twice


@given(_SAFE_TEXT)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_normalize_lowercases_output(value: str) -> None:
    """Normalized text contains no uppercase letters."""

    result = normalize(value)
    assert result == result.lower()


# ---------------------------------------------------------------------------
# Property: $COMPANY round-trip preserves the rest of the answer
# ---------------------------------------------------------------------------


_COMPANY_NAMES = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="-_ ",
    ),
    min_size=1,
    max_size=40,
).filter(lambda s: "$" not in s and s.strip() != "")


@given(_COMPANY_NAMES)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_substitute_company_replaces_every_token(company: str) -> None:
    """``substitute_company`` is equivalent to ``str.replace('$COMPANY', company)``."""

    answer = "I love $COMPANY because $COMPANY values impact."
    substituted = substitute_company(answer, company)

    assert "$COMPANY" not in substituted
    assert substituted == answer.replace("$COMPANY", company)


@given(_COMPANY_NAMES)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_substitute_company_no_placeholder_is_noop(company: str) -> None:
    """``substitute_company`` returns the answer unchanged when no token."""

    answer = "I love engineering teams."
    assert substitute_company(answer, company) == answer


# ---------------------------------------------------------------------------
# Per-company beats anonymized at equal fuzzy scores
# ---------------------------------------------------------------------------


def _write_cache(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    """Persist a minimal cache YAML and return its path."""

    cache_file = tmp_path / "answer_cache.yaml"
    cache_file.write_text(
        yaml.safe_dump({"schema_version": 1, "entries": entries}, allow_unicode=True),
        encoding="utf-8",
    )
    return cache_file


def test_per_company_beats_anonymized_at_equal_score(tmp_path: Path) -> None:
    """At equal exact-hash scores, the per-company entry wins."""

    question = "Why are you interested in this role"
    cache_file = _write_cache(
        tmp_path,
        [
            {
                "question_text": question,
                "question_normalized": normalize(question),
                "answer": "Generic answer.",
                "category": "motivation",
                "company_specific": False,
                "company": None,
            },
            {
                "question_text": question,
                "question_normalized": normalize(question),
                "answer": "Stripe answer.",
                "category": "motivation",
                "company_specific": True,
                "company": "Stripe",
            },
        ],
    )
    cache = load_answer_cache(cache_file)

    hit = cache.lookup(question, company="Stripe")

    assert hit is not None
    assert hit.was_anonymized is False
    assert "Stripe answer." in hit.entry.answer


def test_anonymized_used_when_no_per_company_match(tmp_path: Path) -> None:
    """A different company falls back to the anonymized pool."""

    question = "Why are you interested in this role"
    cache_file = _write_cache(
        tmp_path,
        [
            {
                "question_text": question,
                "question_normalized": normalize(question),
                "answer": "At $COMPANY I admire the work.",
                "category": "motivation",
                "company_specific": False,
                "company": None,
            },
            {
                "question_text": question,
                "question_normalized": normalize(question),
                "answer": "Specific Stripe answer.",
                "category": "motivation",
                "company_specific": True,
                "company": "Stripe",
            },
        ],
    )
    cache = load_answer_cache(cache_file)

    hit = cache.lookup(question, company="Acme")

    assert hit is not None
    assert hit.was_anonymized is True
    assert hit.entry.answer == "At Acme I admire the work."


def test_lookup_returns_none_when_neither_pool_has_match(tmp_path: Path) -> None:
    """When neither pool meets the fuzzy threshold the lookup returns None."""

    cache_file = _write_cache(
        tmp_path,
        [
            {
                "question_text": "What is your favorite color",
                "question_normalized": normalize("What is your favorite color"),
                "answer": "Blue.",
                "category": "trivia",
                "company_specific": False,
                "company": None,
            }
        ],
    )
    cache = load_answer_cache(cache_file)

    assert cache.lookup("Describe your management style", company="Stripe") is None


# ---------------------------------------------------------------------------
# Atomic-write: temp file is cleaned up on disk after append_entry
# ---------------------------------------------------------------------------


def test_append_entry_leaves_no_temp_file_on_disk(tmp_path: Path) -> None:
    """``append_entry`` cleans up its sibling temp file via ``os.replace``."""

    cache_file = _write_cache(tmp_path, [])
    cache = load_answer_cache(cache_file)

    cache.append_entry(
        "Sample question?",
        "Sample answer.",
        category="general",
        company_specific=False,
    )

    leftover_temps = list(tmp_path.glob(".answer_cache_tmp_*.yaml"))
    assert leftover_temps == []


def test_append_entry_index_picks_up_new_entry_without_reload(tmp_path: Path) -> None:
    """The in-memory index sees the entry immediately after append."""

    cache_file = _write_cache(tmp_path, [])
    cache = load_answer_cache(cache_file)

    cache.append_entry(
        "Greenhouse motivation prompt",
        "I love $COMPANY's mission.",
        category="motivation",
        company_specific=False,
    )

    hit = cache.lookup("Greenhouse motivation prompt", company="Notion")

    assert hit is not None
    assert hit.entry.answer == "I love Notion's mission."
