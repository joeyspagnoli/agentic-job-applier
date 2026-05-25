"""Pydantic v2 schema for candidate_profile.yaml validation.

This module provides a strict structural validator for the candidate profile
YAML file consumed by the auto-apply finisher and gate agents. It is loaded
at API startup to surface misconfiguration loudly with actionable error output
rather than failing silently mid-run.
"""

from __future__ import annotations

from typing import Annotated
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


# ── EEO / application defaults ────────────────────────────────────────────────


class EeoDefaults(BaseModel):
    """Default EEO demographic answers pre-filled on every application form.

    Attributes:
        gender: Default gender identity answer.
        race_ethnicity: Default race/ethnicity answer.
        veteran_status: Default veteran-status answer.
        disability_status: Default disability-status answer.
    """

    model_config = ConfigDict(extra="allow")

    gender: str = "prefer_not_to_say"
    race_ethnicity: str = "prefer_not_to_say"
    veteran_status: str = "prefer_not_to_say"
    disability_status: str = "prefer_not_to_say"


class CompensationPrefs(BaseModel):
    """Salary and hourly-rate expectations for application auto-fill.

    Attributes:
        expected_salary_min_usd: Minimum acceptable annual salary in USD.
        expected_salary_max_usd: Maximum acceptable annual salary in USD.
        expected_hourly_rate_usd: Expected hourly rate in USD for contract roles.
    """

    model_config = ConfigDict(extra="allow")

    expected_salary_min_usd: int | None = None
    expected_salary_max_usd: int | None = None
    expected_hourly_rate_usd: int | None = None


class AvailabilityPrefs(BaseModel):
    """Start-date and notice-period availability for application auto-fill.

    Attributes:
        earliest_start_date: ISO date string or ``"flexible"``.
        notice_period_weeks: Notice period in weeks, or ``None`` when not applicable.
    """

    model_config = ConfigDict(extra="allow")

    earliest_start_date: str = "flexible"
    notice_period_weeks: int | None = None


class LocationPrefs(BaseModel):
    """Geographic relocation and remote-work preferences.

    Attributes:
        willing_to_relocate: Whether the candidate will relocate for the role.
        preferred_cities: Ordered list of preferred work cities.
        willing_remote: Whether the candidate accepts fully-remote roles.
        willing_hybrid: Whether the candidate accepts hybrid roles.
    """

    model_config = ConfigDict(extra="allow")

    willing_to_relocate: bool = False
    preferred_cities: list[str] = Field(default_factory=list)
    willing_remote: bool = True
    willing_hybrid: bool = True


class ApplicationDefaults(BaseModel):
    """Application-level defaults used by the auto-apply finisher.

    Attributes:
        how_did_you_hear: Pre-filled answer for "how did you hear about us?"
            fields on application forms.
        tier2_confidence_threshold: Confidence threshold (0.0–1.0) above which
            the finisher submits tier-2 auto-answers without human review.
            Defaults to ``1.0`` (only fully-certain answers are auto-submitted).
    """

    model_config = ConfigDict(extra="allow")

    how_did_you_hear: str = ""
    tier2_confidence_threshold: Annotated[
        float, Field(ge=0.0, le=1.0)
    ] = 1.0


class LanguageEntry(BaseModel):
    """One language proficiency entry.

    Attributes:
        language: Name of the language.
        proficiency: Self-assessed proficiency level.
    """

    model_config = ConfigDict(extra="allow")

    language: str
    proficiency: Literal["basic", "conversational", "fluent", "native"] = "conversational"


