/** A coverage reporter, by name or with its options. */
export type Reporter = string | [string, Record<string, unknown>];

/** The `test` section test() returns. */
export interface TestConfig {
  environment: "jsdom";
  include: string[];
  setupFiles: string[];
  reporters?: string[];
  outputFile?: { junit: string };
  coverage: {
    provider: "v8";
    include: string[];
    exclude: string[];
    reporter: Reporter[];
    reportsDirectory: string;
  };
}

/** The coverage reports: json-summary for the shared gate, lcov for Codecov, and HTML. */
export declare const COVERAGE_REPORTERS: Reporter[];
/** The test settings. */
export declare function test(options?: {
  include?: string[];
  setupFiles?: string[];
  coverage?: { include?: string[]; exclude?: string[] };
  junit?: boolean;
}): TestConfig;
