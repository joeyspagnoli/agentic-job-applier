"""TeX heading normalization and migration-prep helpers for resume uploads."""

from __future__ import annotations

import re

from src.agents.resume_tailor_adk.schemas import ResumeContent

from api.config import PERSONAL_CONTACT_PATTERN
from api.config import PERSONAL_NAME_PATTERN
from api.config import TEX_SECTION_HEADER_PATTERN
from api.config import TEX_SECTION_HEADING_ALIASES


def _normalize_tex_section_headings(tex_text: str) -> str:
    """Normalize common LaTeX resume heading aliases to canonical names.

    Purpose:
        Allow TeX uploads with varied section names to map into the canonical
        migration contract without requiring users to hand-edit heading text.
    Args:
        tex_text: Raw uploaded TeX source text.
    Output:
        Returns TeX text with known heading aliases replaced.
    """

    def _replace_heading(match: re.Match[str]) -> str:
        """Return one canonical replacement heading for alias-normalization.

        Purpose:
            Keep alias replacement logic localized to one callback used by
            the compiled section-header regex substitution.
        Args:
            match: Regex match containing the raw heading text.
        Output:
            Returns the canonical section heading replacement text.
        """

        heading_text = match.group("heading").strip()
        canonical_heading = TEX_SECTION_HEADING_ALIASES.get(
            heading_text.lower(),
            heading_text,
        )
        return f"\\section{{\\textbf{{{canonical_heading}}}}}"

    return TEX_SECTION_HEADER_PATTERN.sub(_replace_heading, tex_text)


def _build_fallback_personal_header(resume_document: ResumeContent) -> str:
    """Build one parseable fallback personal header block for TeX migration.

    Purpose:
        Keep migration resilient when uploaded TeX does not include the exact
        centered heading pattern expected by the migration parser.
    Args:
        resume_document: Current canonical resume document used as fallback.
    Output:
        Returns a compact LaTeX header block parseable by migration logic.
    """

    personal = resume_document.personal
    links_text = " \\textbar\\ ".join(
        f"\\href{{{link.url}}}{{{link.label}}}" for link in personal.links
    )
    contact_parts = [
        personal.phone,
        f"\\href{{mailto:{personal.email}}}{{{personal.email}}}",
    ]
    if links_text != "":
        contact_parts.append(links_text)
    contact_text = " \\textbar\\ ".join(contact_parts)
    return (
        "\\begin{center}\n"
        f"{{\\bfseries {personal.name}}}\\\\\n"
        f"{{\\normalsize {contact_text}}}\n"
        "\\end{center}\n\n"
    )


def _build_fallback_education_section(resume_document: ResumeContent) -> str:
    """Build one parseable fallback education section for TeX migration.

    Purpose:
        Guarantee migration has a valid education section when uploaded TeX
        omits education content or uses incompatible education macros.
    Args:
        resume_document: Current canonical resume document used as fallback.
    Output:
        Returns TeX text for one canonical education section.
    """

    education_entry = (
        resume_document.education.entries[0]
        if len(resume_document.education.entries) > 0
        else None
    )
    if education_entry is None:
        institution = "University"
        date_range = "MM. YYYY -- MM. YYYY"
        degree = "Degree"
        detail = "Details"
        bullet_text = "Education details."
    else:
        institution = education_entry.institution
        date_range = education_entry.date_range
        degree = education_entry.degree
        detail = education_entry.detail
        bullet_text = (
            education_entry.bullets[0].text
            if len(education_entry.bullets) > 0
            else "Education details."
        )

    return (
        "\\section{\\textbf{Education}}\n"
        f"\\resumeSubheading{{{institution}}}{{{date_range}}}{{{degree}}}{{{detail}}}\n"
        "\\begin{itemize}\n"
        f"\\item {bullet_text}\n"
        "\\end{itemize}\n\n"
    )


def _ensure_tex_required_sections(
    *,
    tex_text: str,
    fallback_resume: ResumeContent,
) -> str:
    """Ensure canonical section headings exist before TeX-to-YAML migration.

    Purpose:
        Make migration tolerant of non-standard section naming and partially
        missing sections while still producing a canonical resume payload.
    Args:
        tex_text: Normalized TeX source text.
        fallback_resume: Existing canonical resume used for fallback sections.
    Output:
        Returns TeX text guaranteed to include required canonical headings.
    """

    current_text = tex_text
    section_headings = {
        match.group("heading").strip()
        for match in TEX_SECTION_HEADER_PATTERN.finditer(current_text)
    }

    if "Education" not in section_headings or "\\resumeSubheading{" not in current_text:
        current_text += "\n" + _build_fallback_education_section(fallback_resume)
        section_headings.add("Education")

    if "Experience" not in section_headings:
        current_text += "\n\\section{\\textbf{Experience}}\n\n"
        section_headings.add("Experience")
    if "Projects" not in section_headings:
        current_text += "\n\\section{\\textbf{Projects}}\n\n"
        section_headings.add("Projects")
    if "Skills and Achievements" not in section_headings:
        current_text += "\n\\section{\\textbf{Skills and Achievements}}\n\n"
        section_headings.add("Skills and Achievements")

    return current_text


def _prepare_resume_tex_for_migration(
    *,
    uploaded_tex_text: str,
    fallback_resume: ResumeContent,
) -> str:
    """Prepare uploaded TeX text for robust canonical migration.

    Purpose:
        Normalize heading aliases and inject fallback personal/section content
        so migration succeeds for common resume template variations.
    Args:
        uploaded_tex_text: Raw uploaded TeX source.
        fallback_resume: Existing canonical resume for fallback content.
    Output:
        Returns normalized TeX text ready for migration.
    """

    normalized_text = _normalize_tex_section_headings(uploaded_tex_text)

    has_parseable_personal_header = (
        PERSONAL_NAME_PATTERN.search(normalized_text) is not None
        and PERSONAL_CONTACT_PATTERN.search(normalized_text) is not None
    )
    if not has_parseable_personal_header:
        normalized_text = (
            _build_fallback_personal_header(fallback_resume) + normalized_text
        )

    return _ensure_tex_required_sections(
        tex_text=normalized_text,
        fallback_resume=fallback_resume,
    )
