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
pentimento backfill [--dry-run] [--new-only] [--quiet]
pentimento index
```

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
operator, so a half-implemented plan can still be marked abandoned.

Zero runtime dependencies: this is stdlib-only Python 3, no PyYAML, so it
ships as a plain CLI.
