/**
 * @packageDocumentation
 *
 * Shared API response contracts for dashboard-to-backend wiring.
 */

/** Generic API failure payload returned by backend endpoints. */
export interface ApiErrorPayload {
  /** Whether the request succeeded. Always false for this payload shape. */
  readonly ok: false;
  /** Stable machine-readable error code. */
  readonly code: string;
  /** Human-readable error description. */
  readonly message: string;
  /** Optional structured context for debugging/UI details. */
  readonly details: Record<string, unknown>;
}

/** Response payload for system lifecycle action endpoints. */
export interface SystemLifecycleActionDto {
  readonly ok: true;
  readonly action: "stop" | "restart" | "fetch_jobs";
  readonly status: "accepted";
  readonly request_id: string;
}

/** One source breakdown row returned by dashboard stats endpoint. */
export interface SourceBreakdownDto {
  readonly source: string;
  readonly count: number;
  readonly pct: number;
}

/** One pipeline funnel row returned by dashboard stats endpoint. */
export interface PipelineFunnelDto {
  readonly stage: string;
  readonly count: number;
}

/** One applications-over-time point returned by dashboard stats endpoint. */
export interface ApplicationsOverTimeDto {
  readonly label: string;
  readonly applied: number;
  readonly tailored: number;
}

/** Response payload for `GET /api/dashboard/stats`. */
export interface DashboardStatsDto {
  readonly ok: true;
  readonly jobs_discovered_total: number;
  readonly jobs_discovered_today: number;
  readonly resumes_tailored_total: number;
  readonly resumes_tailored_today: number;
  readonly applications_sent_total: number;
  readonly applications_sent_today: number;
  readonly awaiting_review_total: number;
  readonly source_breakdown: readonly SourceBreakdownDto[];
  readonly pipeline_funnel: readonly PipelineFunnelDto[];
  readonly applications_over_time: readonly ApplicationsOverTimeDto[];
}

/** One discovery trend point from `GET /api/dashboard/discovery-trend`. */
export interface DiscoveryTrendPointDto {
  readonly label: string;
  readonly date: string;
  readonly count: number;
}

/** Response payload for `GET /api/dashboard/discovery-trend`. */
export interface DiscoveryTrendDto {
  readonly ok: true;
  readonly range: "7d" | "30d";
  readonly points: readonly DiscoveryTrendPointDto[];
}

/** One timeline step row in jobs endpoint payload. */
export interface PipelineStepDto {
  readonly label: string;
  readonly status: string;
}

/** Embedded tailor-run snapshot attached to each jobs row. */
export interface TailorRunSummaryDto {
  readonly id: number;
  readonly status: string;
  readonly verdict: string | null;
  readonly page_count: number | null;
  readonly error: string | null;
  readonly pdf_url: string | null;
}

/** One jobs table item row returned by backend. */
export interface JobsItemDto {
  readonly id: number;
  readonly job_hash: string;
  readonly company: string;
  readonly position: string;
  readonly location: string;
  readonly pay: string;
  readonly work_type: string;
  readonly source: string;
  readonly status: string;
  readonly discovered: string;
  readonly pipeline: readonly PipelineStepDto[];
  readonly gate_verdict: string;
  readonly gate_reasoning: string;
  readonly tailored_resume: string | null;
  readonly job_posting_url: string;
  readonly tailor_run: TailorRunSummaryDto | null;
}

/** Response payload for `POST /api/jobs/{job_hash}/tailor`. */
export interface EnqueueTailorRunResponseDto {
  readonly ok: true;
  readonly tailor_run_id: number;
  readonly status: string;
  readonly job_hash: string;
}

/** Response payload for `GET /api/tailor-runs/{id}`. */
export interface TailorRunDetailDto {
  readonly ok: true;
  readonly tailor_run: {
    readonly id: number;
    readonly job_hash: string;
    readonly status: string;
    readonly page_count: number | null;
    readonly error: string | null;
    readonly started_at: string;
    readonly completed_at: string | null;
    readonly deleted_at: string | null;
    readonly pdf_url: string | null;
  };
}

/** Allowed automation modes for the tailor stage. */
export type AutomationMode = "autonomous" | "opt_in" | "both";

