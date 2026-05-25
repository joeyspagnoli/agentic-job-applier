/**
 * @packageDocumentation
 *
 * Typed API client helpers for dashboard-to-backend communication.
 */

import type {
  ApiErrorPayload,
  ApiKeyNameDto,
  ApiKeysResponseDto,
  ApplyRunDto,
  AutomationMode,
  AutomationSettingsDto,
  BudgetDto,
  CostByStageDto,
  ChromeStatusDto,
  ChromeStatusOsHint,
  CostDailyTrendDto,
  CostStatsDto,
  DashboardStatsDto,
  DiscoveryTrendDto,
  EnqueueApplyRunResponseDto,
  EnqueueTailorRunResponseDto,
  RetryTailorRunResponseDto,
  FailuresResponseDto,
  HandoffMutationDto,
  HumanReviewResponseDto,
  JobsResponseDto,
  RetryFailureDto,
  ResumeContentDto,
  SettingsFilesDto,
  SettingsProfileDto,
  SettingsProfileUploadDto,
  SettingsResumeDto,
  SettingsResumeTexUploadDto,
  SettingsResumeUploadDto,
  SystemLifecycleActionDto,
  TailorRunDetailDto,
  TailorRunPlanDto,
} from "@/lib/api/types";

const JSON_HEADERS = {
  "Content-Type": "application/json",
} as const;

/** Union type for all standardized API failures. */
type ApiError = Error & {
  code: string;
  details: Record<string, unknown>;
};

const INVALID_RESPONSE_CODE = "INVALID_RESPONSE_FORMAT";
const EMPTY_RESPONSE_CODE = "EMPTY_RESPONSE_BODY";

/**
 * Build one normalized API error object for transport and parsing failures.
 *
 * @param message - Human-readable error message.
 * @param code - Stable machine-readable error code.
 * @param details - Optional structured details payload.
 * @returns Typed API error instance.
 */
function buildApiError(
  message: string,
  code: string,
  details: Record<string, unknown> = {},
): ApiError {
  const error = new Error(message) as ApiError;
  error.code = code;
  error.details = details;
  return error;
}

/**
 * Parse and throw typed API errors for non-2xx responses.
 *
 * @param response - Fetch response object.
 * @throws Error with API error fields when request fails.
 */
async function throwIfError(response: Response): Promise<void> {
  if (response.ok) {
    return;
  }

  let payload: ApiErrorPayload | null = null;
  try {
    payload = (await response.json()) as ApiErrorPayload;
  } catch {
    payload = null;
  }

  const error = new Error(payload?.message ?? response.statusText) as ApiError;
  error.code = payload?.code ?? "HTTP_ERROR";
  error.details = payload?.details ?? {};
  throw error;
}

/**
 * Fetch JSON and return a typed payload.
 *
 * @typeParam T - Expected response payload shape.
 * @param url - Endpoint URL.
 * @param init - Optional fetch init options.
 * @returns Parsed JSON payload.
 */
async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  await throwIfError(response);

  const responseText = await response.text();
  if (responseText.trim() === "") {
    throw buildApiError("Successful response returned an empty body.", EMPTY_RESPONSE_CODE, {
      url,
      status: response.status,
    });
  }

  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (!contentType.includes("application/json")) {
    throw buildApiError("Successful response did not return JSON content.", INVALID_RESPONSE_CODE, {
      url,
      status: response.status,
      contentType,
    });
  }

  try {
    return JSON.parse(responseText) as T;
  } catch (error: unknown) {
    throw buildApiError("Successful response body was not valid JSON.", INVALID_RESPONSE_CODE, {
      url,
      status: response.status,
      error: error instanceof Error ? error.message : "unknown",
    });
  }
}

/**
 * Request dashboard stats payload.
 *
 * @returns Dashboard stats DTO.
 */
export async function fetchDashboardStats(): Promise<DashboardStatsDto> {
  return getJson<DashboardStatsDto>("/api/dashboard/stats");
}

/**
 * Request discovery trend payload.
 *
 * @param range - Dashboard trend range.
 * @returns Discovery trend DTO.
 */
