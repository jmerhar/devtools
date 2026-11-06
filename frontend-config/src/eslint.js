// @ts-check
/**
 * The shared ESLint flat configuration: the recommended typescript-eslint rules for an
 * application's TypeScript, the recommended JavaScript rules for its plain JavaScript, and Node's
 * globals for the scripts and configuration files that run in Node. TypeScript reports undefined
 * names itself, so the globals matter to the JavaScript.
 *
 *   import { base, node } from "@jmerhar/frontend-config/eslint";
 *   import { react } from "@jmerhar/frontend-config/eslint/react";
 *
 *   export default [...base(), react(), node(["bin/**\/*.mjs"])];
 *
 * @module
 */
import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

/** Output and dependencies, never linted. */
export const IGNORES = ["dist", "coverage", "coverage-upload", "junit", "node_modules"];

/** Files written for Node rather than the browser, linted with Node's globals. */
export const NODE_FILES = ["*.config.{js,mjs,cjs,ts}"];

/** Plain JavaScript, linted with the recommended JavaScript rules. */
export const JS_FILES = ["**/*.{js,mjs,cjs}"];

/**
 * The configuration for an application's browser code.
 *
 * @param {object} [options]
 * @param {string[]} [options.files] The TypeScript files the typescript-eslint rules apply to.
 * @param {string[]} [options.ignores] More paths never linted, besides {@link IGNORES}.
 * @param {Record<string, "readonly" | "writable" | "off">} [options.globals] More browser globals,
 *   such as an extension API.
 * @returns {import("eslint").Linter.Config[]} Flat configuration objects.
 */
export function base({ files = ["**/*.{ts,tsx}"], ignores = [], globals: extra = {} } = {}) {
  const languageOptions = { ecmaVersion: /** @type {const} */ (2022), globals: { ...globals.browser, ...extra } };
  const typescript = tseslint.config({
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files,
    languageOptions,
    rules: {
      // An argument named with a leading underscore is unused on purpose, kept for its position.
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  });
  return [
    { ignores: [...IGNORES, ...ignores] },
    {
      files: JS_FILES,
      ...js.configs.recommended,
      languageOptions: { ...languageOptions, sourceType: "module" },
      rules: {
        ...js.configs.recommended.rules,
        "no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      },
    },
    // typescript-eslint's configuration types are its own; ESLint reads them as its own too.
    .../** @type {import("eslint").Linter.Config[]} */ (/** @type {unknown} */ (typescript)),
  ];
}

/**
 * Node's globals for files that run in Node: build scripts and configuration files.
 *
 * @param {string[]} [files] Those files, besides {@link NODE_FILES}.
 * @returns {import("eslint").Linter.Config} A flat configuration object.
 */
export function node(files = []) {
  return { files: [...NODE_FILES, ...files], languageOptions: { globals: globals.node } };
}
