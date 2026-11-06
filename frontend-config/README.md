# @jmerhar/frontend-config

Shared frontend build configuration: ESLint, TypeScript, Vite and Vitest presets for applications
whose interface is served beside a Python API.

```sh
npm install --save-dev @jmerhar/frontend-config
```

## ESLint

```js
// eslint.config.js
import { base, node } from "@jmerhar/frontend-config/eslint";
import { react } from "@jmerhar/frontend-config/eslint/react";

export default [...base(), react(), node(["bin/**/*.mjs"])];
```

`base()` applies the recommended typescript-eslint rules to `**/*.{ts,tsx}` and the recommended
JavaScript rules to plain JavaScript, with the browser's globals; an argument named with a
leading underscore may go unused. Its options name other TypeScript `files`, more `ignores`, and
more `globals`. `node()` gives configuration files, and the scripts named, Node's globals.
`react()` adds the React hooks and fast-refresh rules, and needs `eslint-plugin-react-hooks` and
`eslint-plugin-react-refresh`. Install `eslint`, `@eslint/js`, `typescript-eslint` and `globals`
beside it.

## TypeScript

```json
{
  "extends": "@jmerhar/frontend-config/tsconfig.base.json",
  "include": ["src"]
}
```

Strict, ES2022, bundler resolution, isolated modules and verbatim module syntax, with no output
of its own (`noEmit`) and checked index access (`noUncheckedIndexedAccess`).

## Vite

```ts
// vite.config.ts
import { mergeConfig } from "vite";
import { app } from "@jmerhar/frontend-config/vite";

export default mergeConfig(app(), { plugins: [svelte()] });
```

The dev server hands `/api` to `VITE_API_TARGET`, or to `http://127.0.0.1:8000` (`app({ apiTarget
})` names another), and a build targets the browsers in `BROWSERS` and writes the licences of
everything bundled to `licenses.md`.

## Vitest

```ts
import { test } from "@jmerhar/frontend-config/vitest";

export default defineConfig({
  test: test({ setupFiles: ["src/test-setup.ts"], coverage: { exclude: ["src/main.ts"] } }),
});
```

Tests run in jsdom, and v8 coverage is written to `coverage/`: `coverage-summary.json` for a
coverage gate, `lcov.info` for Codecov and an HTML report in `coverage/html`. `junit: true` also
writes `junit/vitest.xml`.

## npm

`npmrc.template` is the `.npmrc` an application commits so its lockfile records only the public
registry.
