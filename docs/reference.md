# Reference

Every command's flags and the environment variables. Look here for exact
syntax; for what to do with them, see [workflows.md](workflows.md).

## Commands

```sh
pentimento list [--status STATUS] [--intent INTENT] [--project PROJECT] [--source claude|cursor] [--starred] [--tag TAG]... [--grep PATTERN] [--title PATTERN] [--finding [CODE]] [--since WHEN] [--until WHEN] [--date created|modified] [--format table|json|tsv] [--color auto|always|never] [--columns SPEC] [--sort modified|created|id|status|intent|title] [--order asc|desc] [-n N]
pentimento tree [<id>] [--ancestors] [--status STATUS] [--intent INTENT] [--project PROJECT] [--source claude|cursor] [--starred] [--tag TAG]... [--grep PATTERN] [--title PATTERN] [--finding [CODE]] [--since WHEN] [--until WHEN] [--date created|modified] [--format table|json|tsv] [--color auto|always|never] [--sort modified|created|id|status|intent|title] [--order asc|desc]
pentimento show <id> [--full] [--no-pager] [--format table|json|tsv] [--color auto|always|never]
pentimento set <id>... [--status STATUS | --unpin] [--intent INTENT] [--parent ID | --clear-parent] [--project PROJECT | --clear-project] [--add-tag TAG]... [--remove-tag TAG]... [--clear-tags] [--dry-run]
pentimento backfill [--dry-run] [--quiet] [--only ID]... [--rederive] [--recreate]
pentimento hook
pentimento index
pentimento check [--format table|json|tsv] [--color auto|always|never]
pentimento history <id> [--format table|json|tsv] [--color auto|always|never]
pentimento completion <bash|zsh|fish>
pentimento --version
```

Run `pentimento <command> --help` for that command's own examples.

## Flags

