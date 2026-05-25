"""Behavioral coverage for the new ``apply_prefs`` block on ``CandidateProfile``.

Pairs with ``test_config_schema.py``: that file covers round-trips of the
live YAML and the headline threshold rule. This module locks in the
defaults for sponsorship / work-auth literals, the language proficiency
enum, threshold boundary values, and a structured error on a malformed
sub-block.
"""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from src.config.schema import (
    ApplyPrefs,
    CandidateProfile,
    EeoDefaults,
    LanguageEntry,
)


def _model(yaml_str: str) -> CandidateProfile:
    """Parse ``yaml_str`` into a :class:`CandidateProfile`."""

    raw = yaml.safe_load(yaml_str) or {}
    return CandidateProfile.model_validate(raw)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_apply_prefs_defaults_to_unknown_for_sponsorship_and_work_auth() -> None:
    """An absent ``apply_prefs`` defaults both literals to ``"unknown"``."""

    profile = _model("profile: {}")
    assert profile.apply_prefs.sponsorship_required_now_or_future == "unknown"
    assert profile.apply_prefs.work_authorized_us == "unknown"


def test_eeo_defaults_initialize_to_prefer_not_to_say() -> None:
    """The EEO sub-model defaults every axis to ``prefer_not_to_say``."""

    defaults = EeoDefaults()
    assert defaults.gender == "prefer_not_to_say"
    assert defaults.race_ethnicity == "prefer_not_to_say"
    assert defaults.veteran_status == "prefer_not_to_say"
    assert defaults.disability_status == "prefer_not_to_say"


def test_apply_prefs_defaults_language_list_is_empty() -> None:
    """A blank apply_prefs has an empty ``languages`` list."""

    prefs = ApplyPrefs()
    assert prefs.languages == []


# ---------------------------------------------------------------------------
# Boundary values for tier2_confidence_threshold
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("threshold", [0.0, 0.5, 1.0])
def test_threshold_accepts_in_range_values(threshold: float) -> None:
    """Inclusive bounds [0.0, 1.0] are accepted."""

    profile = _model(
        f"apply_prefs:\n  application_defaults:\n    tier2_confidence_threshold: {threshold}\n"
    )
    assert profile.apply_prefs.application_defaults.tier2_confidence_threshold == pytest.approx(threshold)


@pytest.mark.parametrize("threshold", [-0.0001, 1.0001, 2.0, -1.0])
def test_threshold_rejects_out_of_range_values(threshold: float) -> None:
    """Values outside [0.0, 1.0] raise ValidationError."""

    with pytest.raises(ValidationError):
        _model(
            f"apply_prefs:\n  application_defaults:\n    tier2_confidence_threshold: {threshold}\n"
        )


# ---------------------------------------------------------------------------
# Language proficiency literal
# ---------------------------------------------------------------------------


def test_language_entry_accepts_known_proficiencies() -> None:
    """Each documented proficiency value is accepted."""

    for level in ("basic", "conversational", "fluent", "native"):
        entry = LanguageEntry.model_validate({"language": "French", "proficiency": level})
        assert entry.proficiency == level


def test_language_entry_rejects_unknown_proficiency() -> None:
    """An unrecognised proficiency literal raises ValidationError."""

    with pytest.raises(ValidationError):
        LanguageEntry(language="French", proficiency="elite")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Structural failures
# ---------------------------------------------------------------------------


def test_invalid_sponsorship_literal_raises_validation_error() -> None:
    """A non-yes/no/unknown sponsorship literal is rejected."""

    with pytest.raises(ValidationError):
        _model("apply_prefs:\n  sponsorship_required_now_or_future: maybe\n")


def test_unknown_top_level_keys_are_allowed_via_extra_allow() -> None:
    """``extra='allow'`` permits documented-but-not-modelled keys to survive."""

    profile = _model("totally_new_block: true\nprofile: {}\n")
    # Did not raise — that's the property.
    assert profile.apply_prefs.work_authorized_us == "unknown"
