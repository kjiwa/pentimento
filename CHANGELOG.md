# Changelog

## 0.1.16

Several correctness fixes. Removing a plan's last pentimento field no longer
drops the foreign frontmatter keys and comments around it, and a hand-written
value that fails validation (`project: "a #b"`) no longer makes every `set` and
`backfill` raise: only a value being changed is validated, and an unchanged one
is re-emitted as written. `backfill` validates every plan before writing any.
A parent whose chain runs into another plan's cycle is no longer treated as
cyclic, so `backfill` keeps it and `set --parent` accepts it; a parent that
would close a cycle now exits 2 instead of 1. `set --add-tag` lowercases before
validating, so `Auth` becomes `auth`; `--remove-tag` and `list --tag` reject
malformed tags with exit 2, and adding and removing the same tag in one `set`
is a usage error. `list --grep` no longer matches across the title and body
boundary, and `--finding` no longer offers `unreadable-file`, which names a file
rather than a plan and still appears in `check`.

All output is ASCII. `--ascii` is removed from `list`, `tree`, `show`, `check`,
and `history`; trees draw with `tree(1)` connectors (`|--`, `` `-- ``), `show`
uses `-` bullets, `[x]`/`[ ]` checkboxes, and `...`, and truncation ends in
`...`. Plan text is passed through unchanged.

`list`, `check`, and `history` no longer drop columns as the terminal narrows.
A table prints when every column fits (`TITLE` at 30 columns or more, `PROJECT`
and `TAGS` at 10 or more, `TAGS` ending in `+N` for tags left out); otherwise
each row prints as a stacked record with every field kept. Output that is not a
terminal, with `COLUMNS` unset, is never width-bound, so `list | grep` sees
whole lines. `list` columns now run `id status intent project source title
finding tags created modified`, and tags print as `[a, b]`. `tree` truncates
only a node's title and wraps its metadata line between fields; `show` wraps
finding lines to the terminal width.

## 0.1.15

`backfill` no longer names a plan `home` when its session was launched in `$HOME`.
Such a session takes the outermost directory, among the launch directories of
all sessions, that most of its `cwd` entries and tool-call paths fall under, so
work on `~/src/github/fankado` from a terminal opened in `~` is filed under
`fankado`. With no evidence, or a tie, the project is the home directory's own
name, which is what `--project .` already resolved to there. The first run
re-reads session transcripts once to collect the new signals.

## 0.1.14

`check` treats an explicit status as an answer. A plan with `pinned` set, which
`set --status` does by design, or with status `superseded`, no longer gets
`status-behind-progress`, `status-behind-history`, or `underivable-status`;
the one exception is `pin-behind-progress`, which fires only when the pin is
below what `## Progress` derives. `underivable-status` flags any unpinned
`unknown` plan whose status can't be derived, whether the `## Progress`
heading is absent or holds no checkboxes, and `status-behind-progress` also
catches a stored `unknown`, matching what `backfill` would advance.

A finding is a plan attribute with a fix. Every finding carries a `hint`: the
table prints one `code: fix` line per code under its summary, followed by
`narrow with: pentimento list --finding <code>`, and `check --format json|tsv`
records gain a trailing `hint` field. `list` and `tree` take `--finding
[CODE]` (bare means any finding), `list` shows a `FINDING` column under it or
through `--columns`, `show` prints each finding with its fix above the body,
and the `list`, `tree`, and `show` `--format json|tsv` records gain a
`findings` field. `CODE` no longer drops at narrow widths, the summary is
dimmed after a blank line as in `list`, and finding messages state the fact
only. `docs/workflows.md` has a "Working through `check`" section, and
`docs/troubleshooting.md` lists `unreadable-file`.

Each fact has one form across commands. `tree` and the `created` field of
`--format json|tsv` records use the date `list` shows as `CREATED`, which is
`created` when set and otherwise the date `backfill` would write; a plan with
no `created` field used to print nothing in `tree` and `null` in json.
`history`'s `WHEN` no longer drops at narrow widths. The empty-corpus message
`no plans found; searched: ...` goes to stderr in every format for `list`,
`tree`, `index`, and `backfill`, as it does for `check`, so `--format json`
still prints `[]` on stdout. `no session history for <id>` names the directory
it searched, and an invalid project or tag names the valid form. `show` prints
a finding's fix without the redundant `pentimento show` step. Help text is
worded alike throughout: one `--dry-run` string, one plan-id string for every
id argument and `--only`, `--sort` as the sort key and `--order` as the sort
direction, and "requires" in place of "needs". `hook` and `index` gain
examples, `completion`'s argument is named `SHELL`, and `--ascii` help matches
its effect on every command.

`docs/reference.md` lists flags in parser order, states that ids are accepted
as a short id, full id, filename, or path (`backfill --only` included), no
longer says `PENTIMENTO_NOW` affects `history`, and says `TAGS` and `CREATED`
follow the listed plans, not the whole corpus. A test fails when a parser flag
or its order drifts from that file.

Breaking, for scripts: `missing-progress` is now `underivable-status` and
`pin-diverged` is now `pin-behind-progress`; `set` exits 2 instead of 1 for an
invalid `--project` or `--add-tag`, as the exit codes in `docs/reference.md`
say of usage errors; and `--date` without a bound reports "requires" rather
than "needs".

## 0.1.13

Fixes: `show` no longer cuts a long line in a fenced or indented code block
with `…`, so `show --full` prints the whole body. The line wraps at a space,
or mid-word when a token is wider than the terminal, and each continuation row
is marked `↪` (`>` with `--ascii`) in the block's indent. Adjacent source
lines are still never joined.

## 0.1.12

`list` and `tree` gain `--title PATTERN`, a case-insensitive regex over the
title alone (`--grep` still covers title and body), and `--since WHEN` /
`--until WHEN`, an inclusive local-day range over `modified` -- the `UPDATED`
column -- or over `created` with `--date created`. `WHEN` is `YYYY-MM-DD` or
an age in the units `UPDATED` prints (`14m`, `5h`, `3d`, `2w`, `1y`). Together
they find a past decision across projects and answer what a given week
held. `integrations/claude/skills/prior-plans` is a Claude Code skill that
runs that search before the agent plans a change to shared infrastructure, and
`docs/integrations.md` and `docs/workflows.md` cover installing and using it.

Breaking, for scripts: usage errors now exit 2 instead of 1 -- a missing or
conflicting flag, an invalid value or regex, `tree --ancestors` without an id
-- as do I/O errors, so `check`'s exit 1 (findings) and a plan-not-found exit
1 stay distinct from misuse. Every error message on stderr is prefixed
`pentimento: `. `check --format json|tsv` records name the plan `id`, not
`plan_id`, and follow the table's order: `code`, `id`, `message`.
`--columns` and `PENTIMENTO_COLUMNS` name columns `id` and `modified`, as
`--sort` does, in place of `plan` and `updated`; the old names are rejected.
In `json` and `tsv`, `started` and `modified` are UTC instants with whole
seconds and a trailing `Z` (`modified` was a local offset with microseconds),
`history`'s `when` uses the same form, and `tsv` prints `pinned` as `true` or
`false`. `show --format json|tsv` now includes `body`. Plan titles no longer
carry control characters. A closed pipe (`pentimento list | head`) exits 141
quietly.

`set` rejects flags that conflict (`--parent` with `--clear-parent`,
`--status` with `--unpin`, and so on) and a call that names no field, instead
of silently picking one. `backfill --only` accepts the short id or filename
that `show` does, exits 1 on an unknown one, and prints each field it changes
under the plan's id, so `backfill --only <id> --rederive --dry-run` is a real
preview. `check` on an empty corpus prints the same `no plans found` hint as
`list`.

Fixes: a `#` inside an unrecognized frontmatter value no longer truncates it on
`set` and `backfill`, and a value containing `: ` no longer aborts the run;
CRLF plan files keep their line endings through `set`; a session transcript
line that is not a JSON object no longer crashes every command; `tree <id>
--ancestors` no longer repeats plans caught in a `parent` cycle, and `tree`
roots at the requested plan; a tab or newline in a tag no longer adds a field
to `tsv` output; `list --project ''` filters instead of matching everything;
and `-n abc` and `--columns +` report what was wrong. `--help` text links to
docs by URL, since pip installs carry no `docs/` directory.

## 0.1.11

`tree` now takes an optional `<id>` that roots the tree at that plan --
it plus every plan beneath it, resolved against the whole corpus rather
than filtered first, so `--project` is unnecessary and a subplan can no
longer fall out of the thread for lacking a tag. `--ancestors` extends the
selection with the path down from `<id>`'s topmost ancestor, spine only,
leaving the ancestors' other children out; it requires `<id>` and exits 1
without one. Existing filters, sort, and `--format` all apply within the
selection, so `tree <id> --status partial` answers what's left on a thread.
`show`, `set`, `history`, and now `tree` all accept either the short id or
the full id.

## 0.1.10

`list --columns SPEC` (default: `PENTIMENTO_COLUMNS`) picks the table's
columns and their order explicitly: an absolute list (`created,title,status`),
`+name`/`-name` modifiers on the content-derived default set, or `all`. A
column named this way, or the active `--sort` key's column, never drops as
the terminal narrows -- previously `CREATED` was the first column dropped,
so `--sort created` could sort by a value the table didn't show. `--columns`
applies to `--format table` only; combining it with `--format json|tsv` is
now an error. The `CREATED` cell now prints the same derived date
`--sort created` sorts by, instead of the raw (and sometimes blank)
`created` frontmatter field.

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