| Flag | Meaning |
| --- | --- |
| `--format table\|json\|tsv` | Defaults to `table` (human-readable); `json` and `tsv` are for scripting. |
| `--color auto\|always\|never` | Defaults to `auto`: ANSI color on a tty, off when piped, when `NO_COLOR` is set, or when `TERM=dumb`. |
| `--sort` | Defaults to `modified`; every key sorts ascending, so the row nearest the prompt is last, as with `ls -ltr` and `git log --reverse`. `--order desc` is exactly that order reversed. `modified` and `created` are dates; `id` follows the short id the table shows; `title` ignores case; `status` (`not-started`, `partial`, `complete`, `superseded`, `unknown`) and `intent` (`active`, `queued`, `someday`, `abandoned`, `unset`) follow that rank, then `modified`. Ties on any key resolve on the full id. `tree` orders siblings and project groups the same way. `--columns` and `--sort` share record field names; the `PLAN` and `UPDATED` headers are display labels for `id` and `modified`. |
| `--columns SPEC` (`list` only) | Which table columns to show and in what order; see [Columns](#columns) below. Applies to `--format table` only — combining it with `--format json\|tsv` is an error, since those formats' schema is fixed. Defaults to `PENTIMENTO_COLUMNS`. |
| `--project .` | Resolves to the current directory's name, for `list`, `tree`, and `set`. |
| `--finding [CODE]` | Keeps plans with a `check` finding, or with the finding `CODE` (one of the codes in [troubleshooting.md](troubleshooting.md#check-findings) except `unreadable-file`, which names a file rather than a plan); bare means any finding. `list` shows the `FINDING` column only under this flag or when `--columns` names it. Findings come from a check over the whole corpus, so lineage findings stay correct under other filters. `--format json\|tsv` carries every plan's codes in `findings` whether or not the flag is given. |
| `tree <id>` | Roots the tree at that plan: it plus every plan beneath it, resolved against the whole corpus, so `--project` is unnecessary. Filters apply inside the selection. |
| `tree --ancestors` | Also walks up from `<id>` to its topmost ancestor, spine only — the ancestors' other children stay out. Requires `<id>`; without one, exits 2 with `--ancestors requires a plan id`. |
| `--title PATTERN` | Case-insensitive regex over the title only. An invalid pattern exits 2 with the regex error on stderr. |
| `--grep PATTERN` | Case-insensitive regex over title and body. Invalid patterns fail as `--title` does. Combined with `--title`, a plan must match both. |
| `--since WHEN`, `--until WHEN` | Keep plans on or after, or on or before, a local day; either alone is fine, and both ends are inclusive. `WHEN` is `YYYY-MM-DD` or an age in the units `UPDATED` prints: `14m`, `5h`, `3d`, `2w`, `1y` (`m` is minutes). An age resolves to a day, so `--since 5h` means today. `--since` later than `--until` exits 2. `PENTIMENTO_NOW` fixes "now". |
| `--date created\|modified` | Which date `--since`/`--until` test: `modified` (default, the `UPDATED` column) or `created`. Without a bound it exits 2. |
| `-n N`/`--limit N` (`list` only) | Keeps the `N` highest-sorting rows, by default the `N` most recent, displayed in the chosen order: the last `N` under `--order asc`, the first `N` under `--order desc`. Applied before rendering or emitting, so scripting matches what you see. `0` means zero rows in either order; negative or non-integer values exit 2. |
| `show --full` | Prints the whole body unclipped. Plain `show` clips to the terminal height on a tty and prints a hint to rerun with `--full`. |
| `show --no-pager` | With `--full`, never pages. `--full` pipes through `$PAGER` (`less` if unset) only on a tty and only when the plan is longer than the terminal, so `show <id> --full > out.md` and `... \| cat` write the plain text with no pager and no color. |
| `backfill --only ID` | Restricts writes to the named plan id(s); repeatable. Derivation still spans the whole corpus, since `parent` resolves against every plan, but only the named ids are saved. The narrow alternative to a corpus-wide `--rederive`. |
| `set <id>...` | Edits every named plan in one run. Every id is resolved first, so a miss exits 1 and writes nothing; with more than one id, each change block is headed by the plan's short id. `--dry-run` applies to all. A `--parent` that would create a cycle, counting every plan being edited, exits 2. Changes print as `field: old -> new`, `field: set to value`, or `field: cleared`. |
| `set --status` | Sets `status` and, in the same write, `pinned: true`; see the README's [Frontmatter table](../README.md#frontmatter). |
| `hook` | Reads a `PostToolUse` payload on stdin and backfills the one plan it wrote: fills `intent`, `created`, `project`, and `parent`, and derives `status` capped at `partial`. Only a full `backfill` advances `status` to `complete`. Always exits 0. |

## Plan ids

`list`, `tree`, and `check` tables display the short id: the shortest
trailing run of at least two hyphen-separated segments that is unique across
the corpus. `show`, `set` (including `--parent`), `tree`, `history`, and
`backfill --only` accept the short id, the full id, the filename (`<id>.md`
or `<id>.plan.md`), or the path. `--format json|tsv` output always emits the
full id.

## Columns

`list`'s columns, left to right: `id status intent project source title
finding tags created modified`, shown as `PLAN`, `STATUS`, `INTENT`, `PROJECT`,
`SOURCE`, `TITLE`, `FINDING`, `TAGS`, `CREATED`, `UPDATED`. `TAGS` and
`CREATED` appear only when at least one listed plan has a value. `FINDING`
appears only under `--finding` or when `--columns` names it. Every other
column always appears. No column is ever dropped for width.

`list`, `check`, and `history` choose one of two layouts by terminal width:

- **Table**, one line per row, when every column fits at its floor. `PLAN`,
  `STATUS`, `INTENT`, `SOURCE`, `CREATED`, `UPDATED`, and `FINDING` always
  print whole. The truncated columns end in `...`: `TITLE` (floor 30, comfort
  50), `TAGS` (floor 14, comfort 30), and `PROJECT` (floor 10, comfort 16). A
  floor never exceeds the column's widest value. `TAGS` keeps whole tags and
  ends in `+N` for the rest (`[loadtest, +5]`). Spare width first grows
  `TITLE`, then `TAGS`, then `PROJECT` up to their comforts, then goes to
  the narrowest truncated columns first, so the longest takes what is left.
  `check` wraps `MESSAGE` (floor 20) onto at most 3 lines, and `history`
  truncates `SESSION` (floor 16); a `check` row that needs more than 3 lines
  makes the whole output stacked.
- **Stacked records** otherwise, with no header line. Each record's first line
  is the column with the largest floor (`TITLE` for `list`, `MESSAGE` for
  `check`, `SESSION` for `history`), truncated with `...` to the width;
  the remaining non-empty fields follow in column order, indented two spaces
  and wrapped between fields, so nothing is lost. Tags keep their brackets so
  a value stays identifiable without a header, and `history`'s touch count
  reads `touches N`.

The narrowest table is the sum of the column floors plus two spaces between
columns, so it depends on the listed plans' id, intent, and date widths.
`--columns` with fewer columns fits a table in less. When `COLUMNS` is unset and output is not a terminal, as in
`pentimento list | grep`, width is unbounded: always a table, nothing
truncated. `tree` truncates a node's title with `...` and wraps its metadata
line, including any `(parent elided: ...)` note, between fields.

`--columns SPEC` (and its default, `PENTIMENTO_COLUMNS`) overrides which
columns appear, regardless of content. `SPEC` is one of:

- an absolute, comma-separated list, e.g. `--columns created,title,status`
  — rendered in exactly that order, final regardless of content
- one or more `+name`/`-name` modifiers on the content-derived default set,
  e.g. `--columns +created` or `--columns=-source,-project` (the `=` form keeps
  argparse from reading a leading `-` as a flag)
- `all`, every column in canonical order

Mixing absolute and relative names in one `--columns` is an error, as is an
unknown, duplicate, or empty name, or removing every column; the messages for
names list the valid ones.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success. `pentimento hook` always exits 0. |
| `1` | `check` found something; a plan id named on the command line matches no plan or is ambiguous; `backfill` refused to run because two plans share an id; or an I/O error, reported as `pentimento: <path>: <reason>`. |
| `2` | Usage error: an unknown flag, an invalid value or regex, flags that conflict, a required flag missing, or a `set --parent` that would create a cycle. |
| `141` | A reader closed the pipe early, as `\| head` does; the shell's 128 + `SIGPIPE`. |

Every error message goes to stderr, prefixed `pentimento: `.

## Environment variables

| Variable | Default | Notes |
| --- | --- | --- |
| `AGENT_PLANS_DIR` | `~/.claude/plans` | Claude Code's plan directory. |
| `AGENT_SESSIONS_DIR` | `~/.claude/projects` | Claude Code's session transcripts, the source for `project`, `parent`, `modified`, and `history`. |
| `CURSOR_PLANS_DIR` | `~/.cursor/plans` and `~/Library/Application Support/Cursor/User/plans` (both searched) | Cursor's plan directory. Set to override the defaults; the value is an `os.pathsep`-separated list of paths, so more than one directory can be searched at once. |
| `PAGER` | `less` | Pager for `show --full`. Split with shell quoting, so `PAGER="less -S"` works. Empty disables paging. When it is `less` and `LESS` is unset, pentimento sets `LESS=FRX` so color survives and short output does not open the pager. |
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