class ApplyPrefs(BaseModel):
    """Apply-preferences block consumed by the auto-apply finisher agent.

    Attributes:
        pronouns: Candidate pronouns string (e.g. ``"he/him"``).
        eeo_defaults: Default EEO demographic answers.
        sponsorship_required_now_or_future: Whether the candidate requires
            visa sponsorship now or in the future.
        work_authorized_us: Whether the candidate is authorized to work in
            the United States.
        compensation: Salary and hourly-rate expectations.
        availability: Start-date and notice-period availability.
        location_preferences: Geographic and remote-work preferences.
        application_defaults: Application-level finisher defaults.
        languages: Ordered list of language proficiency entries.
    """

    model_config = ConfigDict(extra="allow")

    pronouns: str = ""
    eeo_defaults: EeoDefaults = Field(default_factory=EeoDefaults)
    sponsorship_required_now_or_future: Literal["yes", "no", "unknown"] = "unknown"
    work_authorized_us: Literal["yes", "no", "unknown"] = "unknown"
    compensation: CompensationPrefs = Field(default_factory=CompensationPrefs)
    availability: AvailabilityPrefs = Field(default_factory=AvailabilityPrefs)
    location_preferences: LocationPrefs = Field(default_factory=LocationPrefs)
    application_defaults: ApplicationDefaults = Field(default_factory=ApplicationDefaults)
    languages: list[LanguageEntry] = Field(default_factory=list)


# ── Existing profile sub-models (minimal — enough for startup validation) ────


class ContactSection(BaseModel):
    """Candidate contact details.

    Attributes:
        full_name: Candidate full legal/preferred name.
        email: Primary email address.
        phone: Primary phone number.
        city: Home city.
        state_or_region: Home state or region.
        country_code: ISO alpha-2 country code.
        country_label: Human-readable country label.
        linkedin_url: LinkedIn profile URL.
        github_url: GitHub profile URL.
        portfolio_url: Portfolio or personal website URL.
    """

    model_config = ConfigDict(extra="allow")

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


class WorkAuthorizationSection(BaseModel):
    """Work-authorization details for the profile.

    Attributes:
        citizenship_country_code: ISO alpha-2 citizenship country code.
        citizenship_country_label: Human-readable citizenship country label.
        authorized_to_work_us: Whether candidate can work in the U.S.
        requires_sponsorship_now_or_future: Sponsorship requirement status.
    """

    model_config = ConfigDict(extra="allow")

    citizenship_country_code: str = ""
    citizenship_country_label: str = ""
    authorized_to_work_us: Literal["yes", "no", "unknown"] = "unknown"
    requires_sponsorship_now_or_future: Literal["yes", "no", "unknown"] = "unknown"


class ProfileSection(BaseModel):
    """Candidate profile section of the YAML document.

    Attributes:
        summary: Short candidate summary.
        contact: Structured contact details.
        work_authorization: Work-authorization details.
        education_summary: High-level education summary.
        education_entries: Structured education rows.
        target_roles: Preferred role titles.
        strongest_areas: Primary technical strengths.
        experience_highlights: Experience highlights.
        hard_filters: Hard-exclusion title patterns.
        preferences: Positive preferences for ranking.
    """

    model_config = ConfigDict(extra="allow")

    summary: str = ""
    contact: ContactSection = Field(default_factory=ContactSection)
    work_authorization: WorkAuthorizationSection = Field(
        default_factory=WorkAuthorizationSection
    )
    education_summary: str = ""
    education_entries: list[object] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    strongest_areas: list[str] = Field(default_factory=list)
    experience_highlights: list[str] = Field(default_factory=list)
    hard_filters: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)


class SearchDefaultsSection(BaseModel):
    """Search defaults for job-board discovery queries.

    Attributes:
        job_board_search_terms: Query terms sent to job boards during discovery.
    """

    model_config = ConfigDict(extra="allow")

    job_board_search_terms: list[str] = Field(default_factory=list)


class CandidateProfile(BaseModel):
    """Top-level candidate_profile.yaml document model.

    Purpose:
        Validate the full candidate profile YAML at API startup so
        misconfiguration is surfaced loudly with actionable error output
        rather than failing silently mid-run.

    Attributes:
        profile: Candidate profile section.
        search_defaults: Job-board search default settings.
        apply_prefs: Auto-apply finisher preferences and EEO defaults.
    """

    model_config = ConfigDict(extra="allow")

    profile: ProfileSection = Field(default_factory=ProfileSection)
    search_defaults: SearchDefaultsSection = Field(
        default_factory=SearchDefaultsSection
    )
    apply_prefs: ApplyPrefs = Field(default_factory=ApplyPrefs)
