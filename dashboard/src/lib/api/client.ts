/**
 * @packageDocumentation
 *
 * Typed API client helpers for dashboard-to-backend communication.
 */

import type {
  ApiErrorPayload,
  BudgetDto,
  CostByStageDto,
  CostDailyTrendDto,
  CostStatsDto,
  DashboardStatsDto,
  DiscoveryTrendDto,
  FailuresResponseDto,
  HandoffMutationDto,
  HumanReviewResponseDto,
  JobsResponseDto,
  RetryFailureDto,
  ResumeContentDto,
  SettingsFilesDto,
  SettingsProfileDto,
  SettingsProfileUploadDto,
  SettingsResumeUploadDto,
  SettingsResumeDto,
  SettingsResumeTexUploadDto,
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
  return getJson<JobsResponseDto>(`/api/jobs?${params.toString()}`);
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
export async function fetchCostDailyTrend(
  range: "7d" | "30d" | "all",
): Promise<CostDailyTrendDto> {
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
    readonly education: string;
    readonly citizenship: string;
    readonly target_roles: readonly string[];
    readonly strongest_areas: readonly string[];
    readonly experience_highlights: readonly string[];
    readonly hard_filters: readonly string[];
    readonly preferences: readonly string[];
  };
  readonly search_defaults: {
    readonly job_board_search_terms: readonly string[];
  };
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
