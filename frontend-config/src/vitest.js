// @ts-check
/**
 * The shared Vitest settings: tests in jsdom, and v8 coverage written where coverage.toml's shared
 * tooling reads it (coverage/coverage-summary.json), with lcov for Codecov and an HTML report.
 *
 *   import { defineConfig } from "vitest/config";
 *   import { test } from "@jmerhar/frontend-config/vitest";
 *
 *   export default defineConfig({ test: test({ coverage: { exclude: ["src/main.ts"] } }) });
 *
 * @module
 */

/**
 * The coverage reports: json-summary for the shared gate, lcov for Codecov, and HTML.
 *
 * @type {import("./vitest.d.ts").Reporter[]}
 */
export const COVERAGE_REPORTERS = ["text", "json-summary", "json", "lcov", ["html", { subdir: "html" }]];

/**
 * The test settings.
 *
 * @param {object} [options]
 * @param {string[]} [options.include] The test files.
 * @param {string[]} [options.setupFiles] Files run before each test file.
 * @param {{ include?: string[], exclude?: string[] }} [options.coverage] The source files measured,
 *   and those left out besides the tests themselves.
 * @param {boolean} [options.junit] Also write a JUnit report to junit/vitest.xml, for Codecov's test
 *   analytics.
 * @returns {import("./vitest.d.ts").TestConfig} The `test` section of a Vitest configuration.
 */
export function test({
  include = ["src/**/*.test.{ts,tsx}"],
  setupFiles = [],
  coverage = {},
  junit = false,
} = {}) {
  return {
    environment: "jsdom",
    include,
    setupFiles,
    ...(junit ? { reporters: ["default", "junit"], outputFile: { junit: "junit/vitest.xml" } } : {}),
    coverage: {
      provider: "v8",
      include: coverage.include ?? ["src/**/*.{ts,tsx,svelte}"],
      exclude: [...include, ...(coverage.exclude ?? [])],
      reporter: COVERAGE_REPORTERS,
      reportsDirectory: "coverage",
    },
  };
}
