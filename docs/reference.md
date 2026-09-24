# Reference

Every command's flags and the environment variables. Look here for exact
syntax; for what to do with them, see [workflows.md](workflows.md).

## Commands

```sh
pentimento list [--status STATUS] [--intent INTENT] [--project PROJECT] [--source claude|cursor] [--starred] [--tag TAG]... [--grep PATTERN] [--title PATTERN] [--finding [CODE]] [--since WHEN] [--until WHEN] [--date created|modified] [--format table|json|tsv] [--color auto|always|never] [--ascii] [--columns SPEC] [--sort modified|created|id|status|title] [--order asc|desc] [-n N]
pentimento tree [<id>] [--ancestors] [--status STATUS] [--intent INTENT] [--project PROJECT] [--source claude|cursor] [--starred] [--tag TAG]... [--grep PATTERN] [--title PATTERN] [--finding [CODE]] [--since WHEN] [--until WHEN] [--date created|modified] [--format table|json|tsv] [--color auto|always|never] [--ascii] [--sort modified|created|id|status|title] [--order asc|desc]
pentimento show <id> [--full] [--no-pager] [--format table|json|tsv] [--color auto|always|never] [--ascii]
pentimento set <id> [--status STATUS] [--unpin] [--intent INTENT] [--parent ID] [--clear-parent] [--project PROJECT] [--clear-project] [--add-tag TAG]... [--remove-tag TAG]... [--clear-tags] [--dry-run]
pentimento backfill [--dry-run] [--quiet] [--only ID]... [--rederive] [--recreate]
pentimento hook
pentimento index
pentimento check [--format table|json|tsv] [--color auto|always|never] [--ascii]
pentimento history <id> [--format table|json|tsv] [--color auto|always|never] [--ascii]
pentimento completion <bash|zsh|fish>
pentimento --version
```

Run `pentimento <command> --help` for that command's own examples.

## Flags