export async function fetchDiscoveryTrend(range: "7d" | "30d"): Promise<DiscoveryTrendDto> {
  const params = new URLSearchParams({ range });
  return getJson<DiscoveryTrendDto>(`/api/dashboard/discovery-trend?${params.toString()}`);
}

/**
 * Request paginated jobs payload.
 *
 * @param args - Jobs list query options.
 * @returns Paginated jobs DTO.
 */
export async function fetchJobs(args: {
  readonly search: string;
  readonly page: number;
  readonly pageSize: number;
  readonly status?: string;
  readonly source?: string;
  readonly hasTailorRun?: boolean;
  readonly tailorState?: string;
}): Promise<JobsResponseDto> {
  const params = new URLSearchParams({
    search: args.search,
    page: String(args.page),
    page_size: String(args.pageSize),
  });
  if (args.status && args.status !== "") {
    params.set("status", args.status);
  }
  if (args.source && args.source !== "") {
    params.set("source", args.source);
  }
  if (args.hasTailorRun === true) {
    params.set("has_tailor_run", "1");
  }
  if (args.tailorState && args.tailorState !== "") {
    params.set("tailor_state", args.tailorState);
  }
  return getJson<JobsResponseDto>(`/api/jobs?${params.toString()}`);
}

/**
 * Enqueue a user-triggered tailor run for one job.
 *
 * @param jobHash - Stable deduplication hash of the target job.
 * @returns Enqueue response with the new tailor_run_id.
 */
