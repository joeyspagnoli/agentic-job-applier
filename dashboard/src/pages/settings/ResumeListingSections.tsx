/**
 * @packageDocumentation
 *
 * Listing sub-sections of the structured resume editor: experience, projects,
 * and skills. All three render alike (header + per-listing card grid) so they
 * live in one file.
 */

import type { JSX } from "react";
import type { ResumeContentDto, ResumeSkillListingDto } from "@/lib/api/types";
import { COLOR_ERROR, COLOR_PRIMARY } from "@/lib/design-tokens";
import { LabeledInput } from "@/components/settings/LabeledInput";
import { LabeledTextarea } from "@/components/settings/LabeledTextarea";

/** Props for the experience listings sub-section. */
export interface ResumeExperienceSectionProps {
  /** Listings to render. */
  readonly listings: ResumeContentDto["experience"]["listings"];
  /** Update a single field on the listing at `index`. */
  readonly onFieldUpdate: (
    index: number,
    fieldName: "id" | "title" | "date_range" | "organization" | "enabled",
    value: string | boolean,
  ) => void;
  /** Replace the bullet list for the listing at `index`. */
  readonly onBulletsUpdate: (index: number, value: string) => void;
  /** Append a new empty listing. */
  readonly onAdd: () => void;
  /** Remove the listing at `index`. */
  readonly onRemove: (index: number) => void;
}

/**
 * Render the work-experience listings sub-section.
 *
 * @param props - Sub-section props.
 * @returns Experience listings markup.
 */
