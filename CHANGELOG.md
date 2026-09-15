# Changelog

## 0.1.4

Docs-only release: the README explains why pentimento exists (long-carried
plans, not just volume, and the origin of the name) and adds a `## Scope`
section ruling out shared or multi-author planning as a non-goal.
`CONTRIBUTING.md` separates the single-maintainer project from the
single-operator tool. `docs/workflows.md` documents which derived fields
survive keeping the plans directory in git and which don't.

## 0.1.3

Broadened the PyPI classifiers.

## 0.1.2

A `pinned` frontmatter field makes a hand-set `status` immune to
derivation, the way `superseded` already is: `set --status` pins it,
`set --unpin` releases it, and `backfill` (with or without `--rederive`)
leaves a pinned status alone. `backfill --only ID` restricts writes to
one plan, the narrow alternative to a corpus-wide `--rederive`. `check`
gains a `pin-diverged` finding for a pinned status that disagrees with
what `## Progress` would derive.

## 0.1.1

`list` and `tree` now always render STATUS, INTENT, PROJECT, and SOURCE,
instead of hiding a column when every plan in the result shares one value.
Narrow terminals still drop columns by the existing fit-driven priority.

## 0.1.0

First release. Reads a directory of agent plan files (Claude Code, Cursor),
derives status, intent, lineage, and project into a frontmatter block, and
provides a CLI (`list`, `tree`, `show`, `set`, `backfill`, `hook`, `index`,
`check`, `history`) to work with the corpus.