export async function enqueueTailorRun(
  jobHash: string,
): Promise<EnqueueTailorRunResponseDto> {
  const response = await fetch(`/api/jobs/${encodeURIComponent(jobHash)}/tailor`, {
    method: "POST",
    headers: JSON_HEADERS,
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as ApiErrorPayload | null;
    throw buildApiError(
      payload?.message ?? `Tailor enqueue failed (HTTP ${response.status})`,
      payload?.code ?? "TAILOR_ENQUEUE_FAILED",
      (payload?.details as Record<string, unknown> | undefined) ?? {},
    );
  }
  return (await response.json()) as EnqueueTailorRunResponseDto;
}

/**
 * Fetch the current state of one tailor run.
 *
 * @param runId - Primary key of the tailor_runs row.
 * @returns Tailor run detail payload.
 */
export async function fetchTailorRun(runId: number): Promise<TailorRunDetailDto> {
  return getJson<TailorRunDetailDto>(`/api/tailor-runs/${runId}`);
}

/**
 * Fetch the persisted planner-rationale JSON for one tailor run.
 *
 * @param runId - Primary key of the tailor_runs row.
 * @returns The planner artifact wrapped in `{ ok, plan }`.
 */
export async function fetchTailorRunPlan(
  runId: number,
): Promise<TailorRunPlanDto> {
  return getJson<TailorRunPlanDto>(`/api/tailor-runs/${runId}/plan`);
}

/**
 * Soft-delete one tailor run.
 *
 * @param runId - Primary key of the tailor_runs row.
 */
export async function deleteTailorRun(runId: number): Promise<void> {
  const response = await fetch(`/api/tailor-runs/${runId}`, { method: "DELETE" });
  if (!response.ok && response.status !== 204) {
    const payload = (await response.json().catch(() => null)) as ApiErrorPayload | null;
    throw buildApiError(
      payload?.message ?? `Tailor delete failed (HTTP ${response.status})`,
      payload?.code ?? "TAILOR_DELETE_FAILED",
      (payload?.details as Record<string, unknown> | undefined) ?? {},
    );
  }
}

/**
 * Atomically soft-delete one tailor run and trigger a fresh attempt.
 *
 * @remarks
 * Replaces the prior "delete then enqueue" sequence that the FAILED and
 * SUCCESS-non-TAILORED branches of `TailoredResumeCell` used to fire
 * from the client. The server picks the right strategy based on the
 * tailor automation mode — see {@link RetryTailorRunResponseDto}.
 *
 * @param runId - Primary key of the tailor_runs row to retry.
 * @returns Retry response keyed by `retry_via`.
 */
export async function retryTailorRun(
  runId: number,
): Promise<RetryTailorRunResponseDto> {
  const response = await fetch(`/api/tailor-runs/${runId}/retry`, {
    method: "POST",
    headers: JSON_HEADERS,
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as ApiErrorPayload | null;
    throw buildApiError(
      payload?.message ?? `Tailor retry failed (HTTP ${response.status})`,
      payload?.code ?? "TAILOR_RETRY_FAILED",
      (payload?.details as Record<string, unknown> | undefined) ?? {},
    );
  }
  return (await response.json()) as RetryTailorRunResponseDto;
}

/**
 * Fetch the current automation modes.
 *
 * @returns Automation settings payload.
 */
export async function fetchAutomationSettings(): Promise<AutomationSettingsDto> {
  return getJson<AutomationSettingsDto>("/api/system-settings/automation");
}

/**
 * Persist a new tailor automation mode.
 *
 * @param patch - Optional new mode for the tailor stage.
 * @returns Updated automation settings payload.
 */
export async function patchAutomationSettings(patch: {
  readonly tailor_mode?: AutomationMode;
}): Promise<AutomationSettingsDto> {
  const response = await fetch("/api/system-settings/automation", {
    method: "PATCH",
    headers: JSON_HEADERS,
    body: JSON.stringify(patch),
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as ApiErrorPayload | null;
    throw buildApiError(
      payload?.message ?? `Automation update failed (HTTP ${response.status})`,
      payload?.code ?? "AUTOMATION_UPDATE_FAILED",
      (payload?.details as Record<string, unknown> | undefined) ?? {},
    );
  }
  return (await response.json()) as AutomationSettingsDto;
}

/**
 * Request paginated human-review queue payload.
 *
 * @param args - Review queue query options.
 * @returns Paginated human-review DTO.
 */
export async function fetchHumanReviewQueue(args: {
  readonly search: string;
  readonly page: number;
  readonly pageSize: number;
  readonly status?: string;
}): Promise<HumanReviewResponseDto> {
  const params = new URLSearchParams({
    search: args.search,
    page: String(args.page),
    page_size: String(args.pageSize),
  });
  if (args.status && args.status !== "") {
    params.set("status", args.status);
  }
  return getJson<HumanReviewResponseDto>(`/api/human-review?${params.toString()}`);
}

/**
 * Mark one review handoff complete.
 *
 * @param handoffId - Handoff identifier.
 * @param reviewerNotes - Optional reviewer note text.
 * @returns Mutation response payload.
 */
export async function completeHumanReview(
  handoffId: number,
  reviewerNotes?: string,
): Promise<HandoffMutationDto> {
  return getJson<HandoffMutationDto>(`/api/human-review/${handoffId}/complete`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ reviewer_notes: reviewerNotes ?? null }),
  });
}

/**
 * Dismiss one review handoff.
 *
 * @param handoffId - Handoff identifier.
 * @param reviewerNotes - Optional reviewer note text.
 * @returns Mutation response payload.
 */
export async function dismissHumanReview(
  handoffId: number,
  reviewerNotes?: string,
): Promise<HandoffMutationDto> {
  return getJson<HandoffMutationDto>(`/api/human-review/${handoffId}/dismiss`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ reviewer_notes: reviewerNotes ?? null }),
  });
}

/**
 * Persist reviewer-typed answers for one handoff's deferred questions.
 *
 * @param handoffId - Handoff identifier.
 * @param answers - Array of `{field_id, answer}` entries. The list
 *   replaces any previously-stored answers wholesale.
 * @returns Mutation response payload containing the persisted answers.
 */
/**
 * Re-enqueue an apply for a PENDING_REVIEW handoff (Bug G, 2026-05-25).
 *
 * @param handoffId - Primary key of the ``apply_handoffs`` row to
 *   relaunch from. The backend inserts a fresh PENDING apply_runs row,
 *   flips the old handoff to APPROVED with a "Relaunched" reviewer note,
 *   and immediately spawns the user-triggered apply task.
 * @returns ``{ok, apply_run_id, status, job_hash}`` so the dashboard
 *   can show "Apply queued (run #N)".
 */