export function ResumeExperienceSection({
  listings,
  onFieldUpdate,
  onBulletsUpdate,
  onAdd,
  onRemove,
}: ResumeExperienceSectionProps): JSX.Element {
  return (
    <div className="rounded-xl border border-outline-variant/30 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-bold uppercase tracking-wide">Work Experience</h4>
        <button className="text-sm font-semibold" style={{ color: COLOR_PRIMARY }} onClick={onAdd}>
          + Add Experience
        </button>
      </div>
      {listings.map((listing, index) => (
        <div
          key={`experience-${index}`}
          className="rounded-xl border border-outline-variant/50 bg-surface-container-low p-3 space-y-3"
        >
          <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
            <LabeledInput
              label="ID"
              value={listing.id}
              onChange={(value) => onFieldUpdate(index, "id", value)}
            />
            <LabeledInput
              label="Title"
              value={listing.title}
              onChange={(value) => onFieldUpdate(index, "title", value)}
            />
            <LabeledInput
              label="Date Range"
              value={listing.date_range}
              onChange={(value) => onFieldUpdate(index, "date_range", value)}
            />
            <LabeledInput
              label="Company"
              value={listing.organization}
              onChange={(value) => onFieldUpdate(index, "organization", value)}
            />
          </div>
          <LabeledTextarea
            label="Bullet Points (one per line)"
            value={listing.bullets.map((bullet) => bullet.text).join("\n")}
            onChange={(value) => onBulletsUpdate(index, value)}
            rows={4}
          />
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold">
              <input
                type="checkbox"
                checked={listing.enabled}
                onChange={(event) => onFieldUpdate(index, "enabled", event.target.checked)}
              />{" "}
              Enabled
            </label>
            <button
              className="text-xs font-semibold"
              style={{ color: COLOR_ERROR }}
              onClick={() => onRemove(index)}
            >
              Remove
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

/** Props for the projects listings sub-section. */
export interface ResumeProjectsSectionProps {
  /** Listings to render. */
  readonly listings: ResumeContentDto["projects"]["listings"];
  /** Update a single field on the listing at `index`. */
  readonly onFieldUpdate: (
    index: number,
    fieldName: "id" | "title" | "date_range" | "tech_stack" | "enabled",
    value: string | boolean,
  ) => void;
  /** Replace the bullet list for the listing at `index`. */
  readonly onBulletsUpdate: (index: number, value: string) => void;
  /** Append a new empty listing. */
  readonly onAdd: () => void;
  /** Remove the listing at `index`. */
  readonly onRemove: (index: number) => void;
}

/**
 * Render the projects listings sub-section.
 *
 * @param props - Sub-section props.
 * @returns Projects listings markup.
 */
export function ResumeProjectsSection({
  listings,
  onFieldUpdate,
  onBulletsUpdate,
  onAdd,
  onRemove,
}: ResumeProjectsSectionProps): JSX.Element {
  return (
    <div className="rounded-xl border border-outline-variant/30 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-bold uppercase tracking-wide">Projects</h4>
        <button className="text-sm font-semibold" style={{ color: COLOR_PRIMARY }} onClick={onAdd}>
          + Add Project
        </button>
      </div>
      {listings.map((listing, index) => (
        <div
          key={`project-${index}`}
          className="rounded-xl border border-outline-variant/50 bg-surface-container-low p-3 space-y-3"
        >
          <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
            <LabeledInput
              label="ID"
              value={listing.id}
              onChange={(value) => onFieldUpdate(index, "id", value)}
            />
            <LabeledInput
              label="Name"
              value={listing.title}
              onChange={(value) => onFieldUpdate(index, "title", value)}
            />
            <LabeledInput
              label="Tech Stack"
              value={listing.tech_stack}
              onChange={(value) => onFieldUpdate(index, "tech_stack", value)}
            />
            <LabeledInput
              label="Date"
              value={listing.date_range}
              onChange={(value) => onFieldUpdate(index, "date_range", value)}
            />
          </div>
          <LabeledTextarea
            label="Bullet Points (one per line)"
            value={listing.bullets.map((bullet) => bullet.text).join("\n")}
            onChange={(value) => onBulletsUpdate(index, value)}
            rows={3}
          />
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold">
              <input
                type="checkbox"
                checked={listing.enabled}
                onChange={(event) => onFieldUpdate(index, "enabled", event.target.checked)}
              />{" "}
              Enabled
            </label>
            <button
              className="text-xs font-semibold"
              style={{ color: COLOR_ERROR }}
              onClick={() => onRemove(index)}
            >
              Remove
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

/** Props for the skills listings sub-section. */
export interface ResumeSkillsSectionProps {
  /** Listings to render. */
  readonly listings: ResumeContentDto["skills_achievements"]["listings"];
  /** Update a single field on the listing at `index`. */
  readonly onFieldUpdate: (
    index: number,
    fieldName: keyof ResumeSkillListingDto,
    value: string | boolean,
  ) => void;
  /** Append a new empty listing. */
  readonly onAdd: () => void;
  /** Remove the listing at `index`. */
  readonly onRemove: (index: number) => void;
}

/**
 * Render the skills/achievements listings sub-section.
 *
 * @param props - Sub-section props.
 * @returns Skills listings markup.
 */
export function ResumeSkillsSection({
  listings,
  onFieldUpdate,
  onAdd,
  onRemove,
}: ResumeSkillsSectionProps): JSX.Element {
  return (
    <div className="rounded-xl border border-outline-variant/30 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-bold uppercase tracking-wide">Skills & Achievements</h4>
        <button className="text-sm font-semibold" style={{ color: COLOR_PRIMARY }} onClick={onAdd}>
          + Add Skill Row
        </button>
      </div>
      {listings.map((listing, index) => (
        <div
          key={`skill-${index}`}
          className="rounded-xl border border-outline-variant/50 bg-surface-container-low p-3 space-y-3"
        >
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <LabeledInput
              label="ID"
              value={listing.id}
              onChange={(value) => onFieldUpdate(index, "id", value)}
            />
            <LabeledInput
              label="Category"
              value={listing.category}
              onChange={(value) => onFieldUpdate(index, "category", value)}
            />
            <LabeledInput
              label="Text"
              value={listing.text}
              onChange={(value) => onFieldUpdate(index, "text", value)}
            />
          </div>
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold">
              <input
                type="checkbox"
                checked={listing.enabled}
                onChange={(event) => onFieldUpdate(index, "enabled", event.target.checked)}
              />{" "}
              Enabled
            </label>
            <button
              className="text-xs font-semibold"
              style={{ color: COLOR_ERROR }}
              onClick={() => onRemove(index)}
            >
              Remove
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
