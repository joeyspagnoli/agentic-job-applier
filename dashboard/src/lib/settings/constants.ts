/**
 * @packageDocumentation
 *
 * Constant tables and static option lists shared across settings tabs.
 */

import type { ApiKeyNameDto, ServiceTierDto } from "@/lib/api/types";
import type { ApiKeyConfig, SelectOption, ServiceTierCard, TopLevelTab } from "./types";

/** All job type values recognized by the filters hard-filter. */
export const JOB_TYPES: readonly string[] = ["Full-time", "Part-time", "Contract", "Internship"];

/** Pixel height used by every Monaco YAML editor instance on the settings page. */
export const EDITOR_HEIGHT_PX = 420;

/** Top-level navigation tabs for the settings page. */
export const TOP_LEVEL_TABS: readonly { id: TopLevelTab; label: string }[] = [
  { id: "general", label: "General" },
  { id: "ai-provider", label: "AI Provider" },
  { id: "candidate", label: "Profile & Resume" },
  { id: "filters", label: "Filters & Sources" },
];

/** API keys exposed in the General → API Keys section. */
export const API_KEYS: readonly ApiKeyConfig[] = [
  {
    name: "OPENAI_API_KEY",
    icon: "auto_awesome",
    description: "Required for gate review, resume tailoring, and full automation.",
  },
  {
    name: "GOOGLE_API_KEY",
    icon: "auto_awesome",
    description: "Optional provider key for alternative model routing.",
  },
  {
    name: "ANTHROPIC_API_KEY",
    icon: "auto_awesome",
    description: "Optional provider key for alternative model routing.",
  },
];

/** Required API keys per service tier. */
export const SERVICE_TIER_REQUIREMENTS: Readonly<
  Record<ServiceTierDto, readonly ApiKeyNameDto[]>
> = {
  base: [],
  latex: ["OPENAI_API_KEY"],
  full: ["OPENAI_API_KEY"],
};

/** Service tier card definitions for the General → Service Tier section. */
export const SERVICE_TIER_CARDS: readonly ServiceTierCard[] = [
  {
    tier: "base",
    icon: "search",
    title: "Base",
    description:
      "Find and filter jobs from configured sources. Gate review is attempted when a provider key exists.",
    features: [
      "Job discovery (Greenhouse, JobSpy, Workday)",
      "Gate filtering (apply/skip decisions)",
      "Works as pure job aggregator without AI keys",
    ],
  },
  {
    tier: "latex",
    icon: "description",
    title: "LaTeX",
    badge: "Recommended",
    description: "Find jobs + tailor resume + human review queue.",
    features: ["Everything in Base", "Resume tailoring (LaTeX/PDF)", "Human review queue"],
  },
  {
    tier: "full",
    icon: "rocket_launch",
    title: "Full",
    description: "Full automation including browser-based application workflows.",
    features: [
      "Everything in LaTeX",
      "Automated browser apply (Playwright + Chromium)",
      "End-to-end autonomous pipeline",
    ],
  },
];

/** Confirmation message shown when navigating away with unsaved changes. */
export const CONFIRM_SWITCH_MESSAGE =
  "You have unsaved settings changes. Switch tabs and discard unsaved edits?";

/** Calendar month options for education entries. */
export const MONTH_OPTIONS: readonly SelectOption[] = [
  { value: "", label: "Month" },
  { value: "01", label: "January" },
  { value: "02", label: "February" },
  { value: "03", label: "March" },
  { value: "04", label: "April" },
  { value: "05", label: "May" },
  { value: "06", label: "June" },
  { value: "07", label: "July" },
  { value: "08", label: "August" },
  { value: "09", label: "September" },
  { value: "10", label: "October" },
  { value: "11", label: "November" },
  { value: "12", label: "December" },
];

/** Degree-level options for education entries. */
export const DEGREE_LEVEL_OPTIONS: readonly SelectOption[] = [
  { value: "", label: "Select degree level" },
  { value: "high_school", label: "High School" },
  { value: "associate", label: "Associate" },
  { value: "bachelor", label: "Bachelor's" },
  { value: "master", label: "Master's" },
  { value: "mba", label: "MBA" },
  { value: "doctorate", label: "Doctorate" },
  { value: "certificate", label: "Certificate" },
  { value: "other", label: "Other" },
];

/** Yes/no/unknown options for work-authorization fields. */
export const YES_NO_UNKNOWN_OPTIONS: readonly SelectOption[] = [
  { value: "unknown", label: "Prefer not to say" },
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
];
