/**
 * @packageDocumentation
 *
 * Monaco worker registration for Vite.
 */

import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import yamlWorker from "monaco-yaml/yaml.worker?worker";

interface MonacoEnvironmentShape {
  /** Resolve the worker implementation for one Monaco language label. */
  readonly getWorker: (_moduleId: string, label: string) => Worker;
}

const globalSelf = self as typeof self & {
  MonacoEnvironment?: MonacoEnvironmentShape;
};

globalSelf.MonacoEnvironment = {
  getWorker(_moduleId: string, label: string): Worker {
    if (label === "yaml") {
      return new yamlWorker();
    }
    return new editorWorker();
  },
};
