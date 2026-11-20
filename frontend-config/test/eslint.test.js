// @ts-check
// The ESLint configuration, applied to real files by ESLint itself.
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";
import { IGNORES, NODE_FILES, base, node } from "../src/eslint.js";
import { react } from "../src/react.js";
import { SVELTE_FILES, svelte } from "../src/svelte.js";

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

describe("svelte", () => {
  const config = [...base(), ...svelte()];

  it("passes a clean TypeScript component and rune module", async () => {
    const result = await lint(config, {
      "src/Ok.svelte":
        '<script lang="ts">\n  let { name }: { name: string } = $props();\n</script>\n\n<p>{name}</p>\n',
      "src/count.svelte.ts":
        "let count = $state(0);\nexport const increment = (): number => (count += 1);\n",
    });
    expect(result["src/Ok.svelte"]).toEqual([]);
    expect(result["src/count.svelte.ts"]).toEqual([]);
  });

  it("applies the TypeScript rules inside a component's script", async () => {
    const result = await lint(config, {
      "src/Bad.svelte": '<script lang="ts">\n  const unused: number = 1;\n</script>\n\n<p>x</p>\n',
    });
    expect(result["src/Bad.svelte"]).toEqual(["@typescript-eslint/no-unused-vars"]);
  });

  it("reports the Svelte rules", async () => {
    const result = await lint(config, {
      "src/Html.svelte": '<script lang="ts">\n  let { html }: { html: string } = $props();\n</script>\n\n{@html html}\n',
      "src/Each.svelte": "<script lang=\"ts\">\n  let { items }: { items: string[] } = $props();\n</script>\n\n{#each items as item}<p>{item}</p>{/each}\n",
    });
    expect(result["src/Html.svelte"]).toEqual(["svelte/no-at-html-tags"]);
    expect(result["src/Each.svelte"]).toEqual(["svelte/require-each-key"]);
  });

  it("applies to the files given", async () => {
    expect(svelte(["app/**/*.svelte"]).filter((c) => c.files).every((c) => c.files?.[0] === "app/**/*.svelte")).toBe(true);
    expect(svelte().filter((c) => c.files).every((c) => c.files === SVELTE_FILES)).toBe(true);
  });
});
