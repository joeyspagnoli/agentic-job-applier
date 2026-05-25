"""Tests for the CandidateProfile Pydantic schema.

Purpose:
    Verify round-trip validation of the live candidate_profile.yaml, default
    behaviour when optional keys are absent, and hard-fail on invalid data.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from src.config.schema import CandidateProfile

# Path to the live fixture — used for the round-trip test.
_LIVE_PROFILE = Path(__file__).parent.parent / "config" / "candidate_profile.yaml"


def _load(text: str) -> dict[str, object]:
    """Parse YAML text into a plain dict.

    Purpose:
        Centralise YAML parsing for test helpers so test bodies stay readable.
    Args:
        text: Raw YAML string to parse.
    Output:
        Returns a parsed dict.
    """

    result = yaml.safe_load(text)
    return result if isinstance(result, dict) else {}


def test_live_profile_round_trips() -> None:
    """Round-trip the live config/candidate_profile.yaml through CandidateProfile.

    Purpose:
        Catch regressions where a hand-edit to the live YAML breaks the schema
        that the apply finisher and startup hook depend on. Skipped on hosts
        without a configured profile (the file is gitignored as user data).
    """

    if not _LIVE_PROFILE.exists():
        pytest.skip(
            "live candidate_profile.yaml not present "
            "(gitignored — populate locally to exercise this round-trip)"
        )

    raw = _live_profile_text()
    parsed = _load(raw)
    model = CandidateProfile.model_validate(parsed)
    # Spot-check known fields to confirm they survived validation.
    assert model.apply_prefs.work_authorized_us == "yes"
    assert model.apply_prefs.sponsorship_required_now_or_future == "no"
    assert model.apply_prefs.application_defaults.tier2_confidence_threshold == 1.0


def test_tier2_confidence_threshold_defaults_to_1_0_when_missing() -> None:
    """tier2_confidence_threshold defaults to 1.0 when the apply_prefs block is absent.

    Purpose:
        Protect backward compat — existing profiles without apply_prefs must
        still load successfully with safe defaults.
    """

    raw = """
profile:
  contact:
    full_name: Test User
search_defaults:
  job_board_search_terms: []
"""
    model = CandidateProfile.model_validate(_load(raw))
    assert model.apply_prefs.application_defaults.tier2_confidence_threshold == 1.0


def test_invalid_tier2_threshold_raises_validation_error() -> None:
    """tier2_confidence_threshold outside [0.0, 1.0] raises ValidationError.

    Purpose:
        Confirm the ge/le constraint on the threshold field is enforced so an
        operator typo cannot silently set the threshold to 5.0 and spam form
        submits on every tier-2 question.
    """

    raw = """
apply_prefs:
  application_defaults:
    tier2_confidence_threshold: 2.5
"""
    with pytest.raises(ValidationError) as exc_info:
        CandidateProfile.model_validate(_load(raw))

    errors = exc_info.value.errors()
    locs = [" -> ".join(str(p) for p in e["loc"]) for e in errors]
    assert any("tier2_confidence_threshold" in loc for loc in locs)


def test_invalid_work_authorized_us_raises_validation_error() -> None:
    """An unrecognised work_authorized_us literal raises ValidationError.

    Purpose:
        Guard against typos such as ``"maybe"`` which would silently pass a
        plain-string field but are nonsensical for the finisher's boolean logic.
    """

    raw = """
apply_prefs:
  work_authorized_us: maybe
"""
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate(_load(raw))


# ── helpers ───────────────────────────────────────────────────────────────────


def _live_profile_text() -> str:
    """Read the live candidate_profile.yaml fixture text.

    Purpose:
        Centralise fixture loading so any test reading the live YAML
        gets a single point to patch during isolated CI runs.
    Args:
        None.
    Output:
        Returns UTF-8 text of the live candidate profile YAML.
    """

    return _LIVE_PROFILE.read_text(encoding="utf-8")
