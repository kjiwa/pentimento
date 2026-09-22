# demo

`fixture.sh` writes a synthetic plan corpus to a directory you name; the
scripts below run against that fixture rather than a real plans directory.

## README samples

`sh demo/capture.sh` regenerates the sample blocks in the top-level
`README.md`, between each pair of `<!-- sample:NAME -->` /
`<!-- /sample -->` markers. CI's `readme-samples` job reruns it and fails on
any diff, so run it and commit the result whenever a change alters what
`list`, `tree`, `show`, `check`, or `history` print.

## The reel

`sh demo/record.sh` re-records `pentimento.gif` from `pentimento.tape`,
along with the gitignored `pentimento-tree.png` frame the tape screenshots
partway through. Recording needs a vhs that is not 0.12.0 (it silently
drops the GIF); pass `VHS=/path/to/vhs` to select one. Nothing in CI checks
the reel and it isn't tied to releases, so re-record only when a command the
tape runs would render differently, or when the tape's narrative itself
changes.

## Social preview

`sh demo/preview.sh` fits the `pentimento-tree.png` frame to GitHub's
1280x640 social-preview size and writes it under `$TMPDIR`, printing the
path. Run `record.sh` first if that frame doesn't exist yet -- it's
gitignored, not committed. The output itself is uploaded to GitHub rather
than committed either, so rebuild and re-upload it only after a recording
changes that frame.
