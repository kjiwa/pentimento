---
name: prior-plans
description: Before planning a change to CI, deploys, auth, cost, shared infrastructure, or anything another project may already have decided, search past plans across all projects with pentimento and read the relevant ones.
---

# Prior plans

Plans hold the reasoning behind decisions, including the ones another project
made and this one would undo. Search them before proposing a change in those
areas. Skip it for a change local to one file or with no cross-project
consequence.

If `pentimento` is not on `$PATH`, say so and stop; do not install or
reimplement it.

## Search

Search all projects: do not pass `--project`.

1. Expand the topic into one regex alternation of its synonyms, abbreviations,
   and the specific platform or system names, since titles use whatever words
   the author had: for GitHub Actions, `github actions|\bGHA\b|workflow|\bCI\b`.
   Also search the cost, security, or reliability angle of the change (`minutes|
   quota|billing`). Leave out generic words like `test` or `release`: they
   match most of the corpus. Matching is case-insensitive.
2. `pentimento list --title '<regex>' --format json`. Titles are terse and
   on-topic, so this is the precise pass. Over about 15 hits, the regex is too
   broad.
3. If that finds nothing, widen to `--grep '<regex>'` (title and body) and to
   `--tag <tag>` for tags seen in the JSON's `tags` fields.
4. Narrow a long result with `--since 12w` or `--since YYYY-MM-DD`, or
   `--status partial` to find work still in flight.

`list` sorts oldest first; the last rows are the most recently modified.

## Read

Choose by relevance to the change, not by count. A `partial` plan with
`intent: active` on the same topic is the most binding: it is live work the
change may collide with. Then completed plans from any project that decided
the same question. Skim titles first; read the few that match with:

```sh
pentimento show <id> --full --no-pager
```

`pentimento tree <id>` shows the plans that descend from one, and `--ancestors`
adds the path back to its root, when a decision spans a thread of plans.

## Use

- A plan records intent, not outcome. Its `status` says how far it got; confirm
  what shipped against the target repo before relying on a claim.
- A `superseded` plan is a rejected or replaced decision. It is evidence for
  why not, not a current requirement.
- Cite the plan id in the new plan's context section, with the constraint it
  imposes, so the reasoning travels with the new plan.
- If a past plan conflicts with the request, surface the conflict to the user
  before implementing.
