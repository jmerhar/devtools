// @ts-check
// The Vite and Vitest presets, the TypeScript base and the files the package publishes.
import { existsSync, readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { API_TARGET, BROWSERS, app } from "../src/vite.js";
import { COVERAGE_REPORTERS, test as testConfig } from "../src/vitest.js";

const root = new URL("..", import.meta.url);

describe("vite", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("proxies /api to the API's default port and builds for the supported browsers", () => {
    vi.stubEnv("VITE_API_TARGET", "");
    expect(app()).toEqual({
      server: { proxy: { "/api": API_TARGET } },
      build: { target: BROWSERS, license: { fileName: "licenses.md" } },
    });
  });

  it("proxies /api to VITE_API_TARGET, then to the target given", () => {
    vi.stubEnv("VITE_API_TARGET", "http://api:8000");
    expect(app({ apiTarget: "http://elsewhere" }).server.proxy["/api"]).toBe("http://api:8000");
    vi.stubEnv("VITE_API_TARGET", "");
    expect(app({ apiTarget: "http://elsewhere" }).server.proxy["/api"]).toBe("http://elsewhere");
  });

  it("returns a fresh list each time", () => {
    app().build.target.push("ie11");
    expect(app().build.target).toEqual(BROWSERS);
  });
});

describe("vitest", () => {
  it("runs in jsdom and measures the sources, not the tests", () => {
    expect(testConfig()).toEqual({
      environment: "jsdom",
      include: ["src/**/*.test.{ts,tsx}"],
      setupFiles: [],
      coverage: {
        provider: "v8",
        include: ["src/**/*.{ts,tsx,svelte}"],
        exclude: ["src/**/*.test.{ts,tsx}"],
        reporter: COVERAGE_REPORTERS,
        reportsDirectory: "coverage",
      },
    });
  });

  it("takes the application's own files", () => {
    const config = testConfig({
      include: ["src/**/*.test.ts"],
      setupFiles: ["src/test-setup.ts"],
      coverage: { include: ["src/**/*.{ts,svelte}"], exclude: ["src/main.ts"] },
    });
    expect(config.setupFiles).toEqual(["src/test-setup.ts"]);
    expect(config.coverage.include).toEqual(["src/**/*.{ts,svelte}"]);
    expect(config.coverage.exclude).toEqual(["src/**/*.test.ts", "src/main.ts"]);
  });

  it("writes the summary the coverage gate reads", () => {
    expect(COVERAGE_REPORTERS).toContain("json-summary");
    expect(COVERAGE_REPORTERS).toContain("lcov");
  });

  it("adds a JUnit report when asked", () => {
    expect(testConfig().reporters).toBeUndefined();
    const config = testConfig({ junit: true });
    expect(config.reporters).toEqual(["default", "junit"]);
    expect(config.outputFile).toEqual({ junit: "junit/vitest.xml" });
  });
});

describe("the published files", () => {
  const pkg = JSON.parse(readFileSync(new URL("package.json", root), "utf8"));

  it("has every file its exports name", () => {
    for (const target of Object.values(pkg.exports)) {
      const paths = typeof target === "string" ? [target] : Object.values(target);
      for (const path of paths) expect(existsSync(new URL(path, root)), path).toBe(true);
    }
  });

  it("has a strict TypeScript base", () => {
    const options = JSON.parse(readFileSync(new URL("tsconfig.base.json", root), "utf8")).compilerOptions;
    expect(options).toMatchObject({
      strict: true,
      target: "ES2022",
      moduleResolution: "bundler",
      isolatedModules: true,
      verbatimModuleSyntax: true,
      noEmit: true,
      noUncheckedIndexedAccess: true,
    });
  });

  it("has an .npmrc template naming only the public registry", () => {
    const template = readFileSync(new URL("npmrc.template", root), "utf8");
    const settings = template.split("\n").filter((line) => line && !line.startsWith("#"));
    expect(settings).toEqual(["registry=https://registry.npmjs.org/"]);
  });
});
