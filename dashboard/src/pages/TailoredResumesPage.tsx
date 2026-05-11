/**
 * @packageDocumentation
 *
 * Tailored Resumes page — a filtered view of {@link JobsPage} that lists
 * every job with a non-deleted tailor_run.
 *
 * @remarks
 * The plan in issue #39 calls for the same row component and expand
 * behavior as JobsPage with a different fetcher; we reach that by
 * passing `hasTailorRun=true` through to the shared `/api/jobs`
 * endpoint and rendering the existing JobsPage component.
 */

import type { JSX } from "react";
import { JobsPage } from "@/pages/JobsPage";

/**
 * Render the Tailored Resumes sidebar page.
 *
 * @returns The JobsPage with the `has_tailor_run` filter pre-applied.
 */
export function TailoredResumesPage(): JSX.Element {
  return <JobsPage hasTailorRunFilter />;
}
