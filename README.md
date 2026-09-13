# pentimento

Status, intent, and lineage over agent plan files.

![demo](demo/pentimento.gif)

Claude Code and Cursor (and other harnesses) accumulate plan files with no
status, no starring, and no record of which plan supersedes which. pentimento
reads a directory of plan markdown files, derives a small frontmatter block
for each one (`status`, `intent`, `parent`, `project`, `created`), and gives
you a CLI to list, filter, and render them as a lineage tree.

## Install

```sh
pip install -e .
# or straight from the git URL:
pip install git+https://github.com/kjiwa/pentimento.git
```

## Quick start

Point `AGENT_PLANS_DIR` at your plans directory (it defaults to
`~/.claude/plans`), then:

```sh
pentimento backfill      # derive status/intent/created/parent/project once
pentimento list          # see the corpus
pentimento set some-plan-id --intent active
pentimento list --starred
```

Sources and their default directories are covered in
[docs/integrations.md](docs/integrations.md); Cursor's caveats are in
[docs/troubleshooting.md](docs/troubleshooting.md).

## Commands

```sh
pentimento list [--status STATUS] [--intent INTENT] [--project PROJECT] [--source claude|cursor] [--starred] [--sort modified|created|id|status|title] [--order asc|desc] [--format table|json|tsv] [--color auto|always|never]
pentimento tree [--status STATUS] [--intent INTENT] [--project PROJECT] [--source claude|cursor] [--starred] [--sort modified|created|id|status|title] [--order asc|desc] [--format table|json|tsv] [--color auto|always|never]
pentimento show <id> [--format table|json|tsv] [--color auto|always|never]
pentimento set <id> [--status STATUS] [--intent INTENT] [--parent ID] [--project PROJECT]
pentimento backfill [--dry-run] [--quiet] [--rederive] [--recreate]
pentimento index
pentimento check [--format table|json|tsv] [--color auto|always|never]
```

`--format` defaults to `table` (human-readable); `json` and `tsv` are for
scripting. `--color` defaults to `auto` -- ANSI colour on a tty, off when
piped, `NO_COLOR` is set, or `TERM=dumb`. `--sort` defaults to `modified`;
every sort key is ascending by default, so the row nearest the prompt is the
most recent one, as with `ls -ltr` and `git log --reverse`. `--order desc`
flips it for any key.

The samples below come straight from `demo/fixture.sh` via `demo/capture.sh`
-- a synthetic corpus, not a real one, so no real project names leak here.

### list

<!-- sample:list -->
```
STATUS       INTENT     PROJECT  PLAN
superseded   abandoned  platform  Write a docs style guide                                         6w
                                 docs-style-guide  2026-07-26 15:45
complete     abandoned  platform  Redesign the auth API                                            5w
                                 api-auth-redesign  2026-07-31 15:45
complete     someday    billing  Rewrite dunning email copy                                       3w
                                 billing-dunning-copy  2026-08-15 15:45
partial      active     platform  Roll out the new auth API                                        2w
                                 api-auth-rollout  2026-08-20 15:45
not-started  queued     platform  Remove the old auth API                                          2w
                                 api-auth-cleanup  2026-08-25 15:45
unknown      unset      billing  Retry failed invoice charges                                     1w
                                 billing-invoice-retry  2026-08-30 15:45
not-started  active     billing  Tune search relevance                                            5d
                                 search-relevance-tuning  2026-09-04 15:45
unknown      unset               Write the onboarding checklist                                   1d
                                 onboarding-checklist  2026-09-08 15:45

8 plans
```
<!-- /sample -->

### tree

<!-- sample:tree -->
```
(no project)
`- Write the onboarding checklist
     onboarding-checklist  unknown  unset  1d

billing
+- Rewrite dunning email copy
|    billing-dunning-copy  complete  someday  3w
+- Retry failed invoice charges (parent elided: no-such-plan)
|    billing-invoice-retry  unknown  unset  1w
`- Tune search relevance
     search-relevance-tuning  not-started  active  5d

platform
+- Write a docs style guide
|    docs-style-guide  superseded  abandoned  6w
`- Redesign the auth API
     api-auth-redesign  complete  abandoned  5w
   `- Roll out the new auth API
        api-auth-rollout  partial  active  2w
      `- Remove the old auth API
           api-auth-cleanup  not-started  queued  2w

8 plans
```
<!-- /sample -->

### show

<!-- sample:show -->
```
# Roll out the new auth API

status: partial
intent: active
parent: api-auth-redesign
project: platform
created: 2026-08-20
source: claude
modified: 2026-08-20 15:45

## Progress

- [x] Ship behind a feature flag
- [ ] Flip the flag for all tenants
```
<!-- /sample -->

`backfill` fills in missing fields without touching what's already set.
`--rederive` instead recomputes `status`, `parent`, and `project` from
scratch and overwrites them -- `intent` (operator-owned) and `created`
(immutable) are never touched; a re-derivation that finds no parent removes
an existing `parent` key. `--recreate` is the one way to change `created`: it
recomputes it from local time, fixing a plan whose `created` was derived
before this local-time fix landed.

### check

`check` validates the corpus -- dangling parents, self-parents,
cross-project parents, cycles, duplicate ids across sources,
off-vocabulary `status`/`intent` values, and missing titles -- and exits 1
on any finding. See
[docs/troubleshooting.md](docs/troubleshooting.md) for what each finding code
means and how to fix it.

<!-- sample:check -->
```
billing-invoice-retry: parent 'no-such-plan' does not resolve to a plan
8 plans checked, 1 finding
```
<!-- /sample -->

## Frontmatter

```yaml
---
pentimento:
  status: not-started | partial | complete | superseded | unknown
  intent: active | queued | someday | abandoned | unset
  parent: some-other-plan-id   # omitted for roots
  project: platform             # omitted if undetermined
  created: 2026-09-08
---
```

The vocabulary lives in one place:
[pentimento/vocabulary.py](pentimento/vocabulary.py).

`status` is derived and correctable; `intent` is only ever set by the
operator, so a half-implemented plan can still be marked abandoned. `parent`
and `project` are derived, not authored — `backfill` fills them in and
`set --parent` refuses a value that resolves to no plan in the corpus.
`created` is a local-date (`YYYY-MM-DD`), derived once and then immutable
except through `backfill --recreate`. `modified` is not stored in
frontmatter; it comes from a plan's session log last-activity timestamp,
falling back to the file's mtime when there is no session record.
`backfill` preserves mtime — deriving frontmatter is not an edit.

Lineage and source discovery are covered in full in
[docs/integrations.md](docs/integrations.md) and
[docs/troubleshooting.md](docs/troubleshooting.md); in short, `parent` comes
from a plan's session log or body referencing an earlier, same-project,
same-source plan by `<id>.md`, and Cursor plans get body-only lineage and no
`project` at all.

Zero runtime dependencies: this is stdlib-only Python 3, no PyYAML, so it
ships as a plain CLI.

## Development

```sh
python3 -m unittest discover
uvx ruff check
```

CI ([.github/workflows/check.yml](.github/workflows/check.yml)) runs both on
Ubuntu and macOS.

## Docs

- [docs/integrations.md](docs/integrations.md) -- wiring `backfill` into
  Claude Code and Cursor, a slash command, `check` in CI.
- [docs/workflows.md](docs/workflows.md) -- triage, supersession, lineage
  trees, scripting with `--format json`.
- [docs/troubleshooting.md](docs/troubleshooting.md) -- every empty field
  and `check` finding, explained.