/** Response payload for `GET /api/system-settings/automation`. */
export interface AutomationSettingsDto {
  readonly ok: true;
  readonly tailor_mode: AutomationMode;
}

/** Paginated jobs endpoint response. */
export interface JobsResponseDto {
  readonly ok: true;
  readonly page: number;
  readonly page_size: number;
  readonly total_items: number;
  readonly total_pages: number;
  readonly items: readonly JobsItemDto[];
}

/** One unresolved field recommendation row in review queue. */
export interface UnresolvedFieldDto {
  readonly field_name: string;
  readonly ai_answer: string;
  readonly reasoning: string;
  readonly answer_confidence: string;
}

/** One row in human-review queue endpoint response. */
export interface HumanReviewItemDto {
  readonly id: number;
  readonly company_name: string;
  readonly position: string;
  readonly status: string;
  readonly confidence_pct: number;
  readonly applied_date: string;
  readonly agent_diagnostic: string;
  readonly job_posting_url: string;
  readonly resume_file_name: string;
  readonly unresolved_fields: readonly UnresolvedFieldDto[];
}

/** Paginated human-review endpoint response. */
export interface HumanReviewResponseDto {
  readonly ok: true;
  readonly page: number;
  readonly page_size: number;
  readonly total_items: number;
  readonly total_pages: number;
  readonly items: readonly HumanReviewItemDto[];
}

/** One row in unified failures endpoint payload. */
export interface FailureItemDto {
  readonly id: string;
  readonly stage: string;
  readonly company: string;
  readonly position: string;
  readonly error_code: string;
  readonly attempts: number;
  readonly max_attempts: number;
  readonly time: string;
  readonly status: string;
  readonly error_trace: readonly string[];
  readonly platform: string;
  readonly job_posting_url: string;
}

/** Failure-summary subsection returned by failures endpoint. */
export interface FailureSummaryDto {
  readonly total_failures: number;
  readonly last_24_hours: number;
  readonly most_failing_stage: {
    readonly stage: string;
    readonly count: number;
  };
  readonly retry_success_rate_pct: number;
}

/** Paginated failures endpoint response. */
export interface FailuresResponseDto {
  readonly ok: true;
  readonly summary: FailureSummaryDto;
  readonly page: number;
  readonly page_size: number;
  readonly total_items: number;
  readonly total_pages: number;
  readonly items: readonly FailureItemDto[];
}

/** Cost stats response for top cards on cost-tracking page. */
export interface CostStatsDto {
  readonly ok: true;
  readonly total_spend_usd: number;
  readonly avg_cost_per_application_usd: number;
  readonly api_calls_today: number;
}

/** One point in cost daily trend endpoint response. */
export interface CostDailyTrendPointDto {
  readonly label: string;
  readonly date?: string;
  readonly spend_usd: number;
}

/** Response payload for cost daily trend endpoint. */
export interface CostDailyTrendDto {
  readonly ok: true;
  readonly range: "7d" | "30d" | "all";
  readonly points: readonly CostDailyTrendPointDto[];
}

/** One stage row from cost-by-stage endpoint. */
export interface CostByStageItemDto {
  readonly stage: string;
  readonly spend_usd: number;
}

/** Response payload for cost-by-stage endpoint. */
export interface CostByStageDto {
  readonly ok: true;
  readonly items: readonly CostByStageItemDto[];
}

/** Budget response payload used by settings and sidebar budget widgets. */
export interface BudgetDto {
  readonly ok: true;
  readonly monthly_budget_usd: number;
  readonly spent_usd: number;
  readonly remaining_usd: number;
  readonly utilization_pct: number;
}

/** Supported environment-backed API key names shown in settings UI. */
export type ApiKeyNameDto =
  | "OPENAI_API_KEY"
  | "GOOGLE_API_KEY"
  | "ANTHROPIC_API_KEY"
  | "ADZUNA_APP_ID"
  | "ADZUNA_APP_KEY";

/** One API key status row for write-only key management UI. */
export interface ApiKeyStatusDto {
  readonly name: ApiKeyNameDto;
  readonly configured: boolean;
}

