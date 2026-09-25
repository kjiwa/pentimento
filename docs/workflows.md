# Workflows

Task-oriented recipes: triage, reusing past decisions, supersession, lineage,
working through `check`, auditing, scripting. Look here for what to do; for
exact flags, see [reference.md](reference.md).

## Triage

`pentimento list --starred` shows only `active`/`queued` intent — the plans
worth looking at today. Narrow further with `--intent active` (just the ones in
flight) or `--intent queued` (up next). `--status` filters by lifecycle stage
independently of intent, so `--status partial --starred` finds work that's
underway and still wanted. `--title PATTERN` and `--grep PATTERN` narrow by a
case-insensitive regex over the title, or over title and body, when a
status/intent/tag filter isn't specific enough; `--project .` filters to the
current directory's project without typing its name out.

To see what a week held, bound the date range. `--since` and `--until` take a
`YYYY-MM-DD` date or an age in the units the `UPDATED` column prints (`14m`,
`5h`, `3d`, `2w`, `1y`), and both ends are inclusive local days:

```sh
pentimento list --status complete --since 1w
pentimento list --status complete --since 2026-09-14 --until 2026-09-20
pentimento list --since 1w --date created
```

The range tests `modified` by default, the same value `list` shows and sorts
by. `--date created` tests when the plan was first written instead, which
answers "what did I start this week" rather than "what did I touch". An age
resolves to a day, so `--since 5h` means today, not five hours ago.

## Picking a plan back up

A plan often finishes with findings worth following up that you will not chase
today. Park it when execution ends, while you still know what it was about:

```sh
pentimento set some-plan-id --add-tag growthbook --intent someday
```

Weeks later, find it by tag, or by state if you never tagged it:

```sh
pentimento list --tag growthbook
pentimento list --status partial --starred
```

`pentimento show <id> --full` reopens the whole plan, and `pentimento history
<id>` lists the sessions that touched it since. When you resume, move it out of
`someday` with `set <id> --intent active`.

`set` takes several ids, so a triage pass can park or tag a batch at once.
Every id is resolved before anything is written, and `--dry-run` previews the
whole batch:

```sh
pentimento set wobbly-willow api-auth-cleanup --intent someday --dry-run
pentimento set wobbly-willow api-auth-cleanup --intent someday --add-tag growthbook
```

## Reusing a past decision

A plan from one project often holds the reasoning a change in another project
needs: why a CI matrix was cut, why one service avoids a library. Search for it
before proposing the change, across every project rather than the current one:

```sh
pentimento list --title 'github actions|\bGHA\b|workflow|\bCI\b'
```

Titles are terse and on-topic, so match them first. A pattern is a regex, so
one alternation covers the abbreviations and synonyms the author might have
used (`GHA`, `GH`, `Actions`); matching ignores case. If the title search finds
nothing, widen to title and body with `--grep`, or to `--tag` for a tag you
know you used. Narrow a long result with `--status partial` (work still in
flight, the plans most likely to collide with your change) or `--since 12w`.

Then read the plan itself, and follow its thread if the decision spans several:

```sh
pentimento show some-plan-id --full
pentimento tree some-plan-id --ancestors
```

A plan records what was decided, not what shipped; check the plan's claims
against the repository before relying on them. A `superseded` plan is evidence
for why an option was rejected, not a requirement.

