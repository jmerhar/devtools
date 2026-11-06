// @ts-check
// The ESLint configuration, applied to real files by ESLint itself.
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";
import { IGNORES, NODE_FILES, base, node } from "../src/eslint.js";
import { react } from "../src/react.js";

/**
 * Lint files in a scratch directory and return each file's rule ids.
 *
 * @param {import("eslint").Linter.Config[]} config
 * @param {Record<string, string>} files
 */
async function lint(config, files) {
  const cwd = mkdtempSync(join(tmpdir(), "frontend-config-"));
  for (const [name, text] of Object.entries(files)) {
    mkdirSync(dirname(join(cwd, name)), { recursive: true });
    writeFileSync(join(cwd, name), text);
  }
  const eslint = new ESLint({ cwd, overrideConfigFile: true, overrideConfig: config });
  const results = await eslint.lintFiles(Object.keys(files));
  return Object.fromEntries(
    results.map((r) => [r.filePath.slice(cwd.length + 1), r.messages.map((m) => m.ruleId)]),
  );
}

describe("base", () => {
  it("passes clean TypeScript and reports an unused variable", async () => {
    const result = await lint(base(), {
      "src/ok.ts": "export const double = (n: number): number => n * 2;\n",
      "src/bad.ts": "const unused = 1;\nexport {};\n",
    });
    expect(result["src/ok.ts"]).toEqual([]);
    expect(result["src/bad.ts"]).toEqual(["@typescript-eslint/no-unused-vars"]);
  });

  it("allows an unused argument named with an underscore", async () => {
    const result = await lint(base(), {
      "src/a.ts": "export const f = (first: number, _second: number): number => first;\n",
      "src/b.ts": "export const g = (first: number, second: number): number => first;\n",
    });
    expect(result["src/a.ts"]).toEqual([]);
    expect(result["src/b.ts"]).toEqual(["@typescript-eslint/no-unused-vars"]);
  });

  it("knows the browser's globals and the ones given", async () => {
    const result = await lint(base({ globals: { chrome: "readonly" } }), {
      "src/page.js": "document.title = String(chrome.runtime.id);\n",
      "src/other.js": "export const x = undeclared;\n",
    });
    expect(result["src/page.js"]).toEqual([]);
    expect(result["src/other.js"]).toEqual(["no-undef"]);
  });

  it("ignores output, dependencies and the paths given", async () => {
    const config = base({ ignores: ["generated"] });
    expect(config[0]).toEqual({ ignores: [...IGNORES, "generated"] });
    const eslint = new ESLint({ overrideConfigFile: true, overrideConfig: config });
    expect(await eslint.isPathIgnored("dist/app.js")).toBe(true);
    expect(await eslint.isPathIgnored("generated/types.js")).toBe(true);
    expect(await eslint.isPathIgnored("src/app.js")).toBe(false);
  });
});

describe("plain JavaScript", () => {
  it("is linted with the recommended rules, unused underscored arguments allowed", async () => {
    const result = await lint(base(), {
      "src/a.js": "export const f = (first, _second) => first;\n",
      "src/b.js": "export const g = (first, second) => first;\n",
    });
    expect(result["src/a.js"]).toEqual([]);
    expect(result["src/b.js"]).toEqual(["no-unused-vars"]);
  });
});

describe("node", () => {
  it("gives configuration files and the scripts named Node's globals", async () => {
    const files = {
      "vite.config.js": "export default { root: process.cwd() };\n",
      "bin/build.mjs": "process.exit(0);\n",
    };
    const plain = await lint(base(), files);
    expect(plain["vite.config.js"]).toEqual(["no-undef"]);
    expect(plain["bin/build.mjs"]).toEqual(["no-undef"]);
    const withNode = await lint([...base(), node(["bin/**/*.mjs"])], files);
    expect(withNode["vite.config.js"]).toEqual([]);
    expect(withNode["bin/build.mjs"]).toEqual([]);
    expect(node().files).toEqual(NODE_FILES);
  });
});

describe("react", () => {
  it("reports a hook called conditionally", async () => {
    const component = [
      'import { useState } from "react";',
      "export function Counter({ on }: { on: boolean }) {",
      "  if (on) {",
      "    const [count] = useState(0);",
      "    return count;",
      "  }",
      "  return 0;",
      "}",
      "",
    ].join("\n");
    const result = await lint([...base(), react()], { "src/Counter.tsx": component });
    expect(result["src/Counter.tsx"]).toContain("react-hooks/rules-of-hooks");
  });

  it("warns about a module that exports more than components", async () => {
    const module = [
      "export const helper = (n: number): number => n + 1;",
      "export function Thing() {",
      "  return null;",
      "}",
      "",
    ].join("\n");
    const result = await lint([...base(), react(["src/**/*.tsx"])], { "src/Thing.tsx": module });
    expect(result["src/Thing.tsx"]).toEqual(["react-refresh/only-export-components"]);
  });
});