export async function relaunchHumanReviewApply(
  handoffId: number,
): Promise<{
  readonly ok: true;
  readonly apply_run_id: number;
  readonly status: string;
  readonly job_hash: string;
}> {
  return getJson(`/api/human-review/${handoffId}/relaunch-apply`, {
    method: "POST",
    headers: JSON_HEADERS,
  });
}

/**
 * JobsPage-side relaunch wrapper keyed by job hash (Bug G, 2026-05-25).
 *
 * @param jobHash - Stable job identifier from the JobsPage row. The
 *   backend resolves the most-recent PENDING_REVIEW handoff for this
 *   job and delegates to the same internal logic
 *   ``relaunchHumanReviewApply`` triggers.
 * @returns Same shape as the handoff-keyed variant, plus the resolved
 *   ``handoff_id`` for diagnostics.
 */
export async function relaunchApplyByJobHash(
  jobHash: string,
): Promise<{
  readonly ok: true;
  readonly apply_run_id: number;
  readonly status: string;
  readonly job_hash: string;
  readonly handoff_id: number;
}> {
  return getJson(`/api/human-review/by-job/${jobHash}/relaunch-apply`, {
    method: "POST",
    headers: JSON_HEADERS,
  });
}

export async function saveHumanReviewAnswers(
  handoffId: number,
  answers: readonly { readonly field_id: string; readonly answer: string }[],
): Promise<{
  readonly ok: true;
  readonly user_answers: readonly {
    readonly field_id: string;
    readonly answer: string;
  }[];
  /**
   * Per-entry summary of what the API appended to ``data/answer_cache.yaml``
   * (Bug F, 2026-05-25). Each row carries the ``field_id`` plus either a
   * ``skipped`` reason or the resolved ``label`` + ``company_specific``
   * flag. The dashboard does not surface this today but reads it during
   * RTL tests so cache-seeding regressions are visible.
   */
  readonly cache_seeded: readonly {
    readonly field_id: string;
    readonly label?: string;
    readonly company_specific?: boolean;
    readonly skipped?: string;
  }[];
}> {
  return getJson(`/api/human-review/${handoffId}/answers`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ answers }),
  });
}

/**
 * Request unified failures payload.
 *
 * @param args - Failures query options.
 * @returns Paginated failures DTO.
 */
export async function fetchFailures(args: {
  readonly search: string;
  readonly page: number;
  readonly pageSize: number;
  readonly stage?: string;
  readonly status?: string;
}): Promise<FailuresResponseDto> {
  const params = new URLSearchParams({
    search: args.search,
    page: String(args.page),
    page_size: String(args.pageSize),
  });
  if (args.stage && args.stage !== "") {
    params.set("stage", args.stage);
  }
  if (args.status && args.status !== "") {
    params.set("status", args.status);
  }
  return getJson<FailuresResponseDto>(`/api/failures?${params.toString()}`);
}

/**
 * Trigger stage-specific failure retry.
 *
 * @param failureId - Stage-qualified failure identifier.
 * @returns Retry mutation payload.
 */
export async function retryFailure(failureId: string): Promise<RetryFailureDto> {
  return getJson<RetryFailureDto>(`/api/failures/${encodeURIComponent(failureId)}/retry`, {
    method: "POST",
  });
}

/** Response shape for `GET /api/system/health`. */
export interface SystemHealthDto {
  /** True when the API process is running. */
  readonly ok: boolean;
  /**
   * True when `OPENAI_API_KEY` is set and non-empty in the API process env.
   *
   * @remarks
   * When `false`, the gate, tailor, and review workers idle and the
   * dashboard renders the {@link MissingKeyBanner}.
   */
  readonly openai_key_configured: boolean;
}

/**
 * Fetch runtime configuration health used to drive dashboard banners.
 *
 * @returns System health DTO including `openai_key_configured`.
 */
export async function fetchSystemHealth(): Promise<SystemHealthDto> {
  return getJson<SystemHealthDto>("/api/system/health");
}

