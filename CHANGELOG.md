# Changelog

All notable changes to devtools are recorded here. Releases are tagged `vX.Y.Z`, and `v1` moves
to the latest `v1.x.y`.

## Unreleased

### Added

- `fetch/devtools-fetch.sh`: the fetcher each repository vendors as `bin/devtools-fetch.sh`. It
  downloads the files `devtools.toml` lists at a pinned ref, and the coverage tooling from
  jmerhar/coverage, into `.devtools/`, keeping the copy on disk when a download fails.
- `bin/devtools-config.py`: prints one setting from `devtools.toml` for the fetched scripts.
- `make/devtools.mk`: `help`, `devtools-update` and `coverage-tooling`.
- `config/ruff.toml`: the shared ruff rules.
