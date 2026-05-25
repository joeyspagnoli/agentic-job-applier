"""Defer-rule classification for the apply finisher.

Loads a user-editable YAML file (``config/defer_rules.yaml``) and exposes a
:class:`DeferRules` dataclass whose :meth:`~DeferRules.classify` method assigns
each form field label to one of three tiers:

- **Tier 1** — safe to auto-fill from the candidate profile.
- **Tier 2** — draft an answer with the LLM and flag for human review.
- **Tier 3** — defer entirely; the finisher never touches these fields.

Typical usage::

    from pathlib import Path
    from src.agents.apply_finisher.defer_rules import load_defer_rules

    rules = load_defer_rules(Path("config/defer_rules.yaml"))
    tier = rules.classify("Will you require sponsorship?", field_type="select")
    # → "tier3"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

__all__ = ["DeferRules", "load_defer_rules"]


@dataclass(frozen=True)
class DeferRules:
    """Compiled defer rules loaded from ``defer_rules.yaml``.

    All pattern tuples are pre-compiled at load time so classification is a
    pure regex scan — no I/O, no YAML parsing in the hot path.

    Attributes:
        _always_defer_patterns: Regexes that force Tier 3 classification.
        _draft_and_flag_patterns: Regexes that force Tier 2 classification.
        bypass_field_types: HTML input types the finisher skips outright.
        never_defer_overrides: Regexes that *remove* Tier 3 from a label
            even when an ``_always_defer_patterns`` match would apply.

    Example::

        rules = load_defer_rules(Path("config/defer_rules.yaml"))
        assert rules.classify("Desired salary", "text") == "tier3"
        assert rules.classify("Why this role?", "textarea") == "tier2"
        assert rules.classify("LinkedIn URL", "url") == "tier1"
    """

    _always_defer_patterns: tuple[re.Pattern[str], ...]
    _draft_and_flag_patterns: tuple[re.Pattern[str], ...]
    bypass_field_types: frozenset[str]
    never_defer_overrides: tuple[re.Pattern[str], ...]

    def classify(
        self,
        label: str,
        field_type: str,
    ) -> Literal["tier1", "tier2", "tier3"]:
        """Classify a form field label into a tier.

        Tier 3 wins unless a ``never_defer_overrides`` regex also matches,
        in which case the label falls through to Tier 2 / Tier 1 evaluation.
        Tier 2 wins over Tier 1 when a ``draft_and_flag_labels`` regex matches.

        Args:
            label: The visible label text of the form field.
            field_type: The HTML input type (e.g., ``"text"``, ``"select"``).

        Returns:
            ``"tier3"``, ``"tier2"``, or ``"tier1"``.
        """
        is_always_defer = any(p.search(label) for p in self._always_defer_patterns)

        if is_always_defer:
            is_overridden = any(p.search(label) for p in self.never_defer_overrides)
            if not is_overridden:
                return "tier3"

        is_draft_and_flag = any(p.search(label) for p in self._draft_and_flag_patterns)
        if is_draft_and_flag:
            return "tier2"

        return "tier1"

    def should_bypass(self, field_type: str) -> bool:
        """Return True when the field type should be skipped entirely.

        The finisher ignores file uploads, hidden inputs, submit buttons,
        and plain button elements regardless of label content.

        Args:
            field_type: The HTML input type string to check.

        Returns:
            True if the finisher should skip this field without classifying it.
        """
        return field_type in self.bypass_field_types


def _compile_patterns(raw_rules: list[dict[str, str]]) -> tuple[re.Pattern[str], ...]:
    """Compile a list of raw YAML regex dicts into re.Pattern objects.

    Args:
        raw_rules: A list of ``{"regex": "<pattern>"}`` dicts from the YAML.

    Returns:
        A tuple of compiled :class:`re.Pattern` objects.

    Raises:
        re.error: If any regex pattern is syntactically invalid.
    """
    return tuple(re.compile(entry["regex"]) for entry in raw_rules)


def load_defer_rules(path: Path) -> DeferRules:
    """Load and compile defer rules from a YAML file.

    Args:
        path: Absolute or relative path to ``defer_rules.yaml``.

    Returns:
        A :class:`DeferRules` instance with all patterns pre-compiled.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        yaml.YAMLError: If the file is not valid YAML.
        KeyError: If a required top-level key is missing from the YAML.
        re.error: If any regex pattern is syntactically invalid.

    Example::

        rules = load_defer_rules(Path("config/defer_rules.yaml"))
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    return DeferRules(
        _always_defer_patterns=_compile_patterns(raw.get("always_defer_labels", [])),
        _draft_and_flag_patterns=_compile_patterns(
            raw.get("draft_and_flag_labels", [])
        ),
        bypass_field_types=frozenset(raw.get("bypass_field_types", [])),
        never_defer_overrides=_compile_patterns(raw.get("never_defer_overrides", [])),
    )
