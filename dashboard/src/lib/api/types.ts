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
