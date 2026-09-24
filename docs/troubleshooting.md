# Troubleshooting

Indexed by symptom: an empty field, a `check` finding, an exit 1. Look here
when the output is not what you expected.

## No output at all

`AGENT_PLANS_DIR` (default `~/.claude/plans`) or `CURSOR_PLANS_DIR` unset or
pointing at a directory that doesn't exist contributes nothing, silently —
a missing harness is a normal, supported state, not an error. Check the
directory actually holds `.md` files (or `.plan.md` for Cursor).

## `project` is empty

Either there's no session log for that plan (nothing in
`AGENT_SESSIONS_DIR`, default `~/.claude/projects`, records that plan's id
as a session `slug`), it's a Cursor plan — Cursor keeps no session logs, so
`project` is never derived for one — or `backfill` hasn't run since the
session log appeared; run `pentimento backfill` (or `check`, which flags
this as `underived-project`). With the `pentimento hook` `PostToolUse` hook
installed ([docs/integrations.md](integrations.md)), a Claude Code plan gets
`project` on its first write, so a persistently empty `project` there is an
anomaly worth investigating, not the steady state.

## `parent` is empty

`backfill` tries two signals in order, stopping at the first that finds a
candidate: a reference in the originating session's first prompt, then the
same reference scan over the plan's body above its first `##` heading. A
reference is either an `<id>.md` / `<id>.plan.md` literal or a trailing
codename — the same segment-aligned suffix `pentimento show` and `list`
accept, e.g. `wobbly-willow` for an id ending `...-wobbly-willow`. A codename
that matches more than one candidate id resolves to nothing. Either way, the
reference must also pass every one of these guards: not the plan itself, in
the same project, from the same source, and strictly earlier by `started`.
Among references that pass, an exact `<id>.md` reference outranks a codename
reference, and the earliest-mentioned reference wins a tie within that
ranking. If no reference passes all four guards, `parent` stays unset rather
than guessed; `check` flags this as `unadopted-reference`.

## `status: unknown`

`unknown` means neither status signal produced an answer. There are two ways
to land here:

- There's no `## Progress` heading at all, and no checkboxes anywhere in
  the body (checkboxes outside a `## Progress` section are only consulted
  when the heading is entirely absent — a Cursor plan, say).
- There is a `## Progress` heading, but its section has no checkboxes and
  no recognized prose phrase (`nothing started`, `planning only`,
  `not started`, `no progress`). Body-wide checkboxes are *not* consulted
  in this case — a `## Progress` heading commits the section to being the
  only signal read.

`check` reports it as `underivable-status`. Two ways out:

- Add checkboxes, or one of the prose phrases, to the `## Progress`
  section, then run `backfill`. Status is recomputed on every run, not just
  `--rederive`.
- State the status yourself: `pentimento set <id> --status <value>`. That
  pins it, so `backfill` leaves it alone and `check` stops reporting status
  findings for the plan.

## `check` findings

Every finding's `code`, with its fix. `check` prints the same fix as a
hint under its summary, and `--format json|tsv` carries it in `hint`.

A plan whose status is explicit is never second-guessed: one with `pinned`
set (any `set --status` pins) or a `superseded` status. The status findings
`underivable-status`, `status-behind-history`, and `status-behind-progress`
skip it. Only `pin-behind-progress` applies, and only when the pin sits
below what `## Progress` derives.