The [`prior-plans` skill](integrations.md#prior-plans-skill) has a coding agent
run this search itself before it plans a change to shared infrastructure, so
you do not have to remember to hand it the plan.

## Recording supersession

When a plan is replaced rather than finished, mark it explicitly instead of
leaving it to rot as `not-started`:

```sh
pentimento set old-plan-id --status superseded
pentimento set old-plan-id --parent new-plan-id
```

`intent` is never touched by this — a superseded plan can still be `abandoned`
(nobody's picking it up) or `active` (its replacement is what's active, but you
still want the paper trail flagged). A corpus-wide `backfill --rederive`
replaces or drops a `parent` set this way, since no plan reference derives it.
See the README's [Frontmatter table](../README.md#frontmatter) for the full
`status`/`intent` ownership rules.

## Triaging by tag

`pentimento list --tag auth --tag security` narrows to plans carrying both tags
— repeated `--tag` is an AND filter, like every other filter. Tags are
operator-owned and cross-cutting, so they group plans across projects in a way
`--project` can't; use `set --add-tag`/`--remove-tag`/`--clear-tags` to
maintain them. `--tag` matches whole tags, ignoring case; to match a topic by a
fuzzier pattern, use `--title` or `--grep`. Lineage is structural, not
cross-cutting: pulling a single thread of subplans back out is `tree <id>`'s
job, not a tag's.

A thread whose subplans are mostly tagged surfaces the stragglers: `check`
flags an untagged plan as `unadopted-tag` when its parent and a tagged sibling
share tags. One command per thread applies the tag to all of them:

```sh
pentimento list --finding unadopted-tag
pentimento set <id> <id> --add-tag <tag>
```

## Following a thread

A topic often outgrows one plan and spawns subplans, but tagging them is manual
and easy to leave inconsistent — a plan filter like `--tag` then drops
whichever subplan didn't get tagged. `tree <id>` sidesteps that by selecting
the thread structurally: `<id>` plus every plan beneath it, resolved against
the whole corpus, so `--project` is unnecessary.

```sh
pentimento tree wobbly-willow
pentimento tree wobbly-willow --ancestors
pentimento tree wobbly-willow --status partial
```

Plain `tree wobbly-willow` shows the thread from that plan down. `--ancestors`
also walks up to the topmost ancestor, spine only — the ancestors' other
children stay out. `--status partial` filters within the selection, so `tree
<id> --status partial` answers "what's left on this thread". A plan whose
recorded parent isn't in the selection gets a `(parent elided: <id>)`
annotation on its root line: the thread continues above — `--ancestors` shows
it.

To tag a thread instead, `pentimento list --finding unadopted-tag` finds the
untagged subplans and `pentimento set <ids> --add-tag <tag>` tags them in one
command.

`pentimento tree --project platform` still groups a whole project's plans into
trees, root to leaf, for when the unit you want is a project rather than a
thread.

## Backfilling safely

With the `pentimento hook` `PostToolUse` hook and the `SessionEnd` sweep both
installed ([docs/integrations.md](integrations.md)), frontmatter stays current
without a manual step. Run `pentimento backfill --dry-run` periodically anyway
to confirm no unexpected churn — e.g. after installing the hooks for the first
time, or against a corpus a harness wrote to directly. Its footer reports `N
plans updated` (or `N plans would change (dry run)`, or `no changes`);
`--quiet` suppresses the footer along with the id list. `--rederive` and
`--recreate` are correction tools, not routine flags — see the README's
[Frontmatter table](../README.md#frontmatter) for what each overwrites.

## Working through `check`

`check` is the overview: every finding, with the fix for each code under the
summary. To work through them, take one code, and one project if the list is
long, oldest plans first:

```sh
pentimento check
pentimento list --finding underivable-status --project platform --sort created
```

For each plan, `show` prints its findings with their fixes above the body. Read
the plan, then state its status; `set --status` pins it, so `check` stops
second-guessing the plan (see
[docs/troubleshooting.md](troubleshooting.md#check-findings)):

```sh
pentimento show some-plan-id
pentimento set some-plan-id --status complete
```

A cluster under a project name that no longer exists, such as a renamed repo,
is one mistake, not many. List the plans under the old name and point them at
the new one:

```sh
pentimento list --project old-name
pentimento set some-plan-id --project new-name
```

`status-behind-history` is the exception: it needs the session trail before you
can judge it; see [Auditing what was actually
done](#auditing-what-was-actually-done).

## Auditing what was actually done

Frontmatter `status` only reflects what the operator set or `backfill` derived
from `## Progress` checkboxes — it says nothing about whether a later session
actually picked the plan up. `check` surfaces the gap as
`status-behind-history` ([troubleshooting](troubleshooting.md#check-findings)).
`pentimento history <id>` shows a plan's full trail — one row per session,
`authored` for the session that wrote the plan and `worked` for every session
since that touched it.

```sh
pentimento list --finding status-behind-history
pentimento history some-plan-id
```

Absent history is not evidence of absent work
([troubleshooting](troubleshooting.md#history-is-empty)). Set `status` on your
own judgement; neither command writes anything.

## Keeping plans in git

Committing the plans directory gets you review and history, but not every field
survives a checkout on another machine the same way. Each row below says how
the field is computed:

| Field | Survives a checkout | Why |
| --- | --- | --- |
| `status` | Yes | Derived from `## Progress` checkboxes in the body — no transcript involved. |
| `parent` (body-referenced) | Yes | Derived from the plan body, with no transcript involved; see [`parent` is empty](troubleshooting.md#parent-is-empty). |
| `parent` (session-prompt-derived) | No | Derived from the originating session's first prompt, and that transcript is machine-local. |
| `project` | No | Derived from a session's `cwd` entries: no session, no derivation. |
| `modified` | No | Not a frontmatter field at all: `max(session end time, file mtime)` — a fresh checkout's mtime is the checkout time, and there's no session to fall back to. |
| `tags`, `intent`, operator-set `status` | Yes | Operator-authored frontmatter, written by `set`, never derived — plain YAML that travels with the file. |

`pentimento index` writes `INDEX.md` into the plans directory: a browsable,
status-grouped list of every plan, suitable for committing alongside the plans
themselves or serving as a static page.

## Scripting

`check --format json|tsv` emits one record per finding: `code`, `id`,
`message`, `hint`. `code` is the stable, greppable identifier that
[docs/troubleshooting.md](troubleshooting.md) is indexed by; `message` is the
sentence the table prints and `hint` the fix printed under its summary.

`list`, `tree`, and `show` emit the same record for every plan:

```
id, title, status, pinned, intent, tags, parent, project, source, created, started, modified, findings, path
```

`started` and `modified` are UTC instants with whole seconds and a trailing
`Z`; `created` is a date; `findings` holds `check` codes; `pinned` is `true` or
`false` in `tsv`. `show --format json|tsv` adds a `body` field. This schema is
fixed regardless of `--columns`/`PENTIMENTO_COLUMNS`, which shape `list`'s
`--format table` output only. `tsv` drops non-scalar fields: `tree --format tsv`
lists every plan, parents before children, with no `children` column and the
`parent` column carrying the structure, so use `json` when you need the nested
tree. `tree <id> --format json` is the scriptable
"everything on this thread" query. A common pattern:

```sh
pentimento list --format json | jq -r '.[] | select(.status == "not-started") | .id'
```
