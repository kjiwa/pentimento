# Troubleshooting

## No output at all

`AGENT_PLANS_DIR` (default `~/.claude/plans`) or `CURSOR_PLANS_DIR` unset or
pointing at a directory that doesn't exist contributes nothing, silently —
a missing harness is a normal, supported state, not an error
([sources.py](../pentimento/sources.py)). Check the directory actually
holds `.md` files (or `.plan.md` for Cursor).

## `project` is empty

Either there's no session log for that plan (nothing in
`AGENT_SESSIONS_DIR`, default `~/.claude/projects`, records that plan's id
as a session `slug`), it's a Cursor plan — Cursor keeps no session logs, so
`project` is never derived for one
([sessions.py](../pentimento/sessions.py)) — or `backfill` hasn't run since
the session log appeared; run `pentimento backfill` (or `check`, which flags
this as `underived-project`). With the `pentimento hook` `PostToolUse` hook
installed ([docs/integrations.md](integrations.md)), a Claude Code plan gets
`project` on its first write, so a persistently empty `project` there is an
anomaly worth investigating, not the steady state.

## `parent` is empty

`derive_parent` ([lineage.py](../pentimento/lineage.py)) tries two signals in
order, stopping at the first that finds a candidate: an `<id>.md` reference
in the originating session's first prompt, then the same reference scan over
the plan's body above its first `##` heading. Either way, the reference must
also pass every one of these guards: not the plan itself, in the same
project, from the same source, and strictly earlier by `started`. If no
reference passes all four guards, `parent` stays unset rather than guessed.

## `status: unknown`

`unknown` means neither signal in [status.py](../pentimento/status.py)
produced an answer. There are two ways to land here:

- There's no `## Progress` heading at all, and no checkboxes anywhere in
  the body (checkboxes outside a `## Progress` section are only consulted
  when the heading is entirely absent — a Cursor plan, say).
- There is a `## Progress` heading, but its section has no checkboxes and
  no recognized prose phrase (`nothing started`, `planning only`,
  `not started`, `no progress`). Body-wide checkboxes are *not* consulted
  in this case — a `## Progress` heading commits the section to being the
  only signal read.

Add checkboxes or one of the prose phrases to the `## Progress` section,
then run `backfill` — status is recomputed on every run now, not just
`--rederive`.

## `check` findings

Every finding's `code`, from [check.py](../pentimento/check.py):

| Code | Meaning | Fix |
| --- | --- | --- |
| `dangling-parent` | `parent` doesn't match any plan's id. | Fix the reference by hand, or run `backfill --rederive`, which drops a `parent` that no longer resolves. |
| `self-parent` | `parent` is the plan's own id. | Fix the frontmatter by hand. |
| `cross-project-parent` | `parent` resolves to a plan in a different `project`. | Usually one of the two plans has the wrong `project`; fix with `pentimento set <id> --project <name>`. |
| `cycle` | Following `parent` links eventually loops back to the plan itself. | Break the cycle by clearing or correcting one link in the chain. |
| `duplicate-id` | The same id appears from two sources (e.g. a Claude plan and a Cursor plan share a filename stem). | Rename one of the files. |
| `off-vocabulary-status` | `status` isn't one of [`vocabulary.py`](../pentimento/vocabulary.py)'s `STATUS_ORDER`. | Fix by hand or run `backfill --rederive`. |
| `off-vocabulary-intent` | `intent` isn't one of `vocabulary.py`'s `INTENT_VALUES`. | Fix with `pentimento set <id> --intent <value>`. |
| `missing-title` | The body has no H1, so `title` falls back to the plan id. | Add a `# Title` line to the body. |
| `malformed-tag` | A tag fails `tags.is_valid` (must match `^[a-z0-9][a-z0-9._/-]*$`). | Fix with `pentimento set <id> --remove-tag <bad> --add-tag <fixed>`. |
| `missing-progress` | The body has no `## Progress` heading, so `status` can never be more than a guess from body-wide checkboxes. | Add a `## Progress` heading with `- [ ]` / `- [x]` items. |
| `underived-project` | The plan has no `project`, but its session log supplies one, meaning `backfill` hasn't caught up. | Run `pentimento backfill`. With the `PostToolUse` hook installed this finding is now an anomaly, not the steady state — see [docs/integrations.md](integrations.md). |
| `status-behind-history` | `status` is `not-started` or `unknown`, but a later, differently-slugged session read, edited, or delegated work on the plan (see [touches.py](../pentimento/touches.py)). | Run `pentimento history <id>` to see the sessions, then `pentimento set <id> --status <value>` on your own judgement — this finding never fires the other way, so a plan with no history isn't flagged as unworked. |
| `status-behind-progress` | `## Progress` checkboxes derive a further-along `status` than what's stored. | Run `pentimento backfill`. |

## `history` is empty

`no session history for <id>` means no transcript under
`AGENT_SESSIONS_DIR` (default `~/.claude/projects`) contains a `tool_use`
call naming that plan's path — never a claim the plan wasn't worked. Common
causes: the work happened in a session whose transcript has since been
deleted (Claude Code prunes old transcripts), or on a different machine.
Absent history is not evidence of absent work.

## No colour

`--color` defaults to `auto`: off when stdout isn't a tty, when `NO_COLOR`
is set, or when `TERM=dumb`
([style.py](../pentimento/style.py)). Pass `--color always` to force it,
e.g. when piping through `less -R`.

## `set` or `show` exits 1

Both exit 1 and print `no such plan: <id>` to stderr when the id doesn't
resolve to exactly one plan; if a close match exists in the corpus, the
message also appends `-- did you mean: <id>?` (`corpus.suggest`, via
`difflib`). If a short id matches more than one plan, the message is instead
`ambiguous plan id: <id> -- matches: <id1>, <id2>` — use the full id to
disambiguate. `set --parent` also exits 1, before writing anything, if the
given parent id doesn't resolve.

`corpus.by_id` accepts more than the bare id: a full filename
(`some-plan.md`), or the id with a `.md` or `.plan.md` suffix still
attached, both resolve the same as the bare id.

`--clear-parent` clears the `parent` key; `--clear-project` clears the
`project` key. `--parent ""` and `--project ""` are not shorthand for
clearing — `--project ""` writes a literal empty string, and `--parent ""`
looks up a plan with the empty string as its id and fails with `no such
plan`.

## Frontmatter isn't recognized

A frontmatter block is only recognized when the file's first three bytes
are literally `---\n` ([frontmatter.py](../pentimento/frontmatter.py)). A
`---` used as a Markdown horizontal rule later in the body is never treated
as a delimiter, but a stray blank line or comment before the opening `---`
means the whole block is read as body text instead.