/**
 * Trigger an immediate job discovery run by restarting the discovery container.
 *
 * @returns Accepted lifecycle action payload.
 */
export async function fetchJobsNow(): Promise<SystemLifecycleActionDto> {
  return getJson<SystemLifecycleActionDto>("/api/system/fetch-jobs", {
    method: "POST",
  });
}

/**
 * Fetch the host Chrome reachability snapshot for the top-bar chip.
 *
 * @param osHint - Caller's OS, used to pick the correct launch command.
 * @returns Chrome status payload including reachability and command hint.
 */
export async function fetchChromeStatus(
  osHint?: ChromeStatusOsHint,
): Promise<ChromeStatusDto> {
  const params = new URLSearchParams();
  if (osHint !== undefined) {
    params.set("os", osHint);
  }
  const querySuffix = params.toString() === "" ? "" : `?${params.toString()}`;
  return getJson<ChromeStatusDto>(`/api/status/chrome${querySuffix}`);
}

/**
 * Request cost summary stats.
 *
 * @returns Cost stats DTO.
 */
export async function fetchCostStats(): Promise<CostStatsDto> {
  return getJson<CostStatsDto>("/api/costs/stats");
}

/**
 * Request cost daily trend payload.
 *
 * @param range - Cost trend range.
 * @returns Cost daily trend DTO.
 */
export async function fetchCostDailyTrend(range: "7d" | "30d" | "all"): Promise<CostDailyTrendDto> {
  const params = new URLSearchParams({ range });
  return getJson<CostDailyTrendDto>(`/api/costs/daily-trend?${params.toString()}`);
}

/**
 * Request stage cost breakdown payload.
 *
 * @returns Cost by stage DTO.
 */
export async function fetchCostByStage(): Promise<CostByStageDto> {
  return getJson<CostByStageDto>("/api/costs/by-stage");
}

/**
 * Request current monthly budget payload.
 *
 * @returns Budget DTO.
 */
export async function fetchBudget(): Promise<BudgetDto> {
  return getJson<BudgetDto>("/api/budget");
}

/**
 * Persist an updated monthly budget value.
 *
 * @param monthlyBudgetUsd - New monthly budget in USD.
 * @returns Updated budget DTO.
 */
export async function updateBudget(monthlyBudgetUsd: number): Promise<BudgetDto> {
  return getJson<BudgetDto>("/api/budget", {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify({ monthly_budget_usd: monthlyBudgetUsd }),
  });
}

/**
 * Request write-only API key configuration statuses.
 *
 * @returns API key statuses for all supported providers.
 */
export async function fetchApiKeysSettings(): Promise<ApiKeysResponseDto> {
  return getJson<ApiKeysResponseDto>("/api/settings/api-keys");
}

/**
 * Add or replace one API key secret value.
 *
 * @param keyName - API key environment variable name.
 * @param keyValue - Secret key value supplied by the user.
 * @returns Updated API key status payload.
 */
export async function upsertApiKeySetting(
  keyName: ApiKeyNameDto,
  keyValue: string,
): Promise<ApiKeysResponseDto> {
  return getJson<ApiKeysResponseDto>(`/api/settings/api-keys/${encodeURIComponent(keyName)}`, {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify({ value: keyValue }),
  });
}

/**
 * Validate an Adzuna app_id / app_key pair against the live Adzuna API.
 *
 * @remarks
 * Used by the onboarding wizard to fail fast on typos. The server makes a
 * tiny probe request to Adzuna and returns 200 only when the credentials
 * authenticate successfully. Throws on non-2xx responses so the caller
 * can surface an inline error.
 */
export async function validateAdzunaKeys(
  appId: string,
  appKey: string,
): Promise<void> {
  const response = await fetch("/api/settings/api-keys/validate-adzuna", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ app_id: appId, app_key: appKey }),
  });
  if (!response.ok) {
    throw new Error(`Adzuna validation failed (HTTP ${String(response.status)}).`);
  }
}

/**
 * Delete one API key secret from runtime configuration.
 *
 * @param keyName - API key environment variable name.
 * @returns Updated API key status payload.
 */
