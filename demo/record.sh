#!/bin/sh
# Regenerate demo/pentimento.gif with VHS.
#
# Usage: sh demo/record.sh
#
# Builds a fresh demo/fixture.sh corpus under a sandboxed DEMO_HOME and runs
# the VHS tape against it. The tape itself exports HOME="$DEMO_HOME" inside
# the recorded shell, so pentimento's default ~/.claude/plans resolves to the
# fixture -- the recording never touches a real plans directory, and the reel
# shows the tool running on its own defaults rather than an env override.
set -eu

_gif_state() {
  _gif_state_path=$1
  if [ -f "$_gif_state_path" ]; then
    stat -f '%m %z' "$_gif_state_path" 2>/dev/null || stat -c '%Y %s' "$_gif_state_path"
  else
    echo "absent"
  fi
}

main() {
  SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
  readonly SCRIPT_DIR
  REPO_ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
  readonly REPO_ROOT
  readonly VHS="${VHS:-vhs}"
  readonly GIF="$REPO_ROOT/demo/pentimento.gif"

  DEMO_HOME=$(mktemp -d "${TMPDIR:-/tmp}/pentimento-record.XXXXXX")
  readonly DEMO_HOME
  trap 'rm -rf "${DEMO_HOME:-}"' EXIT
  export DEMO_HOME

  sh "$SCRIPT_DIR/fixture.sh" "$DEMO_HOME/.claude/plans"

  _main_before=$(_gif_state "$GIF")

  (
    cd "$REPO_ROOT" && \
    AGENT_SESSIONS_DIR="$DEMO_HOME/.claude/plans/sessions" \
      CURSOR_PLANS_DIR=/nonexistent \
      CURSOR_SESSIONS_DIR=/nonexistent \
      "$VHS" "$SCRIPT_DIR/pentimento.tape"
  )

  _main_after=$(_gif_state "$GIF")

  if [ "$_main_before" = "$_main_after" ]; then
    echo "record.sh: $GIF was not written; vhs 0.12.0 has a regression" >&2
    echo "where a cancelled context suppresses the ffmpeg render step." >&2
    echo "Use a working vhs (e.g. 0.11.0) via VHS=/path/to/vhs." >&2
    exit 1
  fi
}

main "$@"
