# Changelog

## 0.1.9

`show --full` now allocates markdown table columns by water-fill instead of raw
proportion: a column that fits inside an equal share keeps its natural width, and
only the columns still contending for what's left split it, weighted by the square
root of their natural width. A single long prose cell no longer starves every other
column down to the four-character floor.

## 0.1.8

`pentimento completion <bash|zsh|fish>` prints a tab-completion script for
subcommands, flags, `choices=` values, corpus-derived projects and tags, and
plan ids — the same short ids `list` prints, reaching the full id on a
longer prefix. A hidden `pentimento __complete` does the actual candidate
work so the three scripts stay thin. The demo reel is now a four-act
narrative (#10), and releases are cut with `scripts/release.sh`, gated on
publish by `scripts/check-release.sh` (#11). `docs/reference.md`'s env-var
table and short-id prose now cover `history` and the `PENTIMENTO_NOW`,
`PENTIMENTO_DEBUG`, and `XDG_CACHE_HOME` variables it was missing.

## 0.1.7

`show` now prints the plan file's absolute path on its own line under `id`,
the same value `--format json` already emitted as `path`. The README's
captured samples rewrite the fixture's temp directory to `~/.claude/plans`
so they stay byte-stable across machines.

## 0.1.6

`show --full` now pages through `$PAGER` (default `less`) when stdout is a
tty and the plan is taller than the terminal, so colour and width resolve
against the real terminal instead of a pipe. Redirects and pipes are
byte-identical to before; `--no-pager` opts out on a tty. The README is
reframed around long-carried plans and rediscovery, and each doc opens with
a line saying when to reach for it.

## 0.1.5

`derive_parent` now resolves a session-prompt or body reference by its
trailing codename (`wobbly-willow` for an id ending `...-wobbly-willow`),
not just a literal `<id>.md`/`<id>.plan.md`. Within a tier, an exact
`<id>.md` reference outranks a codename reference, and the earliest
mention wins a tie. `check` gains an `unadopted-reference` finding for a
parentless plan with an eligible reference it never adopted.

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