export async function deleteApiKeySetting(keyName: ApiKeyNameDto): Promise<ApiKeysResponseDto> {
  return getJson<ApiKeysResponseDto>(`/api/settings/api-keys/${encodeURIComponent(keyName)}`, {
    method: "DELETE",
  });
}

/**
 * Request settings file metadata.
 *
 * @returns Settings files DTO.
 */
export async function fetchSettingsFiles(): Promise<SettingsFilesDto> {
  return getJson<SettingsFilesDto>("/api/settings/files");
}

/**
 * Request candidate profile settings payload for guided and YAML editors.
 *
 * @returns Candidate profile settings DTO.
 */
export async function fetchProfileSettings(): Promise<SettingsProfileDto> {
  return getJson<SettingsProfileDto>("/api/settings/profile");
}

/**
 * Persist candidate profile settings from raw YAML text.
 *
 * @param yamlText - YAML text content to validate and save.
 * @returns Candidate profile settings DTO after save.
 */
export async function updateProfileYaml(yamlText: string): Promise<SettingsProfileDto> {
  return getJson<SettingsProfileDto>("/api/settings/profile", {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify({ yaml_text: yamlText }),
  });
}

/**
 * Persist candidate profile settings from structured guided form fields.
 *
 * @param payload - Structured profile payload.
 * @returns Candidate profile settings DTO after save.
 */
export async function updateProfileStructured(payload: {
  readonly profile: {
    readonly summary: string;
    readonly contact: {
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
    };
    readonly work_authorization: {
      readonly citizenship_country_code: string;
      readonly citizenship_country_label: string;
      readonly authorized_to_work_us: "yes" | "no" | "unknown";
      readonly requires_sponsorship_now_or_future: "yes" | "no" | "unknown";
    };
    readonly education_summary: string;
    readonly education_entries: readonly {
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
    }[];
    readonly target_roles: readonly string[];
    readonly strongest_areas: readonly string[];
    readonly experience_highlights: readonly string[];
    readonly hard_filters: readonly string[];
    readonly preferences: readonly string[];
  };
  readonly search_defaults: {
    readonly job_board_search_terms: readonly string[];
  };
  readonly apply_prefs?: unknown;
  readonly prompt_context: string | null;
}): Promise<SettingsProfileDto> {
  return getJson<SettingsProfileDto>("/api/settings/profile/structured", {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  });
}

/**
 * Request resume settings payload for guided and YAML editors.
 *
 * @returns Resume settings DTO.
 */
export async function fetchResumeSettings(): Promise<SettingsResumeDto> {
  return getJson<SettingsResumeDto>("/api/settings/resume");
}

/**
 * Persist resume settings from raw YAML text.
 *
 * @param yamlText - YAML text content to validate and save.
 * @returns Resume settings DTO after save.
 */
export async function updateResumeYaml(yamlText: string): Promise<SettingsResumeDto> {
  return getJson<SettingsResumeDto>("/api/settings/resume", {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify({ yaml_text: yamlText }),
  });
}

/**
 * Persist resume settings from structured guided form fields.
 *
 * @param resume - Full canonical resume payload.
 * @returns Resume settings DTO after save.
 */
export async function updateResumeStructured(resume: ResumeContentDto): Promise<SettingsResumeDto> {
  return getJson<SettingsResumeDto>("/api/settings/resume/structured", {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify({ resume }),
  });
}

/**
 * Upload one LaTeX resume file and migrate it into canonical YAML.
 *
 * @param file - Uploaded `.tex` file.
 * @returns Resume settings DTO including migration summary.
 */
export async function uploadResumeTex(file: File): Promise<SettingsResumeTexUploadDto> {
  const formData = new FormData();
  formData.append("file", file);
  return getJson<SettingsResumeTexUploadDto>("/api/settings/resume/tex", {
    method: "POST",
    body: formData,
  });
}

/**
 * Upload a replacement resume YAML file.
 *
 * @param file - File object selected by user.
 * @returns Resume upload DTO containing updated resume metadata.
 */
