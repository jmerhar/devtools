#!/usr/bin/env bats
# shellcheck disable=SC2016  # stub bodies are written literally, to expand when the stub runs
# bin/release.sh against a real git repository, and bin/github-release.sh with gh stubbed.

load test_helper

setup() {
  setup_repo
  export STUB_LOG="$BATS_TEST_TMPDIR/calls"
  : > "$STUB_LOG"
  STUBS="$BATS_TEST_TMPDIR/stubs"
  # Nothing from the machine's own git configuration, such as a signing key.
  export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
  git init -q -b main .
  git config user.name "Test" && git config user.email "test@example.com"
  cat > devtools.toml <<'TOML'
[version]
pyprojects = ["pyproject.toml"]

[release]
title = "My app"
TOML
  printf '[project]\nname = "myapp"\nversion = "1.1.0"\n' > pyproject.toml
  printf '# Changelog\n\n## Unreleased\n\n### Fixed\n\n- A bug.\n\n## 1.1.0 — 2026-10-01\n\n- Before.\n' > CHANGELOG.md
  git add . && git commit -q -m "chore: start"
}

@test "release commits the version and tags it with the notes, headings intact" {
  run_script bin/release.sh 1.2.0
  [ "$status" -eq 0 ]
  [[ "$output" == *"Released 1.2.0. Publish it with: git push origin main v1.2.0"* ]]
  [ "$(git log -1 --format=%s)" = "chore(release): 1.2.0" ]
  grep -q 'version = "1.2.0"' pyproject.toml
  grep -q '^## 1.2.0 — ' CHANGELOG.md
  [ "$(git cat-file -t v1.2.0)" = "tag" ]
  [ "$(git tag -l --format='%(contents)' v1.2.0)" = $'My app 1.2.0\n\n### Fixed\n\n- A bug.' ]
  [ -z "$(git status --porcelain)" ]
}

@test "release prints the note devtools.toml sets" {
  printf '[version]\npyprojects = ["pyproject.toml"]\n\n[release]\ntitle = "My app"\nnote = "Run make install."\n' > devtools.toml
  git commit -q -am "chore: note"
  run_script bin/release.sh 1.2.0
  [ "$status" -eq 0 ]
  [ "${lines[-1]}" = "Run make install." ]
}

@test "release refuses a dirty working tree" {
  echo change >> CHANGELOG.md
  run_script bin/release.sh 1.2.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"the working tree has changes"* ]]
  [ -z "$(git tag)" ]
}

@test "release refuses a branch other than main" {
  git checkout -q -b feature
  run_script bin/release.sh 1.2.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"releases are cut from main"* ]]
}

@test "release leaves neither a commit nor a tag when the version cannot be cut" {
  run_script bin/release.sh 1.0.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"1.0.0 is not after 1.1.0"* ]]
  [ "$(git log -1 --format=%s)" = "chore: start" ]
  [ -z "$(git tag)" ]
  [ -z "$(git status --porcelain)" ]
}

@test "release needs a version argument and a title" {
  run_script bin/release.sh
  [ "$status" -ne 0 ]
  [[ "$output" == *"usage: .devtools/bin/release.sh X.Y.Z"* ]]
  printf '[version]\npyprojects = ["pyproject.toml"]\n' > devtools.toml
  run_script bin/release.sh 1.2.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"devtools.toml sets no release.title"* ]]
}

@test "github-release creates the release from the tag's changelog section" {
  run_script bin/release.sh 1.2.0
  make_stub "$STUBS/gh" '[ "$2" = view ] && exit 1' 'cat > "$STUB_LOG.notes"'
  GH="$STUBS/gh" run_script bin/github-release.sh v1.2.0
  [ "$status" -eq 0 ]
  [ "$(tail -1 "$STUB_LOG")" = "gh release create v1.2.0 --verify-tag --title My app 1.2.0 --notes-file -" ]
  [ "$(cat "$STUB_LOG.notes")" = $'### Fixed\n\n- A bug.' ]
}

@test "github-release leaves an existing release alone" {
  run_script bin/release.sh 1.2.0
  make_stub "$STUBS/gh"
  GH="$STUBS/gh" run_script bin/github-release.sh v1.2.0
  [ "$status" -eq 0 ]
  [[ "$output" == *"v1.2.0 already has a release"* ]]
  refute grep -q 'release create' "$STUB_LOG"
}

@test "github-release refuses a tag the manifests do not name" {
  make_stub "$STUBS/gh"
  GH="$STUBS/gh" run_script bin/github-release.sh v9.0.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"the tag is v9.0.0, but the manifests name 1.1.0"* ]]
  [ ! -s "$STUB_LOG" ]
}

@test "release refuses a tag that exists, before changing anything" {
  git tag v1.2.0
  run_script bin/release.sh 1.2.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"the tag v1.2.0 already exists"* ]]
  [ "$(git log -1 --format=%s)" = "chore: start" ]
  [ -z "$(git status --porcelain)" ]
}

@test "release restores the files when the commit fails" {
  printf '#!/bin/sh\nexit 1\n' > .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
  run_script bin/release.sh 1.2.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"the commit failed; the files are restored"* ]]
  [ -z "$(git status --porcelain)" ]
  [ -z "$(git tag)" ]
  rm .git/hooks/pre-commit
  run_script bin/release.sh 1.2.0
  [ "$status" -eq 0 ]
}

@test "release undoes the commit when tagging fails" {
  # A signing key with a signing program that always fails, so the tag fails after the commit.
  git config user.signingkey "test-key"
  git config gpg.program false
  run_script bin/release.sh 1.2.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"tagging failed; the release commit is undone"* ]]
  [ "$(git log -1 --format=%s)" = "chore: start" ]
  [ -z "$(git status --porcelain)" ]
  [ -z "$(git tag)" ]
}

@test "release and github-release need version.py beside them" {
  mkdir -p alone
  ln -s "$DEVTOOLS_ROOT/bin/release.sh" "$DEVTOOLS_ROOT/bin/github-release.sh" alone/
  run_alone release.sh 1.2.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"add bin/version.py to [fetch] files"* ]]
  run_alone github-release.sh v1.2.0
  [ "$status" -eq 1 ]
  [[ "$output" == *"add bin/version.py to [fetch] files"* ]]
}
