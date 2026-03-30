"""Verify profile settings API contract for the structured candidate schema.

Purpose:
    Protect the frontend settings migration by asserting profile settings
    endpoints expose and validate the new structured candidate profile shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main as api_main


@pytest.fixture
def profile_settings_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """Build a TestClient configured for isolated profile-settings tests.

    Purpose:
        Keep profile endpoint tests deterministic by using temporary profile
        settings files and backup paths for each test invocation.
    Args:
        tmp_path: Per-test temporary directory fixture.
        monkeypatch: Fixture used to patch settings file paths.
    Output:
        Returns an isolated FastAPI `TestClient` instance.
    """

    monkeypatch.setattr(
        api_main, "SETTINGS_PROFILE_PATH", tmp_path / "candidate_profile.yaml"
    )
    monkeypatch.setattr(api_main, "SETTINGS_BACKUPS_DIR", tmp_path / "backups")

    return TestClient(api_main.app)


def _write_profile_yaml(path: Path, *, yaml_text: str) -> None:
    """Write profile YAML fixture content to the configured test path.

    Purpose:
        Keep profile endpoint tests focused on API contract behavior by using
        one helper to prepare deterministic source YAML content.
    Args:
        path: Filesystem path for candidate profile YAML under test.
        yaml_text: YAML content to write before endpoint invocation.
    Output:
        Returns `None` after writing UTF-8 YAML text to disk.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml_text, encoding="utf-8")


def test_get_profile_settings_exposes_structured_profile_defaults(
    profile_settings_client: TestClient,
) -> None:
    """Verify profile GET returns the new structured schema keys.

    Purpose:
        Ensure settings UI hydration receives `contact`, `work_authorization`,
        and education structure even when YAML only includes minimal fields.
    Args:
        profile_settings_client: Isolated API client fixture.
    Output:
        Returns `None`; test passes when response includes new profile fields.
    """

    _write_profile_yaml(
        api_main.SETTINGS_PROFILE_PATH,
        yaml_text=(
            "profile:\n"
            '  summary: "Candidate summary"\n'
            "search_defaults:\n"
            "  job_board_search_terms:\n"
            '    - "software engineer"\n'
        ),
    )

    response = profile_settings_client.get("/api/settings/profile")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "contact" in payload["profile"]
    assert "work_authorization" in payload["profile"]
    assert "education_summary" in payload["profile"]
    assert "education_entries" in payload["profile"]
    assert payload["profile"]["contact"]["country_code"] == ""
    assert (
        payload["profile"]["work_authorization"]["authorized_to_work_us"] == "unknown"
    )


def test_update_profile_structured_rejects_duplicate_education_entry_ids(
    profile_settings_client: TestClient,
) -> None:
    """Verify structured profile saves reject duplicate education IDs.

    Purpose:
        Protect frontend repeatable-row behavior by ensuring backend validation
        enforces unique `education_entries[].id` values.
    Args:
        profile_settings_client: Isolated API client fixture.
    Output:
        Returns `None`; test passes when endpoint returns HTTP 422.
    """

    response = profile_settings_client.put(
        "/api/settings/profile/structured",
        json={
            "profile": {
                "summary": "summary",
                "contact": {
                    "full_name": "",
                    "email": "",
                    "phone": "",
                    "city": "",
                    "state_or_region": "",
                    "country_code": "US",
                    "country_label": "United States",
                    "linkedin_url": "",
                    "github_url": "",
                    "portfolio_url": "",
                },
                "work_authorization": {
                    "citizenship_country_code": "US",
                    "citizenship_country_label": "United States",
                    "authorized_to_work_us": "yes",
                    "requires_sponsorship_now_or_future": "no",
                },
                "education_summary": "summary",
                "education_entries": [
                    {
                        "id": "entry-1",
                        "school": "UF",
                        "degree_level": "BS",
                        "degree_name": "Computer Science",
                        "field_of_study": "",
                        "start_month": "",
                        "start_year": "",
                        "end_month": "",
                        "end_year": "",
                        "is_current": True,
                        "gpa": "",
                        "location": "",
                        "highlights": [],
                    },
                    {
                        "id": "entry-1",
                        "school": "UF",
                        "degree_level": "BS",
                        "degree_name": "Computer Science",
                        "field_of_study": "",
                        "start_month": "",
                        "start_year": "",
                        "end_month": "",
                        "end_year": "",
                        "is_current": True,
                        "gpa": "",
                        "location": "",
                        "highlights": [],
                    },
                ],
                "target_roles": [],
                "strongest_areas": [],
                "experience_highlights": [],
                "hard_filters": [],
                "preferences": [],
            },
            "search_defaults": {"job_board_search_terms": []},
            "prompt_context": None,
        },
    )

    assert response.status_code == 422
    error_details = response.json()["detail"]
    assert "Education entries must use unique IDs." in str(error_details)


def test_update_profile_structured_accepts_new_shape_and_persists_yaml(
    profile_settings_client: TestClient,
) -> None:
    """Verify structured profile save returns and persists the new schema.

    Purpose:
        Confirm the endpoint accepts the migrated payload shape and writes a
        canonical YAML document that includes nested profile sections.
    Args:
        profile_settings_client: Isolated API client fixture.
    Output:
        Returns `None`; test passes when response and stored YAML include keys.
    """

    response = profile_settings_client.put(
        "/api/settings/profile/structured",
        json={
            "profile": {
                "summary": "Candidate summary",
                "contact": {
                    "full_name": "Jane Doe",
                    "email": "jane@example.com",
                    "phone": "555-0100",
                    "city": "Gainesville",
                    "state_or_region": "FL",
                    "country_code": "US",
                    "country_label": "United States",
                    "linkedin_url": "",
                    "github_url": "",
                    "portfolio_url": "",
                },
                "work_authorization": {
                    "citizenship_country_code": "US",
                    "citizenship_country_label": "United States",
                    "authorized_to_work_us": "yes",
                    "requires_sponsorship_now_or_future": "no",
                },
                "education_summary": "BS in Computer Science in progress",
                "education_entries": [
                    {
                        "id": "edu-1",
                        "school": "University of Florida",
                        "degree_level": "BS",
                        "degree_name": "Computer Science",
                        "field_of_study": "",
                        "start_month": "",
                        "start_year": "",
                        "end_month": "",
                        "end_year": "",
                        "is_current": True,
                        "gpa": "",
                        "location": "",
                        "highlights": [],
                    }
                ],
                "target_roles": ["Software Engineering Internship"],
                "strongest_areas": ["Python"],
                "experience_highlights": ["Built APIs"],
                "hard_filters": ["US roles only"],
                "preferences": ["Prefer internships"],
            },
            "search_defaults": {"job_board_search_terms": ["software internship"]},
            "prompt_context": None,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["profile"]["contact"]["full_name"] == "Jane Doe"
    assert payload["profile"]["work_authorization"]["authorized_to_work_us"] == "yes"
    assert payload["profile"]["education_entries"][0]["id"] == "edu-1"

    persisted_yaml = api_main.SETTINGS_PROFILE_PATH.read_text(encoding="utf-8")
    assert "contact:" in persisted_yaml
    assert "work_authorization:" in persisted_yaml
    assert "education_entries:" in persisted_yaml
