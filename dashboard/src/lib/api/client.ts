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
  SettingsFilesDto,
} from "@/lib/api/types";

const JSON_HEADERS = {
  "Content-Type": "application/json",
} as const;

/** Union type for all standardized API failures. */
type ApiError = Error & {
  code: string;
  details: Record<string, unknown>;
};

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
  return (await response.json()) as T;
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
 * Upload a replacement resume YAML file.
 *
 * @param file - File object selected by user.
 * @returns Settings files DTO containing updated resume metadata.
 */
export async function uploadResume(file: File): Promise<SettingsFilesDto> {
  const formData = new FormData();
  formData.append("file", file);
  return getJson<SettingsFilesDto>("/api/settings/resume", {
    method: "POST",
    body: formData,
  });
}

/**
 * Upload a replacement candidate profile YAML file.
 *
 * @param file - File object selected by user.
 * @returns Settings files DTO containing updated profile metadata.
 */
export async function uploadProfile(file: File): Promise<SettingsFilesDto> {
  const formData = new FormData();
  formData.append("file", file);
  return getJson<SettingsFilesDto>("/api/settings/profile", {
    method: "POST",
    body: formData,
  });
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