| Flag | Meaning |
| --- | --- |
| `--format table\|json\|tsv` | Defaults to `table` (human-readable); `json` and `tsv` are for scripting. |
| `--color auto\|always\|never` | Defaults to `auto`: ANSI colour on a tty, off when piped, when `NO_COLOR` is set, or when `TERM=dumb`. |
| `--ascii` | Forces `+- `/`` `- ``/`\|  ` box-drawing instead of the Unicode `├─ `/`└─ `/`│  `. `list`, `tree`, `show`, `check`, and `history` use Unicode by default whenever the output stream's encoding is UTF-8 and `TERM` isn't `dumb`. |
| `--sort` | Defaults to `modified`; every key sorts ascending, so the row nearest the prompt is last, as with `ls -ltr` and `git log --reverse`. `--order desc` flips it. The sorted-on column never drops, so the order it produces is always visible in `list`'s table. `--columns` and `--sort` share record field names; the `PLAN` and `UPDATED` headers are display labels for `id` and `modified`. |
| `--columns SPEC` (`list` only) | Which table columns to show and in what order; see [Columns](#columns) below. Applies to `--format table` only -- combining it with `--format json\|tsv` is an error, since those formats' schema is fixed. Defaults to `PENTIMENTO_COLUMNS`. |
| `--project .` | Resolves to the current directory's name, the same way `backfill` derives `project` from a session's `cwd`. |
| `--finding [CODE]` | Keeps plans with a `check` finding, or with the finding `CODE` (one of the codes in [troubleshooting.md](troubleshooting.md#check-findings) except `unreadable-file`, which names a file rather than a plan); bare means any finding. `list` adds a `FINDING` column. Findings come from a check over the whole corpus, so lineage findings stay correct under other filters. `--format json\|tsv` carries every plan's codes in `findings` whether or not the flag is given. |
| `tree <id>` | Roots the tree at that plan: it plus every plan beneath it, resolved against the whole corpus, so `--project` is unnecessary. Filters apply inside the selection. |
| `tree --ancestors` | Also walks up from `<id>` to its topmost ancestor, spine only -- the ancestors' other children stay out. Requires `<id>`; without one, exits 2 with `--ancestors requires a plan id`. |
| `--title PATTERN` | Case-insensitive regex over the title only. An invalid pattern exits 2 with the regex error on stderr. |
| `--grep PATTERN` | Case-insensitive regex over title and body. Invalid patterns fail as `--title` does. Combined with `--title`, a plan must match both. |
| `--since WHEN`, `--until WHEN` | Keep plans on or after, or on or before, a local day; either alone is fine, and both ends are inclusive. `WHEN` is `YYYY-MM-DD` or an age in the units `UPDATED` prints: `14m`, `5h`, `3d`, `2w`, `1y` (`m` is minutes). An age resolves to a day, so `--since 5h` means today. `--since` later than `--until` exits 2. `PENTIMENTO_NOW` fixes "now". |
| `--date created\|modified` | Which date `--since`/`--until` test: `modified` (default, the `UPDATED` column) or `created`. Without a bound it exits 2. |
| `-n N`/`--limit N` (`list` only) | Keeps the `N` rows nearest the prompt: the last `N` under `--order asc`, the first `N` under `--order desc`. Applied before rendering or emitting, so scripting matches what you see. `0` means zero rows in either order; negative or non-integer values exit 2. |
| `show --full` | Prints the whole body unclipped. Plain `show` clips to the terminal height on a tty and prints a hint to rerun with `--full`. |
| `show --no-pager` | With `--full`, never pages. `--full` pipes through `$PAGER` (`less` if unset) only on a tty and only when the plan is longer than the terminal, so `show <id> --full > out.md` and `... \| cat` write the plain text with no pager and no colour. |
| `backfill --only ID` | Restricts writes to the named plan id(s); repeatable. Derivation still spans the whole corpus, since `parent` resolves against every plan, but only the named ids are saved. The narrow alternative to a corpus-wide `--rederive`. |
| `set --status` | Sets `status` and, in the same write, `pinned: true`; see the README's [Frontmatter table](../README.md#frontmatter). |

`list`, `tree`, and `check` tables display the short id: the shortest
trailing run of at least two hyphen-separated segments that's unique across
the corpus. `show`, `set`, `history`, `tree`, `set --parent`, and
`backfill --only` accept the short id, the full id, the filename, or the path
as input. `--format json|tsv` output always emits the full id.

## Columns

`list`'s columns, left to right: `status intent project source id title
finding tags created modified`. `TAGS`, `CREATED`, and `FINDING` only appear
when at least one listed plan has tags, a `created` date, or a finding
(`FINDING` also shows under `--finding`); every other column always appears.

As the table narrows, columns drop by rank, one at a time, before any
column's text is truncated: `created`, `tags`, `source`, `project`,
`intent`, `status`, `id`, then `finding`. `title` and `modified` never drop;
they shrink instead.

`--columns SPEC` (and its default, `PENTIMENTO_COLUMNS`) overrides both
rules -- content and width. `SPEC` is one of:

- an absolute, comma-separated list, e.g. `--columns created,title,status`
  -- rendered in exactly that order, final regardless of content or width
- one or more `+name`/`-name` modifiers on the content-derived default set,
  e.g. `--columns +created` or `--columns=-source,-project` (the `=` form keeps
  argparse from reading a leading `-` as a flag)
- `all`, every column in canonical order

Mixing absolute and relative names in one `--columns` is an error, as is an
unknown or empty name; both messages list the valid names. Whichever way a
column is named -- explicitly in `--columns`, as the `--sort` key's column, or
as `FINDING` under `--finding` -- it never drops for width, though it
truncates like any other column if the terminal is too narrow to show it
whole.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success. `pentimento hook` always exits 0. |
| `1` | `check` found something, or a plan id named on the command line matches no plan. |
| `2` | Usage error: an unknown flag, an invalid value or regex, flags that conflict, a required flag missing, a `set --parent` that would create a cycle, or an I/O error. |
| `141` | A reader closed the pipe early, as `\| head` does; the shell's 128 + `SIGPIPE`. |

Every error message goes to stderr, prefixed `pentimento: `.

## Environment variables

| Variable | Default | Notes |
| --- | --- | --- |
| `AGENT_PLANS_DIR` | `~/.claude/plans` | Claude Code's plan directory. |
| `AGENT_SESSIONS_DIR` | `~/.claude/projects` | Claude Code's session transcripts, the source for `project`, `parent`, `modified`, and `history`. |
| `CURSOR_PLANS_DIR` | `~/.cursor/plans` and `~/Library/Application Support/Cursor/User/plans` (both searched) | Cursor's plan directory. Set to override the defaults; the value is an `os.pathsep`-separated list of paths, so more than one directory can be searched at once. |
| `PAGER` | `less` | Pager for `show --full`. Split with shell quoting, so `PAGER="less -S"` works. Empty disables paging. When it is `less` and `LESS` is unset, pentimento sets `LESS=FRX` so colour survives and short output does not open the pager. |
| `PENTIMENTO_COLUMNS` | unset | Default `--columns` value for `list`'s `--format table` output; same syntax. Ignored for `--format json\|tsv`. An invalid value prints `pentimento: PENTIMENTO_COLUMNS: <message>` to stderr and exits 2. |
| `PENTIMENTO_DEBUG` | unset | When set, `pentimento hook` prints a traceback to stderr on an internal error instead of failing silently. |
| `PENTIMENTO_NOW` | current time | ISO 8601 instant overriding "now" for relative-time rendering (`list`/`tree`'s `UPDATED` column) and for `--since`/`--until` ages. Set for reproducible output, e.g. in `demo/capture.sh`. |
| `XDG_CACHE_HOME` | `~/.cache` | Where session transcripts are cached between runs. |

## Shell completion

```sh
pentimento completion bash >> ~/.bashrc
pentimento completion zsh  # add to an fpath directory, or eval "$(pentimento completion zsh)"
pentimento completion fish > ~/.config/fish/completions/pentimento.fish
```

Each script is a thin, static wrapper that shells out to a hidden
`pentimento __complete <words>` for every actual candidate decision:
subcommand names, `choices=` flags, corpus-derived projects and tags, and
plan ids (the same short ids `list` prints, plus any full id the typed
prefix reaches).
