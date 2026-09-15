# Reference

## Commands

```sh
pentimento list [--status STATUS] [--intent INTENT] [--project PROJECT] [--source claude|cursor] [--starred] [--tag TAG]... [--grep PATTERN] [--sort modified|created|id|status|title] [--order asc|desc] [-n LIMIT] [--format table|json|tsv] [--color auto|always|never] [--ascii]
pentimento tree [--status STATUS] [--intent INTENT] [--project PROJECT] [--source claude|cursor] [--starred] [--tag TAG]... [--grep PATTERN] [--sort modified|created|id|status|title] [--order asc|desc] [--format table|json|tsv] [--color auto|always|never] [--ascii]
pentimento show <id> [--full] [--format table|json|tsv] [--color auto|always|never] [--ascii]
pentimento set <id> [--status STATUS] [--unpin] [--intent INTENT] [--parent ID] [--clear-parent] [--project PROJECT] [--clear-project] [--add-tag TAG]... [--remove-tag TAG]... [--clear-tags] [--dry-run]
pentimento backfill [--dry-run] [--quiet] [--only ID]... [--rederive] [--recreate]
pentimento hook
pentimento index
pentimento check [--format table|json|tsv] [--color auto|always|never] [--ascii]
pentimento history <id> [--format table|json|tsv] [--color auto|always|never] [--ascii]
pentimento --version
```

Run `pentimento <command> --help` for that command's own examples.

## Flags

| Flag | Meaning |
| --- | --- |
| `--format table\|json\|tsv` | Defaults to `table` (human-readable); `json` and `tsv` are for scripting. |
| `--color auto\|always\|never` | Defaults to `auto`: ANSI colour on a tty, off when piped, when `NO_COLOR` is set, or when `TERM=dumb`. |
| `--ascii` | Forces `+- `/`` `- ``/`\|  ` box-drawing instead of the Unicode `├─ `/`└─ `/`│  `. `list`, `tree`, `show`, and `check` use Unicode by default whenever the output stream's encoding is UTF-8 and `TERM` isn't `dumb`. |
| `--sort` | Defaults to `modified`; every key sorts ascending, so the row nearest the prompt is last, as with `ls -ltr` and `git log --reverse`. `--order desc` flips it. |
| `--project .` | Resolves to the current directory's name, the same way `backfill` derives `project` from a session's `cwd`. |
| `--grep PATTERN` | Case-insensitive regex over title and body. An invalid pattern exits 1 with the regex error on stderr. |
| `-n`/`--limit` (`list` only) | Keeps the `N` rows nearest the prompt: the last `N` under `--order asc`, the first `N` under `--order desc`. Applied before rendering or emitting, so scripting matches what you see. `0` means zero rows in either order; negative values are rejected. |
| `show --full` | Prints the whole body unclipped. Plain `show` clips to the terminal height on a tty and prints a hint to rerun with `--full`. |
| `backfill --only ID` | Restricts writes to the named plan id(s); repeatable. Derivation still spans the whole corpus, since `parent` resolves against every plan, but only the named ids are saved. The narrow alternative to a corpus-wide `--rederive`. |
| `set --status` | Sets `status` and, in the same write, `pinned: true` -- an operator statement is immune to every future `backfill`, including `--rederive`, until `set --unpin` releases it. |

`list`, `tree`, `check`, and `show`'s tables display the short id: the
shortest trailing run of at least two hyphen-separated segments that's
unique across the corpus (`shortid.MIN_SEGMENTS = 2`). `show`, `set`,
`history`, and `set --parent` all accept either the short id or the full id
as input; `check`'s `--format json|tsv` output always emits the full id.

## Environment variables

| Variable | Default | Notes |
| --- | --- | --- |
| `AGENT_PLANS_DIR` | `~/.claude/plans` | Claude Code's plan directory. |
| `AGENT_SESSIONS_DIR` | `~/.claude/projects` | Claude Code's session transcripts, the source for `project`, `parent`, `modified`, and `history`. |
| `CURSOR_PLANS_DIR` | `~/.cursor/plans` and `~/Library/Application Support/Cursor/User/plans` (both searched) | Cursor's plan directory. Set to override the defaults; the value is an `os.pathsep`-separated list of paths, so more than one directory can be searched at once ([sources.py](../pentimento/sources.py)). |
