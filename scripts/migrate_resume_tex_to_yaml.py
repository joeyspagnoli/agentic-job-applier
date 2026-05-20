#!/usr/bin/env python3
"""Migrate existing resume LaTeX into canonical YAML resume content.

Purpose:
    Convert the current resume `.tex` source into the YAML-canonical model used
    by the pi-mono resume-tailor runtime.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from src.agents.resume_tailor.schemas import EducationEntry
from src.agents.resume_tailor.schemas import EducationSection
from src.agents.resume_tailor.schemas import ExperienceListing
from src.agents.resume_tailor.schemas import ExperienceSection
from src.agents.resume_tailor.schemas import PersonalSection
from src.agents.resume_tailor.schemas import ProjectListing
from src.agents.resume_tailor.schemas import ProjectsSection
from src.agents.resume_tailor.schemas import ResumeBullet
from src.agents.resume_tailor.schemas import ResumeContent
from src.agents.resume_tailor.schemas import ResumeLink
from src.agents.resume_tailor.schemas import SkillListing
from src.agents.resume_tailor.schemas import SkillsAchievementsSection
from src.agents.resume_tailor.yaml_io import save_resume_yaml
from src.utils.paths import resolve_repo_root

SECTION_HEADER_PATTERN = re.compile(r"\\section\{\\textbf\{(?P<heading>[^}]+)\}\}")
EXPERIENCE_HEADER_PATTERN = re.compile(
    r"^\s*\\item\s+\{\\textbf\{(?P<title>.+?)\}\}\s+\\hfill\s+\{\\textbf\{(?P<date>.+?)\}\}\\\\\s*$",
    re.MULTILINE,
)
PROJECT_HEADER_PATTERN = re.compile(
    r"^\s*\\item\{\\textbf\{(?P<title_stack>.+?)\}\}\\hfill\\textbf\{(?P<date>.+?)\}\s*$",
    re.MULTILINE,
)


class ResumeMigrationError(RuntimeError):
    """Represent migration failures for `.tex` to canonical YAML conversion."""


def _slugify(value: str) -> str:
    """Convert arbitrary text into a stable lowercase identifier.

    Purpose:
        Generate deterministic IDs for listings and bullets extracted from
        freeform LaTeX text.
    Args:
        value: Source text used to derive an identifier.
    Output:
        Returns a normalized identifier containing lowercase letters, digits,
        and underscores only.
    """

    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return normalized or "item"


def _extract_brace_balanced_args(text: str, command: str) -> list[str]:
    """Extract all arguments of `\\command{...}` with proper brace balancing.

    Unlike a greedy/lazy regex, this walks character-by-character so nested
    braces inside the argument (e.g. `\\textbf{foo}`) don't terminate early.
    """
    results: list[str] = []
    search = f"\\{command}{{"
    pos = 0
    while True:
        start = text.find(search, pos)
        if start == -1:
            break
        # Position of the opening brace for the argument
        arg_start = start + len(search)
        depth = 1
        i = arg_start
        while i < len(text) and depth > 0:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        results.append(text[arg_start : i - 1])
        pos = i
    return results


def _extract_section_blocks(tex_text: str) -> dict[str, str]:
    """Extract LaTeX section bodies keyed by heading text.

    Purpose:
        Split the source document into section-level chunks for focused parsers.
    Args:
        tex_text: Full LaTeX resume source text.
    Output:
        Returns heading-to-section-body mapping.
    """

    section_matches = list(SECTION_HEADER_PATTERN.finditer(tex_text))
    sections: dict[str, str] = {}

    for index, match in enumerate(section_matches):
        start = match.end()
        end = (
            section_matches[index + 1].start()
            if index + 1 < len(section_matches)
            else len(tex_text)
        )
        sections[match.group("heading")] = tex_text[start:end]

    return sections


def _extract_personal_section(tex_text: str) -> PersonalSection:
    """Extract the personal heading/contact block from resume LaTeX.

    Purpose:
        Build canonical personal section fields from the centered heading block.
    Args:
        tex_text: Full LaTeX resume source text.
    Output:
        Returns parsed `PersonalSection` model.
    Raises:
        ResumeMigrationError: When required heading fields cannot be parsed.
    """

    name_match = re.search(r"\\bfseries\s+([^}]+)\}\\\\", tex_text)
    if name_match is None:
        raise ResumeMigrationError("Could not parse name from LaTeX heading block")

    contact_match = re.search(
        r"\{\\normalsize\s*(.+?)\}\s*\\end\{center\}", tex_text, re.DOTALL
    )
    if contact_match is None:
        raise ResumeMigrationError("Could not parse contact block from LaTeX heading")

    contact_text = " ".join(contact_match.group(1).split())
    raw_segments = [segment.strip() for segment in contact_text.split("\\textbar\\")]
    if len(raw_segments) < 3:
        raise ResumeMigrationError("Contact block did not contain expected segments")

    phone = raw_segments[0]

    email_match = re.search(r"\\href\{mailto:([^}]+)\}\{([^}]+)\}", raw_segments[1])
    if email_match is None:
        raise ResumeMigrationError("Could not parse email link in contact block")
    email = email_match.group(2)

    links: list[ResumeLink] = []
    for segment in raw_segments[2:]:
        href_match = re.search(r"\\href\{([^}]+)\}\{([^}]+)\}", segment)
        if href_match is None:
            continue
        label = href_match.group(2)
        link_id = _slugify(label.replace(".", "_"))
        links.append(
            ResumeLink(
                id=link_id,
                label=label,
                url=href_match.group(1),
            )
        )

    return PersonalSection(
        name=name_match.group(1).strip(),
        phone=phone,
        email=email,
        links=links,
    )


def _extract_education_section(section_text: str) -> EducationSection:
    """Extract immutable education entries from LaTeX section text.

    Purpose:
        Build canonical education entries while preserving all visible text.
    Args:
        section_text: LaTeX content slice for the Education section.
    Output:
        Returns parsed `EducationSection` model.
    Raises:
        ResumeMigrationError: When the primary education listing is missing.
    """

    subheading_match = re.search(
        r"\\resumeSubheading\{(.+?)\}\{(.+?)\}\{(.+?)\}\{(.+?)\}",
        section_text,
        re.DOTALL,
    )
    if subheading_match is None:
        raise ResumeMigrationError("Could not parse education subheading")

    bullets: list[ResumeBullet] = []
    bullet_matches = re.findall(
        r"^\s*\\item\s+(.+?)\s*$", section_text, flags=re.MULTILINE
    )
    for index, bullet_text in enumerate(bullet_matches, start=1):
        bullets.append(
            ResumeBullet(
                id=f"education_bullet_{index}",
                text=bullet_text.strip(),
            )
        )

    education_entry = EducationEntry(
        id="education_1",
        institution=subheading_match.group(1).strip(),
        date_range=subheading_match.group(2).strip(),
        degree=subheading_match.group(3).strip(),
        detail=subheading_match.group(4).strip(),
        bullets=bullets,
    )

    return EducationSection(entries=[education_entry])


def _extract_experience_section(section_text: str) -> ExperienceSection:
    """Extract active/inactive experience listings from LaTeX section text.

    Purpose:
        Build canonical experience listing entries and IDs from role headers and
        bullet blocks.
    Args:
        section_text: LaTeX content slice for the Experience section.
    Output:
        Returns parsed `ExperienceSection` model.
    """

    listings: list[ExperienceListing] = []
    header_matches = list(EXPERIENCE_HEADER_PATTERN.finditer(section_text))

    for index, match in enumerate(header_matches, start=1):
        start = match.end()
        end = (
            header_matches[index].start()
            if index < len(header_matches)
            else len(section_text)
        )
        listing_block = section_text[start:end]

        organization_match = re.search(r"\\textbf\{([^}]+)\}", listing_block)
        organization = organization_match.group(1).strip() if organization_match else ""

        bullet_texts = _extract_brace_balanced_args(listing_block, "resumeItem")
        bullets: list[ResumeBullet] = []
        for bullet_index, bullet_text in enumerate(bullet_texts, start=1):
            bullets.append(
                ResumeBullet(
                    id=f"exp_{index}_bullet_{bullet_index}",
                    text=" ".join(bullet_text.split()),
                )
            )

        listing_id = f"exp_{index}_{_slugify(match.group('title'))}"
        listings.append(
            ExperienceListing(
                id=listing_id,
                enabled=True,
                title=match.group("title").strip(),
                date_range=match.group("date").strip(),
                organization=organization,
                bullets=bullets,
            )
        )

    listings.append(
        ExperienceListing(
            id="exp_pool_template",
            enabled=False,
            title="Candidate Experience Listing",
            date_range="MM. YYYY -- MM. YYYY",
            organization="Organization $|$ Location",
            bullets=[
                ResumeBullet(
                    id="exp_pool_template_bullet_1",
                    text="Template inactive listing for future pool swaps.",
                )
            ],
        )
    )

    return ExperienceSection(listings=listings)


def _extract_projects_section(section_text: str) -> ProjectsSection:
    """Extract active/inactive project listings from LaTeX section text.

    Purpose:
        Build canonical project listing entries and IDs from project headers and
        bullet blocks.
    Args:
        section_text: LaTeX content slice for the Projects section.
    Output:
        Returns parsed `ProjectsSection` model.
    """

    listings: list[ProjectListing] = []
    header_matches = list(PROJECT_HEADER_PATTERN.finditer(section_text))

    for index, match in enumerate(header_matches, start=1):
        start = match.end()
        end = (
            header_matches[index].start()
            if index < len(header_matches)
            else len(section_text)
        )
        listing_block = section_text[start:end]

        raw_title_stack = match.group("title_stack").strip()
        if "$|$" in raw_title_stack:
            title, tech_stack = [
                part.strip() for part in raw_title_stack.split("$|$", maxsplit=1)
            ]
        else:
            title = raw_title_stack
            tech_stack = ""

        bullet_texts = _extract_brace_balanced_args(listing_block, "resumeItem")
        bullets: list[ResumeBullet] = []
        for bullet_index, bullet_text in enumerate(bullet_texts, start=1):
            bullets.append(
                ResumeBullet(
                    id=f"proj_{index}_bullet_{bullet_index}",
                    text=" ".join(bullet_text.split()),
                )
            )

        listings.append(
            ProjectListing(
                id=f"project_{index}_{_slugify(title)}",
                enabled=True,
                title=title,
                tech_stack=tech_stack,
                date_range=match.group("date").strip(),
                bullets=bullets,
            )
        )

    listings.append(
        ProjectListing(
            id="project_pool_template",
            enabled=False,
            title="Candidate Project Listing",
            tech_stack="Python, Tooling",
            date_range="MM. YYYY -- MM. YYYY",
            bullets=[
                ResumeBullet(
                    id="project_pool_template_bullet_1",
                    text="Template inactive project listing for pool swaps.",
                )
            ],
        )
    )

    return ProjectsSection(listings=listings)


def _extract_skills_section(section_text: str) -> SkillsAchievementsSection:
    """Extract skill lines from LaTeX section text.

    Purpose:
        Build canonical skills-line entries with stable IDs and category labels.
    Args:
        section_text: LaTeX content slice for the Skills section.
    Output:
        Returns parsed `SkillsAchievementsSection` model.
    """

    listings: list[SkillListing] = []
    skill_matches = re.findall(
        r"\\item\{\\textbf\{(.+?)\}:\s*(.+?)\}",
        section_text,
        flags=re.DOTALL,
    )

    for index, (category, text) in enumerate(skill_matches, start=1):
        listings.append(
            SkillListing(
                id=f"skill_{index}_{_slugify(category)}",
                enabled=True,
                category=category.strip(),
                text=" ".join(text.split()),
            )
        )

    listings.append(
        SkillListing(
            id="skills_pool_template",
            enabled=False,
            category="Additional",
            text="Template inactive skills row for future pool swaps.",
        )
    )

    return SkillsAchievementsSection(listings=listings)


def migrate_resume_tex_to_yaml(
    *,
    resume_tex_path: str | Path,
    output_yaml_path: str | Path,
) -> ResumeContent:
    """Migrate source `.tex` resume content into canonical YAML format.

    Purpose:
        Parse structured LaTeX resume sections and persist the equivalent YAML
        canonical model used by the tailor runtime.
    Args:
        resume_tex_path: Source LaTeX resume file path.
        output_yaml_path: Destination canonical YAML file path.
    Output:
        Returns the generated `ResumeContent` model.
    Raises:
        ResumeMigrationError: When required sections cannot be parsed.
    """

    source_tex_path = Path(resume_tex_path).resolve()
    if not source_tex_path.exists():
        raise ResumeMigrationError(
            f"LaTeX source file does not exist: {source_tex_path}"
        )

    tex_text = source_tex_path.read_text(encoding="utf-8")
    sections = _extract_section_blocks(tex_text)

    required_sections = (
        "Education",
        "Experience",
        "Projects",
        "Skills and Achievements",
    )
    missing_sections = [
        section for section in required_sections if section not in sections
    ]
    if missing_sections:
        raise ResumeMigrationError(
            f"LaTeX source is missing required sections: {', '.join(missing_sections)}"
        )

    resume_content = ResumeContent(
        personal=_extract_personal_section(tex_text),
        education=_extract_education_section(sections["Education"]),
        experience=_extract_experience_section(sections["Experience"]),
        projects=_extract_projects_section(sections["Projects"]),
        skills_achievements=_extract_skills_section(
            sections["Skills and Achievements"]
        ),
    )

    save_resume_yaml(path=output_yaml_path, resume_content=resume_content)
    return resume_content


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for LaTeX-to-YAML resume migration.

    Purpose:
        Provide explicit command-line controls for source and destination file
        paths used by migration workflows.
    Args:
        None.
    Output:
        Returns configured argparse parser.
    """

    repo_root = resolve_repo_root()

    parser = argparse.ArgumentParser(
        description="Migrate LaTeX resume to canonical YAML resume_content format"
    )
    parser.add_argument(
        "--resume-tex-path",
        type=str,
        default=str((repo_root.parent / "resume" / "resume.tex").resolve()),
        help="Source LaTeX resume file path",
    )
    parser.add_argument(
        "--output-yaml-path",
        type=str,
        default=str((repo_root / "config" / "resume_content.yaml").resolve()),
        help="Destination canonical YAML path",
    )
    return parser


def main() -> int:
    """Run LaTeX-to-YAML migration from CLI arguments.

    Purpose:
        Execute migration with deterministic stdout output for operators and
        automation tooling.
    Args:
        None.
    Output:
        Returns process exit status `0` on success and `1` on failure.
    """

    parser = build_parser()
    args = parser.parse_args()

    try:
        resume_content = migrate_resume_tex_to_yaml(
            resume_tex_path=args.resume_tex_path,
            output_yaml_path=args.output_yaml_path,
        )
    except Exception as exc:
        print(f"Migration failed: {exc}")
        return 1

    print(
        "Migration succeeded:\n"
        f"- Source: {Path(args.resume_tex_path).resolve()}\n"
        f"- Output: {Path(args.output_yaml_path).resolve()}\n"
        f"- Experience listings: {len(resume_content.experience.listings)}\n"
        f"- Project listings: {len(resume_content.projects.listings)}\n"
        f"- Skill listings: {len(resume_content.skills_achievements.listings)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
