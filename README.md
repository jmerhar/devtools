# devtools

Shared build and CI tooling for my repositories: the scripts, Makefile targets and config presets
each of them would otherwise carry its own copy of. Nothing here runs in production; it runs in CI
and on a developer's machine.

A repository commits one file from here, the fetcher, and declares in `devtools.toml` what to
fetch. Everything else is downloaded into a gitignored `.devtools/` at a pinned ref, so a fix made
here reaches every repository on its next fetch: every CI run, and locally whenever
`devtools.toml` changes or `make devtools-update` runs.

## Adopting it

**1. Vendor the fetcher** as `bin/devtools-fetch.sh`, unchanged:

```sh
curl -fsSL -o bin/devtools-fetch.sh \
  https://raw.githubusercontent.com/jmerhar/devtools/v1/fetch/devtools-fetch.sh
chmod +x bin/devtools-fetch.sh
```

**2. Declare what to fetch** in `devtools.toml` at the repository root:

```toml
[fetch]
ref = "v1"
files = [
  "make/devtools.mk",
  "config/ruff.toml",
  "bin/ci-ruff.sh",
  "bin/check-compose.sh",
]
coverage = true   # coverage-report.py and run-kcov.sh from jmerhar/coverage at its own v1

# Settings for the fetched scripts; each script's section below names what it reads.
[compose]
stacks = [["docker-compose.yml"], ["docker-compose.yml", "docker-compose.build.yml"]]
```

Each file keeps its path under `.devtools/`, so `make/devtools.mk` lands at
`.devtools/make/devtools.mk`. `bin/devtools-config.py`, which the scripts read their settings
through, comes along whenever any file is listed. `.devtools/` writes its own `.gitignore`, so it
needs no entry in the repository's.

**3. Include the shared targets** at the top of the Makefile:

```make
.DEFAULT_GOAL := help
include .devtools/make/devtools.mk
.devtools/make/devtools.mk: devtools.toml bin/devtools-fetch.sh
	bin/devtools-fetch.sh
```

make fetches the tooling on the first run and whenever `devtools.toml` changes;
`make devtools-update` fetches it again. A failed fetch stops make, and the next make tries again.
(make 3.81 first warns that the included file does not exist yet.)

**4. Fetch in CI** before any step that uses `.devtools/`:

```yaml
- run: bin/devtools-fetch.sh
```

## The fetcher

`bin/devtools-fetch.sh` reads the `[fetch]` table and downloads each file from
`raw.githubusercontent.com` at `ref`.

- Each download goes to a temporary name first and is moved into place, so an interrupted
  transfer never replaces a good copy.
- When the network fails, the copy already on disk is kept with a warning, so a local run works
  offline.
- Any other failure fails the run, after the remaining files have been tried: a file with no copy
  on disk, or one the server does not have, which means a wrong ref or path.
- `ref`, `files` and `coverage` are the only keys. A path must stay inside `.devtools/`, and a ref
  must be a plain git ref.

Run it from the repository root; it needs `curl` and Python 3.11 or newer, for `tomllib`.
`DEVTOOLS_URL` and `COVERAGE_URL` override where it fetches from, and `DEVTOOLS_FETCH_RETRIES`
(default 2) and `DEVTOOLS_FETCH_TIMEOUT` (seconds per attempt, default 60) how hard it tries.

## Shared Makefile targets

`make/devtools.mk` provides:

| Target | Does |
|---|---|
| `help` | lists the targets whose rule line ends in a `## description`, in `##@ Heading` sections |
| `devtools-update` | runs the fetcher |
| `coverage-tooling` | the same; refreshes the coverage tooling before a coverage run |

It also sets `COVERAGE_TOOLING` to `.devtools/coverage`, for a repository's own coverage target:

```make
coverage: coverage-tooling
	bash $(COVERAGE_TOOLING)/run-kcov.sh
	python3 $(COVERAGE_TOOLING)/coverage-report.py --gate
```

The repository keeps its own `test`, `lint`, `check`, `dev`, `build` and `deploy` targets.

## Scripts

Every script acts on the current directory, so run it from the repository root, as make and CI
do. Commands they drive can be replaced through the environment (`DOCKER`, `NPM`, `RUFF`).

| Script | Does | Reads from `devtools.toml` |
|---|---|---|
| `bin/ci-ruff.sh` | `ruff check` and `ruff format --check` over the repository | — |
| `bin/check-compose.sh` | `docker compose config -q` for each stack | `[compose] stacks`: lists of files passed together with `-f` |
| `bin/dev.sh` | `docker compose up --build` with hot reload, handing compose the registry npm reaches as `NPM_REGISTRY` unless the environment or `.env` sets it | `[dev] compose_files`: a list of files |
| `bin/devtools-config.py` | prints one setting, for the scripts above | — |

## Config presets

**`config/ruff.toml`** holds the shared ruff rules: line length 100, Python 3.14, the rule sets
`E F W I B C4 UP ARG SIM`, unused-argument checks off under `tests/` and `test/`, and line-length
and import-order checks off in Alembic's generated migrations. A repository's `ruff.toml` extends it:

```toml
extend = ".devtools/config/ruff.toml"

[lint.isort]
known-first-party = ["myapp"]
```

## Versioning

Tags are semver, `vX.Y.Z`, and `v1` moves to the latest `v1.x.y`. A repository pins `v1` and
picks up fixes on its next fetch; a breaking change goes to `v2`.

## Developing

`make install` creates the virtualenv; bats and ShellCheck come from Homebrew
(`brew install bats-core shellcheck`). `make check` runs ShellCheck, ruff, both suites and the
coverage gates in `coverage.toml`: the bats suites under kcov for the shell, and pytest under
coverage.py for the Python. kcov runs locally when it can trace with a modern bash, and in the
coverage repository's pinned container otherwise.

## License

MIT
