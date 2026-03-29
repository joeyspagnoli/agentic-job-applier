/**
 * @packageDocumentation
 *
 * ESLint flat-config for the AutoApply dashboard.
 *
 * @remarks
 * Uses typescript-eslint strict + stylistic type-checked rules,
 * tsdoc comment linting, and prettier compat layer to avoid
 * formatting conflicts.
 */

import eslint from "@eslint/js";
import tseslint from "typescript-eslint";
import tsdocPlugin from "eslint-plugin-tsdoc";
import prettierConfig from "eslint-config-prettier";

export default tseslint.config(
  eslint.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,
  prettierConfig,
  {
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: { tsdoc: tsdocPlugin },
    rules: {
      /* --- Safety --- */
      "no-console": "warn",
      "no-debugger": "error",
      eqeqeq: ["error", "always"],

      /* --- TypeScript --- */
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/explicit-function-return-type": ["error", { allowExpressions: true }],
      "@typescript-eslint/no-non-null-assertion": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/consistent-type-imports": ["error", { prefer: "type-imports" }],
      "@typescript-eslint/consistent-type-definitions": ["error", "interface"],

      /* --- TSDoc --- */
      "tsdoc/syntax": "warn",

      /* --- Architecture --- */
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["../**"],
              message: "Prefer absolute path aliases over parent traversal.",
            },
          ],
        },
      ],
    },
  },
  /* --- Test file overrides --- */
  {
    files: ["**/*.test.ts", "**/*.spec.ts", "**/*.test.tsx", "**/*.spec.tsx"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-non-null-assertion": "off",
      "@typescript-eslint/explicit-function-return-type": "off",
    },
  },
  /* --- Config file overrides --- */
  {
    files: ["*.config.ts", "*.config.js"],
    rules: {
      "@typescript-eslint/explicit-function-return-type": "off",
    },
  },
);
