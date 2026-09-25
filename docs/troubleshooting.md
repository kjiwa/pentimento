# Troubleshooting

Indexed by symptom: an empty field, a `check` finding, an exit 1. Look here
when the output is not what you expected.

## No output at all

`pentimento: no plans found; searched: <directories>; set AGENT_PLANS_DIR or
CURSOR_PLANS_DIR to search elsewhere` on stderr, with exit 0, means every plan
directory is missing or empty. `AGENT_PLANS_DIR` (default
`~/.claude/plans`) or `CURSOR_PLANS_DIR` pointing at a directory that doesn't
exist contributes nothing: a missing harness is a normal, supported state, not
an error. Check the directories named in the message actually hold `.md` files
(or `.plan.md` for Cursor). `list`, `tree`, `index`, `backfill`, and `check`
print the message in every `--format`; `--format json` still prints `[]` on
stdout.

## `project` is empty

Either there's no session transcript for that plan (nothing in
`AGENT_SESSIONS_DIR`, default `~/.claude/projects`, records that plan's id as a
session `slug` or shows a session writing the plan file), it's a Cursor plan
that fails the [name-match rule](integrations.md#cursor) against
`CURSOR_SESSIONS_DIR` (default `~/.cursor/projects`), or `backfill` hasn't run
since the session transcript appeared; run `pentimento backfill` (or `check`,
which flags this as `underived-project`). With the `pentimento hook`
`PostToolUse` hook installed ([docs/integrations.md](integrations.md)), a Claude
Code plan gets `project` on its first write, so a persistently empty `project`
there is an anomaly worth investigating, not the steady state.

## `parent` is empty

`backfill` tries two signals in order, stopping at the first that finds a
candidate: a reference in the originating session's first prompt, then the same
reference scan over the plan's body above its first `##` heading. A reference
is either an `<id>.md` / `<id>.plan.md` literal or a
[short id](reference.md#plan-ids), a trailing run of segments such as
`auth-redesign` for `api-auth-redesign`. A short id that matches more than one
candidate resolves to nothing. Either way, the reference must
also pass every one of these guards: not the plan itself, in the same project,
from the same source, and strictly earlier by `started`. Among references that
pass, an exact `<id>.md` reference outranks a short-id reference, and the
earliest-mentioned reference wins a tie within that ranking. If no reference
passes all four guards, `parent` stays unset rather than guessed; `check` flags
this as `unadopted-reference`.

## `status: unknown`

`unknown` means no status signal produced an answer. There are three, tried
in order; the first to answer wins:

1. The `## Progress` section: checkboxes, else a prose phrase (`nothing
   started`, `planning only`, `not started`, `no progress`).
2. A Cursor plan's `todos:` frontmatter: all `pending` is `not-started`, all
   `completed` is `complete`, any other mix of `pending`, `in_progress`, and
   `completed` is `partial`. An empty list or any other todo status answers
   nothing.
3. Checkboxes anywhere in the body, consulted only when there is no
   `## Progress` heading at all.

With a `## Progress` heading present, checkboxes elsewhere in the body are
not read.

`check` reports it as `underivable-status`. Two ways out:

- Add checkboxes, or one of the prose phrases, to the `## Progress`
  section, then run `backfill`. Plain `backfill` advances `status` when the
  status signals are ahead of it; `--rederive` recomputes it outright.
- State the status yourself: `pentimento set <id> --status <value>`. That
  pins it, so `backfill` leaves it alone and `check` stops reporting the
  status findings for the plan; only [`pin-behind-progress`](#check-findings)
  still applies.

## `check` findings

Every finding's `code`, with its fix. Status findings name the signal they
read: `'## Progress'`, `todos`, or `body checkboxes`. `check` prints the fix
as a hint under its summary, and `--format json|tsv` carries it in `hint`;
`show <id>` prints it with that plan's findings, minus the `pentimento show
<id>` step it is already running.

A plan whose status is explicit is never second-guessed: one with `pinned` set
(any `set --status` pins) or a `superseded` status. The status findings
`underivable-status`, `status-behind-history`, and `status-behind-progress`
skip it. Only `pin-behind-progress` applies, and only when the pin sits below
what the status signals derive.

| Code | Meaning | Fix |
| --- | --- | --- |
| `unreadable-file` | A plan file couldn't be read, e.g. for permissions or a non-UTF-8 encoding; the message names the path and the error. Only `check` reports it; `--finding` does not take it. | Check the file's permissions and encoding. |
| `dangling-parent` | `parent` doesn't match any plan's id. | `pentimento set <id> --parent <id>`, or `--clear-parent`. `backfill --rederive` also drops a `parent` that no longer resolves. |
| `self-parent` | `parent` is the plan's own id. | `pentimento set <id> --clear-parent`. |
| `cross-project-parent` | `parent` resolves to a plan in a different `project`. | `pentimento set <id> --project <name>` on whichever plan is wrong. |
| `cycle` | Following `parent` links eventually loops back to the plan itself. | `pentimento set <id> --parent <id>`, or `--clear-parent`, on one plan in the chain. |
| `duplicate-id` | The same id appears from two sources (e.g. a Claude plan and a Cursor plan share a filename stem). | Rename one of the files. |
| `off-vocabulary-status` | `status` isn't one of `not-started`, `partial`, `complete`, `superseded`, `unknown`. | `pentimento set <id> --status <value>`. |
| `off-vocabulary-intent` | `intent` isn't one of `active`, `queued`, `someday`, `abandoned`, `unset`. | `pentimento set <id> --intent <value>`. |
| `missing-title` | The body has no H1, so `title` falls back to the plan id. | Add a '# Title' line to the plan body. |
| `malformed-tag` | A tag doesn't match `^[a-z0-9][a-z0-9._/-]*$`. | `pentimento set <id> --remove-tag <bad> --add-tag <fixed>`. |
| `underived-project` | The plan has no `project`, but its session transcript supplies one, meaning `backfill` hasn't caught up. | `pentimento backfill`. With the `PostToolUse` hook installed ([docs/integrations.md](integrations.md)) this finding is an anomaly. |
| `underivable-status` | `status` is `unknown` and no status signal derives anything better; see [`status: unknown`](#status-unknown). | Add a checklist to '## Progress', or `pentimento show <id>`, then `pentimento set <id> --status <value>`. |
| `status-behind-history` | `status` is `not-started` or `unknown`, but a later session, other than the one that wrote the plan, edited, wrote, or delegated work on the plan; sessions that only read it don't count (`pentimento history <id>` lists both). | Tick the plan's '## Progress', or `pentimento history <id>`, then `pentimento set <id> --status <value>` (pins). This finding never fires the other way, so a plan with no history isn't flagged as unworked. |
| `status-behind-progress` | A status signal derives a further-along `status` than the one stored, including a stored `unknown`. | `pentimento backfill`, or `pentimento show <id>`, then `pentimento set <id> --status <value>`. |
| `pin-behind-progress` | `pinned` is set, but a status signal derives a further-along `status` than the pinned one. | `pentimento show <id>`, then `pentimento set <id> --status <value>`, or `pentimento set <id> --unpin` to hand the status back to `backfill`. |
| `unadopted-reference` | The plan has no `parent`, but a session-prompt or body reference would resolve to one under the same guards `backfill` applies. | `pentimento backfill`, or leave it if the omission was deliberate. `backfill` adopts the reference. |
| `unadopted-tag` | The plan has no tags, but its parent is tagged and at least one tagged sibling exists; the thread's evidence is the tags the parent and every tagged sibling share, and the message names them. Any tag on the plan clears the finding. | `pentimento set <id> --add-tag <tag>`; `set` takes several ids, so one command clears a thread. |

## `list` shows records instead of a table

The terminal is too narrow for every column. Widen it, or pick fewer columns
with `--columns`; see [Columns](reference.md#columns) for the layout rule and
which columns appear when.

## `history` is empty

`pentimento: no session history for <id>; searched: <directory>` (on stderr,
exit 0) means no transcript under that directory (`AGENT_SESSIONS_DIR`, default
`~/.claude/projects`) contains a tool call whose target path, or a `Task`
call's prompt, names that plan. It is never a claim the plan wasn't worked.
Common causes: the work happened in a session whose transcript has since been
deleted (Claude Code prunes old transcripts), or on a different machine. A
Cursor chat never appears in `history`, since Cursor transcripts feed only
`project` and prompt lineage. Absent history is not evidence of absent work.

## No color

Color follows `--color`; see [reference.md](reference.md#flags) for when it is
off. Pass `--color always` to force it, e.g. when piping `list` through `less
-R`.

## A plan id doesn't resolve

`show`, `set`, `tree`, `history`, and `backfill --only` exit 1 and print `no
such plan: '<id>'` to stderr when the id doesn't resolve to exactly one plan; see
[Plan ids](reference.md#plan-ids) for the accepted forms. If a close match
exists in the corpus, the message also appends `; did you mean: '<id>'?`. If a
short id matches more than one plan, the message is instead `ambiguous plan id:
'<id>'; matches: '<id1>', '<id2>'` — use the full id to disambiguate. `set
--parent` also exits 1, before writing anything, if the given parent id doesn't
resolve, and exits 2 if the parent would create a cycle.

`--clear-parent` clears the `parent` key; `--clear-project` clears the
`project` key. `--parent ""` and `--project ""` are not shorthand for clearing
— `--project ""` writes a literal empty string, and `--parent ""` looks up a
plan with the empty string as its id and fails with `no such plan`.

A `--project` or `--add-tag` value that can't be written to frontmatter is a
usage error, not a missing plan: it exits 2, writes nothing, and the message
states the valid form.

## Completions don't fire

Restart the shell after installing a completion script — `bash`/`zsh` only read
`complete`/`compdef` registrations at startup. For zsh, the directory holding
`pentimento completion zsh`'s output must be on `fpath` *before* `compinit`
runs, or autoload never finds `_pentimento`; `eval "$(pentimento completion
zsh)"` sidesteps `fpath` entirely and works either way. On macOS system bash
(3.2), install `bash-completion` (Homebrew: `brew install bash-completion@2`)
and source it before `pentimento completion bash`'s output — bash's `complete
-F` registration works without it, but interactive `<TAB>` handling on a stock
macOS shell is otherwise unreliable.

## Frontmatter isn't recognized

A frontmatter block is only recognized when the file's first three bytes are
literally `---\n`. A `---` used as a Markdown horizontal rule later in the body
is never treated as a delimiter, but a stray blank line or comment before the
opening `---` means the whole block is read as body text instead.