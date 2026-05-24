"""Endpoint tests for the Phase 3 `.tex`-only resume settings router.

Purpose:
    Cover the full Phase 3 API surface: conforming `POST /resume` writes
    the file + returns a manifest preview, `GET /resume` returns the
    saved text + contract status, `GET /resume/download` serves the
    file with the right MIME type, missing-file branches return 404,
    and every retired endpoint returns the structured 410 GONE envelope.

    The existing `test_api_resume_download_and_settings_upload.py`
    covers two of these branches already (422 invalid-tex + 410 for
    `POST /resume/tex`); this module fills the gaps the Phase 1-4
    handoff called out.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main as api_main


# A small but contract-conforming `.tex` document. Jake's-family
# `\resumeSubheading` + `\resumeItem` — already exercised by the
# locator / validator suites.
_CONFORMING_TEX = (
    "\\documentclass[letterpaper,10pt]{article}\n"
    "\\newcommand{\\resumeItem}[1]{\\item #1}\n"
    "\\newcommand{\\resumeSubheading}[4]"
    "{\\item \\textbf{#1} \\hfill \\textbf{#2}\\\\#3\\hfill#4}\n"
    "\\begin{document}\n"
    "\\section{Experience}\n"
    "\\begin{itemize}\n"
    "  \\resumeSubheading{Engineer}{2024}{Acme}{Remote}\n"
    "    \\begin{itemize}\n"
    "      \\resumeItem{Shipped the ingestion service.}\n"
    "    \\end{itemize}\n"
    "\\end{itemize}\n"
    "\\end{document}\n"
)


@pytest.fixture
def api_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    """Build a FastAPI TestClient with an isolated resume + backups dir.

    Purpose:
        Each test gets its own `config/resume.tex` location so writes
        never touch the real dogfood resume in the repo. The backups
        dir is also redirected so `_backup_settings_file` has somewhere
        sandboxed to write rotated copies.
    Args:
        tmp_path: pytest-provided per-test temp dir.
        monkeypatch: monkeypatch fixture for module attribute swaps.
    Output:
        Configured `TestClient` for `api_main.app`.
    """

    database_path = tmp_path / "jobs.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setattr(api_main, "SETTINGS_RESUME_PATH", tmp_path / "resume.tex")
    monkeypatch.setattr(api_main, "SETTINGS_BACKUPS_DIR", tmp_path / "backups")
    return TestClient(api_main.app)


# ---------------------------------------------------------------------------
# POST /resume — happy path
# ---------------------------------------------------------------------------


def test_post_resume_with_conforming_tex_returns_200_and_manifest_preview(
    api_client: TestClient,
) -> None:
    """Conforming `.tex` uploads succeed and surface a manifest preview."""

    response = api_client.post(
        "/api/settings/resume",
        files={"file": ("resume.tex", _CONFORMING_TEX.encode("utf-8"), "text/plain")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["manifest_preview"] is not None
    sections = payload["manifest_preview"]["sections"]
    assert any(section["kind"] == "experience" for section in sections)


def test_post_resume_persists_uploaded_tex_to_settings_path(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful upload writes the bytes to `SETTINGS_RESUME_PATH`."""

    response = api_client.post(
        "/api/settings/resume",
        files={"file": ("resume.tex", _CONFORMING_TEX.encode("utf-8"), "text/plain")},
    )

    assert response.status_code == 200
    resume_path: Path = api_main.SETTINGS_RESUME_PATH
    assert resume_path.exists()
    assert resume_path.read_text(encoding="utf-8") == _CONFORMING_TEX


