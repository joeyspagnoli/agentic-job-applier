/**
 * @packageDocumentation
 *
 * Round-trip tests for the structured profile payload — focused on the new
 * education entries and the tri-state `willing_to_relocate` field added by
 * Bug D (2026-05-25).
 */

import { describe, expect, it } from "vitest";

import {
  defaultApplyPrefsDraft,
  defaultEducationEntry,
  defaultFiltersDraft,
  defaultProfileDraft,
  defaultRolesDraft,
} from "./defaults";
import { buildStructuredProfilePayload } from "./profile-payload";
import type { EducationEntry } from "./types";

function buildBaseArgs(): {
  profile: ReturnType<typeof defaultProfileDraft>;
  roles: ReturnType<typeof defaultRolesDraft>;
  filters: ReturnType<typeof defaultFiltersDraft>;
  applyPrefs: ReturnType<typeof defaultApplyPrefsDraft>;
} {
  return {
    profile: defaultProfileDraft(),
    roles: defaultRolesDraft(),
    filters: defaultFiltersDraft(),
    applyPrefs: defaultApplyPrefsDraft(),
  };
}

describe("buildStructuredProfilePayload — education entries", () => {
  it("emits an empty education_entries array when no rows are captured", () => {
    const payload = buildStructuredProfilePayload({
      ...buildBaseArgs(),
      education: [],
    });
    expect(payload.profile.education_entries).toEqual([]);
  });

  it("splits YYYY-MM dates into discrete year/month fields", () => {
    const entry: EducationEntry = {
      ...defaultEducationEntry(0),
      school: "University of Florida",
      degree: "Bachelor of Science",
      major: "Computer Science",
      startDate: "2022-08",
      endDate: "2026-05",
      gpa: "3.8",
      currentlyEnrolled: true,
      minors: ["Statistics", "Electrical Engineering"],
    };
    const payload = buildStructuredProfilePayload({
      ...buildBaseArgs(),
      education: [entry],
    });
    expect(payload.profile.education_entries).toEqual([
      {
        id: "edu-1",
        school: "University of Florida",
        degree_level: "",
        degree_name: "Bachelor of Science",
        field_of_study: "Computer Science",
        start_month: "08",
        start_year: "2022",
        end_month: "05",
        end_year: "2026",
        is_current: true,
        gpa: "3.8",
        location: "",
        highlights: [],
        minors: ["Statistics", "Electrical Engineering"],
      },
    ]);
  });

  it("tolerates blank dates by emitting empty year/month strings", () => {
    const entry: EducationEntry = {
      ...defaultEducationEntry(0),
      school: "Local College",
      degree: "Associate",
      startDate: "",
      endDate: "",
    };
    const payload = buildStructuredProfilePayload({
      ...buildBaseArgs(),
      education: [entry],
    });
    expect(payload.profile.education_entries[0]).toMatchObject({
      start_year: "",
      start_month: "",
      end_year: "",
      end_month: "",
    });
  });
});

describe("buildStructuredProfilePayload — apply_prefs willing_to_relocate", () => {
  it("passes the tri-state value through verbatim", () => {
    const args = buildBaseArgs();
    args.applyPrefs.location_preferences.willing_to_relocate = "yes";
    const payload = buildStructuredProfilePayload({
      ...args,
      education: [],
    });
    expect(payload.apply_prefs.location_preferences.willing_to_relocate).toBe("yes");
  });

  it("defaults to open_to_discussion when the user has not touched the radio", () => {
    const payload = buildStructuredProfilePayload({
      ...buildBaseArgs(),
      education: [],
    });
    expect(payload.apply_prefs.location_preferences.willing_to_relocate).toBe(
      "open_to_discussion",
    );
  });
});
