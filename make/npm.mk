# The npm targets for repositories that use jmerhar/devtools, included by devtools.mk when the
# fetcher has fetched this file. They install and regenerate each directory [npm] dirs lists:
#
#   [fetch]
#   files = ["make/devtools.mk", "make/npm.mk", "bin/npm-ci.sh", "bin/lockfile.sh",
#            "bin/check-lockfile.sh"]
#
#   [npm]
#   dirs = ["frontend"]
#
# A repository's install target, which also sets up anything else it needs, runs
# `$(MAKE) node-modules`.

.PHONY: node-modules lockfile

##@ npm

node-modules: ## Install each npm directory's node_modules from its lockfile
	@$(DEVTOOLS_BIN)/npm-ci.sh

lockfile: ## Regenerate each npm directory's package-lock.json (Linux binaries; needs Docker)
	@$(DEVTOOLS_BIN)/lockfile.sh
