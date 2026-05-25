"""Append Human Review answers into the finisher's answer cache.

Background:
    Without this step every Human Review session is throwaway. The next
    apply for the same company re-defers the same questions, the finisher
    burns tokens drafting placeholders, and the user types the same
    answers again. Routing saved answers through
    :func:`src.agents.apply_finisher.answer_cache.AnswerCache.append_entry`
    is the natural durable home for "the human already answered this".

Concurrency:
    ``append_entry`` reads, mutates, and atomically rewrites
    ``data/answer_cache.yaml`` per call. Two concurrent saves could each
    read the same baseline file and one would clobber the other. We
    serialize via a single module-level ``asyncio.Lock`` (single-user
    repo, single process — no need for cross-process file locking).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from loguru import logger

from src.agents.apply_finisher.answer_cache import (
    AnswerCache,
    load_answer_cache,
    normalize,
)


# Module-level lock that serializes append-and-rewrite cycles for the
# answer-cache YAML. The lock is per-event-loop; in production both the
# autonomous worker loop and the FastAPI request loop run inside the
# same process so this is the right granularity.
_CACHE_WRITE_LOCK = asyncio.Lock()


# Default category written when the deferred question carried none.
_FALLBACK_CATEGORY = "user_review"

# Placeholder label produced by the salary helper when the legacy
# unresolved-fields payload had neither label nor field_id. We must not
# write these into the cache — they would re-match every blank field on
# every future application.
_PLACEHOLDER_LABEL = "(no label)"


class AnswerCacheSeedingError(RuntimeError):
    """Raised when the YAML cache cannot be loaded or written.

    Purpose:
        The HTTP layer translates this into a 500-class error rather
        than the generic 400 used for save_handoff_user_answers failures
        since the durable user data has already been persisted.
    """


def _index_questions_by_field_id(
    deferred_questions: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build a ``field_id -> question metadata`` map for quick lookup.

    Args:
        deferred_questions: Decoded list from
            ``apply_handoffs.deferred_questions_json``.
    Returns:
        Map of ``field_id`` to the raw deferred-question dict. Entries
        without a ``field_id`` are silently dropped (the dashboard never
        round-trips them since the textarea is disabled).
    """

    indexed: dict[str, dict[str, Any]] = {}
    for question in deferred_questions:
        if not isinstance(question, dict):
            continue
        field_id_value = question.get("field_id")
        if not field_id_value:
            continue
        indexed[str(field_id_value)] = question
    return indexed


def _is_company_specific(
    *, company: str, label: str, answer: str
) -> bool:
    """Decide whether one (question, answer) pair should be company-scoped.

    Heuristic per the Bug F spec: default to anonymized (False) and only
    flip to True when either the question label or the answer mentions
    the company name verbatim (case-insensitive). Motivation prompts
    like "Why do you want to work at Cloudflare?" hit this branch;
    EEO / relocation / sponsorship answers do not.

    Args:
        company: Company name pulled from the handoff's job posting. May
            be empty, in which case we always return False.
        label: Visible question label captured by the finisher.
        answer: Reviewer-typed answer text.
    Returns:
        ``True`` when the entry should be filed under the company-specific
        bucket; ``False`` otherwise.
    """

    if not company:
        return False
    needle = company.strip().lower()
    if needle == "":
        return False
    haystack = f"{label}\n{answer}".lower()
    return needle in haystack


def _already_cached(
    *, cache: AnswerCache, label: str, answer: str, company: str
) -> bool:
    """Return ``True`` when an exact-match entry with the same answer
    already exists in the cache.

    Purpose:
        Idempotency guard so repeated saves do not pile up duplicate
        YAML rows. We rely on ``AnswerCache.lookup`` returning a hit
        with ``score == 100.0`` for normalize-equal questions; equality
        on the answer (after ``$COMPANY`` substitution) closes the loop.
    Args:
        cache: Loaded :class:`AnswerCache` instance.
        label: Raw question label to dedup against.
        answer: Reviewer-typed answer to compare with the cached one.
        company: Company name passed through ``cache.lookup`` so the
            company-specific bucket is consulted first.
    Returns:
        ``True`` when the cache already holds this answer verbatim.
    """

    company_for_lookup = company if company else "_"
    hit = cache.lookup(label, company=company_for_lookup)
    if hit is None:
        return False
    if hit.score < 100.0:
        return False
    return hit.entry.answer == answer


