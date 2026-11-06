// @ts-check
/**
 * The shared Vite settings for an application whose interface is served beside its API: the dev
 * server hands /api to the API, and a build targets the browsers below and writes the licences of
 * everything bundled. Merged into an application's own configuration:
 *
 *   import { mergeConfig } from "vite";
 *   import { app } from "@jmerhar/frontend-config/vite";
 *
 *   export default mergeConfig(app(), { plugins: [svelte()] });
 *
 * @module
 */

/** The oldest browsers a build supports. */
export const BROWSERS = ["chrome109", "edge109", "firefox115", "safari16", "ios16"];

/** Where the dev server sends /api when VITE_API_TARGET is unset: the API's default port. */
export const API_TARGET = "http://127.0.0.1:8000";

/**
 * The settings, with the API's address read from VITE_API_TARGET when it is set.
 *
 * @param {object} [options]
 * @param {string} [options.apiTarget] Where /api goes when VITE_API_TARGET is unset.
 * @returns {import("./vite.d.ts").AppConfig} Settings to merge into the application's own.
 */
export function app({ apiTarget = API_TARGET } = {}) {
  const target = process.env.VITE_API_TARGET || apiTarget;
  return {
    server: { proxy: { "/api": target } },
    build: {
      target: [...BROWSERS],
      // The licences of everything bundled, which theirs ask to travel with it.
      license: { fileName: "licenses.md" },
    },
  };
}
