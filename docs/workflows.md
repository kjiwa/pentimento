# Workflows

## Triage

`pentimento list --starred` shows only `active`/`queued` intent -- the
plans worth looking at today. Narrow further with `--intent active` (just
the ones in flight) or `--intent queued` (up next). `--status` filters by
lifecycle stage independently of intent, so `--status partial --starred`
finds work that's underway and still wanted.

## Recording supersession

`status` is maintained automatically -- `backfill` recomputes it from the
`## Progress` checkboxes on every run, plain or `--rederive`. `set --status`
exists for the two cases that are always the operator's call: marking a
plan `superseded` (a value `backfill` never derives and never overwrites),
and overriding a derivation that's stuck at `unknown` (no `## Progress`
heading, or one with neither checkboxes nor a recognized prose phrase).

When a plan is replaced rather than finished, mark it explicitly instead of
leaving it to rot as `not-started`:

```sh
pentimento set old-plan-id --status superseded
pentimento set old-plan-id --parent new-plan-id
```

`intent` is never touched by `set --status` or by `backfill` --
it's operator-owned, so a superseded plan can still be `abandoned` (nobody's
picking it up) or `active` (its replacement is what's active, but you still
want the paper trail flagged). Nothing infers intent from status.

## Triaging by tag

`pentimento list --tag auth --tag security` narrows to plans carrying both
tags -- repeated `--tag` is an AND filter, like every other filter. Tags are
operator-owned and cross-cutting, so they group plans across projects in a
way `--project` can't; use `set --add-tag`/`--remove-tag`/`--clear-tags` to
maintain them.

## Reading lineage

`pentimento tree --project platform` groups a project's plans into ASCII
trees, root to leaf, so you can see which plan is a re-attempt of which. A
plan whose recorded parent isn't in the filtered set gets a
`(parent elided: <id>)` annotation on its root line rather than silently
becoming a root -- run `tree` without `--project` to see the whole chain.

## Backfilling safely

Run `pentimento backfill --dry-run` periodically to see what a real run
would change before it writes anything. Its footer reports `N plans updated`
(or `N plans would change (dry run)`, or `no changes`), so a dry run is never
mistaken for a real one; `--quiet` suppresses the footer along with the id
list. Plain `backfill` always recomputes `status`, and fills in `parent` and
`project` only if missing; `--rederive` additionally recomputes `parent` and
`project` from scratch and overwrites them, which is safe to run repeatedly
but will remove a `parent` that no longer resolves.
`--recreate` is the one flag that touches `created`, and should only be run
once, deliberately, to fix a plan whose `created` was derived incorrectly --
never as part of a routine job.

## Publishing an index

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
id, title, status, intent, tags, parent, project, source, created, started, modified, path
```

(see [record.py](../pentimento/record.py)). `tsv` drops non-scalar fields
-- a `tree --format tsv` row has no `children` column, only the flat record
-- so use `json` when you need the nested tree structure
([formats.py](../pentimento/formats.py)). A common pattern:

```sh
pentimento list --format json | jq -r '.[] | select(.status == "not-started") | .id'
```
