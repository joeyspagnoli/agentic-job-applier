/**
 * @packageDocumentation
 *
 * Step 3 of the onboarding wizard: resume file upload.
 */

import type { ChangeEvent, JSX } from "react";
import {
  COLOR_ON_SURFACE,
  COLOR_ON_SURFACE_VARIANT,
  COLOR_OUTLINE,
  COLOR_OUTLINE_VARIANT,
  COLOR_PRIMARY,
  COLOR_PRIMARY_FIXED,
  COLOR_SUCCESS,
} from "@/lib/design-tokens";

/** Props for {@link StepResume}. */
export interface StepResumeProps {
  /** Currently selected file, if any. */
  readonly file: File | null;
  /** Whether upload succeeded. */
  readonly uploaded: boolean;
  /** Whether upload is in progress. */
  readonly uploading: boolean;
  /** File input change handler. */
  readonly onFileChange: (e: ChangeEvent<HTMLInputElement>) => void;
}

/**
 * Step 3: Resume upload.
 *
 * @param props - {@link StepResumeProps}
 * @returns Resume upload form.
 */
export function StepResume({
  file,
  uploaded,
  uploading,
  onFileChange,
}: StepResumeProps): JSX.Element {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-bold" style={{ color: COLOR_ON_SURFACE }}>
          Resume
        </h2>
        <p className="text-sm mt-1" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          Upload a LaTeX <code>.tex</code> resume that follows our contract. We
          patch bullets in place and recompile — every tailored PDF looks
          identical to your upload. PDF / DOCX users: see the onboarding
          migration skill (docs).
        </p>
      </div>
      <div
        className="border-2 border-dashed rounded-2xl p-8 text-center transition-colors"
        style={{ borderColor: COLOR_OUTLINE_VARIANT }}
      >
        <span
          className="material-symbols-outlined text-4xl mb-3 block"
          style={{ color: COLOR_OUTLINE }}
        >
          upload_file
        </span>
        <p className="text-sm font-medium mb-4" style={{ color: COLOR_ON_SURFACE_VARIANT }}>
          {file ? file.name : "Drag and drop or click to select"}
        </p>
        <label
          className="inline-block px-5 py-2 rounded-xl text-sm font-bold cursor-pointer transition-all scale-98-on-click"
          style={{ backgroundColor: COLOR_PRIMARY_FIXED, color: COLOR_PRIMARY }}
        >
          Choose File
          <input
            type="file"
            accept=".tex"
            className="hidden"
            onChange={onFileChange}
          />
        </label>
        {uploading && (
          <p className="text-xs mt-3 animate-pulse" style={{ color: COLOR_PRIMARY }}>
            Uploading...
          </p>
        )}
        {uploaded && (
          <p className="text-xs mt-3 font-semibold" style={{ color: COLOR_SUCCESS }}>
            Resume uploaded successfully
          </p>
        )}
      </div>
    </div>
  );
}