export async function uploadResume(file: File): Promise<SettingsResumeUploadDto> {
  const formData = new FormData();
  formData.append("file", file);
  return getJson<SettingsResumeUploadDto>("/api/settings/resume", {
    method: "POST",
    body: formData,
  });
}

/**
 * Upload a PDF resume and convert it to a canonical YAML stub.
 *
 * @param file - PDF file selected by user.
 * @returns Resume upload DTO containing updated resume metadata.
 */
export async function uploadResumePdf(file: File): Promise<SettingsResumeUploadDto> {
  const formData = new FormData();
  formData.append("file", file);
  return getJson<SettingsResumeUploadDto>("/api/settings/resume/pdf", {
    method: "POST",
    body: formData,
  });
}

/**
 * Upload a replacement candidate profile YAML file.
 *
 * @param file - File object selected by user.
 * @returns Profile upload DTO containing updated profile metadata.
 */
export async function uploadProfile(file: File): Promise<SettingsProfileUploadDto> {
  const formData = new FormData();
  formData.append("file", file);
  return getJson<SettingsProfileUploadDto>("/api/settings/profile", {
    method: "POST",
    body: formData,
  });
}

/**
 * Build tailored resume PDF endpoint URL for one job row.
 *
 * @param jobHash - Stable lowercase hex job hash from jobs payload.
 * @returns Absolute path for tailored resume download endpoint.
 */
export function getTailoredResumeUrl(jobHash: string): string {
  return `/api/jobs/${encodeURIComponent(jobHash)}/resume`;
}

/**
 * Build resume download endpoint URL.
 *
 * @returns Absolute path for resume download endpoint.
 */
export function getResumeDownloadUrl(): string {
  return "/api/settings/resume/download";
}

/**
 * Build profile download endpoint URL.
 *
 * @returns Absolute path for profile download endpoint.
 */
export function getProfileDownloadUrl(): string {
  return "/api/settings/profile/download";
}

// ── Fetcher Settings ────────────────────────────────────────────────

/** Response shape for filters and sources YAML settings endpoints. */
interface YamlSettingsResponse {
  ok: boolean;
  yaml_text: string;
  data: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

/**
 * Parse a fetch response as JSON with standard error handling.
 *
 * @param response - Fetch response to parse.
 * @returns Typed YAML settings response payload.
 * @throws ApiError when the response is not OK or body is not valid JSON.
 */
async function parseJsonResponse(response: Response): Promise<YamlSettingsResponse> {
  await throwIfError(response);
  return (await response.json()) as YamlSettingsResponse;
}

/**
 * Fetch the current filters.yaml configuration.
 *
 * @returns Parsed filters config with raw YAML text.
 */
export async function fetchFiltersSettings(): Promise<YamlSettingsResponse> {
  return parseJsonResponse(await fetch("/api/settings/filters"));
}

/**
 * Write updated filters.yaml configuration.
 *
 * @param yamlText - Raw YAML string to persist.
 * @returns Confirmation with file metadata.
 */
export async function updateFiltersYaml(yamlText: string): Promise<YamlSettingsResponse> {
  return parseJsonResponse(
    await fetch("/api/settings/filters", {
      method: "PUT",
      headers: JSON_HEADERS,
      body: JSON.stringify({ yaml_text: yamlText }),
    }),
  );
}

/**
 * Fetch the current companies.yaml source configuration.
 *
 * @returns Parsed sources config with raw YAML text.
 */
export async function fetchSourcesSettings(): Promise<YamlSettingsResponse> {
  return parseJsonResponse(await fetch("/api/settings/sources"));
}

/**
 * Write updated companies.yaml source configuration.
 *
 * @param yamlText - Raw YAML string to persist.
 * @returns Confirmation with file metadata.
 */
export async function updateSourcesYaml(yamlText: string): Promise<YamlSettingsResponse> {
  return parseJsonResponse(
    await fetch("/api/settings/sources", {
      method: "PUT",
      headers: JSON_HEADERS,
      body: JSON.stringify({ yaml_text: yamlText }),
    }),
  );
}

// ── Onboarding ─────────────────────────────────────────────────────

/** Response shape for onboarding status check. */
export interface OnboardingStatusDto {
  readonly ok: true;
  readonly is_complete: boolean;
  readonly completed_steps: readonly string[];
  readonly missing_steps: readonly string[];
}

/**
 * Check whether the user has completed onboarding.
 *
 * @returns Onboarding status with completed/missing step info.
 */
export async function fetchOnboardingStatus(): Promise<OnboardingStatusDto> {
  return getJson<OnboardingStatusDto>("/api/settings/onboarding-status");
}

// ── Apply runs ─────────────────────────────────────────────────────

/**
 * Thrown when a POST to `/api/jobs/{jobHash}/apply` returns HTTP 409.
 *
 * @remarks
 * A 409 means an apply run already exists for this job and is either
 * PENDING or RUNNING. The caller should surface this as a non-blocking
 * notice rather than an error banner, since the in-progress run may
 * complete shortly.
 */
export class ApplyRunConflictError extends Error {
  /** Machine-readable error code for upstream handling. */
  readonly code = "APPLY_RUN_CONFLICT" as const;

