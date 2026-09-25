#!/bin/sh
# Drive the real Claude Code CLI against a scripted local Messages endpoint and
# check that the shipped hooks keep a plan's frontmatter current.
#
# Usage: sh tests/e2e/claude.sh
#
# Needs `claude` and `pentimento` on PATH and a free loopback port. Runs in a
# throwaway HOME with a dummy `ANTHROPIC_AUTH_TOKEN`, so no subscription or
# API key is used and nothing outside the temp directory is touched.
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
readonly ROOT
readonly PLAN_ID=e2e-sample

WORK_DIR=
SERVER_PID=

_cleanup() {
  [ -z "$SERVER_PID" ] || kill "$SERVER_PID" 2>/dev/null || true
  [ -z "$WORK_DIR" ] || rm -rf "$WORK_DIR"
}

_fail() {
  echo "e2e failed: $1" >&2
  [ ! -f "$WORK_DIR/requests.log" ] || echo "requests logged: $(wc -l <"$WORK_DIR/requests.log")" >&2
  exit 1
}

_start_server() {
  python3 "$ROOT/tests/e2e/fake_anthropic.py" \
    "$HOME/.claude/plans/$PLAN_ID.md" "$WORK_DIR/port" "$WORK_DIR/requests.log" &
  SERVER_PID=$!
  _start_server_tries=0
  while [ ! -s "$WORK_DIR/port" ]; do
    _start_server_tries=$((_start_server_tries + 1))
    [ "$_start_server_tries" -lt 100 ] || _fail "server did not start"
    sleep 0.1
  done
}

_run_claude() {
  mkdir -p "$WORK_DIR/project"
  (
    cd "$WORK_DIR/project"
    ANTHROPIC_BASE_URL="http://127.0.0.1:$(cat "$WORK_DIR/port")" \
      ANTHROPIC_AUTH_TOKEN=e2e \
      CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
      CURSOR_PLANS_DIR=/nonexistent \
      CURSOR_SESSIONS_DIR=/nonexistent \
      claude -p "Write the sample plan." --permission-mode bypassPermissions
  )
}

_assert_output_has() {
  _assert_output_has_expect=$1
  shift
  _assert_output_has_output=$(pentimento "$@" --color never) || _fail "pentimento $* exited nonzero"
  printf '%s\n' "$_assert_output_has_output" | grep -q "$_assert_output_has_expect" ||
    _fail "pentimento $* lacks '$_assert_output_has_expect'"
}

main() {
  WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/pentimento-e2e.XXXXXX")
  trap _cleanup EXIT INT TERM
  HOME="$WORK_DIR/home"
  export HOME
  mkdir -p "$HOME/.claude"
  cp "$ROOT/integrations/claude/settings-snippet.json" "$HOME/.claude/settings.json"

  _start_server
  _run_claude
  [ -f "$HOME/.claude/plans/$PLAN_ID.md" ] || _fail "the scripted Write never created the plan"

  export CURSOR_PLANS_DIR=/nonexistent CURSOR_SESSIONS_DIR=/nonexistent
  _assert_output_has "status: partial" show "$PLAN_ID"
  _assert_output_has authored history "$PLAN_ID"
  echo "e2e ok: hooks derived status for $PLAN_ID"
}

main "$@"
