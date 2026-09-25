#!/bin/sh
# Build demo/pentimento-preview.png for GitHub's social-preview slot.
#
# Usage: sh demo/preview.sh [output-dir]
#
# Fits demo/pentimento-tree.png -- a Screenshot taken by the VHS tape -- to
# GitHub's 1280x640 social-preview size. Writes to $1, or ${TMPDIR:-/tmp} by
# default, and prints the path. The PNG is not committed -- GitHub stores the
# uploaded copy, and record.sh does not commit intermediates either.
set -eu

main() {
  _main_script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
  _main_out_dir=${1:-${TMPDIR:-/tmp}}
  readonly MAGICK="${MAGICK:-magick}"
  readonly FRAME="$_main_script_dir/pentimento-tree.png"
  readonly OUT="${_main_out_dir%/}/pentimento-preview.png"

  "$MAGICK" "$FRAME" -fuzz 8% -trim +repage \
    -bordercolor black -border 34 \
    -resize 1280x640 -background black -gravity center -extent 1280x640 \
    "$OUT"

  echo "$OUT"
}

main "$@"
