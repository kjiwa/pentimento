# Integrations

Wiring pentimento into Claude Code and Cursor, and `check` into CI. Start here
to keep frontmatter current without running `backfill` by hand, or to let an
agent search past plans on its own.

## Claude Code

Two hooks, split by what each field needs to be trustworthy:

- A `PostToolUse` hook on `Write|Edit` runs `pentimento hook` after every
  plan-file write and backfills that plan on the spot; what it fills is in
  [reference.md](reference.md#flags).
- A `SessionEnd` hook runs `pentimento backfill` as a full sweep, which
  advances `status` to `complete`. `SessionEnd` supports a `matcher` on the
  exit reason (`clear`, `resume`, `logout`, `prompt_input_exit`, `other`) if
  you want to filter which exits trigger it; leaving it unset runs on every
  exit reason.

Copy [integrations/claude/settings-snippet.json](../integrations/claude/settings-snippet.json)
into `~/.claude/settings.json` (or `.claude/settings.json` in a project, to
scope the hooks to that repo). `pentimento hook` always exits 0, so it never blocks a write, and Claude
Code does not feed the changed ids it prints to the model; `backfill --quiet`
prints nothing; keep each to the one command, and use `backfill --dry-run` from a
terminal to see what a sweep would change before it runs unattended.

Two gaps the hooks don't close: `--rederive` is the correction for a `parent`
that was derived from a transient preamble reference; and a wholesale
re-`Write` of a plan file (as opposed to an edit) replaces the frontmatter
outright, dropping every operator-set field (`intent`, `tags`, `pinned`,
`parent`). The next `backfill` refills only what it derives: `intent` at its
default, `created`, `project`, `parent`, and `status`.

Both hooks run the plain, monotonic form of `backfill` — never `--rederive`
— so neither ever sets or clears `pinned`, and both leave a pinned `status`
alone. Pinning and unpinning are operator actions only, via `pentimento set`.

A `/plans` slash command passes `$ARGUMENTS` straight through to
`pentimento` — `/plans` alone runs `pentimento list`, and `/plans tree
--project platform`, `/plans show <id>`, or `/plans set <id> --intent active`
run verbatim; if `pentimento` isn't on `$PATH` it reports that and stops.
Copy [integrations/claude/commands/plans.md](../integrations/claude/commands/plans.md)
to `~/.claude/commands/plans.md`.

### `prior-plans` skill

`/plans` is a command you type; it is marked so Claude never invokes it on
its own. The [`prior-plans` skill](../integrations/claude/skills/prior-plans/SKILL.md)
is the model-invoked counterpart: when Claude is about to plan a change to
CI, deploys, auth, cost, or anything another project may already have
decided, it searches every project's plans with `pentimento list --title` and
`--grep`, reads the best matches with `pentimento show <id> --full`, and cites
them in the new plan. That is how a decision recorded in one project reaches
the plan for another without you remembering to hand it over. It finds plans
by title, so it works on plans you never tagged; tags and an accurate `status`
only sharpen the result.

Install it for every project by copying the directory into your user skills:

```sh
mkdir -p ~/.claude/skills
cp -R integrations/claude/skills/prior-plans ~/.claude/skills/
```

Without a checkout, fetch the one file instead:

```sh
mkdir -p ~/.claude/skills/prior-plans
curl -fsSL -o ~/.claude/skills/prior-plans/SKILL.md \
  https://raw.githubusercontent.com/kjiwa/pentimento/main/integrations/claude/skills/prior-plans/SKILL.md
```

To scope it to one repository, use `.claude/skills/prior-plans/` inside that
repository instead. Claude Code picks the skill up in a new session; ask it to
plan a change to a shared workflow and it should run `pentimento list --title
...` before proposing anything. Like `/plans`, it needs `pentimento` on
`$PATH` and reports that and stops if it is missing.

### Triage nudge

A plan is unfindable later when it has run (`status` is `partial` or
`complete`) but has no `intent` (`unset`) or no `tags`. Neither field can be
derived, and the end of execution is when nobody remembers to set them.
`pentimento check` already names the tag case for a subplan of a tagged
thread (`unadopted-tag`), with the tags to add.

A `PostToolUse` hook on `Write|Edit` can record each plan a session writes,
and a `Stop` hook can check those plans against that rule with `pentimento
list --format tsv` and exit 2, which blocks the stop and returns its stderr
to Claude. Have the message name the plan and ask for a tag and an intent to
propose to you; both are operator-owned, so Claude should not set them
unasked. Drop each id from the record once raised so a plan nags once, which
also keeps the `Stop` hook from re-firing on itself.

This is a pattern to adapt, not a shipped script: the hooks depend on how
your harness names sessions and where it keeps state.

## Cursor

Cursor has no hook system, so there's no way to run `backfill` automatically.
Configure `CURSOR_PLANS_DIR` (see [docs/reference.md](reference.md)) and run
`pentimento backfill` by hand, or on a schedule (e.g. a cron job or a CI
job). Because Cursor keeps no session transcripts, a Cursor plan's `project` is
never derived and its `parent` only ever comes from the body-preamble
reference scan.

## `check` in CI

`check` exits 1 on any finding, so it plugs into CI as a plain step:

```yaml
- run: pentimento check
```

See [docs/troubleshooting.md](troubleshooting.md) for what each finding code
means.
