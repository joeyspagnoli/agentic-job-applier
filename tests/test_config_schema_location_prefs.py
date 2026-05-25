"""Tests for the Bug D LocationPrefs migration to a tri-state literal.

Locks in:

* The new ``"yes" | "no" | "open_to_discussion"`` shape.
* Backwards-compatible coercion of legacy boolean YAML values written by
  candidate profiles created before 2026-05-25, so existing config files
  keep loading without re-running onboarding.
* Pass-through of ``education_entries`` (the wizard now serializes a real
  list of rows; the schema just needs to keep tolerating the structure).
"""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from src.config.schema import ApplyPrefs, CandidateProfile, LocationPrefs


def test_location_prefs_default_is_open_to_discussion() -> None:
    """A fresh ``LocationPrefs`` defaults willing_to_relocate to the
    tri-state ``"open_to_discussion"`` value the wizard surfaces as a radio.
    """

    prefs = LocationPrefs()
    assert prefs.willing_to_relocate == "open_to_discussion"


def test_location_prefs_accepts_yes_no_open_to_discussion() -> None:
    """The three accepted literal values round-trip without coercion."""

    for value in ("yes", "no", "open_to_discussion"):
        prefs = LocationPrefs(willing_to_relocate=value)  # type: ignore[arg-type]
        assert prefs.willing_to_relocate == value


def test_location_prefs_rejects_unknown_string_value() -> None:
    """A typo like ``"maybe"`` raises ``ValidationError`` rather than
    silently surviving as an arbitrary string."""

    with pytest.raises(ValidationError):
        LocationPrefs(willing_to_relocate="maybe")  # type: ignore[arg-type]


def test_location_prefs_coerces_legacy_false_to_no() -> None:
    """Profiles written before the migration encoded the field as a
    boolean. The validator coerces ``False`` -> ``"no"`` so existing YAML
    keeps loading on startup.
    """

    prefs = LocationPrefs.model_validate({"willing_to_relocate": False})
    assert prefs.willing_to_relocate == "no"


def test_location_prefs_coerces_legacy_true_to_yes() -> None:
    """Legacy ``True`` boolean values map to the new ``"yes"`` literal."""

    prefs = LocationPrefs.model_validate({"willing_to_relocate": True})
    assert prefs.willing_to_relocate == "yes"


def test_candidate_profile_loads_legacy_boolean_yaml_end_to_end() -> None:
    """Full candidate_profile.yaml documents with the legacy boolean shape
    must keep loading via the top-level ``CandidateProfile`` model.
    """

    raw = yaml.safe_load(
        """
        profile:
          summary: ""
        apply_prefs:
          location_preferences:
            willing_to_relocate: false
            preferred_cities: ["NYC"]
        """
    )
    document = CandidateProfile.model_validate(raw)
    assert document.apply_prefs.location_preferences.willing_to_relocate == "no"
    assert document.apply_prefs.location_preferences.preferred_cities == ["NYC"]


def test_candidate_profile_exposes_education_entries_to_finisher() -> None:
    """The finisher loads candidate_profile.yaml as raw text but the
    structured loader must accept the new ``education_entries`` shape so
    startup validation does not reject post-Bug-D profiles.
    """

    raw = yaml.safe_load(
        """
        profile:
          summary: ""
          education_entries:
            - id: edu-1
              school: University of Florida
              degree_name: Bachelor of Science
              field_of_study: Computer Science
              start_year: "2022"
              start_month: "08"
              end_year: "2026"
              end_month: "05"
              is_current: true
              gpa: "3.8"
              minors:
                - Statistics
        apply_prefs:
          location_preferences:
            willing_to_relocate: open_to_discussion
        """
    )
    document = CandidateProfile.model_validate(raw)
    assert len(document.profile.education_entries) == 1
    entry = document.profile.education_entries[0]
    # ``education_entries`` is declared list[object] so the validator does
    # not strip unknown fields — assert that the raw dict survives intact.
    assert isinstance(entry, dict)
    assert entry["school"] == "University of Florida"
    assert entry["is_current"] is True
    assert entry["minors"] == ["Statistics"]


def test_apply_prefs_full_round_trip_with_new_relocation_value() -> None:
    """Sanity check: the new ``willing_to_relocate`` flows through the
    full ``ApplyPrefs`` model the apply finisher reads.
    """

    prefs = ApplyPrefs.model_validate(
        {
            "location_preferences": {
                "willing_to_relocate": "yes",
                "preferred_cities": ["Austin"],
                "willing_remote": True,
            }
        }
    )
    assert prefs.location_preferences.willing_to_relocate == "yes"
    assert prefs.location_preferences.preferred_cities == ["Austin"]
