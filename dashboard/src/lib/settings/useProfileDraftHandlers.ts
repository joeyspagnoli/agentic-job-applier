/**
 * @packageDocumentation
 *
 * React hook that derives field-level update handlers for the profile draft.
 * Centralizing them here keeps the guided view focused on rendering.
 */

import { useMemo } from "react";
import type { CandidateEducationEntryDto, SettingsProfileDto } from "@/lib/api/types";
import { buildPrioritizedCountryOptions } from "@/lib/constants/countries";
import {
  buildDefaultEducationEntry,
  linesToList,
  nextGeneratedId,
} from "./transforms";
import type { ProfileDraft } from "./transforms";

/** Field names that are list-typed on the profile object. */
export type ProfileListField =
  | "target_roles"
  | "strongest_areas"
  | "experience_highlights"
  | "hard_filters"
  | "preferences";

/** All scalar fields modified by the guided editor. */
export type ProfileScalarField = "summary" | "education_summary";

/** Bundle of derived handlers used by the guided view. */
export interface ProfileDraftHandlers {
  /** Country option list with U.S. pinned first. */
  readonly countryOptions: ReturnType<typeof buildPrioritizedCountryOptions>;
  /** Update a scalar field on `profile`. */
  readonly updateScalar: (fieldName: ProfileScalarField, value: string) => void;
  /** Update a list-typed field on `profile`. */
  readonly updateList: (fieldName: ProfileListField, value: string) => void;
  /** Update a single contact field. */
  readonly updateContactField: (
    fieldName: keyof SettingsProfileDto["profile"]["contact"],
    value: string,
  ) => void;
  /** Update the contact country (sets both code and label). */
  readonly updateContactCountry: (countryCode: string) => void;
  /** Update a single work-authorization field. */
  readonly updateWorkAuthorizationField: (
    fieldName: keyof SettingsProfileDto["profile"]["work_authorization"],
    value: string,
  ) => void;
  /** Update the citizenship country (sets both code and label). */
  readonly updateCitizenshipCountry: (countryCode: string) => void;
  /** Update one field on the education entry at `index`. */
  readonly updateEducationField: (
    index: number,
    fieldName: keyof CandidateEducationEntryDto,
    value: string | boolean,
  ) => void;
  /** Replace the highlights list for the education entry at `index`. */
  readonly updateEducationHighlights: (index: number, value: string) => void;
  /** Append a new empty education entry. */
  readonly addEducationEntry: () => void;
  /** Remove the education entry at `index`. */
  readonly removeEducationEntry: (index: number) => void;
  /** Update the search-defaults search-terms list. */
  readonly updateSearchTerms: (value: string) => void;
  /** Update the optional prompt context override. */
  readonly updatePromptContext: (value: string) => void;
}

/**
 * Build the field-level draft handlers used by the guided profile view.
 *
 * @param onDraftChange - Functional draft replacement callback.
 * @returns Memoized handler bundle.
 */
export function useProfileDraftHandlers(
  onDraftChange: (next: ProfileDraft | ((current: ProfileDraft) => ProfileDraft)) => void,
): ProfileDraftHandlers {
  const countryOptions = useMemo(() => buildPrioritizedCountryOptions(), []);
  const countryLabelByCode = useMemo(
    () =>
      new Map<string, string>(
        countryOptions.map((countryOption) => [countryOption.code, countryOption.label]),
      ),
    [countryOptions],
  );

  return useMemo<ProfileDraftHandlers>(() => {
    function updateProfileField<K extends keyof SettingsProfileDto["profile"]>(
      fieldName: K,
      value: SettingsProfileDto["profile"][K],
    ): void {
      onDraftChange((current) => ({
        ...current,
        profile: { ...current.profile, [fieldName]: value },
      }));
    }

    return {
      countryOptions,
      updateScalar: (fieldName, value) => {
        updateProfileField(fieldName, value);
      },
      updateList: (fieldName, value) => {
        updateProfileField(fieldName, linesToList(value));
      },
      updateContactField: (fieldName, value) => {
        onDraftChange((current) => ({
          ...current,
          profile: {
            ...current.profile,
            contact: { ...current.profile.contact, [fieldName]: value },
          },
        }));
      },
      updateContactCountry: (countryCode) => {
        const selectedCountryLabel = countryLabelByCode.get(countryCode) ?? "";
        onDraftChange((current) => ({
          ...current,
          profile: {
            ...current.profile,
            contact: {
              ...current.profile.contact,
              country_code: countryCode,
              country_label: selectedCountryLabel,
            },
          },
        }));
      },
      updateWorkAuthorizationField: (fieldName, value) => {
        onDraftChange((current) => ({
          ...current,
          profile: {
            ...current.profile,
            work_authorization: {
              ...current.profile.work_authorization,
              [fieldName]: value,
            },
          },
        }));
      },
      updateCitizenshipCountry: (countryCode) => {
        const selectedCountryLabel = countryLabelByCode.get(countryCode) ?? "";
        onDraftChange((current) => ({
          ...current,
          profile: {
            ...current.profile,
            work_authorization: {
              ...current.profile.work_authorization,
              citizenship_country_code: countryCode,
              citizenship_country_label: selectedCountryLabel,
            },
          },
        }));
      },
      updateEducationField: (index, fieldName, value) => {
        onDraftChange((current) => {
          const updatedEntries = current.profile.education_entries.map((entry, entryIndex) => {
            if (entryIndex !== index) {
              return entry;
            }
            return { ...entry, [fieldName]: value };
          });
          return {
            ...current,
            profile: { ...current.profile, education_entries: updatedEntries },
          };
        });
      },
      updateEducationHighlights: (index, value) => {
        onDraftChange((current) => {
          const updatedEntries = current.profile.education_entries.map((entry, entryIndex) => {
            if (entryIndex !== index) {
              return entry;
            }
            return { ...entry, highlights: linesToList(value) };
          });
          return {
            ...current,
            profile: { ...current.profile, education_entries: updatedEntries },
          };
        });
      },
      addEducationEntry: () => {
        onDraftChange((current) => {
          const existingIds = current.profile.education_entries.map((entry) => entry.id);
          const entryId = nextGeneratedId("education", existingIds);
          return {
            ...current,
            profile: {
              ...current.profile,
              education_entries: [
                ...current.profile.education_entries,
                buildDefaultEducationEntry(entryId),
              ],
            },
          };
        });
      },
      removeEducationEntry: (index) => {
        onDraftChange((current) => ({
          ...current,
          profile: {
            ...current.profile,
            education_entries: current.profile.education_entries.filter(
              (_entry, entryIndex) => entryIndex !== index,
            ),
          },
        }));
      },
      updateSearchTerms: (value) => {
        onDraftChange((current) => ({
          ...current,
          search_defaults: { job_board_search_terms: linesToList(value) },
        }));
      },
      updatePromptContext: (value) => {
        onDraftChange((current) => ({
          ...current,
          prompt_context: value.trim() === "" ? null : value,
        }));
      },
    };
  }, [countryOptions, countryLabelByCode, onDraftChange]);
}
