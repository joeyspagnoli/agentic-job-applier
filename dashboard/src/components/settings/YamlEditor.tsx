/**
 * @packageDocumentation
 *
 * Monaco-backed YAML editor wrapper with shared schema configuration applied
 * to every instance on the settings page.
 */

import type { JSX } from "react";
import Editor, { type Monaco } from "@monaco-editor/react";
import { configureYamlSchemas } from "@/lib/monaco/yaml-config";
import { EDITOR_HEIGHT_PX } from "@/lib/settings/constants";

/** Props for monaco-backed YAML editor wrapper. */
export interface YamlEditorProps {
  /** Model URI path for schema matching. */
  readonly modelPath: string;
  /** Current editor value. */
  readonly value: string;
  /** Callback invoked on editor value changes. */
  readonly onChange: (value: string) => void;
}

/**
 * Render one Monaco YAML editor with schema tooling enabled.
 *
 * @param props - YAML editor props.
 * @returns One editor panel element.
 */
export function YamlEditor({ modelPath, value, onChange }: YamlEditorProps): JSX.Element {
  function handleBeforeMount(monaco: Monaco): void {
    configureYamlSchemas(monaco);
  }

  return (
    <div className="overflow-hidden rounded-xl border border-outline-variant">
      <Editor
        beforeMount={handleBeforeMount}
        path={modelPath}
        defaultLanguage="yaml"
        height={`${EDITOR_HEIGHT_PX}px`}
        value={value}
        onChange={(nextValue) => {
          onChange(nextValue ?? "");
        }}
        options={{
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          fontSize: 13,
          wordWrap: "on",
          automaticLayout: true,
        }}
      />
    </div>
  );
}
