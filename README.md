# pentimento

Status, intent, and lineage over agent plan files.

Claude Code and Cursor (and other harnesses) accumulate plan files with no
status, no starring, and no record of which plan supersedes which. pentimento
reads a directory of plan markdown files, derives a small frontmatter block
for each one (`status`, `intent`, `parent`, `project`, `created`), and gives
you a CLI to list, filter, and render them as a lineage tree.

## Install

```sh
pip install -e .
```

## Usage

Two sources are read. Claude Code plans live in
`${AGENT_PLANS_DIR:-$HOME/.claude/plans}/*.md`, one file per plan, its
filename stem as the id, its first `# H1` as the title. Cursor plans live in
`${CURSOR_PLANS_DIR:-$HOME/.cursor/plans:$HOME/Library/Application Support/Cursor/User/plans}/*.plan.md`
(`CURSOR_PLANS_DIR` is `:`-separated for multiple directories); the id is the
filename stem with `.plan` stripped, e.g. `refactor-auth.plan.md` ->
`refactor-auth`. A directory that doesn't exist contributes nothing.

```sh
pentimento list [--status STATUS] [--intent INTENT] [--project PROJECT] [--source claude|cursor] [--starred] [--sort modified|created|id|status|title] [--reverse] [--format table|json|tsv] [--color auto|always|never]
pentimento tree [--status STATUS] [--intent INTENT] [--project PROJECT] [--source claude|cursor] [--starred] [--sort modified|created|id|status|title] [--reverse] [--format table|json|tsv] [--color auto|always|never]
pentimento show <id> [--format table|json|tsv] [--color auto|always|never]
pentimento set <id> [--status STATUS] [--intent INTENT] [--parent ID] [--project PROJECT]
pentimento backfill [--dry-run] [--quiet] [--rederive] [--recreate]
pentimento index
pentimento check [--format table|json|tsv] [--color auto|always|never]
```

`--format` defaults to `table` (human-readable); `json` and `tsv` are for
scripting. `--color` defaults to `auto` -- ANSI colour on a tty, off when
piped, `NO_COLOR` is set, or `TERM=dumb`. `--sort` defaults to `modified`,
newest first; `id`, `status`, and `title` sort ascending by default.
`--reverse` flips whichever order is in play.

`backfill` fills in missing fields without touching what's already set.
`--rederive` instead recomputes `status`, `parent`, and `project` from
scratch and overwrites them -- `intent` (operator-owned) and `created`
(immutable) are never touched; a re-derivation that finds no parent removes
an existing `parent` key. `--recreate` is the one way to change `created`: it
recomputes it from local time, fixing a plan whose `created` was derived
before this local-time fix landed.

`check` validates the corpus -- dangling parents, self-parents,
cross-project parents, cycles, duplicate ids across sources, and
off-vocabulary `status`/`intent` values -- and exits 1 on any finding.

## Frontmatter

```yaml
---
status: not-started | partial | complete | superseded | unknown
intent: active | queued | someday | abandoned | unset
parent: some-other-plan-id   # omitted for roots
project: platform             # omitted if undetermined
created: 2026-09-08
---
```

`status` is derived and correctable; `intent` is only ever set by the
operator, so a half-implemented plan can still be marked abandoned. `parent`
and `project` are derived, not authored — `backfill` fills them in and
`set --parent` refuses a value that resolves to no plan in the corpus.
`created` is a local-date (`YYYY-MM-DD`), derived once and then immutable
except through `backfill --recreate`.

Lineage is read from the harness's own session logs, in
`${AGENT_SESSIONS_DIR:-$HOME/.claude/projects}/<encoded-dir>/<uuid>.jsonl` —
one directory per project, one file per session. Each plan's id is a
session `slug`; a plan's parent is whichever earlier, same-project,
same-source plan its originating session's first prompt (or, failing that,
the plan body above its first `##` heading) references by `<id>.md`.
`project` is the basename of the common path across a session's `cwd`
values. Never guessed: a plan with no session record and no reference falls
back to no parent and no project.

Cursor has no session logs, so a Cursor plan's parent (if any) comes only
from the body-preamble reference scan, and its `project` is never derived.
A Cursor plan with no `## Progress` heading derives `status` from a
checkbox ratio over the whole body instead.

Zero runtime dependencies: this is stdlib-only Python 3, no PyYAML, so it
ships as a plain CLI.
