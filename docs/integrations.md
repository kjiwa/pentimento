# Integrations

## Claude Code

Two hooks, split by what each field needs to be trustworthy:

- A `PostToolUse` hook on `Write|Edit` runs `pentimento hook` after every
  plan-file write. `project`, `created`, and (with `--rederive`) `parent` are
  derived from the session log, which carries `slug` and `cwd` from its first
  record -- they're safe to write from the moment the plan file exists, so
  this hook backfills them on every write. It deliberately does not derive
  `status`: a half-written `## Progress` section can read all-checked mid-draft,
  and `status` derivation only ever advances, never retracts, so that would
  make `complete` permanent.
- A `SessionEnd` hook runs `pentimento backfill --quiet` as a sweep, deriving
  `status` from the finished draft. `SessionEnd` supports a `matcher` on the
  exit reason (`clear`, `resume`, `logout`, `prompt_input_exit`, `other`) if
  you want to filter which exits trigger it; leaving it unset runs on every
  exit reason.

Copy [integrations/claude/settings-snippet.json](../integrations/claude/settings-snippet.json)
into `~/.claude/settings.json` (or `.claude/settings.json` in a project, to
scope the hooks to that repo). Both hooks run `pentimento`'s own writes
through `plan.save(keep_mtime=True)`, which do not themselves re-fire
`PostToolUse` -- that event fires on Claude's tool use, not on filesystem
changes, so there's no re-entrancy to worry about. Neither hook can block or
report back to Claude, so keep each to the one command, and use
`backfill --dry-run` from a terminal if you want to see what a sweep would
change before it runs unattended.

Two gaps the hooks don't close: `--rederive` is the correction for a `parent`
that was derived from a transient preamble reference; and a wholesale
re-`Write` of a plan file (as opposed to an edit) replaces the frontmatter
outright, dropping an operator-set `intent` until the next sweep gap-fills it
back to the default.

A `/plans` slash command that passes `$ARGUMENTS` straight through to
`pentimento` -- `/plans` alone runs `pentimento list`, and `/plans tree
--project platform`, `/plans show <id>`, or `/plans set <id> --intent active`
run verbatim. It doesn't reimplement any of pentimento's logic; if
`pentimento` isn't on `$PATH` it reports that and stops. Copy
[integrations/claude/commands/plans.md](../integrations/claude/commands/plans.md)
to `~/.claude/commands/plans.md`.

## Cursor

Cursor has no hook system, so there's no way to run `backfill` automatically.
Configure `CURSOR_PLANS_DIR` (see the main [README](../README.md)) and run
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