def _resolve_question_metadata(
    question: dict[str, Any],
) -> tuple[str, str] | None:
    """Pull the label + category out of one deferred-question dict.

    Args:
        question: One entry from ``deferred_questions_json``.
    Returns:
        Tuple of ``(label, category)`` when the entry carries enough
        metadata to seed the cache, or ``None`` when the row is the
        placeholder ``(no label)`` case that must not be cached.
    """

    raw_label = question.get("label")
    if not raw_label:
        return None
    label = str(raw_label).strip()
    if label == "" or label == _PLACEHOLDER_LABEL:
        return None
    raw_category = question.get("category")
    category = str(raw_category).strip() if raw_category else ""
    if category == "":
        category = _FALLBACK_CATEGORY
    return label, category


async def seed_answer_cache_from_handoff(
    *,
    cache_path: Path,
    company: str,
    deferred_questions_json: str | None,
    answers: list[dict[str, str]],
) -> list[dict[str, object]]:
    """Append every reviewer-supplied answer to the persistent cache.

    Purpose:
        Mirror the Cloudflare smoke-test agent's manual seed step. Each
        ``(field_id, answer)`` pair is matched against the handoff's
        deferred-question metadata to recover the question label + the
        finisher's category tag, then appended via
        :meth:`AnswerCache.append_entry`. The cache file is created if
        it does not yet exist (``load_answer_cache`` seeds an empty doc).
    Args:
        cache_path: Absolute path to ``data/answer_cache.yaml``.
        company: Company name from the handoff's ``job_postings`` row,
            used both for ``company_specific`` detection and for the
            per-company bucket.
        deferred_questions_json: Raw JSON from
            ``apply_handoffs.deferred_questions_json``. ``None`` / empty
            means there is nothing to cache.
        answers: List of ``{"field_id", "answer"}`` dicts as persisted
            by ``save_handoff_user_answers``.
    Returns:
        List of summary records (one per appended entry) shaped
        ``{"field_id", "label", "company_specific", "skipped"}``. The
        ``skipped`` field is populated with a short reason string when
        we chose not to append (placeholder label, empty answer,
        duplicate, etc.).
    Raises:
        AnswerCacheSeedingError: When the cache YAML cannot be loaded
            or persisted; the HTTP layer surfaces this as a 500.
    """

    summaries: list[dict[str, object]] = []
    if not deferred_questions_json:
        return summaries

    try:
        deferred_payload = json.loads(deferred_questions_json)
    except json.JSONDecodeError as exc:
        logger.warning("deferred_questions_json malformed: {}", exc)
        return summaries
    if not isinstance(deferred_payload, list):
        return summaries

    questions_by_field_id = _index_questions_by_field_id(deferred_payload)

    async with _CACHE_WRITE_LOCK:
        try:
            cache = load_answer_cache(cache_path)
        except Exception as exc:  # noqa: BLE001 - filesystem or YAML
            raise AnswerCacheSeedingError(
                f"Failed to load answer cache at {cache_path}: {exc}"
            ) from exc

        for entry in answers:
            field_id = entry.get("field_id") or ""
            answer_text = (entry.get("answer") or "").strip()
            if not field_id or answer_text == "":
                summaries.append(
                    {
                        "field_id": field_id,
                        "skipped": "empty_answer" if field_id else "missing_field_id",
                    }
                )
                continue

            question = questions_by_field_id.get(field_id)
            if question is None:
                summaries.append(
                    {"field_id": field_id, "skipped": "no_matching_question"}
                )
                continue

            resolved = _resolve_question_metadata(question)
            if resolved is None:
                summaries.append(
                    {"field_id": field_id, "skipped": "placeholder_label"}
                )
                continue
            label, category = resolved

            company_specific = _is_company_specific(
                company=company, label=label, answer=answer_text
            )
            cache_company = company if company_specific else "_"

            if _already_cached(
                cache=cache,
                label=label,
                answer=answer_text,
                company=cache_company,
            ):
                summaries.append(
                    {"field_id": field_id, "label": label, "skipped": "duplicate"}
                )
                continue

            try:
                cache.append_entry(
                    question_text=label,
                    answer=answer_text,
                    category=category,
                    company_specific=company_specific,
                    company=company if company_specific else None,
                )
            except Exception as exc:  # noqa: BLE001
                raise AnswerCacheSeedingError(
                    f"Failed to append answer for field {field_id}: {exc}"
                ) from exc

            summaries.append(
                {
                    "field_id": field_id,
                    "label": label,
                    "company_specific": company_specific,
                }
            )
            logger.info(
                "Seeded answer cache: field_id={} label={!r} "
                "company_specific={} normalized={!r}",
                field_id,
                label,
                company_specific,
                normalize(label),
            )

    return summaries
