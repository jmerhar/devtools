#!/usr/bin/env bats
# tooling/frontend-config-version.sh, against a copy of the package's manifest and changelog.

load test_helper

setup() {
  setup_repo
  mkdir -p tooling frontend-config
  cp "$DEVTOOLS_ROOT/tooling/frontend-config-version.sh" tooling/
  printf '{ "name": "@jmerhar/frontend-config", "version": "1.2.0" }\n' > frontend-config/package.json
  printf '# Changelog\n\n## 1.2.0 — 2026-11-06\n\n- A change.\n' > frontend-config/CHANGELOG.md
}

@test "frontend-config-version passes a tag that names the package's released version" {
  run tooling/frontend-config-version.sh frontend-config-v1.2.0
  [ "$status" -eq 0 ]
  [[ "$output" == *"frontend-config-v1.2.0 matches package.json and CHANGELOG.md"* ]]
}

@test "frontend-config-version refuses a tag for another version" {
  run tooling/frontend-config-version.sh frontend-config-v1.3.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"the tag is frontend-config-v1.3.0, but package.json names 1.2.0"* ]]
}

@test "frontend-config-version needs the version's dated changelog section" {
  printf '# Changelog\n\n## Unreleased\n\n## 1.20.0 — 2026-11-06\n' > frontend-config/CHANGELOG.md
  run tooling/frontend-config-version.sh frontend-config-v1.2.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"CHANGELOG.md has no dated section for 1.2.0"* ]]
}
