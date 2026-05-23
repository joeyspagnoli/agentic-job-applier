"""Schema definitions and lock policy for the pi-mono resume tailor.

Purpose:
    Define the canonical YAML resume model, tailor invocation contract, and
    strongly typed run result payloads used by the resume-tailoring workflow.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9_]+$")
LOCKED_SECTION_ORDER: tuple[str, ...] = (
    "education",
    "experience",
    "projects",
    "skills_achievements",
)
LOCKED_SECTION_HEADINGS: dict[str, str] = {
    "education": "Education",
    "experience": "Experience",
    "projects": "Projects",
    "skills_achievements": "Skills and Achievements",
}
NON_EDITABLE_SECTION_IDS: tuple[str, ...] = ("personal", "education")


class ResumeLink(BaseModel):
    """Represent one personal-profile hyperlink in the resume heading.

    Purpose:
        Keep personal contact links structured so they can be rendered
        deterministically and validated before LaTeX generation.
    """

    id: str
    label: str
    url: str

    @field_validator("id")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        """Validate that the link ID follows stable identifier conventions.

        Purpose:
            Enforce deterministic IDs so references remain stable for future
            tooling and targeted edits.
        Args:
            value: Candidate identifier for a resume link.
        Output:
            Returns a lowercased identifier that uses `a-z0-9_` only.
        Raises:
            ValueError: When the identifier is empty or contains invalid chars.
        """

        normalized_value = value.strip().lower()
        if not IDENTIFIER_PATTERN.fullmatch(normalized_value):
            raise ValueError(
                "Link IDs must use lowercase letters, digits, and underscores"
            )
        return normalized_value


class ResumeBullet(BaseModel):
    """Represent one editable bullet point in an experience/project listing.

    Purpose:
        Provide a stable bullet ID plus text payload so the tailoring agent can
        rewrite/add/remove bullets at granular scope.
    """

    id: str
    text: str

    @field_validator("id")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        """Validate that the bullet ID is stable and machine-friendly.

        Purpose:
            Keep bullet references predictable across repeated tailoring runs.
        Args:
            value: Candidate bullet identifier.
        Output:
            Returns a normalized lowercase identifier.
        Raises:
            ValueError: When the identifier is empty or invalid.
        """

        normalized_value = value.strip().lower()
        if not IDENTIFIER_PATTERN.fullmatch(normalized_value):
            raise ValueError(
                "Bullet IDs must use lowercase letters, digits, and underscores"
            )
        return normalized_value


class PersonalSection(BaseModel):
    """Store immutable personal heading/contact text for the resume.

    Purpose:
        Keep the heading block structured and separate from editable sections so
        policy checks can enforce non-editable boundaries.
    """

    section_id: Literal["personal"] = "personal"
    name: str
    phone: str
    email: str
    links: list[ResumeLink] = Field(default_factory=list)


class EducationEntry(BaseModel):
    """Store one education listing entry.

    Purpose:
        Capture all text-bearing education data so it can be rendered exactly
        while staying outside the editable tailoring scope.
    """

    id: str
    institution: str
    date_range: str
    degree: str
    detail: str
    bullets: list[ResumeBullet] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        """Validate that the education entry ID is stable and normalized.

        Purpose:
            Preserve deterministic references for immutable education content.
        Args:
            value: Candidate education entry identifier.
        Output:
            Returns a normalized identifier suitable for machine references.
        Raises:
            ValueError: When the identifier is empty or invalid.
        """

        normalized_value = value.strip().lower()
        if not IDENTIFIER_PATTERN.fullmatch(normalized_value):
            raise ValueError(
                "Education IDs must use lowercase letters, digits, and underscores"
            )
        return normalized_value


class EducationSection(BaseModel):
    """Store the Education section payload.

    Purpose:
        Keep heading and listing data grouped under one immutable section model
        used by lock enforcement and deterministic rendering.
    """

    section_id: Literal["education"] = "education"
    heading: str = LOCKED_SECTION_HEADINGS["education"]
    entries: list[EducationEntry] = Field(default_factory=list)


class ExperienceListing(BaseModel):
    """Store one experience listing with toggleable active state.

    Purpose:
        Allow agent-driven listing swaps through `enabled` flags while
        preserving stable IDs for active/inactive pool management.
    """

    id: str
    enabled: bool = True
    title: str
    date_range: str
    organization: str
    bullets: list[ResumeBullet] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        """Validate that the experience listing ID uses stable formatting.

        Purpose:
            Keep listing references deterministic for targeted edits and pool
            toggling behavior.
        Args:
            value: Candidate experience listing identifier.
        Output:
            Returns a normalized lowercase identifier.
        Raises:
            ValueError: When the identifier is empty or invalid.
        """

        normalized_value = value.strip().lower()
        if not IDENTIFIER_PATTERN.fullmatch(normalized_value):
            raise ValueError(
                "Experience IDs must use lowercase letters, digits, and underscores"
            )
        return normalized_value


class ExperienceSection(BaseModel):
    """Store the Experience section payload and listing pool entries.

    Purpose:
        Keep all active and inactive experience listings in one canonical list
        controlled by `enabled` flags.
    """

    section_id: Literal["experience"] = "experience"
    heading: str = LOCKED_SECTION_HEADINGS["experience"]
    listings: list[ExperienceListing] = Field(default_factory=list)


class ProjectListing(BaseModel):
    """Store one project listing with active/inactive pool semantics.

    Purpose:
        Model project entries so the tailor agent can swap entire listings by
        toggling `enabled` and editing bullets.
    """

    id: str
    enabled: bool = True
    title: str
    tech_stack: str
    date_range: str
    bullets: list[ResumeBullet] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        """Validate that the project listing ID uses stable formatting.

        Purpose:
            Ensure project references stay stable across tailoring iterations.
        Args:
            value: Candidate project listing identifier.
        Output:
            Returns a normalized lowercase identifier.
        Raises:
            ValueError: When the identifier is empty or invalid.
        """

        normalized_value = value.strip().lower()
        if not IDENTIFIER_PATTERN.fullmatch(normalized_value):
            raise ValueError(
                "Project IDs must use lowercase letters, digits, and underscores"
            )
        return normalized_value


class ProjectsSection(BaseModel):
    """Store the Projects section payload and listing pool entries.

    Purpose:
        Keep all project listings in canonical YAML with render-time inclusion
        driven by each listing's `enabled` flag.
    """

    section_id: Literal["projects"] = "projects"
    heading: str = LOCKED_SECTION_HEADINGS["projects"]
    listings: list[ProjectListing] = Field(default_factory=list)


class SkillListing(BaseModel):
    """Store one Skills and Achievements row with active/inactive controls.

    Purpose:
        Support targeted skill-line editing and optional inclusion toggles while
        preserving section structure and ordering.
    """

    id: str
    enabled: bool = True
    category: str
    text: str

    @field_validator("id")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        """Validate that the skill listing ID uses stable formatting.

        Purpose:
            Keep skill-line references stable for targeted rewrite operations.
        Args:
            value: Candidate skill listing identifier.
        Output:
            Returns a normalized lowercase identifier.
        Raises:
            ValueError: When the identifier is empty or invalid.
        """

        normalized_value = value.strip().lower()
        if not IDENTIFIER_PATTERN.fullmatch(normalized_value):
            raise ValueError(
                "Skill IDs must use lowercase letters, digits, and underscores"
            )
        return normalized_value


class SkillsAchievementsSection(BaseModel):
    """Store the Skills and Achievements section content.

    Purpose:
        Keep rows grouped under the locked section heading while allowing
        listing-level edits and enable/disable toggles.
    """

    section_id: Literal["skills_achievements"] = "skills_achievements"
    heading: str = LOCKED_SECTION_HEADINGS["skills_achievements"]
    listings: list[SkillListing] = Field(default_factory=list)


class LayoutKnobs(BaseModel):
    """Store layout controls used for deterministic page-fit adjustments.

    Purpose:
        Centralize rendering knobs so content-first retries can fall back to a
        bounded layout compression profile only after retry limits are reached.
    """

    margin_in: float = 0.50
    top_vspace_in: float = -0.45
    section_heading_font_size_pt: float = 13.0
    section_heading_line_height_pt: float = 15.0
    section_spacing_before_pt: float = 1.0
    section_spacing_after_pt: float = 1.0
    subheading_itemsep_pt: float = 2.0
    bullet_itemsep_pt: float = 1.0


class ResumeLockRules(BaseModel):
    """Store the canonical lock boundaries for section policy enforcement.

    Purpose:
        Define immutable section order, section headers, and non-editable
        section IDs that runtime checks enforce before rendering.
    """

    section_order: list[str] = Field(default_factory=lambda: list(LOCKED_SECTION_ORDER))
    section_headings: dict[str, str] = Field(
        default_factory=lambda: dict(LOCKED_SECTION_HEADINGS)
    )
    non_editable_sections: list[str] = Field(
        default_factory=lambda: list(NON_EDITABLE_SECTION_IDS)
    )


class ResumeContent(BaseModel):
    """Represent the full YAML-canonical resume document.

    Purpose:
        Serve as the source-of-truth model that the pi-mono tailor edits and
        the renderer converts into deterministic LaTeX output.
    """

    schema_version: int = 1
    lock_rules: ResumeLockRules = Field(default_factory=ResumeLockRules)
    layout: LayoutKnobs = Field(default_factory=LayoutKnobs)
    personal: PersonalSection
    education: EducationSection
    experience: ExperienceSection
    projects: ProjectsSection
    skills_achievements: SkillsAchievementsSection

    @model_validator(mode="after")
    def _validate_unique_listing_ids(self) -> "ResumeContent":
        """Validate that listing IDs are unique inside each editable section.

        Purpose:
            Prevent ambiguous references during targeted listing/bullet edits and
            pool toggles.
        Args:
            self: Candidate `ResumeContent` instance being validated.
        Output:
            Returns `self` when per-section listing IDs are unique.
        Raises:
            ValueError: When any section contains duplicate listing IDs.
        """

        for section_name, listings in (
            ("experience", self.experience.listings),
            ("projects", self.projects.listings),
            ("skills_achievements", self.skills_achievements.listings),
        ):
            listing_ids = [listing.id for listing in listings]
            if len(listing_ids) != len(set(listing_ids)):
                raise ValueError(f"Duplicate listing IDs in section '{section_name}'")
        return self


class TailorJobRef(BaseModel):
    """Represent the job selector passed to the resume-tailor pipeline.

    Purpose:
        Allow callers to reference a target job by either hash or numeric ID
        while keeping selector validation explicit and strict.
    """

    job_hash: str | None = None
    job_id: int | None = None

    @model_validator(mode="after")
    def _validate_selector(self) -> "TailorJobRef":
        """Validate that exactly one job selector field is set.

        Purpose:
            Avoid ambiguous DB lookup behavior and keep invocation contracts
            deterministic for tooling and scripts.
        Args:
            self: Candidate `TailorJobRef` instance being validated.
        Output:
            Returns `self` when exactly one selector is provided.
        Raises:
            ValueError: When both selectors are present or both are missing.
        """

        has_hash = self.job_hash is not None and self.job_hash.strip() != ""
        has_id = self.job_id is not None
        if has_hash == has_id:
            raise ValueError("Provide exactly one of job_hash or job_id")
        if self.job_hash is not None:
            self.job_hash = self.job_hash.strip()
        return self


class TailorAttemptRecord(BaseModel):
    """Represent one compile-check attempt in the one-page enforcement loop.

    Purpose:
        Preserve transparent run history for debugging and future review-agent
        integration without requiring verbose log inspection.
    """

    phase: Literal["content", "layout"]
    attempt_index: int
    page_count: int | None = None
    success: bool = False
    message: str


class TailorRunResult(BaseModel):
    """Represent the final output of a resume-tailor pipeline run.

    Purpose:
        Return a deterministic success/failure payload with artifact paths and
        attempt history for operational scripts and later stage integration.
    """

    success: bool
    failure_reason: str | None = None
    output_tex_path: str
    output_pdf_path: str
    final_page_count: int | None = None
    attempts: list[TailorAttemptRecord] = Field(default_factory=list)
    active_git_branch: str | None = None


def validate_locked_structure(resume_content: ResumeContent) -> None:
    """Validate lock rules and immutable section headings/order.

    Purpose:
        Enforce the hard section lock contract before rendering so prompt drift
        or malformed edits cannot change section-level structure.
    Args:
        resume_content: Parsed canonical resume model to validate.
    Output:
        Returns `None` when locked structure is valid.
    Raises:
        ValueError: When section order/headings or non-editable set differ from
            expected lock-policy constants.
    """

    section_order = tuple(resume_content.lock_rules.section_order)
    if section_order != LOCKED_SECTION_ORDER:
        raise ValueError(
            f"Section order is locked and must equal {list(LOCKED_SECTION_ORDER)}"
        )

    non_editable = tuple(resume_content.lock_rules.non_editable_sections)
    if non_editable != NON_EDITABLE_SECTION_IDS:
        raise ValueError(
            "Non-editable section set is locked and must equal "
            f"{list(NON_EDITABLE_SECTION_IDS)}"
        )

    for section_id, expected_heading in LOCKED_SECTION_HEADINGS.items():
        configured_heading = resume_content.lock_rules.section_headings.get(section_id)
        if configured_heading != expected_heading:
            raise ValueError(
                f"Heading lock for section '{section_id}' must be '{expected_heading}'"
            )

    if resume_content.education.heading != LOCKED_SECTION_HEADINGS["education"]:
        raise ValueError("Education heading is locked")
    if resume_content.experience.heading != LOCKED_SECTION_HEADINGS["experience"]:
        raise ValueError("Experience heading is locked")
    if resume_content.projects.heading != LOCKED_SECTION_HEADINGS["projects"]:
        raise ValueError("Projects heading is locked")
    if (
        resume_content.skills_achievements.heading
        != LOCKED_SECTION_HEADINGS["skills_achievements"]
    ):
        raise ValueError("Skills and Achievements heading is locked")


def build_locked_section_snapshot(resume_content: ResumeContent) -> str:
    """Build a digest snapshot for non-editable section integrity checks.

    Purpose:
        Create a fast immutable baseline used to detect unauthorized edits to
        personal or education sections during tailoring runs.
    Args:
        resume_content: Parsed canonical resume model to snapshot.
    Output:
        Returns a SHA256 hex digest covering non-editable sections and locks.
    """

    canonical_payload = {
        "lock_rules": resume_content.lock_rules.model_dump(mode="json"),
        "personal": resume_content.personal.model_dump(mode="json"),
        "education": resume_content.education.model_dump(mode="json"),
    }
    payload_text = json.dumps(canonical_payload, sort_keys=True, ensure_ascii=True)
    return sha256(payload_text.encode("utf-8")).hexdigest()


def ensure_locked_sections_unchanged(
    resume_content: ResumeContent,
    *,
    locked_snapshot: str,
) -> None:
    """Ensure personal and education sections match the baseline snapshot.

    Purpose:
        Guard non-editable content so tailoring runs cannot silently mutate
        locked sections even if a model response drifts out of bounds.
    Args:
        resume_content: Parsed resume model to verify.
        locked_snapshot: Snapshot digest from the baseline canonical YAML.
    Output:
        Returns `None` when locked sections are unchanged.
    Raises:
        ValueError: When the current locked-section digest differs from baseline.
    """

    current_snapshot = build_locked_section_snapshot(resume_content)
    if current_snapshot != locked_snapshot:
        raise ValueError(
            "Locked section content changed; personal and education are immutable"
        )