| Code | Meaning | Fix |
| --- | --- | --- |
| `unreadable-file` | A plan file couldn't be read, e.g. for permissions or a non-UTF-8 encoding; the message names the path and the error. | Fix the file's permissions or encoding. |
| `dangling-parent` | `parent` doesn't match any plan's id. | Fix the reference by hand, or run `backfill --rederive`, which drops a `parent` that no longer resolves. |
| `self-parent` | `parent` is the plan's own id. | Fix the frontmatter by hand. |
| `cross-project-parent` | `parent` resolves to a plan in a different `project`. | Usually one of the two plans has the wrong `project`; fix with `pentimento set <id> --project <name>`. |
| `cycle` | Following `parent` links eventually loops back to the plan itself. | Break the cycle by clearing or correcting one link in the chain. |
| `duplicate-id` | The same id appears from two sources (e.g. a Claude plan and a Cursor plan share a filename stem). | Rename one of the files. |
| `off-vocabulary-status` | `status` isn't one of `not-started`, `partial`, `complete`, `superseded`, `unknown`. | Fix by hand or run `backfill --rederive`. |
| `off-vocabulary-intent` | `intent` isn't one of `active`, `queued`, `someday`, `abandoned`, `unset`. | Fix with `pentimento set <id> --intent <value>`. |
| `missing-title` | The body has no H1, so `title` falls back to the plan id. | Add a `# Title` line to the body. |
| `malformed-tag` | A tag doesn't match `^[a-z0-9][a-z0-9._/-]*$`. | Fix with `pentimento set <id> --remove-tag <bad> --add-tag <fixed>`. |
| `underived-project` | The plan has no `project`, but its session log supplies one, meaning `backfill` hasn't caught up. | Run `pentimento backfill`. With the `PostToolUse` hook installed this finding is now an anomaly, not the steady state — see [docs/integrations.md](integrations.md). |
| `underivable-status` | `status` is `unknown` and `## Progress` derives nothing better; see [`status: unknown`](#status-unknown). | Add checkboxes to `## Progress`, or `pentimento show <id>`, then `pentimento set <id> --status <value>`. |
| `status-behind-history` | `status` is `not-started` or `unknown`, but a later, differently-slugged session read, edited, or delegated work on the plan (`pentimento history <id>` lists them). | Run `pentimento history <id>` to see the sessions, then `pentimento set <id> --status <value>` on your own judgement. This finding never fires the other way, so a plan with no history isn't flagged as unworked. |
| `status-behind-progress` | `## Progress` checkboxes derive a further-along `status` than the one stored, including a stored `unknown`. | Run `pentimento backfill`, or `pentimento set <id> --status <value>`. |
| `pin-behind-progress` | `pinned` is set, but `## Progress` derives a further-along `status` than the pinned one. | Nothing is fixed automatically. `pentimento show <id>`, then `pentimento set <id> --status <value>`, or `--unpin` to hand the status back to `backfill`. |
| `unadopted-reference` | The plan has no `parent`, but a session-prompt or body reference would resolve to one under the same guards `backfill` applies. | Run `pentimento backfill` to adopt it, or leave it if the omission was deliberate. |

## A `list` column I expected is missing

`TAGS`, `CREATED`, and `FINDING` only appear when at least one plan in the
result has tags, a `created` date, or a finding; every other column always
appears unless the table is too narrow, in which case columns drop by rank
before any column is truncated ([docs/reference.md#columns](reference.md#columns)).
`--columns` (or `PENTIMENTO_COLUMNS`) names exactly the columns you want, in
order, and overrides both rules; the column the active `--sort` key uses
never drops either way.

## `history` is empty

`no session history for <id>` means no transcript under
`AGENT_SESSIONS_DIR` (default `~/.claude/projects`) contains a `tool_use`
call naming that plan's path — never a claim the plan wasn't worked. Common
causes: the work happened in a session whose transcript has since been
deleted (Claude Code prunes old transcripts), or on a different machine.
Absent history is not evidence of absent work.

## No colour

`--color` defaults to `auto`: off when stdout isn't a tty, when `NO_COLOR`
is set, or when `TERM=dumb`. Pass `--color always` to force it, e.g. when piping `list` through `less -R`. `show --full` needs no flag: it
pages with colour on its own.

## `set` or `show` exits 1

Both exit 1 and print `no such plan: <id>` to stderr when the id doesn't
resolve to exactly one plan; if a close match exists in the corpus, the
message also appends `-- did you mean: <id>?` (a close-match search over the
corpus's ids). If a short id matches more than one plan, the message is
instead `ambiguous plan id: <id> -- matches: <id1>, <id2>` — use the full id
to disambiguate. `set --parent` also exits 1, before writing anything, if the
given parent id doesn't resolve.

Every command that takes a plan id accepts more than the bare id: a full filename
(`some-plan.md`), or the id with a `.md` or `.plan.md` suffix still
attached, both resolve the same as the bare id.

`--clear-parent` clears the `parent` key; `--clear-project` clears the
`project` key. `--parent ""` and `--project ""` are not shorthand for
clearing — `--project ""` writes a literal empty string, and `--parent ""`
looks up a plan with the empty string as its id and fails with `no such
plan`.

## Completions don't fire

Restart the shell after installing a completion script — `bash`/`zsh` only
read `complete`/`compdef` registrations at startup. For zsh, the directory
holding `pentimento completion zsh`'s output must be on `fpath` *before*
`compinit` runs, or autoload never finds `_pentimento`; `eval
"$(pentimento completion zsh)"` sidesteps `fpath` entirely and works either
way. On macOS system bash (3.2), install `bash-completion` (Homebrew:
`brew install bash-completion@2`) and source it before
`pentimento completion bash`'s output — bash's `complete -F` registration
works without it, but interactive `<TAB>` handling on a stock macOS shell is
otherwise unreliable.

## Frontmatter isn't recognized

A frontmatter block is only recognized when the file's first three bytes
are literally `---\n`. A
`---` used as a Markdown horizontal rule later in the body is never treated
as a delimiter, but a stray blank line or comment before the opening `---`
means the whole block is read as body text instead.
