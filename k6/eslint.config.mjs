import globals from "globals";

import js from "@eslint/js";
import tseslint from "typescript-eslint";
import eslintConfigPrettier from "eslint-config-prettier/flat";

// Framework-agnostic subset of navigator-frontend's eslint.config.mjs rules —
// no React/Next.js/Storybook/import-order, none of which applies to k6
// scripts. @types/k6 declares k6's globals (__ENV, __VU, open, etc.) and
// modules (k6/http, k6/data, ...) as real ambient TS types, so no manual
// globals list or import-resolver config is needed for those to resolve.
const eslintConfig = [
  {
    ignores: ["**/node_modules", "**/dist"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.ts"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.es2025,
      },
    },
    rules: {
      eqeqeq: "warn",
      "no-console": ["warn", { allow: ["error"] }],
      "prefer-const": "warn",
      "no-var": "warn",
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/no-unsafe-function-type": "warn",
      "@typescript-eslint/no-unused-vars": "warn",
      "@typescript-eslint/no-unused-expressions": "warn",
      "@typescript-eslint/no-wrapper-object-types": "warn",
      "@typescript-eslint/no-empty-object-type": "warn",
    },
  },
  eslintConfigPrettier,
];

export default eslintConfig;
