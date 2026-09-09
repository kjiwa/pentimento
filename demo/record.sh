#!/bin/sh
# Regenerate demo/pentimento.gif with VHS.
#
# Usage: sh demo/record.sh
#
# Builds a fresh demo/fixture.sh corpus, points AGENT_PLANS_DIR at it, and
# runs the VHS tape against that corpus so the recording never touches a
# real plans directory.
set -eu

main() {
  SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)

  FIXTURE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/pentimento-record.XXXXXX")
  trap 'rm -rf "$FIXTURE_DIR"' EXIT

  sh "$SCRIPT_DIR/fixture.sh" "$FIXTURE_DIR"

  AGENT_PLANS_DIR="$FIXTURE_DIR" \
    AGENT_SESSIONS_DIR="$FIXTURE_DIR/no-such-sessions-dir" \
    CURSOR_PLANS_DIR=/nonexistent \
    vhs "$SCRIPT_DIR/pentimento.tape"
}

main "$@"