def test_post_resume_response_carries_file_metadata(
    api_client: TestClient,
) -> None:
    """The 200 response includes settings-file metadata for the dashboard."""

    response = api_client.post(
        "/api/settings/resume",
        files={"file": ("resume.tex", _CONFORMING_TEX.encode("utf-8"), "text/plain")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "resume" in payload
    # `_resolve_settings_file_metadata` returns at minimum `exists` +
    # `size` keys for a real file. Pin existence so any future shape
    # change is intentional.
    assert payload["resume"]["exists"] is True


# ---------------------------------------------------------------------------
# GET /resume — present + missing
# ---------------------------------------------------------------------------


def test_get_resume_returns_200_with_tex_text_when_file_exists(
    api_client: TestClient,
) -> None:
    """`GET /resume` reads back the file and reports contract_pass=true."""

    api_main.SETTINGS_RESUME_PATH.parent.mkdir(parents=True, exist_ok=True)
    api_main.SETTINGS_RESUME_PATH.write_text(_CONFORMING_TEX, encoding="utf-8")

    response = api_client.get("/api/settings/resume")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["tex_text"] == _CONFORMING_TEX
    assert payload["contract_pass"] is True
    assert payload["manifest_preview"] is not None


def test_get_resume_returns_404_when_file_missing(api_client: TestClient) -> None:
    """`GET /resume` returns 404 when no resume is on disk."""

    response = api_client.get("/api/settings/resume")

    assert response.status_code == 404


def test_get_resume_reports_contract_failure_for_existing_invalid_file(
    api_client: TestClient,
) -> None:
    """An existing-but-invalid `.tex` returns 200 + `contract_pass=false`.

    The GET endpoint is read-only — it does not refuse to surface a
    non-conforming file, it just reports the contract status so the
    frontend can render the warning.
    """

    api_main.SETTINGS_RESUME_PATH.parent.mkdir(parents=True, exist_ok=True)
    api_main.SETTINGS_RESUME_PATH.write_text(
        "\\documentclass{article}\\begin{document}no sections\\end{document}",
        encoding="utf-8",
    )

    response = api_client.get("/api/settings/resume")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_pass"] is False
    assert payload["manifest_preview"] is None


# ---------------------------------------------------------------------------
# GET /resume/download — MIME type + 404
# ---------------------------------------------------------------------------


def test_get_resume_download_serves_tex_mime_type(api_client: TestClient) -> None:
    """`GET /resume/download` advertises `application/x-tex`."""

    api_main.SETTINGS_RESUME_PATH.parent.mkdir(parents=True, exist_ok=True)
    api_main.SETTINGS_RESUME_PATH.write_text(_CONFORMING_TEX, encoding="utf-8")

    response = api_client.get("/api/settings/resume/download")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-tex")
    assert response.content == _CONFORMING_TEX.encode("utf-8")


def test_get_resume_download_returns_404_when_file_missing(
    api_client: TestClient,
) -> None:
    """`GET /resume/download` returns 404 when no resume is on disk."""

    response = api_client.get("/api/settings/resume/download")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 410 GONE envelopes — every retired endpoint surfaces the same shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method, path",
    [
        ("PUT", "/api/settings/resume"),
        ("PUT", "/api/settings/resume/structured"),
        ("POST", "/api/settings/resume/pdf"),
        ("POST", "/api/settings/resume/tex"),
    ],
)
def test_retired_endpoints_return_410_with_structured_envelope(
    api_client: TestClient, method: str, path: str
) -> None:
    """Every removed endpoint returns the same 410 GONE envelope shape."""

    response = api_client.request(method=method, url=path)

    assert response.status_code == 410
    payload = response.json()
    assert payload["ok"] is False
    assert payload["code"] == "ENDPOINT_REMOVED"
    assert payload["new_endpoint"] == "POST /api/settings/resume"
    assert payload["docs_url"] == "/docs/resume-tex-contract.md"


def test_410_envelope_message_names_the_specific_retired_endpoint(
    api_client: TestClient,
) -> None:
    """The 410 message mentions which specific endpoint was retired."""

    response = api_client.put("/api/settings/resume/structured")

    assert response.status_code == 410
    payload = response.json()
    assert "structured" in payload["message"]
