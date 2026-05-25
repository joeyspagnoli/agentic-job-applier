"""Fuzzy-match answer cache for the apply finisher.

Persists previously-answered application questions to a YAML file
(``data/answer_cache.yaml``) so the finisher can reuse answers across runs.

Lookup strategy (per :meth:`AnswerCache.lookup`):

1. **Per-company entries** (``company_specific=True AND company==company``) —
   exact normalized-hash match first, then RapidFuzz ``token_set_ratio >= 85``.
2. **Anonymized entries** (``company_specific=False``) — same exact-then-fuzzy
   lookup.  ``$COMPANY`` tokens in the stored answer are substituted at
   retrieval time.
3. The highest-scoring hit is returned; per-company beats anonymized at equal
   scores.

Typical usage::

    from pathlib import Path
    from src.agents.apply_finisher.answer_cache import load_answer_cache

    cache = load_answer_cache(Path("data/answer_cache.yaml"))
    hit = cache.lookup("Why do you want to work here?", company="Stripe")
    if hit:
        print(hit.entry.answer)   # already has "Stripe" substituted
"""

from __future__ import annotations

import os
import re
import string
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from rapidfuzz import fuzz

__all__ = [
    "AnswerCache",
    "CacheEntry",
    "CacheHit",
    "load_answer_cache",
]

# Minimum RapidFuzz token_set_ratio score to accept a fuzzy match.
_FUZZY_THRESHOLD: int = 85

# Sentinel substituted for the literal "$COMPANY" token during normalization
# so fuzzy comparisons are company-agnostic.
_COMPANY_TOKEN: str = "COMPANY"


@dataclass(frozen=True)
class CacheEntry:
    """A single cached question-answer pair.

    Attributes:
        question_text: The original, unmodified question label.
        question_normalized: The normalized form used for hashing and fuzzy
            matching (produced by :func:`normalize`).
        answer: The stored answer. May contain the literal ``$COMPANY``
            placeholder for anonymized entries.
        category: Free-form category tag (e.g., ``"sponsorship"``,
            ``"motivation"``).
        company_specific: When True, this entry is only surfaced for the
            matching ``company``.
        company: The company name this entry is locked to, or None for
            anonymized entries.

    Example::

        entry = CacheEntry(
            question_text="Why do you want to work here?",
            question_normalized="why do you want to work here",
            answer="At $COMPANY I admire the mission.",
            category="motivation",
            company_specific=False,
            company=None,
        )
    """

    question_text: str
    question_normalized: str
    answer: str
    category: str
    company_specific: bool
    company: str | None


@dataclass(frozen=True)
class CacheHit:
    """The result of a successful cache lookup.

    Attributes:
        entry: The matched :class:`CacheEntry` with ``$COMPANY`` already
            substituted in :attr:`~CacheEntry.answer`.
        score: RapidFuzz ``token_set_ratio`` score (100.0 for exact matches).
        was_anonymized: True when the hit came from an anonymized entry
            (``company_specific=False``).

    Example::

        hit = cache.lookup("Why Stripe?", company="Stripe")
        assert hit is not None
        assert "Stripe" in hit.entry.answer
    """

    entry: CacheEntry
    score: float
    was_anonymized: bool


def normalize(text: str) -> str:
    """Normalize a question string for hashing and fuzzy comparison.

    Steps applied in order:
    1. Replace the literal ``$COMPANY`` with the sentinel token ``COMPANY``
       so anonymized entries match regardless of company name.
    2. Convert to lowercase.
    3. Strip punctuation (keep alphanumerics + spaces).
    4. Collapse runs of whitespace to a single space.
    5. Strip leading/trailing whitespace.

    Args:
        text: The raw question or answer text to normalize.

    Returns:
        A normalized string suitable for equality checks and fuzzy matching.

    Example::

        normalize("Why $COMPANY?!") == "why company"
        normalize("  Tell us,  about yourself. ") == "tell us about yourself"
    """
    # Replace $COMPANY before lowercasing so the substitution is case-exact.
    text = text.replace("$COMPANY", _COMPANY_TOKEN)
    text = text.lower()
    # Remove all punctuation characters, keeping alphanumerics and spaces.
    text = text.translate(str.maketrans("", "", string.punctuation))
    # Collapse internal whitespace.
    text = re.sub(r"\s+", " ", text).strip()
    return text


