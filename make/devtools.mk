# Shared Makefile targets for repositories that use jmerhar/devtools.
#
# Fetched into .devtools/ by bin/devtools-fetch.sh and included from the repository's Makefile,
# which also tells make how to fetch it when it is missing or older than devtools.toml:
#
#   .DEFAULT_GOAL := help
#   include .devtools/make/devtools.mk
#   .devtools/make/devtools.mk: devtools.toml bin/devtools-fetch.sh
#   	bin/devtools-fetch.sh
#
# The repository keeps its own test, dev, build and deploy targets, and its own lint and check.
# The help target lists every target, here and in the Makefile, that has a `## description`;
# a `##@ Heading` line starts a section.

# Where the fetcher puts the tooling, and the fetcher itself.
DEVTOOLS_DIR ?= .devtools
DEVTOOLS_FETCH ?= bin/devtools-fetch.sh

# The coverage tooling from jmerhar/coverage, fetched when devtools.toml sets `coverage = true`:
#   bash $(COVERAGE_TOOLING)/run-kcov.sh
#   python3 $(COVERAGE_TOOLING)/coverage-report.py --gate
COVERAGE_TOOLING := $(DEVTOOLS_DIR)/coverage

.PHONY: help devtools-update coverage-tooling

##@ Shared tooling

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "} \
		/^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5); next} \
		/^[a-zA-Z0-9_.\/-]+:.*## / {printf "  \033[36mmake %-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

devtools-update: ## Fetch the shared tooling at the ref devtools.toml pins
	@$(DEVTOOLS_FETCH)

# Refreshed on every coverage run, because v1 moves within its major version and a local summary
# should gate on exactly what CI does.
coverage-tooling: devtools-update ## Fetch the shared coverage tooling
