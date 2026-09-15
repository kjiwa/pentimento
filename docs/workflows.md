# Workflows

## Triage

`pentimento list --starred` shows only `active`/`queued` intent — the
plans worth looking at today. Narrow further with `--intent active` (just
the ones in flight) or `--intent queued` (up next). `--status` filters by
lifecycle stage independently of intent, so `--status partial --starred`
finds work that's underway and still wanted. `--grep PATTERN` narrows by a
case-insensitive regex over title and body when a status/intent/tag filter
isn't specific enough; `--project .` filters to the current directory's
project without typing its name out.

## Recording supersession

When a plan is replaced rather than finished, mark it explicitly instead of
leaving it to rot as `not-started`:

```sh
pentimento set old-plan-id --status superseded
pentimento set old-plan-id --parent new-plan-id
```

`intent` is never touched by this — a superseded plan can still be
`abandoned` (nobody's picking it up) or `active` (its replacement is what's
active, but you still want the paper trail flagged). See the README's
[Frontmatter table](../README.md#frontmatter) for the full `status`/`intent`
ownership rules.

## Triaging by tag

`pentimento list --tag auth --tag security` narrows to plans carrying both
tags — repeated `--tag` is an AND filter, like every other filter. Tags are
operator-owned and cross-cutting, so they group plans across projects in a
way `--project` can't; use `set --add-tag`/`--remove-tag`/`--clear-tags` to
maintain them.

## Reading lineage

`pentimento tree --project platform` groups a project's plans into Unicode
trees, root to leaf, so you can see which plan is a re-attempt of which
(`--ascii` for plain-text glyphs). A plan whose recorded parent isn't in the
filtered set gets a `(parent elided: <id>)` annotation on its root line
rather than silently becoming a root — run `tree` without `--project` to see
the whole chain.

## Backfilling safely

With the `pentimento hook` `PostToolUse` hook and the `SessionEnd` sweep
both installed ([docs/integrations.md](integrations.md)), frontmatter stays
current without a manual step. Run `pentimento backfill --dry-run`
periodically anyway to confirm no unexpected churn — e.g. after installing
the hooks for the first time, or against a corpus a harness wrote to
directly. Its footer reports `N plans updated` (or `N plans would change
(dry run)`, or `no changes`); `--quiet` suppresses the footer along with the
id list. `--rederive` and `--recreate` are correction tools, not routine
flags — see the README's Frontmatter table for what each overwrites.

## Auditing what was actually done

Frontmatter `status` only reflects what the operator set or `backfill`
derived from `## Progress` checkboxes — it says nothing about whether a
later session actually picked the plan up. `pentimento check` surfaces the
gap: `status-behind-history` fires on any `not-started`/`unknown` plan that
a later, differently-slugged session read, edited, or delegated work on.
`pentimento history <id>` shows that plan's full trail — one row per
session, `authored` for the session that wrote the plan and `worked` for
every session since that touched it.

```sh
pentimento check --format tsv | grep status-behind-history
pentimento history some-plan-id
```

Absence of history is not evidence of absent work — it just means no
transcript naming that plan's path survives on this machine (see
[docs/troubleshooting.md](troubleshooting.md)). Update `status` on the
operator's own judgement; neither command writes anything.

## Keeping plans in git

Committing the plans directory gets you review and history, but not every
field survives a checkout on another machine the same way. Each row below
cites the module that computes the field:

| Field | Survives a checkout | Why |
| --- | --- | --- |
| `status` | Yes | Derived from `## Progress` checkboxes in the body ([status.py](../pentimento/status.py)) — no transcript involved. |
| `parent` (body-referenced) | Yes | One of two lineage signals: a reference to another plan's id in the body preamble above the first `##` heading ([lineage.py](../pentimento/lineage.py)). |
| `parent` (session-prompt-derived) | No | The other lineage signal: a reference in the originating session's first prompt ([lineage.py](../pentimento/lineage.py)) — that transcript is machine-local. |
| `project` | No | Derived from the common path of a session's `cwd` entries ([sessions.py](../pentimento/sessions.py)) — no session, no derivation. |
| `modified` | No | Not a frontmatter field at all: `max(session end time, file mtime)` ([plan.py](../pentimento/plan.py)) — a fresh checkout's mtime is the checkout time, and there's no session to fall back to. |
| `tags`, `intent`, operator-set `status` | Yes | Operator-authored frontmatter, written by `set`, never derived — plain YAML that travels with the file. |

`pentimento index` writes `INDEX.md` into the plans directory: a browsable,
status-grouped list of every plan, suitable for committing alongside the
plans themselves or serving as a static page.

## Scripting

`check --format json|tsv` emits one record per finding: `plan_id`, `code`,
`message` (see [check.py](../pentimento/check.py)'s `Finding`). `code` is
the stable, greppable identifier that
[docs/troubleshooting.md](troubleshooting.md) is indexed by; `message` is
the human-readable sentence the table format prints.

`--format json` and `--format tsv` emit the same record for every plan:

```
id, title, status, pinned, intent, tags, parent, project, source, created, started, modified, path
```

(see [record.py](../pentimento/record.py)). `tsv` drops non-scalar fields
— a `tree --format tsv` row has no `children` column, only the flat record
— so use `json` when you need the nested tree structure
([formats.py](../pentimento/formats.py)). A common pattern:

```sh
pentimento list --format json | jq -r '.[] | select(.status == "not-started") | .id'
```
