// @ts-check
/**
 * The Svelte rules for the shared ESLint configuration: eslint-plugin-svelte's recommended rules
 * for components and rune modules, with their TypeScript parsed by typescript-eslint so the base
 * configuration's TypeScript rules apply inside `<script lang="ts">` as well. Needs
 * eslint-plugin-svelte. Place it after base(), whose TypeScript parser it replaces for these files:
 *
 *   export default [...base(), ...svelte()];
 *
 * @module
 */
import sveltePlugin from "eslint-plugin-svelte";
import tseslint from "typescript-eslint";
import { TYPESCRIPT_RULES } from "./eslint.js";

/** Components, and the modules that use runes outside a component. */
export const SVELTE_FILES = ["**/*.svelte", "**/*.svelte.ts", "**/*.svelte.js"];

/**
 * The Svelte configuration.
 *
 * @param {string[]} [files] The files it applies to, {@link SVELTE_FILES} unless given.
 * @returns {import("eslint").Linter.Config[]} Flat configuration objects.
 */
export function svelte(files = SVELTE_FILES) {
  // The plugin's own types describe more than ESLint's configuration type allows, though ESLint
  // loads them.
  const recommended = /** @type {import("eslint").Linter.Config[]} */ (
    /** @type {unknown} */ (sveltePlugin.configs["flat/recommended"])
  );
  return [
    ...recommended.map((config) => (config.files ? { ...config, files } : config)),
    {
      files,
      languageOptions: {
        parserOptions: {
          parser: tseslint.parser,
          extraFileExtensions: [".svelte"],
        },
      },
      // The base configuration's TypeScript rules reach only .ts and .tsx files.
      plugins: { "@typescript-eslint": /** @type {import("eslint").ESLint.Plugin} */ (tseslint.plugin) },
      rules: {
        ...TYPESCRIPT_RULES,
        // Props come from `let { ... } = $props()`, which the core rule would have be const;
        // the plugin's rule knows the runes.
        "prefer-const": "off",
        "svelte/prefer-const": "error",
      },
    },
  ];
}
