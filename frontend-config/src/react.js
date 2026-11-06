// @ts-check
/**
 * The React rules for the shared ESLint configuration: hooks used correctly, and modules that keep
 * fast refresh working. Needs eslint-plugin-react-hooks and eslint-plugin-react-refresh.
 *
 * @module
 */
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

/**
 * The React configuration, applied to the files that hold components.
 *
 * @param {string[]} [files] Those files.
 * @returns {import("eslint").Linter.Config} A flat configuration object.
 */
export function react(files = ["**/*.{ts,tsx}"]) {
  return {
    files,
    // The plugins' own types describe more than ESLint's plugin type allows, though ESLint loads them.
    plugins: {
      "react-hooks": /** @type {import("eslint").ESLint.Plugin} */ (/** @type {unknown} */ (reactHooks)),
      "react-refresh": /** @type {import("eslint").ESLint.Plugin} */ (/** @type {unknown} */ (reactRefresh)),
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  };
}
