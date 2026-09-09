# Troubleshooting

## No output at all

`AGENT_PLANS_DIR` (default `~/.claude/plans`) or `CURSOR_PLANS_DIR` unset or
pointing at a directory that doesn't exist contributes nothing, silently --
a missing harness is a normal, supported state, not an error
([sources.py](../pentimento/sources.py)). Check the directory actually
holds `.md` files (or `.plan.md` for Cursor).

## `project` is empty

Either there's no session log for that plan (nothing in
`AGENT_SESSIONS_DIR`, default `~/.claude/projects`, records that plan's id
as a session `slug`), or it's a Cursor plan -- Cursor keeps no session logs,
so `project` is never derived for one
([sessions.py](../pentimento/sessions.py)).

## `parent` is empty

`lineage.py`'s eligibility guards ([lineage.py](../pentimento/lineage.py))
require a candidate parent to be: not the plan itself, in the same project,
from the same source, strictly earlier by `started`, and referenced by
`<id>.md` in either the originating session's first prompt or the plan's
body above its first `##` heading. If a reference doesn't meet all four,
`parent` stays unset rather than guessed.

## `status: unknown`

`unknown` means neither signal in [status.py](../pentimento/status.py)
produced an answer: no `## Progress` heading and no checkboxes anywhere in
the body. Add a `## Progress` section with `- [ ]` / `- [x]` items, or run
`backfill --rederive` once it's there.

## `check` findings

Each finding code and its fix ([check.py](../pentimento/check.py)):

- `dangling-parent` -- `parent` doesn't match any plan's id. Fix the
  reference by hand, or run `backfill --rederive`, which drops a `parent`
  that no longer resolves to anything.
- `self-parent` -- `parent` is the plan's own id. Fix the frontmatter by
  hand.
- `cross-project-parent` -- `parent` resolves to a plan in a different
  `project`. Usually means one of the two plans has the wrong `project`;
  fix that with `pentimento set <id> --project <name>`.
- `cycle` -- following `parent` links eventually loops back to the plan
  itself. Break the cycle by clearing or correcting one link in the chain.
- `duplicate-id` -- the same id appears from two sources (e.g. a Claude
  plan and a Cursor plan share a filename stem). Rename one of the files.
- `off-vocabulary-status` -- `status` isn't one of
  [`pentimento/vocabulary.py`](../pentimento/vocabulary.py)'s
  `STATUS_ORDER`. Fix by hand or run `backfill --rederive`.
- `off-vocabulary-intent` -- `intent` isn't one of `vocabulary.py`'s
  `INTENT_VALUES`. Fix with `pentimento set <id> --intent <value>`.

## No colour

`--color` defaults to `auto`: off when stdout isn't a tty, when `NO_COLOR`
is set, or when `TERM=dumb`
([style.py](../pentimento/style.py)). Pass `--color always` to force it,
e.g. when piping through `less -R`.

## `set` or `show` exits 1

Both exit 1 and print `no such plan: <id>` to stderr when the id doesn't
match any plan's filename stem. `set --parent` also exits 1, before writing
anything, if the given parent id doesn't resolve.

## Frontmatter isn't recognized

A frontmatter block is only recognized when the file's first three bytes
are literally `---\n` ([frontmatter.py](../pentimento/frontmatter.py)). A
`---` used as a Markdown horizontal rule later in the body is never treated
as a delimiter, but a stray blank line or comment before the opening `---`
means the whole block is read as body text instead.
