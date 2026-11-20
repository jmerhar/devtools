# Changelog

All notable changes to @jmerhar/frontend-config are recorded here. Releases are tagged
`frontend-config-vX.Y.Z` in jmerhar/devtools.

## Unreleased

## 0.2.0 — 2026-11-20

### Added

- `eslint/svelte`: `svelte()`, eslint-plugin-svelte's recommended rules and the TypeScript rules
  for components and rune modules.
- `eslint`: `UNUSED_ARGS` and `TYPESCRIPT_RULES`, the rule settings `base()` applies.

### Changed

- The README says `licenses.md` needs Vite 8 or later.

## 0.1.0 — 2026-11-16

### Added

- `eslint`: `base()` and `node()`; `eslint/react`: `react()`.
- `tsconfig.base.json`.
- `vite`: `app()`, with the `/api` proxy, browser targets and the licences file.
- `vitest`: `test()`, with jsdom, v8 coverage and an optional JUnit report.
- `npmrc.template`.
