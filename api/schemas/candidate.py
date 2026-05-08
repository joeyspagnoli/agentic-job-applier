"""Pydantic schemas for the guided candidate-profile settings forms.

These structured payloads back the `/api/settings/profile/structured` and
`/api/settings/resume/structured` endpoints so settings UI submissions are
validated against the same shape that gets persisted as YAML.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

from api.config import COUNTRY_CODE_PATTERN
from api.config import WORK_AUTH_STATUS_UNKNOWN


def _normalize_optional_country_code(value: str) -> str:
    """Normalize one optional ISO alpha-2 country code string.

    Purpose:
        Keep country-code payload values deterministic by uppercasing valid
        alpha-2 values and rejecting malformed non-empty strings.
    Args:
        value: Raw country code value from request payload.
    Output:
        Returns an uppercase alpha-2 code, or an empty string.
    Raises:
        ValueError: When a non-empty value is not a valid alpha-2 code.
    """

    normalized_value = value.strip().upper()
    if normalized_value == "":
        return ""
    if not COUNTRY_CODE_PATTERN.fullmatch(normalized_value):
        raise ValueError("Country code must be a valid ISO alpha-2 code.")
    return normalized_value


class CandidateContactSectionPayload(BaseModel):
    """Structured candidate contact details used by guided settings forms.

    Attributes:
        full_name: Candidate full legal/preferred name.
        email: Primary email used for applications.
        phone: Primary phone number used for applications.
        city: Home city used for location defaults.
        state_or_region: Home state or region for location defaults.
        country_code: ISO alpha-2 home country code.
        country_label: Human-readable home country label.
        linkedin_url: LinkedIn profile URL.
        github_url: GitHub profile URL.
        portfolio_url: Portfolio or personal website URL.
    """

    full_name: str = ""
    email: str = ""
    phone: str = ""
    city: str = ""
    state_or_region: str = ""
    country_code: str = ""
    country_label: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""

    @field_validator("country_code")
    @classmethod
    def validate_country_code(cls, value: str) -> str:
        """Validate and normalize the optional contact country code.

        Purpose:
            Enforce ISO alpha-2 format so downstream ATS mappings can rely on
            a stable country-code representation.
        Args:
            value: Raw country code value for contact settings.
        Output:
            Returns a normalized country code string.
        Raises:
            ValueError: When the submitted code is not empty and not alpha-2.
        """

        return _normalize_optional_country_code(value)


class CandidateWorkAuthorizationSectionPayload(BaseModel):
    """Structured work-authorization details for guided settings forms.

    Attributes:
        citizenship_country_code: ISO alpha-2 citizenship country code.
        citizenship_country_label: Human-readable citizenship country label.
        authorized_to_work_us: Whether candidate can work in the U.S.
        requires_sponsorship_now_or_future: Sponsorship requirement status.
    """

    citizenship_country_code: str = ""
    citizenship_country_label: str = ""
    authorized_to_work_us: Literal["yes", "no", "unknown"] = WORK_AUTH_STATUS_UNKNOWN
    requires_sponsorship_now_or_future: Literal[
        "yes",
        "no",
        "unknown",
    ] = WORK_AUTH_STATUS_UNKNOWN

    @field_validator("citizenship_country_code")
    @classmethod
    def validate_citizenship_country_code(cls, value: str) -> str:
        """Validate and normalize the optional citizenship country code.

        Purpose:
            Keep work-authorization country values aligned with ISO alpha-2
            formatting expected by downstream apply payload mapping.
        Args:
            value: Raw citizenship country code string.
        Output:
            Returns a normalized alpha-2 code string.
        Raises:
            ValueError: When the submitted code is not empty and not alpha-2.
        """

        return _normalize_optional_country_code(value)


class CandidateEducationEntryPayload(BaseModel):
    """Structured education row payload for guided settings forms.

    Attributes:
        id: Stable client-generated row identifier.
        school: Institution name.
        degree_level: Degree level label (for example BS or MS).
        degree_name: Degree title text.
        field_of_study: Primary major or concentration.
        start_month: Education start month value.
        start_year: Education start year value.
        end_month: Education end month value.
        end_year: Education end year value.
        is_current: Whether this education entry is still in progress.
        gpa: Optional GPA text.
        location: Optional education location text.
        highlights: Optional bullet-style highlights.
    """

    id: str = Field(
        min_length=1,
        description="Stable client-generated identifier for one education row.",
    )
    school: str = ""
    degree_level: str = ""
    degree_name: str = ""
    field_of_study: str = ""
    start_month: str = ""
    start_year: str = ""
    end_month: str = ""
    end_year: str = ""
    is_current: bool = False
    gpa: str = ""
    location: str = ""
    highlights: list[str] = Field(default_factory=list)


class CandidateProfileSectionPayload(BaseModel):
    """Structured candidate profile subsection used by guided settings forms.

    Attributes:
        summary: Short candidate summary used in gate prompt context.
        contact: Structured candidate contact details.
        work_authorization: Structured work-authorization details.
        education_summary: High-level education summary line.
        education_entries: Structured list of education rows.
        target_roles: Preferred role titles for matching.
        strongest_areas: Primary technical strengths.
        experience_highlights: Experience highlights for prompt grounding.
        hard_filters: Hard exclusions that should trigger skip behavior.
        preferences: Positive preferences used for gate ranking.
    """

    summary: str = ""
    contact: CandidateContactSectionPayload = Field(
        default_factory=CandidateContactSectionPayload
    )
    work_authorization: CandidateWorkAuthorizationSectionPayload = Field(
        default_factory=CandidateWorkAuthorizationSectionPayload
    )
    education_summary: str = ""
    education_entries: list[CandidateEducationEntryPayload] = Field(
        default_factory=list
    )
    target_roles: list[str] = Field(default_factory=list)
    strongest_areas: list[str] = Field(default_factory=list)
    experience_highlights: list[str] = Field(default_factory=list)
    hard_filters: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_education_entry_ids(self) -> CandidateProfileSectionPayload:
        """Ensure education row identifiers remain unique within one profile.

        Purpose:
            Prevent ambiguous UI updates and backend merges by enforcing stable
            unique IDs for each education entry row.
        Args:
            None.
        Output:
            Returns the validated model instance.
        Raises:
            ValueError: When duplicate education entry IDs are detected.
        """

        entry_ids = [entry.id.strip() for entry in self.education_entries]
        unique_entry_ids = set(entry_ids)
        if len(entry_ids) != len(unique_entry_ids):
            raise ValueError("Education entries must use unique IDs.")
        return self


class CandidateSearchDefaultsPayload(BaseModel):
    """Structured search-default fields used for job-board query defaults.

    Attributes:
        job_board_search_terms: Search term list for discovery polling.
    """

    job_board_search_terms: list[str] = Field(default_factory=list)


class CandidateProfileDocumentPayload(BaseModel):
    """Structured candidate profile document persisted as YAML.

    Attributes:
        profile: Candidate profile section.
        search_defaults: Default search term section.
        prompt_context: Optional full prompt override string.
    """

    model_config = ConfigDict(extra="allow")

    profile: CandidateProfileSectionPayload = Field(
        default_factory=CandidateProfileSectionPayload
    )
    search_defaults: CandidateSearchDefaultsPayload = Field(
        default_factory=CandidateSearchDefaultsPayload
    )
    prompt_context: str | None = None


class ProfileStructuredUpdateRequest(BaseModel):
    """Request payload for guided candidate-profile save operations.

    Attributes:
        profile: Guided profile fields from settings form.
        search_defaults: Guided search defaults from settings form.
        prompt_context: Optional prompt-context override.
    """

    profile: CandidateProfileSectionPayload
    search_defaults: CandidateSearchDefaultsPayload
    prompt_context: str | None = None


class ResumeStructuredUpdateRequest(BaseModel):
    """Request payload for guided resume save operations.

    Attributes:
        resume: Full resume JSON payload to validate and persist as YAML.
    """

    resume: dict[str, object]