def substitute_company(answer: str, company: str) -> str:
    """Replace the ``$COMPANY`` literal in an answer with the real company name.

    Args:
        answer: The stored answer, potentially containing ``$COMPANY``.
        company: The company name to substitute in.

    Returns:
        The answer with all ``$COMPANY`` occurrences replaced by ``company``.

    Example::

        substitute_company("I love $COMPANY's mission.", "Stripe")
        # → "I love Stripe's mission."
    """
    return answer.replace("$COMPANY", company)


@dataclass
class AnswerCache:
    """In-memory view of the answer cache backed by a YAML file.

    Entries are partitioned internally into per-company and anonymized buckets
    so lookup can apply the priority order described in the module docstring
    without linear scans across the full entry list.

    Attributes:
        _path: Path to the backing YAML file.
        _per_company: Mapping of company name → list of company-specific entries.
        _anonymized: List of entries with ``company_specific=False``.

    Example::

        cache = load_answer_cache(Path("data/answer_cache.yaml"))
        cache.append_entry(
            "Why do you want this role?",
            "I admire $COMPANY's engineering culture.",
            category="motivation",
            company_specific=False,
        )
        hit = cache.lookup("Why do you want this role?", company="Stripe")
        assert hit is not None
        assert "Stripe" in hit.entry.answer
    """

    _path: Path
    _per_company: dict[str, list[CacheEntry]] = field(default_factory=dict)
    _anonymized: list[CacheEntry] = field(default_factory=list)

    def lookup(self, question_text: str, *, company: str) -> CacheHit | None:
        """Find the best cached answer for a question.

        Applies the two-pass lookup strategy: per-company entries first, then
        anonymized entries.  Within each pass, an exact normalized hash is
        preferred; fuzzy matching is used as a fallback.

        Args:
            question_text: The raw label text of the form field.
            company: The name of the company whose form is being filled.

        Returns:
            The highest-scoring :class:`CacheHit`, or ``None`` if no entry
            meets the :data:`_FUZZY_THRESHOLD` threshold.
        """
        query_normalized = normalize(question_text)

        per_company_hit = self._best_hit(
            query_normalized,
            self._per_company.get(company, []),
            company=company,
            is_anonymized=False,
        )
        anonymized_hit = self._best_hit(
            query_normalized,
            self._anonymized,
            company=company,
            is_anonymized=True,
        )

        if per_company_hit is None and anonymized_hit is None:
            return None

        if per_company_hit is None:
            return anonymized_hit

        if anonymized_hit is None:
            return per_company_hit

        # Per-company wins on ties.
        if per_company_hit.score >= anonymized_hit.score:
            return per_company_hit
        return anonymized_hit

    def _best_hit(
        self,
        query_normalized: str,
        entries: list[CacheEntry],
        *,
        company: str,
        is_anonymized: bool,
    ) -> CacheHit | None:
        """Return the best-matching entry from a list of candidates.

        Prefers an exact normalized-hash match (score 100.0) over fuzzy.
        Among fuzzy candidates returns the highest scorer above the threshold.

        Args:
            query_normalized: Pre-normalized query string.
            entries: Candidate :class:`CacheEntry` objects to search.
            company: Company name for ``$COMPANY`` substitution.
            is_anonymized: Passed through to :class:`CacheHit`.

        Returns:
            The best :class:`CacheHit` or ``None``.
        """
        best_score: float = -1.0
        best_entry: CacheEntry | None = None

        for entry in entries:
            if entry.question_normalized == query_normalized:
                # Exact match — can't do better; return immediately.
                return self._make_hit(entry, 100.0, company, is_anonymized)

            ratio: float = fuzz.token_set_ratio(
                query_normalized, entry.question_normalized
            )
            if ratio >= _FUZZY_THRESHOLD and ratio > best_score:
                best_score = ratio
                best_entry = entry

        if best_entry is None:
            return None
        return self._make_hit(best_entry, best_score, company, is_anonymized)

    def _make_hit(
        self,
        entry: CacheEntry,
        score: float,
        company: str,
        is_anonymized: bool,
    ) -> CacheHit:
        """Build a :class:`CacheHit` with company substitution applied.

        Args:
            entry: The matched cache entry.
            score: The match score (100.0 for exact, <100 for fuzzy).
            company: The company name to substitute for ``$COMPANY``.
            is_anonymized: Whether the entry came from the anonymized pool.

        Returns:
            A :class:`CacheHit` with ``entry.answer`` already substituted.
        """
        substituted_answer = substitute_company(entry.answer, company)
        substituted_entry = CacheEntry(
            question_text=entry.question_text,
            question_normalized=entry.question_normalized,
            answer=substituted_answer,
            category=entry.category,
            company_specific=entry.company_specific,
            company=entry.company,
        )
        return CacheHit(
            entry=substituted_entry,
            score=score,
            was_anonymized=is_anonymized,
        )

    def append_entry(
        self,
        question_text: str,
        answer: str,
        *,
        category: str,
        company_specific: bool,
        company: str | None = None,
    ) -> None:
        """Append a new entry and atomically persist the full cache to disk.

        Reads the current YAML file, appends the new entry, and writes back
        via a temporary file + ``os.replace`` to avoid corruption on crash.

        Args:
            question_text: The raw question label text.
            answer: The answer to store.  Use ``$COMPANY`` as a placeholder
                for the company name in anonymized entries.
            category: Free-form category tag for grouping related entries.
            company_specific: When True, the entry is only returned for
                ``company`` during lookup.
            company: Required when ``company_specific=True``.

        Raises:
            ValueError: If ``company_specific=True`` but ``company`` is None.
            OSError: If the YAML file cannot be written.
        """
        if company_specific and company is None:
            raise ValueError("company must be provided when company_specific=True")

        entry = CacheEntry(
            question_text=question_text,
            question_normalized=normalize(question_text),
            answer=answer,
            category=category,
            company_specific=company_specific,
            company=company,
        )

        # Update the in-memory index.
        if company_specific and company is not None:
            self._per_company.setdefault(company, []).append(entry)
        else:
            self._anonymized.append(entry)

        self._persist(entry)

    def _persist(self, new_entry: CacheEntry) -> None:
        """Atomically append ``new_entry`` to the backing YAML file.

        Reads the full file, appends the serialized entry, then writes to a
        sibling temp file and renames to prevent partial-write corruption.

        Args:
            new_entry: The entry to append.

        Raises:
            yaml.YAMLError: If the existing file cannot be parsed.
            OSError: If the write or rename fails.
        """
        raw = yaml.safe_load(self._path.read_text(encoding="utf-8"))
        raw.setdefault("entries", [])
        raw["entries"].append(
            {
                "question_text": new_entry.question_text,
                "question_normalized": new_entry.question_normalized,
                "answer": new_entry.answer,
                "category": new_entry.category,
                "company_specific": new_entry.company_specific,
                "company": new_entry.company,
            }
        )

        serialized = yaml.safe_dump(raw, allow_unicode=True, sort_keys=False)

        # Write to a sibling temp file, then atomically rename.
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self._path.parent,
            prefix=".answer_cache_tmp_",
            suffix=".yaml",
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(serialized)
            os.replace(tmp_path, self._path)
        except Exception:
            # Clean up the temp file if something went wrong.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


