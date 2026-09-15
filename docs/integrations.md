# Integrations

## Claude Code

Two hooks, split by what each field needs to be trustworthy:

- A `PostToolUse` hook on `Write|Edit` runs `pentimento hook` after every
  plan-file write. It backfills `project` and `created` on the spot, and
  derives `status` capped at `partial` so a half-written `## Progress`
  section can't prematurely land `complete`.
- A `SessionEnd` hook runs `pentimento backfill` as a sweep -- the only
  thing that advances `status` all the way to `complete`. `SessionEnd`
  supports a `matcher` on the exit reason (`clear`, `resume`, `logout`,
  `prompt_input_exit`, `other`) if you want to filter which exits trigger
  it; leaving it unset runs on every exit reason.

Copy [integrations/claude/settings-snippet.json](../integrations/claude/settings-snippet.json)
into `~/.claude/settings.json` (or `.claude/settings.json` in a project, to
scope the hooks to that repo). Neither hook can block or report back to
Claude, so keep each to the one command, and use `backfill --dry-run` from
a terminal if you want to see what a sweep would change before it runs
unattended.

Two gaps the hooks don't close: `--rederive` is the correction for a `parent`
that was derived from a transient preamble reference; and a wholesale
re-`Write` of a plan file (as opposed to an edit) replaces the frontmatter
outright, dropping an operator-set `intent` until the next sweep gap-fills it
back to the default.

Both hooks run the plain, monotonic form of `backfill` -- never `--rederive`
-- so neither ever sets or clears `pinned`, and both leave a pinned `status`
alone. Pinning and unpinning are operator actions only, via `pentimento set`.

A `/plans` slash command passes `$ARGUMENTS` straight through to
`pentimento` -- `/plans` alone runs `pentimento list`, and `/plans tree
--project platform`, `/plans show <id>`, or `/plans set <id> --intent active`
run verbatim; if `pentimento` isn't on `$PATH` it reports that and stops.
Copy [integrations/claude/commands/plans.md](../integrations/claude/commands/plans.md)
to `~/.claude/commands/plans.md`.

## Cursor

Cursor has no hook system, so there's no way to run `backfill` automatically.
Configure `CURSOR_PLANS_DIR` (see [docs/reference.md](reference.md)) and run
`pentimento backfill` by hand, or on a schedule (e.g. a cron job or a CI
job). Because Cursor keeps no session logs, a Cursor plan's `project` is
never derived and its `parent` only ever comes from the body-preamble
reference scan -- see [sources.py](../pentimento/sources.py) and
[lineage.py](../pentimento/lineage.py).

## `check` in CI

`check` exits 1 when it finds a lineage or vocabulary defect
([cli.py](../pentimento/cli.py)), so it plugs into CI as a plain step:

```yaml
- run: pentimento check
```

See [docs/troubleshooting.md](troubleshooting.md) for what each finding code
means.