/** Response payload for API key status endpoint. */
export interface ApiKeysResponseDto {
  readonly ok: true;
  readonly keys: readonly ApiKeyStatusDto[];
}

/** Supported service tier identifiers for pipeline depth controls. */
export type ServiceTierDto = "base" | "latex" | "full";

/** Response payload for service tier read/write endpoints. */
export interface ServiceTierResponseDto {
  readonly ok: true;
  readonly tier: ServiceTierDto;
}

/** File metadata for settings-managed YAML files. */
export interface SettingsFileMetadataDto {
  readonly filename: string;
  readonly path: string;
  readonly exists: boolean;
  readonly size_bytes: number;
  readonly modified_at: string | null;
}

/** Response payload for settings file metadata endpoint. */
export interface SettingsFilesDto {
  readonly ok: true;
  readonly resume: SettingsFileMetadataDto;
  readonly profile: SettingsFileMetadataDto;
}

/** Response payload for resume upload endpoint. */
export interface SettingsResumeUploadDto {
  readonly ok: true;
  readonly resume: SettingsFileMetadataDto;
}

/** Response payload for profile upload endpoint. */
export interface SettingsProfileUploadDto {
  readonly ok: true;
  readonly profile: SettingsFileMetadataDto;
}

/** Structured candidate profile fields used by guided settings forms. */
export interface CandidateContactSectionDto {
  readonly full_name: string;
  readonly email: string;
  readonly phone: string;
  readonly city: string;
  readonly state_or_region: string;
  readonly country_code: string;
  readonly country_label: string;
  readonly linkedin_url: string;
  readonly github_url: string;
  readonly portfolio_url: string;
}

/** Structured work-authorization fields used by guided settings forms. */
export interface CandidateWorkAuthorizationSectionDto {
  readonly citizenship_country_code: string;
  readonly citizenship_country_label: string;
  readonly authorized_to_work_us: "yes" | "no" | "unknown";
  readonly requires_sponsorship_now_or_future: "yes" | "no" | "unknown";
}

/** Structured education row used by guided settings forms. */
export interface CandidateEducationEntryDto {
  readonly id: string;
  readonly school: string;
  readonly degree_level: string;
  readonly degree_name: string;
  readonly field_of_study: string;
  readonly start_month: string;
  readonly start_year: string;
  readonly end_month: string;
  readonly end_year: string;
  readonly is_current: boolean;
  readonly gpa: string;
  readonly location: string;
  readonly highlights: readonly string[];
}

/** Structured candidate profile fields used by guided settings forms. */
export interface CandidateProfileSectionDto {
  readonly summary: string;
  readonly contact: CandidateContactSectionDto;
  readonly work_authorization: CandidateWorkAuthorizationSectionDto;
  readonly education_summary: string;
  readonly education_entries: readonly CandidateEducationEntryDto[];
  readonly target_roles: readonly string[];
  readonly strongest_areas: readonly string[];
  readonly experience_highlights: readonly string[];
  readonly hard_filters: readonly string[];
  readonly preferences: readonly string[];
}

/** Search defaults subsection for candidate profile settings. */
export interface CandidateSearchDefaultsDto {
  readonly job_board_search_terms: readonly string[];
}

/** Candidate profile settings response payload. */
export interface SettingsProfileDto {
  readonly ok: true;
  readonly metadata: SettingsFileMetadataDto;
  readonly yaml_text: string;
  readonly profile: CandidateProfileSectionDto;
  readonly search_defaults: CandidateSearchDefaultsDto;
  readonly prompt_context: string | null;
}

/** Resume link entry for personal section. */
export interface ResumeLinkDto {
  readonly id: string;
  readonly label: string;
  readonly url: string;
}

/** Resume bullet row shared by entries and listings. */
export interface ResumeBulletDto {
  readonly id: string;
  readonly text: string;
}

/** Locked personal section payload. */
export interface ResumePersonalSectionDto {
  readonly section_id: "personal";
  readonly name: string;
  readonly phone: string;
  readonly email: string;
  readonly links: readonly ResumeLinkDto[];
}

/** Locked education entry payload. */
export interface ResumeEducationEntryDto {
  readonly id: string;
  readonly institution: string;
  readonly date_range: string;
  readonly degree: string;
  readonly detail: string;
  readonly bullets: readonly ResumeBulletDto[];
}

