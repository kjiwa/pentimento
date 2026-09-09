# pentimento

Status, intent, and lineage over agent plan files.

Claude Code (and other harnesses) accumulate plan files with no status, no
starring, and no record of which plan supersedes which. pentimento reads a
directory of plan markdown files, derives a small frontmatter block for each
one (`status`, `intent`, `parent`, `project`, `created`), and gives you a CLI
to list, filter, and render them as a lineage tree.

## Install

```sh
pip install -e .
```

## Usage

Plans live in `${AGENT_PLANS_DIR:-$HOME/.claude/plans}` — one markdown file
per plan, its filename stem as the id, its first `# H1` as the title.

```sh
pentimento list [--status STATUS] [--intent INTENT] [--project PROJECT] [--starred]
pentimento tree [--project PROJECT]
pentimento show <id>
pentimento set <id> [--status STATUS] [--intent INTENT] [--parent ID] [--project PROJECT]
pentimento backfill [--dry-run] [--quiet] [--rederive]
pentimento index
pentimento check
```

`backfill` fills in missing fields without touching what's already set.
`--rederive` instead recomputes `status`, `parent`, and `project` from
scratch and overwrites them -- `intent` (operator-owned) and `created`
(immutable) are never touched; a re-derivation that finds no parent removes
an existing `parent` key.

`check` validates the corpus -- dangling parents, self-parents,
cross-project parents, cycles, and off-vocabulary `status`/`intent` values
-- and exits 1 on any finding.

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

Lineage is read from the harness's own session logs, in
`${AGENT_SESSIONS_DIR:-$HOME/.claude/projects}/<encoded-dir>/<uuid>.jsonl` —
one directory per project, one file per session. Each plan's id is a
session `slug`; a plan's parent is whichever earlier, same-project plan its
originating session's first prompt (or, failing that, the plan body above
its first `##` heading) references by `<id>.md`. `project` is the basename
of the common path across a session's `cwd` values. Never guessed: a plan
with no session record and no reference falls back to no parent and no
project.

Zero runtime dependencies: this is stdlib-only Python 3, no PyYAML, so it
ships as a plain CLI.
