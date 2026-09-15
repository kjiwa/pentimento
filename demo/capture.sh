#!/bin/sh
# Regenerate the README's captured command output from the demo fixture.
#
# Usage: sh demo/capture.sh
#
# Runs `pentimento list`, `tree`, `show`, and `check` against a fresh
# `demo/fixture.sh` corpus and splices each result into README.md between
# `<!-- sample:NAME -->` / `<!-- /sample -->` marker pairs, so the samples
# are regenerable. Pins `PENTIMENTO_NOW` unconditionally, overriding any
# value already in the environment, so the fixture's mtimes and the
# captured relative times agree byte-for-byte no matter the real wall
# clock at capture time.
set -eu

_capture() {
  _capture_name=$1
  shift
  _capture_status=0
  AGENT_PLANS_DIR="$FIXTURE_DIR" \
    AGENT_SESSIONS_DIR="$FIXTURE_DIR/sessions" \
    CURSOR_PLANS_DIR=/nonexistent \
    COLUMNS=110 \
    pentimento "$@" --color never >"$CAPTURE_DIR/$_capture_name.txt" || _capture_status=$?

  # `check` exits 1 when it finds something; the fixture has a deliberate
  # dangling parent, so that exit code is expected, not a capture failure.
  if [ "$_capture_status" -ne 0 ] && [ "$_capture_name" != "check" ]; then
    echo "capture failed: pentimento $* (exit $_capture_status)" >&2
    return "$_capture_status"
  fi
}

_splice() {
  _splice_name=$1
  _splice_content="$CAPTURE_DIR/$_splice_name.txt"
  _splice_out="$CAPTURE_DIR/README.spliced"

  awk -v marker="$_splice_name" -v contentfile="$_splice_content" '
    BEGIN {
      content = ""
      while ((getline line < contentfile) > 0) {
        content = content line "\n"
      }
      close(contentfile)
    }
    $0 == "<!-- sample:" marker " -->" {
      print
      print "```"
      printf "%s", content
      print "```"
      skip = 1
      next
    }
    skip && $0 == "<!-- /sample -->" {
      print
      skip = 0
      next
    }
    skip { next }
    { print }
  ' "$README" >"$_splice_out"
  mv "$_splice_out" "$README"
}

main() {
  SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
  REPO_ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
  README="$REPO_ROOT/README.md"

  FIXTURE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/pentimento-fixture.XXXXXX")
  CAPTURE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/pentimento-capture.XXXXXX")
  trap 'rm -rf "$FIXTURE_DIR" "$CAPTURE_DIR"' EXIT

  PENTIMENTO_NOW=2026-09-14T12:30:00Z
  export PENTIMENTO_NOW

  sh "$SCRIPT_DIR/fixture.sh" "$FIXTURE_DIR"

  _capture list list
  _capture tree tree
  _capture show show api-auth-rollout
  _capture check check
  _capture history history api-auth-cleanup

  for _name in list tree show check history; do
    _splice "$_name"
  done
}

main "$@"
