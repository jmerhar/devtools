// @ts-check
// The package's own tests, in Node, with coverage where coverage.toml's js suite reads it.
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["test/**/*.test.js"],
    reporters: ["default", "junit"],
    outputFile: { junit: "junit/vitest.xml" },
    coverage: {
      provider: "v8",
      include: ["src/**/*.js"],
      reporter: ["text", "json-summary", ["html", { subdir: "html" }]],
      reportsDirectory: "coverage",
    },
  },
});
