/**
 * @packageDocumentation
 *
 * React hook that derives field-level update handlers for the resume draft.
 */

import { useMemo } from "react";
import type { ResumeContentDto, ResumeSkillListingDto } from "@/lib/api/types";
import { linesToList, nextGeneratedId } from "./transforms";

/** Bundle of derived handlers for the structured resume editor. */
export interface ResumeDraftHandlers {
  /** Update a layout knob (numeric coercion). */
  readonly updateLayoutField: (fieldName: keyof ResumeContentDto["layout"], value: string) => void;
  /** Update one field on the experience listing at `index`. */
  readonly updateExperienceField: (
    index: number,
    fieldName: "id" | "title" | "date_range" | "organization" | "enabled",
    value: string | boolean,
  ) => void;
  /** Replace the bullet list for the experience listing at `index`. */
  readonly updateExperienceBullets: (index: number, value: string) => void;
  /** Append a new empty experience listing. */
  readonly addExperienceListing: () => void;
  /** Remove the experience listing at `index`. */
  readonly removeExperienceListing: (index: number) => void;
  /** Update one field on the project listing at `index`. */
  readonly updateProjectField: (
    index: number,
    fieldName: "id" | "title" | "date_range" | "tech_stack" | "enabled",
    value: string | boolean,
  ) => void;
  /** Replace the bullet list for the project listing at `index`. */
  readonly updateProjectBullets: (index: number, value: string) => void;
  /** Append a new empty project listing. */
  readonly addProjectListing: () => void;
  /** Remove the project listing at `index`. */
  readonly removeProjectListing: (index: number) => void;
  /** Update one field on the skill listing at `index`. */
  readonly updateSkillField: (
    index: number,
    fieldName: keyof ResumeSkillListingDto,
    value: string | boolean,
  ) => void;
  /** Append a new empty skill listing. */
  readonly addSkillListing: () => void;
  /** Remove the skill listing at `index`. */
  readonly removeSkillListing: (index: number) => void;
}

/**
 * Build the field-level draft handlers used by the resume guided view.
 *
 * @param onDraftChange - Functional draft replacement callback.
 * @returns Memoized handler bundle.
 */
export function useResumeDraftHandlers(
  onDraftChange: (
    next: ResumeContentDto | ((current: ResumeContentDto) => ResumeContentDto),
  ) => void,
): ResumeDraftHandlers {
  return useMemo<ResumeDraftHandlers>(
    () => ({
      updateLayoutField: (fieldName, value) => {
        const parsedValue = Number.parseFloat(value);
        if (!Number.isFinite(parsedValue)) {
          return;
        }
        onDraftChange((current) => ({
          ...current,
          layout: { ...current.layout, [fieldName]: parsedValue },
        }));
      },
      updateExperienceField: (index, fieldName, value) => {
        onDraftChange((current) => ({
          ...current,
          experience: {
            ...current.experience,
            listings: current.experience.listings.map((listing, listingIndex) => {
              if (listingIndex !== index) {
                return listing;
              }
              return { ...listing, [fieldName]: value };
            }),
          },
        }));
      },
      updateExperienceBullets: (index, value) => {
        onDraftChange((current) => ({
          ...current,
          experience: {
            ...current.experience,
            listings: current.experience.listings.map((listing, listingIndex) => {
              if (listingIndex !== index) {
                return listing;
              }
              const nextBullets = linesToList(value).map((line, lineIndex) => ({
                id: `${listing.id || "exp"}_bullet_${lineIndex + 1}`,
                text: line,
              }));
              return { ...listing, bullets: nextBullets };
            }),
          },
        }));
      },
      addExperienceListing: () => {
        onDraftChange((current) => {
          const existingIds = current.experience.listings.map((listing) => listing.id);
          const nextId = nextGeneratedId("exp_new", existingIds);
          return {
            ...current,
            experience: {
              ...current.experience,
              listings: [
                ...current.experience.listings,
                {
                  id: nextId,
                  enabled: true,
                  title: "New Experience Role",
                  date_range: "MM. YYYY -- MM. YYYY",
                  organization: "Organization",
                  bullets: [
                    { id: `${nextId}_bullet_1`, text: "Add impact-focused bullet text here." },
                  ],
                },
              ],
            },
          };
        });
      },
      removeExperienceListing: (index) => {
        onDraftChange((current) => ({
          ...current,
          experience: {
            ...current.experience,
            listings: current.experience.listings.filter(
              (_listing, listingIndex) => listingIndex !== index,
            ),
          },
        }));
      },
      updateProjectField: (index, fieldName, value) => {
        onDraftChange((current) => ({
          ...current,
          projects: {
            ...current.projects,
            listings: current.projects.listings.map((listing, listingIndex) => {
              if (listingIndex !== index) {
                return listing;
              }
              return { ...listing, [fieldName]: value };
            }),
          },
        }));
      },
      updateProjectBullets: (index, value) => {
        onDraftChange((current) => ({
          ...current,
          projects: {
            ...current.projects,
            listings: current.projects.listings.map((listing, listingIndex) => {
              if (listingIndex !== index) {
                return listing;
              }
              const nextBullets = linesToList(value).map((line, lineIndex) => ({
                id: `${listing.id || "project"}_bullet_${lineIndex + 1}`,
                text: line,
              }));
              return { ...listing, bullets: nextBullets };
            }),
          },
        }));
      },
      addProjectListing: () => {
        onDraftChange((current) => {
          const existingIds = current.projects.listings.map((listing) => listing.id);
          const nextId = nextGeneratedId("proj_new", existingIds);
          return {
            ...current,
            projects: {
              ...current.projects,
              listings: [
                ...current.projects.listings,
                {
                  id: nextId,
                  enabled: true,
                  title: "New Project",
                  tech_stack: "Tech stack",
                  date_range: "MM. YYYY -- MM. YYYY",
                  bullets: [
                    { id: `${nextId}_bullet_1`, text: "Add measurable project bullet text here." },
                  ],
                },
              ],
            },
          };
        });
      },
      removeProjectListing: (index) => {
        onDraftChange((current) => ({
          ...current,
          projects: {
            ...current.projects,
            listings: current.projects.listings.filter(
              (_listing, listingIndex) => listingIndex !== index,
            ),
          },
        }));
      },
      updateSkillField: (index, fieldName, value) => {
        onDraftChange((current) => ({
          ...current,
          skills_achievements: {
            ...current.skills_achievements,
            listings: current.skills_achievements.listings.map((listing, listingIndex) => {
              if (listingIndex !== index) {
                return listing;
              }
              return { ...listing, [fieldName]: value };
            }),
          },
        }));
      },
      addSkillListing: () => {
        onDraftChange((current) => {
          const existingIds = current.skills_achievements.listings.map((listing) => listing.id);
          const nextId = nextGeneratedId("skill_new", existingIds);
          return {
            ...current,
            skills_achievements: {
              ...current.skills_achievements,
              listings: [
                ...current.skills_achievements.listings,
                { id: nextId, enabled: true, category: "Category", text: "Skill text" },
              ],
            },
          };
        });
      },
      removeSkillListing: (index) => {
        onDraftChange((current) => ({
          ...current,
          skills_achievements: {
            ...current.skills_achievements,
            listings: current.skills_achievements.listings.filter(
              (_listing, listingIndex) => listingIndex !== index,
            ),
          },
        }));
      },
    }),
    [onDraftChange],
  );
}
