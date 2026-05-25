/**
 * @packageDocumentation
 *
 * Frontend adapter layer that maps snake_case API DTOs into dashboard view
 * models consumed by React page components.
 */

import type {
  CostByStageDto,
  CostDailyTrendDto,
  CostStatsDto,
  DashboardStatsDto,
  DiscoveryTrendDto,
  FailureItemDto,
  FailuresResponseDto,
  HumanReviewItemDto,
  HumanReviewResponseDto,
  JobsItemDto,
  JobsResponseDto,
} from "@/lib/api/types";

/** One normalized KPI record for stat card rendering. */
export interface KpiCardModel {
  readonly label: string;
  readonly value: string;
  readonly subText: string;
}

/** Embedded tailor-run snapshot for one jobs row. */
export interface TailorRunSummaryModel {
  readonly id: number;
  readonly status: string;
  readonly verdict: string | null;
  readonly pageCount: number | null;
  readonly error: string | null;
  readonly pdfUrl: string | null;
  /**
   * Structured reason from the latest review_runs row's `review_report_json`.
   * Drives NO_IMPROVEMENT verdict copy in the jobs table; see
   * `TailorRunSummaryDto.review_reason` for full semantics.
   */
  readonly reviewReason: string | null;
  /**
   * URL of the planner-rationale artifact, when the tailor run wrote one
   * (Bug E, 2026-05-25). `null` for older runs and for failures, so the
   * dashboard can hide the "Why these edits" panel without speculating.
   */
  readonly planUrl: string | null;
}

/** One normalized jobs row used by jobs-page table rendering. */
export interface JobsRowModel {
  readonly id: number;
  readonly jobHash: string;
  readonly company: string;
  readonly position: string;
  readonly location: string;
  readonly pay: string;
  readonly workType: string;
  readonly source: string;
  readonly status: string;
  readonly discovered: string;
  readonly pipeline: readonly { label: string; status: string }[];
  readonly gateVerdict: string;
  readonly gateReasoning: string;
  readonly tailoredResume: string | null;
  readonly jobPostingUrl: string;
  readonly tailorRun: TailorRunSummaryModel | null;
}

/**
 * Convert numeric USD amount to fixed 2-decimal currency text.
 *
 * @param amountUsd - Raw USD amount.
 * @returns Display string in `$123.45` format.
 */
export function formatUsd(amountUsd: number): string {
  return `$${amountUsd.toFixed(2)}`;
}

/**
 * Adapt dashboard stats payload to page-level card model values.
 *
 * @param dto - Dashboard stats DTO from backend.
 * @returns Array of four KPI card models.
 */
export function toDashboardKpis(dto: DashboardStatsDto): readonly KpiCardModel[] {
  return [
    {
      label: "Jobs Discovered",
      value: dto.jobs_discovered_total.toLocaleString(),
      subText: `+${dto.jobs_discovered_today} today`,
    },
    {
      label: "Resumes Tailored",
      value: dto.resumes_tailored_total.toLocaleString(),
      subText: `+${dto.resumes_tailored_today} today`,
    },
    {
      label: "Applications Sent",
      value: dto.applications_sent_total.toLocaleString(),
      subText: `+${dto.applications_sent_today} today`,
    },
    {
      label: "Awaiting Review",
      value: dto.awaiting_review_total.toLocaleString(),
      subText: dto.awaiting_review_total > 0 ? "Action required" : "Queue clear",
    },
  ];
}

/**
 * Adapt jobs endpoint DTO rows to jobs-page row models.
 *
 * @param dto - Jobs endpoint payload.
 * @returns Normalized rows for table rendering.
 */
