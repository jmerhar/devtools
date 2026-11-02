# Changelog

All notable changes to devtools are recorded here. Releases are tagged `vX.Y.Z`, and `v1` moves
to the latest `v1.x.y`.

## Unreleased

### Added

- `bin/lint.sh`, which runs the checks `[lint]` lists and the repository's own commands.
- `bin/lockfile.sh` and `bin/check-lockfile.sh`, for any number of npm directories; the check
  compares URLs as a literal prefix and also covers every lockfile git tracks.
- `bin/version.py`, `bin/release.sh` and `bin/github-release.sh`, with the manifests, images and
  release title in devtools.toml, and development versions such as `1.2.0.dev0`.
- `bin/openapi.sh` and `bin/export-openapi.py`, which builds the app through a callable the
  repository names.
- `bin/test-bruno.sh`, `bin/app-icons.sh` and `bin/inspect.sh`.

## 1.0.1 — 2026-11-02

### Changed

- `config/ruff.toml` also ignores import order (I001) in Alembic's generated migrations, which
  ruff sorts differently when the config sits beside the local `alembic/` directory.

## 1.0.0 — 2026-11-02

### Added

- `fetch/devtools-fetch.sh`: the fetcher each repository vendors as `bin/devtools-fetch.sh`. It
  downloads the files `devtools.toml` lists at a pinned ref, and the coverage tooling from
  jmerhar/coverage, into `.devtools/`, keeping the copy on disk when a download fails.
- `bin/devtools-config.py`: prints one setting from `devtools.toml` for the fetched scripts.
- `make/devtools.mk`: `help`, `devtools-update` and `coverage-tooling`.
- `config/ruff.toml`: the shared ruff rules.
- `bin/ci-ruff.sh`, `bin/check-compose.sh` and `bin/dev.sh`.
