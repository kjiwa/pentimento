---
name: Quiet flag
overview: Add a POSIX `-q`/`--quiet` option to dircompare.sh that prints nothing on success or differences and exits 0 or 1, while still reporting usage/runtime errors on stderr with exit 2. Document it in README.md.
todos:
  - id: parse-quiet
    content: Add QUIET flag, -q/--quiet parsing, and usage text in dircompare.sh
    status: completed
  - id: suppress-output
    content: Skip comparison printing; exit 1 on first difference in quiet mode
    status: completed
  - id: readme
    content: Document -q in README.md usage, options, and examples
    status: completed
  - id: verify
    content: shellcheck plus identical/different/error smoke checks
    status: completed
isProject: false
---

# Add `-q` quiet mode to dircompare.sh

## Behavior

- `-q` / `--quiet` (long form matches existing `-h`/`-x`/`-c` style) suppresses **all comparison output** (the three `===` sections, file lists, and blank lines).
- Exit status is unchanged: **0** identical, **1** different, **2** error.
- **`error_exit` and invalid-usage `usage >&2` stay on stderr.** Silent comparison with a silent failure would make `exit 2` indistinguishable from a bug. `-h` still prints help and exits 0.

In quiet mode, **stop at the first difference** (`exit 1`) so hashing/stat of remaining files is skipped. Identical trees still walk everything. `trap cleanup EXIT` already runs on `exit`.

## Script changes ([dircompare.sh](dircompare.sh))

- Add `QUIET=0` next to the other globals; `readonly QUIET` with the other flags at the end of `parse_args`.
- In `parse_args`, handle `-q | --quiet)` with `QUIET=1` and `shift`.
- Extend `usage()`: add the flag to the usage line and option list.

Gate output in:

- [`show_only_in`](dircompare.sh): skip `echo`/`printf`; if `only` is non-empty, set `DIFFERENCES_FOUND=1` and `exit 1` when quiet.
- [`show_content_diffs`](dircompare.sh): skip the header; on first signature mismatch, `exit 1` when quiet.

Keep comparison logic (lists, `comm`, hash/size) the same so `-q` combines with `-x` and `-c`.

## Docs ([README.md](README.md))

- Add `-q` to the usage synopsis and Options.
- Note under Output / Exit Codes that quiet mode prints nothing on 0/1; errors still go to stderr.
- Add a short example, e.g. `if ./dircompare.sh -q dir1 dir2; then ...`.

## Verify (after implementation)

- `sh -n dircompare.sh` and `shellcheck dircompare.sh`.
- Identical dirs: no stdout/stderr, exit 0.
- Different dirs (only-in and content): no stdout, exit 1.
- Missing dir / bad flag: stderr message, exit 2.
