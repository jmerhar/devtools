#!/usr/bin/env bats
# bin/pages-artifact.sh, archiving a built site.

load test_helper

setup() {
  setup_repo
  mkdir -p site/.well-known site/.git site/.github site/css outside
  echo "<html>" > site/index.html
  echo "{}" > site/.well-known/assetlinks.json
  echo "secret" > site/.git/config
  echo "ci" > site/.github/x.yml
  echo "body {}" > outside/style.css
  ln -s ../../outside/style.css site/css/style.css
}

@test "pages-artifact keeps hidden files, follows links and leaves git out" {
  run_script bin/pages-artifact.sh site "$BATS_TEST_TMPDIR/site.tar"
  [ "$status" -eq 0 ]
  [[ "$output" == *"archived site into"* ]]
  listing=$(tar -tf "$BATS_TEST_TMPDIR/site.tar")
  [[ "$listing" == *"./index.html"* ]]
  [[ "$listing" == *"./.well-known/assetlinks.json"* ]]
  [[ "$listing" != *".git/"* ]]
  [[ "$listing" != *".github/"* ]]
  mkdir extracted && tar -xf "$BATS_TEST_TMPDIR/site.tar" -C extracted
  [ ! -L extracted/css/style.css ]
  [ "$(cat extracted/css/style.css)" = "body {}" ]
}

@test "pages-artifact refuses a missing or empty site" {
  run_script bin/pages-artifact.sh nowhere "$BATS_TEST_TMPDIR/site.tar"
  [ "$status" -eq 1 ]
  [[ "$output" == *"nowhere is missing or empty"* ]]
  mkdir empty
  run_script bin/pages-artifact.sh empty "$BATS_TEST_TMPDIR/site.tar"
  [ "$status" -eq 1 ]
  [ ! -e "$BATS_TEST_TMPDIR/site.tar" ]
}

@test "pages-artifact needs both arguments" {
  run_script bin/pages-artifact.sh site
  [ "$status" -ne 0 ]
  [[ "$output" == *"usage: pages-artifact.sh SITE_DIR ARCHIVE"* ]]
}
