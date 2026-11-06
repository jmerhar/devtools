import type { Linter } from "eslint";

/** Output and dependencies, never linted. */
export declare const IGNORES: string[];
/** Plain JavaScript, linted with the recommended JavaScript rules. */
export declare const JS_FILES: string[];
/** Files written for Node rather than the browser, linted with Node's globals. */
export declare const NODE_FILES: string[];
/** The configuration for an application's browser code. */
export declare function base(options?: {
  files?: string[];
  ignores?: string[];
  globals?: Record<string, "readonly" | "writable" | "off">;
}): Linter.Config[];
/** Node's globals for files that run in Node: build scripts and configuration files. */
export declare function node(files?: string[]): Linter.Config;