/** Locked education section payload. */
export interface ResumeEducationSectionDto {
  readonly section_id: "education";
  readonly heading: string;
  readonly entries: readonly ResumeEducationEntryDto[];
}

/** Editable experience listing row. */
export interface ResumeExperienceListingDto {
  readonly id: string;
  readonly enabled: boolean;
  readonly title: string;
  readonly date_range: string;
  readonly organization: string;
  readonly bullets: readonly ResumeBulletDto[];
}

/** Editable experience section payload. */
export interface ResumeExperienceSectionDto {
  readonly section_id: "experience";
  readonly heading: string;
  readonly listings: readonly ResumeExperienceListingDto[];
}

/** Editable project listing row. */
export interface ResumeProjectListingDto {
  readonly id: string;
  readonly enabled: boolean;
  readonly title: string;
  readonly tech_stack: string;
  readonly date_range: string;
  readonly bullets: readonly ResumeBulletDto[];
}

/** Editable projects section payload. */
export interface ResumeProjectsSectionDto {
  readonly section_id: "projects";
  readonly heading: string;
  readonly listings: readonly ResumeProjectListingDto[];
}

/** Editable skills row payload. */
export interface ResumeSkillListingDto {
  readonly id: string;
  readonly enabled: boolean;
  readonly category: string;
  readonly text: string;
}

/** Editable skills and achievements section payload. */
export interface ResumeSkillsAchievementsSectionDto {
  readonly section_id: "skills_achievements";
  readonly heading: string;
  readonly listings: readonly ResumeSkillListingDto[];
}

/** Resume layout knobs payload. */
export interface ResumeLayoutDto {
  readonly margin_in: number;
  readonly top_vspace_in: number;
  readonly section_heading_font_size_pt: number;
  readonly section_heading_line_height_pt: number;
  readonly section_spacing_before_pt: number;
  readonly section_spacing_after_pt: number;
  readonly subheading_itemsep_pt: number;
  readonly bullet_itemsep_pt: number;
}

/** Resume lock rules payload. */
export interface ResumeLockRulesDto {
  readonly section_order: readonly string[];
  readonly section_headings: Record<string, string>;
  readonly non_editable_sections: readonly string[];
}

/** Full canonical resume payload used by structured settings APIs. */
export interface ResumeContentDto {
  readonly schema_version: number;
  readonly lock_rules: ResumeLockRulesDto;
  readonly layout: ResumeLayoutDto;
  readonly personal: ResumePersonalSectionDto;
  readonly education: ResumeEducationSectionDto;
  readonly experience: ResumeExperienceSectionDto;
  readonly projects: ResumeProjectsSectionDto;
  readonly skills_achievements: ResumeSkillsAchievementsSectionDto;
}

/** Resume section counts returned with read/write settings responses. */
export interface ResumeCountsDto {
  readonly education_entries: number;
  readonly experience_listings: number;
  readonly project_listings: number;
  readonly skill_rows: number;
}

/** Resume settings response payload. */
export interface SettingsResumeDto {
  readonly ok: true;
  readonly metadata: SettingsFileMetadataDto;
  readonly yaml_text: string;
  readonly resume: ResumeContentDto;
  readonly counts: ResumeCountsDto;
}

/** Resume TeX conversion summary returned after migration upload. */
export interface ResumeTexMigrationDto {
  readonly source_tex_path: string;
  readonly output_yaml_path: string;
  readonly normalized_input: boolean;
  readonly education_entries: number;
  readonly experience_listings: number;
  readonly project_listings: number;
  readonly skill_rows: number;
}

/** Resume TeX upload response payload. */
export interface SettingsResumeTexUploadDto extends SettingsResumeDto {
  readonly migration: ResumeTexMigrationDto;
}

/** Mutation response payload for retry endpoint. */
export interface RetryFailureDto {
  readonly ok: true;
  readonly failure_id: string;
  readonly requeued: boolean;
  readonly deleted_failures?: number;
}

/** Mutation response payload for review actions. */
export interface HandoffMutationDto {
  readonly ok: true;
  readonly handoff: Record<string, unknown>;
}
