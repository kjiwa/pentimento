#!/bin/sh
# Regenerate demo/pentimento.gif with VHS.
#
# Usage: sh demo/record.sh
#
# Builds a fresh demo/fixture.sh corpus, points AGENT_PLANS_DIR at it, and
# runs the VHS tape against that corpus so the recording never touches a
# real plans directory.
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
  REPO_ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
  VHS=${VHS:-vhs}
  GIF="$REPO_ROOT/demo/pentimento.gif"

  FIXTURE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/pentimento-record.XXXXXX")
  trap 'rm -rf "$FIXTURE_DIR"' EXIT

  sh "$SCRIPT_DIR/fixture.sh" "$FIXTURE_DIR"

  _before=$(_gif_state "$GIF")

  (
    cd "$REPO_ROOT" && \
    AGENT_PLANS_DIR="$FIXTURE_DIR" \
      AGENT_SESSIONS_DIR="$FIXTURE_DIR/no-such-sessions-dir" \
      CURSOR_PLANS_DIR=/nonexistent \
      "$VHS" "$SCRIPT_DIR/pentimento.tape"
  )

  _after=$(_gif_state "$GIF")

  if [ "$_before" = "$_after" ]; then
    echo "record.sh: $GIF was not written; vhs 0.12.0 has a regression" >&2
    echo "where a cancelled context suppresses the ffmpeg render step." >&2
    echo "Use a working vhs (e.g. 0.11.0) via VHS=/path/to/vhs." >&2
    exit 1
  fi
}

main "$@"
