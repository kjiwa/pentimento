# Integrations

## Claude Code

Run `backfill` automatically when a session ends, with a `SessionEnd` hook.
Use `SessionEnd`, not `Stop`: `Stop` fires at every turn, and lineage is only
complete once the session log is finished being written. `SessionEnd`
supports a `matcher` on the exit reason (`clear`, `resume`, `logout`,
`prompt_input_exit`, `other`) if you want to filter which exits trigger it;
leaving it unset runs on every exit reason.

Copy [integrations/claude/settings-snippet.json](../integrations/claude/settings-snippet.json)
into `~/.claude/settings.json` (or `.claude/settings.json` in a project, to
scope the hook to that repo). `backfill` now recomputes `status` from the
`## Progress` checkboxes on every run, so this one hook keeps `status`
current as well as `intent`/`created`/`parent`/`project` -- there's no
separate step for status to go stale in. `SessionEnd` hooks can't block or
report back to Claude, so keep this to the one command, and use
`backfill --dry-run` from a terminal if you want to see what it would
change before it runs unattended.

A slash command wrapping `pentimento list --starred`, so you can pull up
your active/queued plans mid-session. Copy
[integrations/claude/commands/plans.md](../integrations/claude/commands/plans.md)
to `~/.claude/commands/plans.md`.

`allowed-tools` pre-approves the exact command so Claude doesn't prompt for
permission when the command runs it.

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
