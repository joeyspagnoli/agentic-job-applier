"""Helpers for building canonical resume YAML stubs from non-YAML uploads."""

from __future__ import annotations

import io
from pathlib import Path

import pypdf
import yaml

from src.agents.resume_tailor.schemas import EducationSection
from src.agents.resume_tailor.schemas import ExperienceSection
from src.agents.resume_tailor.schemas import PersonalSection
from src.agents.resume_tailor.schemas import ProjectsSection
from src.agents.resume_tailor.schemas import ResumeContent
from src.agents.resume_tailor.schemas import SkillsAchievementsSection


def read_pdf_pages(raw_bytes: bytes) -> tuple[pypdf.PdfReader, list[str]]:
    """Decode raw PDF bytes and return reader plus extracted per-page text.

    Purpose:
        Centralize PDF text extraction so the upload route stays focused on
        request and response handling.
    Args:
        raw_bytes: Raw PDF file content.
    Output:
        Returns the parsed `PdfReader` and a list of per-page text strings.
    Raises:
        Exception: When the bytes are not a valid PDF document. Callers should
            translate this into a deterministic API error response.
    """

    reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
    extracted_pages = [(page.extract_text() or "") for page in reader.pages]
    return reader, extracted_pages


def read_candidate_contact_from_profile_yaml(
    profile_path: Path,
) -> tuple[str, str, str]:
    """Read minimum candidate-contact strings from the profile YAML on disk.

    Purpose:
        Allow the PDF upload flow to seed the canonical YAML stub with the
        candidate's stored contact details when present.
    Args:
        profile_path: Filesystem path to candidate profile YAML.
    Output:
        Returns `(name, phone, email)` strings (empty when missing or invalid).
    """

    if not profile_path.exists():
        return "", "", ""

    try:
        profile_text = profile_path.read_text(encoding="utf-8")
        profile_data = yaml.safe_load(profile_text) or {}
        contact = (profile_data.get("profile") or {}).get("contact") or {}
        candidate_name = str(contact.get("full_name") or "").strip()
        candidate_phone = str(contact.get("phone") or "").strip()
        candidate_email = str(contact.get("email") or "").strip()
        return candidate_name, candidate_phone, candidate_email
    except (OSError, yaml.YAMLError, KeyError, TypeError, AttributeError):
        return "", "", ""


def build_stub_resume_content(
    *,
    candidate_name: str,
    candidate_phone: str,
    candidate_email: str,
) -> ResumeContent:
    """Build a minimal canonical `ResumeContent` for PDF upload onboarding.

    Purpose:
        Keep settings-resume routes focused on persistence, not stub-resume
        construction details.
    Args:
        candidate_name: Candidate's full name (empty falls back to placeholder).
        candidate_phone: Candidate's phone (empty allowed).
        candidate_email: Candidate's email (empty allowed).
    Output:
        Returns a populated `ResumeContent` placeholder.
    """

    return ResumeContent(
        personal=PersonalSection(
            name=candidate_name or "Your Name",
            phone=candidate_phone or "",
            email=candidate_email or "",
            links=[],
        ),
        education=EducationSection(),
        experience=ExperienceSection(),
        projects=ProjectsSection(),
        skills_achievements=SkillsAchievementsSection(),
    )