export function toJobsRows(dto: JobsResponseDto): readonly JobsRowModel[] {
  return dto.items.map((item: JobsItemDto) => ({
    id: item.id,
    jobHash: item.job_hash,
    company: item.company,
    position: item.position,
    location: item.location,
    pay: item.pay,
    workType: item.work_type,
    source: item.source,
    status: item.status,
    discovered: item.discovered,
    pipeline: item.pipeline,
    gateVerdict: item.gate_verdict,
    gateReasoning: item.gate_reasoning,
    tailoredResume: item.tailored_resume,
    jobPostingUrl: item.job_posting_url,
    tailorRun:
      item.tailor_run !== null
        ? {
            id: item.tailor_run.id,
            status: item.tailor_run.status,
            verdict: item.tailor_run.verdict,
            pageCount: item.tailor_run.page_count,
            error: item.tailor_run.error,
            pdfUrl: item.tailor_run.pdf_url,
            reviewReason: item.tailor_run.review_reason ?? null,
            planUrl: item.tailor_run.plan_url ?? null,
          }
        : null,
  }));
}

/**
 * Adapt one failure DTO row to compact card/table-friendly values.
 *
 * @param row - Failure row DTO.
 * @returns Adapted row preserving important fields.
 */
export function toFailureRow(row: FailureItemDto): FailureItemDto {
  return row;
}

/**
 * Adapt full failures response DTO without shape changes.
 *
 * @param dto - Failures response payload.
 * @returns Same payload for ergonomic call-site symmetry.
 */
export function toFailuresModel(dto: FailuresResponseDto): FailuresResponseDto {
  return dto;
}

/**
 * Adapt full human-review DTO without shape changes.
 *
 * @param dto - Human-review queue response payload.
 * @returns Same payload for ergonomic call-site symmetry.
 */
export function toHumanReviewModel(dto: HumanReviewResponseDto): HumanReviewResponseDto {
  return dto;
}

/**
 * Adapt one human-review row to rendering shape.
 *
 * @param row - Human-review DTO row.
 * @returns Same row payload.
 */
export function toHumanReviewRow(row: HumanReviewItemDto): HumanReviewItemDto {
  return row;
}

/**
 * Adapt cost stats DTO to display strings.
 *
 * @param dto - Cost stats payload.
 * @returns Display-oriented card values.
 */
export function toCostKpis(dto: CostStatsDto): {
  readonly totalSpend: string;
  readonly avgCostPerApp: string;
  readonly apiCallsToday: string;
} {
  return {
    totalSpend: formatUsd(dto.total_spend_usd),
    avgCostPerApp: formatUsd(dto.avg_cost_per_application_usd),
    apiCallsToday: dto.api_calls_today.toLocaleString(),
  };
}

/**
 * Adapt discovery trend DTO for chart component consumption.
 *
 * @param dto - Discovery trend payload.
 * @returns Chart points with existing key names.
 */
export function toDiscoveryChartPoints(dto: DiscoveryTrendDto): readonly {
  day: string;
  count: number;
}[] {
  return dto.points.map((point) => ({ day: point.label, count: point.count }));
}

/**
 * Adapt cost daily trend DTO for bar visualization.
 *
 * @param dto - Cost daily trend payload.
 * @returns Label/value chart points.
 */
export function toCostDailyTrendPoints(dto: CostDailyTrendDto): readonly {
  label: string;
  spendUsd: number;
}[] {
  return dto.points.map((point) => ({ label: point.label, spendUsd: point.spend_usd }));
}

/**
 * Adapt cost-by-stage DTO to percent-width display rows.
 *
 * @param dto - Cost-by-stage payload.
 * @returns Stage rows with computed width percentages.
 */
export function toCostByStageRows(dto: CostByStageDto): readonly {
  stage: string;
  spendUsd: number;
  widthPct: number;
}[] {
  const maxSpend = Math.max(0, ...dto.items.map((item) => item.spend_usd));
  return dto.items.map((item) => ({
    stage: item.stage,
    spendUsd: item.spend_usd,
    widthPct: maxSpend === 0 ? 0 : (item.spend_usd / maxSpend) * 100,
  }));
}