def _entry_from_dict(raw: dict[str, object]) -> CacheEntry:
    """Deserialize a single YAML entry dict into a :class:`CacheEntry`.

    Args:
        raw: A dictionary loaded from the ``entries`` list in the YAML file.

    Returns:
        A populated :class:`CacheEntry`.

    Raises:
        KeyError: If a required key is missing from ``raw``.
    """
    return CacheEntry(
        question_text=str(raw["question_text"]),
        question_normalized=str(raw["question_normalized"]),
        answer=str(raw["answer"]),
        category=str(raw["category"]),
        company_specific=bool(raw["company_specific"]),
        company=str(raw["company"]) if raw.get("company") is not None else None,
    )


def load_answer_cache(path: Path) -> AnswerCache:
    """Load the answer cache from a YAML file.

    Creates an :class:`AnswerCache` with all existing entries indexed into
    per-company and anonymized buckets.

    Args:
        path: Path to ``answer_cache.yaml``.

    Returns:
        A ready-to-use :class:`AnswerCache` instance.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        yaml.YAMLError: If the file is not valid YAML.

    Example::

        cache = load_answer_cache(Path("data/answer_cache.yaml"))
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw_entries: list[dict[str, object]] = raw.get("entries") or []

    per_company: dict[str, list[CacheEntry]] = {}
    anonymized: list[CacheEntry] = []

    for raw_entry in raw_entries:
        entry = _entry_from_dict(raw_entry)
        if entry.company_specific and entry.company is not None:
            per_company.setdefault(entry.company, []).append(entry)
        else:
            anonymized.append(entry)

    return AnswerCache(_path=path, _per_company=per_company, _anonymized=anonymized)
