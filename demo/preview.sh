#!/bin/sh
# Build demo/pentimento-preview.png for GitHub's social-preview slot.
#
# Usage: sh demo/preview.sh [output-dir]
#
# Extracts one frame from demo/pentimento.gif and fits it to GitHub's
# 1280x640 social-preview size. Writes to $1, or ${TMPDIR:-/tmp} by default,
# and prints the path. The PNG is not committed -- GitHub stores the
# uploaded copy, and record.sh does not commit intermediates either.
set -eu

main() {
  SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
  REPO_ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
  FFMPEG=${FFMPEG:-ffmpeg}
  MAGICK=${MAGICK:-magick}
  OUT_DIR=${1:-${TMPDIR:-/tmp}}
  GIF="$REPO_ROOT/demo/pentimento.gif"
  OUT="$OUT_DIR/pentimento-preview.png"

  # SECONDS=21 is the `pentimento tree` frame, the only full-screen output
  # in the tape with no typing cursor on it.
  SECONDS=21

  "$FFMPEG" -v error -ss "$SECONDS" -i "$GIF" -frames:v 1 -y "$OUT_DIR/frame.png"
  "$MAGICK" "$OUT_DIR/frame.png" -fuzz 8% -trim +repage \
    -bordercolor black -border 34 \
    -resize 1280x640 -background black -gravity center -extent 1280x640 \
    "$OUT"

  echo "$OUT"
}

main "$@"
