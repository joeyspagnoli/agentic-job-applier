/**
 * @packageDocumentation
 *
 * Shared YAML schema configuration for Monaco settings editors.
 */

import type { Monaco } from "@monaco-editor/react";
import { configureMonacoYaml } from "monaco-yaml";

export const PROFILE_EDITOR_MODEL_URI = "file:///settings/candidate_profile.yaml";
export const RESUME_EDITOR_MODEL_URI = "file:///settings/resume_content.yaml";

const PROFILE_SCHEMA_URI = "https://autoapply.local/schemas/candidate-profile.json";
const RESUME_SCHEMA_URI = "https://autoapply.local/schemas/resume-content.json";

const PROFILE_SCHEMA = {
  type: "object",
  properties: {
    profile: {
      type: "object",
      properties: {
        summary: { type: "string" },
        contact: {
          type: "object",
          properties: {
            full_name: { type: "string" },
            email: { type: "string" },
            phone: { type: "string" },
            city: { type: "string" },
            state_or_region: { type: "string" },
            country_code: { type: "string" },
            country_label: { type: "string" },
            linkedin_url: { type: "string" },
            github_url: { type: "string" },
            portfolio_url: { type: "string" },
          },
          required: [
            "full_name",
            "email",
            "phone",
            "city",
            "state_or_region",
            "country_code",
            "country_label",
            "linkedin_url",
            "github_url",
            "portfolio_url",
          ],
        },
        work_authorization: {
          type: "object",
          properties: {
            citizenship_country_code: { type: "string" },
            citizenship_country_label: { type: "string" },
            authorized_to_work_us: { type: "string", enum: ["yes", "no", "unknown"] },
            requires_sponsorship_now_or_future: {
              type: "string",
              enum: ["yes", "no", "unknown"],
            },
          },
          required: [
            "citizenship_country_code",
            "citizenship_country_label",
            "authorized_to_work_us",
            "requires_sponsorship_now_or_future",
          ],
        },
        education_summary: { type: "string" },
        education_entries: {
          type: "array",
          items: {
            type: "object",
            properties: {
              id: { type: "string" },
              school: { type: "string" },
              degree_level: { type: "string" },
              degree_name: { type: "string" },
              field_of_study: { type: "string" },
              start_month: { type: "string" },
              start_year: { type: "string" },
              end_month: { type: "string" },
              end_year: { type: "string" },
              is_current: { type: "boolean" },
              gpa: { type: "string" },
              location: { type: "string" },
              highlights: { type: "array", items: { type: "string" } },
            },
            required: [
              "id",
              "school",
              "degree_level",
              "degree_name",
              "field_of_study",
              "start_month",
              "start_year",
              "end_month",
              "end_year",
              "is_current",
              "gpa",
              "location",
              "highlights",
            ],
          },
        },
        target_roles: { type: "array", items: { type: "string" } },
        strongest_areas: { type: "array", items: { type: "string" } },
        experience_highlights: { type: "array", items: { type: "string" } },
        hard_filters: { type: "array", items: { type: "string" } },
        preferences: { type: "array", items: { type: "string" } },
      },
      required: [
        "summary",
        "contact",
        "work_authorization",
        "education_summary",
        "education_entries",
        "target_roles",
        "strongest_areas",
        "experience_highlights",
        "hard_filters",
        "preferences",
      ],
    },
    search_defaults: {
      type: "object",
      properties: {
        job_board_search_terms: { type: "array", items: { type: "string" } },
      },
      required: ["job_board_search_terms"],
    },
    prompt_context: { type: ["string", "null"] },
  },
  required: ["profile", "search_defaults"],
};

const RESUME_SCHEMA = {
  type: "object",
  properties: {
    schema_version: { type: "number" },
    lock_rules: { type: "object" },
    layout: {
      type: "object",
      properties: {
        margin_in: { type: "number" },
        top_vspace_in: { type: "number" },
        section_heading_font_size_pt: { type: "number" },
        section_heading_line_height_pt: { type: "number" },
        section_spacing_before_pt: { type: "number" },
        section_spacing_after_pt: { type: "number" },
        subheading_itemsep_pt: { type: "number" },
        bullet_itemsep_pt: { type: "number" },
      },
      required: [
        "margin_in",
        "top_vspace_in",
        "section_heading_font_size_pt",
        "section_heading_line_height_pt",
        "section_spacing_before_pt",
        "section_spacing_after_pt",
        "subheading_itemsep_pt",
        "bullet_itemsep_pt",
      ],
    },
    personal: { type: "object" },
    education: { type: "object" },
    experience: { type: "object" },
    projects: { type: "object" },
    skills_achievements: { type: "object" },
  },
  required: [
    "schema_version",
    "lock_rules",
    "layout",
    "personal",
    "education",
    "experience",
    "projects",
    "skills_achievements",
  ],
};

let isYamlConfigured = false;

/**
 * Configure Monaco YAML support once per dashboard runtime.
 *
 * @param monaco - Monaco editor runtime instance.
 */
export function configureYamlSchemas(monaco: Monaco): void {
  if (isYamlConfigured) {
    return;
  }

  configureMonacoYaml(monaco, {
    enableSchemaRequest: false,
    validate: true,
    format: true,
    completion: true,
    hover: true,
    schemas: [
      {
        uri: PROFILE_SCHEMA_URI,
        fileMatch: [PROFILE_EDITOR_MODEL_URI],
        schema: PROFILE_SCHEMA,
      },
      {
        uri: RESUME_SCHEMA_URI,
        fileMatch: [RESUME_EDITOR_MODEL_URI],
        schema: RESUME_SCHEMA,
      },
    ],
  });

  isYamlConfigured = true;
}