  /**
   * @param jobHash - The job hash that already has an active apply run.
   */
  constructor(jobHash: string) {
    super(`An apply run is already active for job ${jobHash}.`);
    this.name = "ApplyRunConflictError";
  }
}

/**
 * Enqueue a user-triggered apply run for one job.
 *
 * @param jobHash - Stable deduplication hash of the target job.
 * @returns Enqueue response with the new apply_run_id.
 * @throws {@link ApplyRunConflictError} When HTTP 409 — an active run already exists.
 * @throws ApiError for other non-2xx responses.
 */
export async function postApplyRun(jobHash: string): Promise<EnqueueApplyRunResponseDto> {
  const response = await fetch(`/api/jobs/${encodeURIComponent(jobHash)}/apply`, {
    method: "POST",
    headers: JSON_HEADERS,
  });

  if (response.status === 409) {
    throw new ApplyRunConflictError(jobHash);
  }

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as ApiErrorPayload | null;
    throw buildApiError(
      payload?.message ?? `Apply enqueue failed (HTTP ${response.status})`,
      payload?.code ?? "APPLY_ENQUEUE_FAILED",
      (payload?.details as Record<string, unknown> | undefined) ?? {},
    );
  }

  return (await response.json()) as EnqueueApplyRunResponseDto;
}

/**
 * Fetch the current state of one apply run.
 *
 * @param runId - Primary key of the apply_runs row.
 * @returns Apply run DTO with current status and outcome.
 */
export async function getApplyRun(runId: number): Promise<ApplyRunDto> {
  return getJson<ApplyRunDto>(`/api/apply-runs/${runId}`);
}

/**
 * Soft-delete one apply run.
 *
 * @param runId - Primary key of the apply_runs row.
 */
export async function deleteApplyRun(runId: number): Promise<void> {
  const response = await fetch(`/api/apply-runs/${runId}`, { method: "DELETE" });
  if (!response.ok && response.status !== 204) {
    const payload = (await response.json().catch(() => null)) as ApiErrorPayload | null;
    throw buildApiError(
      payload?.message ?? `Apply run delete failed (HTTP ${response.status})`,
      payload?.code ?? "APPLY_DELETE_FAILED",
      (payload?.details as Record<string, unknown> | undefined) ?? {},
    );
  }
}

// ── Job Import ─────────────────────────────────────────────────────

/**
 * Import a job posting manually by URL or pasted text.
 *
 * @param payload - Import mode and associated data.
 * @returns Created job identifier.
 */
export async function importJob(payload: {
  readonly mode: "url" | "text";
  readonly url?: string;
  readonly company?: string;
  readonly title?: string;
  readonly location?: string;
  readonly description?: string;
}): Promise<{
  readonly ok: true;
  readonly job_id: number;
  readonly job_hash: string;
  readonly duplicate: boolean;
}> {
  return getJson<{
    readonly ok: true;
    readonly job_id: number;
    readonly job_hash: string;
    readonly duplicate: boolean;
  }>("/api/jobs/import", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  });
}
