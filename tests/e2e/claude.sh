#!/bin/sh
# Drive the real Claude Code CLI against a scripted local Messages endpoint and
# check that a stock install (no hooks) already shows the session's project and
# that the shipped hooks keep a plan's frontmatter current.
#
# Usage: sh tests/e2e/claude.sh
#
# Needs `claude` and `pentimento` on PATH and a free loopback port. Runs in a
# throwaway HOME with a dummy `ANTHROPIC_AUTH_TOKEN`, so no subscription or
# API key is used and nothing outside the temp directory is touched. A `claude`
# that runs longer than CLAUDE_TIMEOUT seconds fails the script.
set -eu

readonly PLAN_ID=e2e-sample
readonly CLAUDE_TIMEOUT=120
readonly START_TRIES=30

_cleanup() {
  [ -z "${WATCHDOG_PID:-}" ] || kill "$WATCHDOG_PID" 2>/dev/null || true
  [ -z "${SERVER_PID:-}" ] || kill "$SERVER_PID" 2>/dev/null || true
  [ -z "${WORK_DIR:-}" ] || rm -rf "$WORK_DIR"
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
  readonly SERVER_PID
  _start_server_tries=0
  while [ ! -s "$WORK_DIR/port" ]; do
    kill -0 "$SERVER_PID" 2>/dev/null || _fail "server exited during startup"
    _start_server_tries=$((_start_server_tries + 1))
    [ "$_start_server_tries" -lt "$START_TRIES" ] || _fail "server did not start"
    sleep 1
  done
}

_watch() {
  (
    sleep "$CLAUDE_TIMEOUT" &
    _watch_sleep=$!
    trap 'kill "$_watch_sleep" 2>/dev/null; exit 0' TERM
    wait "$_watch_sleep"
    kill "$1" 2>/dev/null || true
  ) &
  WATCHDOG_PID=$!
}

_run_claude() {
  mkdir -p "$WORK_DIR/project"
  (
    cd -- "$WORK_DIR/project"
    ANTHROPIC_BASE_URL="http://127.0.0.1:$(cat "$WORK_DIR/port")" \
      ANTHROPIC_AUTH_TOKEN=e2e \
      CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
      claude -p "Write the sample plan." --permission-mode bypassPermissions
  ) &
  _run_claude_pid=$!
  _watch "$_run_claude_pid"
  wait "$_run_claude_pid" || _fail "claude failed or exceeded ${CLAUDE_TIMEOUT}s"
  kill "$WATCHDOG_PID" 2>/dev/null || true
}

_assert_output_has() {
  _assert_output_has_expect=$1
  shift
  _assert_output_has_output=$(pentimento "$@" --color never) || _fail "pentimento $* exited nonzero"
  printf '%s\n' "$_assert_output_has_output" | grep -q "$_assert_output_has_expect" ||
    _fail "pentimento $* lacks '$_assert_output_has_expect'"
}

main() {
  ROOT=$(cd -- "$(dirname "$0")/../.." && pwd)
  readonly ROOT
  WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/pentimento-e2e.XXXXXX")
  readonly WORK_DIR
  trap _cleanup EXIT
  trap 'exit 130' INT TERM
  unset CLAUDE_CONFIG_DIR AGENT_PLANS_DIR AGENT_SESSIONS_DIR \
    CURSOR_PLANS_DIR CURSOR_SESSIONS_DIR ANTHROPIC_API_KEY
  readonly HOME="$WORK_DIR/home"
  readonly XDG_CACHE_HOME="$WORK_DIR/cache"
  export HOME XDG_CACHE_HOME
  mkdir -p "$HOME/.claude"

  _start_server
  _run_claude
  [ -f "$HOME/.claude/plans/$PLAN_ID.md" ] || _fail "the scripted Write never created the plan"
  _assert_output_has "status: partial" show "$PLAN_ID"
  grep -q "status: not-started" "$HOME/.claude/plans/$PLAN_ID.md" ||
    _fail "a read command rewrote the plan"
  echo "e2e ok: no hooks, status derived live for $PLAN_ID"

  rm "$HOME/.claude/plans/$PLAN_ID.md"
  cp "$ROOT/integrations/claude/settings-snippet.json" "$HOME/.claude/settings.json"
  _run_claude
  [ -f "$HOME/.claude/plans/$PLAN_ID.md" ] || _fail "the scripted Write never created the plan"

  grep -q "status: partial" "$HOME/.claude/plans/$PLAN_ID.md" || _fail "the hooks did not persist status"
  _assert_output_has authored history "$PLAN_ID"
  echo "e2e ok: hooks derived status for $PLAN_ID"
}

main "$@"
