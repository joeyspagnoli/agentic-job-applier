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
        education: { type: "string" },
        citizenship: { type: "string" },
        target_roles: { type: "array", items: { type: "string" } },
        strongest_areas: { type: "array", items: { type: "string" } },
        experience_highlights: { type: "array", items: { type: "string" } },
        hard_filters: { type: "array", items: { type: "string" } },
        preferences: { type: "array", items: { type: "string" } },
      },
      required: [
        "summary",
        "education",
        "citizenship",
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
