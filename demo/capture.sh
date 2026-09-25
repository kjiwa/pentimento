#!/bin/sh
# Regenerate the README's captured command output from the demo fixture.
#
# Usage: sh demo/capture.sh
#
# Splices each command's output against a fresh `demo/fixture.sh` corpus into
# README.md between `<!-- sample:NAME -->` / `<!-- /sample -->` markers. Pins
# `PENTIMENTO_NOW` and `TZ`, overriding the environment, so relative and
# absolute times are reproducible. Rewrites the fixture's temp directory to
# `~/.claude/plans` in each capture, in both the absolute form and the
# `~`-collapsed form `show` prints when the temp directory is under `$HOME`.
set -eu

_capture() {
  _capture_name=$1
  _capture_columns=$2
  shift 2
  _capture_status=0
  AGENT_PLANS_DIR="$FIXTURE_DIR" \
    AGENT_SESSIONS_DIR="$FIXTURE_DIR/sessions" \
    CURSOR_PLANS_DIR=/nonexistent \
    CURSOR_SESSIONS_DIR=/nonexistent \
    COLUMNS="$_capture_columns" \
    pentimento "$@" --color never >"$CAPTURE_DIR/$_capture_name.txt" || _capture_status=$?

  # `check` exits 1 when it finds something; the fixture has a deliberate
  # dangling parent, so that exit code is expected, not a capture failure.
  if [ "$_capture_status" -ne 0 ] && [ "$_capture_name" != "check" ]; then
    echo "capture failed: pentimento $* (exit $_capture_status)" >&2
    return "$_capture_status"
  fi

  sed -e "s|$FIXTURE_DIR|~/.claude/plans|g" \
      -e "s|$FIXTURE_DISPLAY|~/.claude/plans|g" \
    "$CAPTURE_DIR/$_capture_name.txt" \
    >"$CAPTURE_DIR/$_capture_name.norm"
  mv "$CAPTURE_DIR/$_capture_name.norm" "$CAPTURE_DIR/$_capture_name.txt"
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

  # A trailing slash on $TMPDIR (macOS) doubles the slash in FIXTURE_DIR, which
  # then never matches the normalized path the CLI prints.
  _main_tmp=${TMPDIR:-/tmp}
  FIXTURE_DIR=$(mktemp -d "${_main_tmp%/}/pentimento-fixture.XXXXXX")
  CAPTURE_DIR=$(mktemp -d "${_main_tmp%/}/pentimento-capture.XXXXXX")
  trap 'rm -rf "$FIXTURE_DIR" "$CAPTURE_DIR"' EXIT

  # `show` collapses $HOME to ~ before printing a path (cli.py:_display_path),
  # so a fixture under $HOME appears in captured output in this form too.
  FIXTURE_DISPLAY=$FIXTURE_DIR
  # shellcheck disable=SC2088 # literal ~ prefix, not meant to expand
  case $FIXTURE_DIR in
    "$HOME"/*) FIXTURE_DISPLAY="~/${FIXTURE_DIR#"$HOME"/}" ;;
  esac

  PENTIMENTO_NOW=2026-09-14T12:30:00Z
  export PENTIMENTO_NOW

  TZ=UTC
  export TZ

  sh "$SCRIPT_DIR/fixture.sh" "$FIXTURE_DIR"

  _capture list 132 list
  _capture list-narrow 80 list
  _capture tree 110 tree
  _capture tree-thread 110 tree auth-rollout --ancestors
  _capture show 110 show api-auth-rollout
  _capture check 110 check
  _capture history 110 history api-auth-cleanup

  for _name in list list-narrow tree tree-thread show check history; do
    _splice "$_name"
  done
}

main "$@"
