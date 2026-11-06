.DEFAULT_GOAL := help
.PHONY: install test lint coverage check clean

# This repository uses its own devtools.mk from the working tree rather than a fetched copy, so a
# change to it is exercised here before it is released; the fetcher is its source copy.
DEVTOOLS_FETCH := fetch/devtools-fetch.sh
include make/devtools.mk

##@ Setup

install: ## Create the virtualenv with pytest, coverage and ruff (bats and ShellCheck: brew install bats-core shellcheck)
	python3 -m venv .venv
	.venv/bin/pip install --quiet --upgrade pip
	.venv/bin/pip install --quiet -r requirements-dev.txt

##@ Checks

test: ## Run the bats and pytest suites (ARGS pass through to pytest)
	tooling/test.sh $(ARGS)

lint: ## ShellCheck, ruff, actionlint and the lockfile's registry
	tooling/lint.sh

coverage: coverage-tooling ## Measure every suite and enforce the gates in coverage.toml
	tooling/coverage-python.sh
	tooling/frontend-config.sh
	bash $(COVERAGE_TOOLING)/run-kcov.sh
	python3 $(COVERAGE_TOOLING)/coverage-report.py --gate --format md

check: lint coverage ## Everything (gate a commit on this)

##@ Housekeeping

clean: ## Remove test and coverage output
	rm -rf coverage junit .coverage .ruff_cache .devtools frontend-config/coverage \
		frontend-config/junit
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
