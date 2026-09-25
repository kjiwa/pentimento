"""Argument parsing and command dispatch."""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import importlib.metadata
import os
import re
import sys
import traceback
from pathlib import Path

from pentimento import backfill as backfill_module
from pentimento import check as check_module
from pentimento import columns as columns_module
from pentimento import (
    completion,
    corpus,
    counts,
    formats,
    frontmatter,
    lineage,
    listing,
    markdown,
    pager,
    shortid,
    style,
    table,
    vocabulary,
)
from pentimento import history as history_module
from pentimento import hook as hook_module
from pentimento import index as index_module
from pentimento import plan as plan_module
from pentimento import record as record_module
from pentimento import sessions as sessions_module
from pentimento import sources as sources_module
from pentimento import tags as tags_module
from pentimento import times as times_module
from pentimento import touches as touches_module
from pentimento import tree as tree_module
from pentimento import vocabulary as vocabulary_module

STARRED_INTENTS = vocabulary_module.STARRED_INTENTS
_MIN_INSTANT = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
_MIN_DATE = datetime.date.min
_UNRANKED_STATUS = len(vocabulary_module.STATUS_ORDER)


def _status_rank(status: str) -> int:
    try:
        return vocabulary_module.STATUS_ORDER.index(status)
    except ValueError:
        return _UNRANKED_STATUS


SORT_KEYS = {
    "modified": lambda p: p.modified,
    "created": lambda p: (p.created_date or _MIN_DATE, p.created_at or _MIN_INSTANT),
    "id": lambda p: p.id,
    "status": lambda p: _status_rank(p.status),
    "title": lambda p: p.title,
}
SORT_CHOICES = tuple(SORT_KEYS)

_DOCS_URL = "https://github.com/kjiwa/pentimento/blob/main/docs"

_ORDER_ASC, _ORDER_DESC = "asc", "desc"
ORDER_CHOICES = (_ORDER_ASC, _ORDER_DESC)

DATE_CHOICES = ("created", "modified")

_ID_HELP = "full id, short id, filename, or path"
_DRY_RUN_HELP = "report what would change, without writing"
_PROJECT_FORM = "use a single line with no surrounding space, '#', or ': '"
_TAG_FORM = "use lowercase letters, digits, and . _ / -, starting with a letter or digit"
_TAG_MATCH_HELP = f"tags match {tags_module.PATTERN}, and matching ignores case"


class UsageError(Exception):
    """Invalid arguments found after parsing; `main` reports it as a usage error."""


def _report(message: str) -> None:
    print(f"pentimento: {message}", file=sys.stderr)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        _report(message)
        sys.exit(2)


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {value}") from None
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"limit must not be negative: {value}")
    return parsed


def _regex(value: str) -> re.Pattern:
    try:
        return re.compile(value, re.IGNORECASE)
    except re.error as exc:
        raise argparse.ArgumentTypeError(f"invalid regex: {exc}") from exc


def _tag(value: str) -> str:
    tag = tags_module.normalize(value)
    if not tags_module.is_valid(tag):
        raise argparse.ArgumentTypeError(f"invalid tag: '{value}' -- {_TAG_FORM}")
    return tag


def _when(value: str) -> datetime.date:
    day = times_module.parse_when(value)
    if day is None:
        raise argparse.ArgumentTypeError(
            f"invalid date or age: {value} -- use YYYY-MM-DD or an age like 14m, 5h, 3d, 2w, 1y"
        )
    return day


def _column_spec(value: str) -> columns_module.Selection:
    try:
        return columns_module.parse(value, listing.NAMES)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _add_filter_args(parser):
    group = parser.add_argument_group("filters")
    group.add_argument("--status", choices=vocabulary_module.STATUS_ORDER, help="filter by status")
    group.add_argument("--intent", choices=vocabulary_module.INTENT_VALUES, help="filter by intent")
    group.add_argument(
        "--project", help="filter by project; '.' resolves to the current directory's name"
    )
    group.add_argument("--source", choices=sources_module.SOURCE_NAMES, help="filter by source")
    group.add_argument("--starred", action="store_true", help="only active/queued intent")
    group.add_argument(
        "--tag",
        type=_tag,
        action="append",
        help=f"filter by tag; repeatable, every given tag must be present; {_TAG_MATCH_HELP}",
    )
    group.add_argument(
        "--grep",
        metavar="PATTERN",
        type=_regex,
        help="filter by a case-insensitive regex over title and body",
    )
    group.add_argument(
        "--title",
        metavar="PATTERN",
        type=_regex,
        help="filter by a case-insensitive regex over the title",
    )
    group.add_argument(
        "--finding",
        nargs="?",
        metavar="CODE",
        choices=tuple(code for code in check_module.HINTS if code != "unreadable-file"),
        const=None,
        default=False,
        help="only plans with a check finding, or with the finding CODE",
    )
    group.add_argument(
        "--since",
        metavar="WHEN",
        type=_when,
        help="only plans on or after WHEN: YYYY-MM-DD or an age (14m, 5h, 3d, 2w, 1y)",
    )
    group.add_argument(
        "--until",
        metavar="WHEN",
        type=_when,
        help="only plans on or before WHEN; same forms as --since",
    )
    group.add_argument(
        "--date",
        choices=DATE_CHOICES,
        help="which date --since/--until compare (default: modified)",
    )


def _add_sort_args(parser):
    group = parser.add_argument_group("sorting")
    group.add_argument(
        "--sort", choices=SORT_CHOICES, default="modified", help="sort key (default: modified)"
    )
    group.add_argument(
        "--order",
        choices=ORDER_CHOICES,
        default=_ORDER_ASC,
        help=f"sort direction (default: {_ORDER_ASC})",
    )
    return group


def _sort_key(args):
    return SORT_KEYS[args.sort]


def _sort_descending(args) -> bool:
    return args.order == _ORDER_DESC


def _add_format_args(parser):
    group = parser.add_argument_group("output")
    group.add_argument(
        "--format",
        choices=formats.CHOICES,
        default=formats.TABLE,
        help=f"output format (default: {formats.TABLE})",
    )
    group.add_argument(
        "--color",
        choices=style.COLOR_CHOICES,
        default="auto",
        help="color policy (default: auto)",
    )
    return group


def _resolve_project(value: str) -> str:
    """`.` resolves to the current directory's name -- exactly how `backfill`
    derives `project` from a session's `cwd`."""
    return Path.cwd().name if value == "." else value


def _plan_day(plan, which: str):
    if which == "created":
        return plan.created_date
    return times_module.local_day(plan.modified)


def _require_valid_dates(args) -> None:
    if args.date is not None and args.since is None and args.until is None:
        raise UsageError("--date requires --since or --until")
    if args.since is not None and args.until is not None and args.since > args.until:
        raise UsageError(f"--since {args.since} is after --until {args.until}")


def _within_dates(plans, args):
    which = args.date or "modified"
    kept = []
    for plan in plans:
        day = _plan_day(plan, which)
        if day is None:
            continue
        if args.since is not None and day < args.since:
            continue
        if args.until is not None and day > args.until:
            continue
        kept.append(plan)
    return kept


def _finding_requested(args) -> bool:
    """`--finding` is `False` when absent and `None` when bare: argparse checks
    a string `const` against `choices` on some Python versions."""
    return args.finding is not False


def _has_finding(plan, code: str | None) -> bool:
    return bool(plan.findings) if code is None else code in plan.findings


def _findings_by_id(plans) -> dict[str, list[check_module.Finding]]:
    by_id: dict[str, list[check_module.Finding]] = {}
    for finding in check_module.run(plans, sessions_module.load(), touches_module.load()):
        by_id.setdefault(finding.id, []).append(finding)
    return by_id


def _attach_findings(plans) -> dict[str, list[check_module.Finding]]:
    """Set each plan's `findings` from a check over `plans`, which must be
    the whole corpus so lineage findings stay correct."""
    by_id = _findings_by_id(plans)
    for p in plans:
        p.findings = sorted({f.code for f in by_id.get(p.id, [])})
    return by_id


def _apply_filters(plans, args):
    _require_valid_dates(args)
    if args.status:
        plans = [p for p in plans if p.status == args.status]
    if args.intent:
        plans = [p for p in plans if p.intent == args.intent]
    if args.project is not None:
        project = _resolve_project(args.project)
        plans = [p for p in plans if p.project == project]
    if args.source:
        plans = [p for p in plans if p.source == args.source]
    if args.starred:
        plans = [p for p in plans if p.intent in STARRED_INTENTS]
    if args.tag:
        wanted = set(args.tag)
        plans = [p for p in plans if wanted <= tags_module.normalized(p.tags)]
    if args.grep is not None:
        plans = [p for p in plans if args.grep.search(p.title + "\n" + p.body)]
    if args.title is not None:
        plans = [p for p in plans if args.title.search(p.title)]
    if _finding_requested(args):
        plans = [p for p in plans if _has_finding(p, args.finding)]
    if args.since is not None or args.until is not None:
        plans = _within_dates(plans, args)
    return plans


def _select_lineage(corpus_plans, target, args):
    """`target` plus its descendants, and with `--ancestors` the path down
    from its topmost ancestor. The whole corpus when there is no target."""
    if target is None:
        return corpus_plans
    selected = tree_module.subtree(corpus_plans, target)
    if args.ancestors:
        below = {p.id for p in selected}
        selected = [
            p for p in tree_module.spine(corpus_plans, target) if p.id not in below
        ] + selected
    return selected


def _version() -> str:
    try:
        return importlib.metadata.version("pentimento")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _add_command(sub, name, help, description=None, epilog=None):
    command_parser = sub.add_parser(
        name,
        help=help,
        description=description or help,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    command_parser.set_defaults(command_parser=command_parser)
    return command_parser


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="pentimento",
        description="Status, intent, and lineage for Claude Code and Cursor plan files.",
        epilog=(
            "Plans are read from AGENT_PLANS_DIR (default: ~/.claude/plans) and\n"
            "CURSOR_PLANS_DIR; session history from AGENT_SESSIONS_DIR (default:\n"
            "~/.claude/projects).\n"
            "Run `pentimento <command> --help` for a command's flags."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"pentimento {_version()}")
    sub = parser.add_subparsers(
        dest="command", required=True, title="commands", metavar="<command>"
    )

    p_list = _add_command(
        sub,
        "list",
        "flat table of plans",
        description=(
            "One line per plan; the row nearest the prompt is the most recent.\n"
            "TAGS and CREATED appear only when the corpus has them. When the\n"
            "terminal is too narrow for the table, each plan prints as a short\n"
            "record with every field kept; see docs/reference.md#columns."
        ),
        epilog=(
            "Examples:\n"
            "  pentimento list --starred\n"
            "  pentimento list --project . --status partial\n"
            "  pentimento list --grep auth -n 3\n"
            "  pentimento list --title 'github actions|\\bGHA\\b'\n"
            "  pentimento list --since 1w --status complete\n"
            "  pentimento list --columns status,title,created"
        ),
    )
    _add_filter_args(p_list)
    format_group = _add_format_args(p_list)
    format_group.add_argument(
        "--columns",
        type=_column_spec,
        metavar="SPEC",
        help=(
            "which table columns to show and in what order: an absolute, comma-"
            "separated list (e.g. status,title); +name/-name to add/remove from the "
            "default set (write -name as --columns=-name); or 'all'. Names are the "
            f"record fields: {', '.join(listing.NAMES)}. "
            "Table format only; defaults to PENTIMENTO_COLUMNS"
        ),
    )
    sort_group = _add_sort_args(p_list)
    sort_group.add_argument(
        "-n",
        "--limit",
        metavar="N",
        type=_non_negative_int,
        help="keep only the N rows nearest the prompt (before rendering or emitting); 0 means none",
    )

    p_tree = _add_command(
        sub,
        "tree",
        "lineage tree, grouped by project",
        description=(
            "Plans nested under their parents, grouped by project. <id> is\n"
            "resolved against the whole corpus, so --project is unnecessary; it\n"
            "selects a lineage thread whatever its subplans are tagged."
        ),
        epilog=(
            "Examples:\n  pentimento tree --project .\n  pentimento tree --starred\n"
            "  pentimento tree wobbly-willow\n  pentimento tree wobbly-willow --ancestors"
        ),
    )
    p_tree.add_argument(
        "id",
        nargs="?",
        help=f"{_ID_HELP}; roots the tree at that plan and every plan beneath it",
    )
    p_tree.add_argument(
        "--ancestors",
        action="store_true",
        help="also show the path down from this plan's topmost ancestor",
    )
    _add_filter_args(p_tree)
    _add_format_args(p_tree)
    _add_sort_args(p_tree)

    p_show = _add_command(
        sub,
        "show",
        "H1, frontmatter, and the rendered body",
        description=(
            "One plan's H1, frontmatter, and body. On a tty the body clips to\n"
            "the terminal height; --full prints it whole, through $PAGER if it\n"
            "is longer than the terminal."
        ),
        epilog=(
            "Examples:\n  pentimento show api-auth-rollout --full\n"
            "  pentimento show api-auth-rollout --full --no-pager"
        ),
    )
    p_show.add_argument("id", help=_ID_HELP)
    p_show.add_argument("--full", action="store_true", help="print the whole body, unclipped")
    p_show.add_argument("--no-pager", action="store_true", help="with --full, never use a pager")
    _add_format_args(p_show)

    p_set = _add_command(
        sub,
        "set",
        "rewrite frontmatter in place",
        description=(
            "Rewrite the named plans' frontmatter in place. Only the fields you\n"
            "name change. Every id is resolved before anything is written."
        ),
        epilog=(
            "Examples:\n"
            "  pentimento set api-auth-rollout --intent active\n"
            "  pentimento set api-auth-rollout --status complete --add-tag auth\n"
            "  pentimento set api-auth-rollout --clear-parent\n"
            "  pentimento set wobbly-willow api-auth-cleanup --intent someday"
        ),
    )
    p_set.add_argument("ids", nargs="+", metavar="ID", help=f"{_ID_HELP}; one or more")
    pin_group = p_set.add_mutually_exclusive_group()
    pin_group.add_argument(
        "--status",
        choices=vocabulary_module.STATUS_ORDER,
        help="new status; pins it against derivation",
    )
    pin_group.add_argument(
        "--unpin", action="store_true", help="release a pinned status back to derivation"
    )
    p_set.add_argument("--intent", choices=vocabulary_module.INTENT_VALUES, help="new intent")
    parent_group = p_set.add_mutually_exclusive_group()
    parent_group.add_argument(
        "--parent",
        metavar="ID",
        help=f"new parent: {_ID_HELP}; rejected if it would create a cycle",
    )
    parent_group.add_argument("--clear-parent", action="store_true", help="clear parent plan id")
    project_group = p_set.add_mutually_exclusive_group()
    project_group.add_argument(
        "--project", help="new project; '.' resolves to the current directory's name"
    )
    project_group.add_argument("--clear-project", action="store_true", help="clear project")
    p_set.add_argument(
        "--add-tag",
        metavar="TAG",
        type=_tag,
        action="append",
        help=f"add a tag; repeatable; {_TAG_MATCH_HELP}",
    )
    p_set.add_argument(
        "--remove-tag",
        metavar="TAG",
        type=_tag,
        action="append",
        help=f"remove a tag; repeatable; {_TAG_MATCH_HELP}",
    )
    p_set.add_argument(
        "--clear-tags",
        action="store_true",
        help="remove all tags; not combinable with --add-tag or --remove-tag",
    )
    p_set.add_argument("--dry-run", action="store_true", help=_DRY_RUN_HELP)

    p_backfill = _add_command(
        sub,
        "backfill",
        "gap-fill intent/created/project/parent; advance status",
        description=(
            "Gap-fill intent, created, project, and parent for plans missing\n"
            "them, advance status when '## Progress' is ahead of it, and write\n"
            "the frontmatter block. To fix one plan, use --only or `pentimento\n"
            "set`; --rederive recomputes derived fields across the whole corpus\n"
            "and cannot change a pinned status."
        ),
        epilog="Examples:\n  pentimento backfill --dry-run",
    )
    p_backfill.add_argument("--dry-run", action="store_true", help=_DRY_RUN_HELP)
    p_backfill.add_argument(
        "--quiet", action="store_true", help="suppress changed-id and field-change output"
    )
    p_backfill.add_argument(
        "--only",
        metavar="ID",
        action="append",
        help=f"{_ID_HELP}; repeatable, restricts writes to the named plans",
    )
    p_backfill.add_argument(
        "--rederive",
        action="store_true",
        help="recompute derived fields across the whole corpus; cannot change a pinned status",
    )
    p_backfill.add_argument(
        "--recreate", action="store_true", help="recompute created from local time too"
    )

    _add_command(
        sub,
        "hook",
        "run as a Claude Code PostToolUse hook; reads the payload on stdin",
        description=(
            "Read a Claude Code PostToolUse payload on stdin and backfill\n"
            "frontmatter for the plan just written, deriving status capped at\n"
            f"partial. Wiring:\n{_DOCS_URL}/integrations.md"
        ),
        epilog=(
            "Examples:\n"
            '  echo \'{"tool_input": {"file_path": "~/.claude/plans/api-auth.md"}}\' \\\n'
            "    | pentimento hook"
        ),
    )

    _add_command(
        sub,
        "index",
        "write INDEX.md into the plans directory",
        description=(
            "Write INDEX.md into the plans directory: one linked row per plan,\ngrouped by status."
        ),
        epilog="Examples:\n  pentimento index",
    )

    p_check = _add_command(
        sub,
        "check",
        "validate lineage, vocabulary, status, and tags; exits 1 on any finding",
        description=(
            "Validate lineage, vocabulary, status, and tags across the corpus.\n"
            "Exits 1 when anything is found; finding codes are in\n"
            f"{_DOCS_URL}/troubleshooting.md"
        ),
        epilog=(
            "Examples:\n"
            "  pentimento check\n"
            "  pentimento check --format json\n"
            "  pentimento check --color never"
        ),
    )
    _add_format_args(p_check)

    p_history = _add_command(
        sub,
        "history",
        "session-touch history for a plan",
        description="Every session that touched one plan, oldest first.",
        epilog="Examples:\n  pentimento history api-auth-cleanup --format json",
    )
    p_history.add_argument("id", help=_ID_HELP)
    _add_format_args(p_history)

    p_completion = _add_command(
        sub,
        "completion",
        "print a shell integration script",
        description=(
            "Print an integration script for SHELL to stdout. Source it, or\n"
            "eval its output, to get tab completion for subcommands, flags, and\n"
            "plan ids."
        ),
        epilog=("Examples:\n  pentimento completion bash\n  pentimento completion zsh"),
    )
    p_completion.add_argument(
        "shell", choices=completion.SHELLS, metavar="SHELL", help="bash, zsh, or fish"
    )

    return parser


def _no_such_plan(plans, wanted: str) -> str:
    matches = corpus.ambiguous(plans, wanted)
    if matches:
        return f"ambiguous plan id: {wanted} -- matches: {', '.join(matches)}"
    message = f"no such plan: {wanted}"
    close = corpus.suggest(plans, wanted)
    if close:
        message += f" -- did you mean: {', '.join(close)}?"
    return message


def _empty_corpus_hint() -> str:
    directories = []
    for source in sources_module.all_sources():
        directories.extend(str(d) for d in source.directories)
    return "no plans found; searched: " + ", ".join(directories)


def _report_if_empty(plans) -> None:
    if not plans:
        _report(_empty_corpus_hint())


def _apply_limit(plans, args):
    """Keep the N rows nearest the prompt: the tail under `--order asc`, the head under `desc`."""
    if args.limit is None:
        return plans
    if args.limit == 0:
        return []
    return plans[: args.limit] if _sort_descending(args) else plans[-args.limit :]


def _render_table_or_empty(corpus_plans, plans, args, render):
    """Shared `list`/`tree` table-format tail: nothing for an empty corpus, empty-filter
    summary, or `render(on_color, short_ids)` followed by the
    filtered/total summary line."""
    if not corpus_plans:
        return 0
    if not plans:
        on_color = style.enabled(sys.stdout, args.color)
        print(style.paint(counts.summary(0, len(corpus_plans)), style.DIM, on=on_color))
        return 0
    on_color = style.enabled(sys.stdout, args.color)
    short_ids = shortid.shorten(p.id for p in corpus_plans)
    print(render(on_color, short_ids))
    print()
    print(style.paint(counts.summary(len(plans), len(corpus_plans)), style.DIM, on=on_color))
    return 0


def _columns_selection(args):
    """The `--columns` selection, or `PENTIMENTO_COLUMNS` when the flag is
    absent; `UsageError` when the environment variable is invalid."""
    if args.columns is not None:
        return args.columns
    env_value = os.environ.get("PENTIMENTO_COLUMNS")
    if not env_value:
        return None
    try:
        return _column_spec(env_value)
    except argparse.ArgumentTypeError as exc:
        raise UsageError(f"PENTIMENTO_COLUMNS: {exc}") from exc


def _selects_finding(selection) -> bool:
    return selection is not None and "finding" in (*(selection.absolute or ()), *selection.add)


def cmd_list(args) -> int:
    if args.columns is not None and args.format != formats.TABLE:
        raise UsageError("--columns only applies to --format table")

    corpus_plans = corpus.load_all()
    _report_if_empty(corpus_plans)
    selection = None if args.format != formats.TABLE else _columns_selection(args)
    if _finding_requested(args) or args.format != formats.TABLE or _selects_finding(selection):
        _attach_findings(corpus_plans)
    plans = _apply_filters(corpus_plans, args)
    plans = sorted(plans, key=_sort_key(args), reverse=_sort_descending(args))
    plans = _apply_limit(plans, args)
    if args.format != formats.TABLE:
        formats.emit(
            [record_module.as_dict(p) for p in plans], args.format, sys.stdout, record_module.FIELDS
        )
        return 0

    return _render_table_or_empty(
        corpus_plans,
        plans,
        args,
        lambda on_color, short_ids: listing.render(
            plans, on_color, short_ids=short_ids, selection=selection
        ),
    )


def cmd_tree(args) -> int:
    if args.id is None and args.ancestors:
        raise UsageError("--ancestors requires a plan id")
    corpus_plans = corpus.load_all()
    _report_if_empty(corpus_plans)
    target = None
    if args.id is not None:
        target = corpus.by_id(corpus_plans, args.id)
        if target is None:
            _report(_no_such_plan(corpus_plans, args.id))
            return 1
    if _finding_requested(args) or args.format != formats.TABLE:
        _attach_findings(corpus_plans)
    plans = _apply_filters(_select_lineage(corpus_plans, target, args), args)
    root_id = target.id if target else None
    key, reverse = _sort_key(args), _sort_descending(args)
    if args.format != formats.TABLE:
        records = tree_module.as_records(plans, key=key, reverse=reverse, root_id=root_id)
        if args.format == "tsv":
            records = tree_module.flatten(records)
        formats.emit(records, args.format, sys.stdout, record_module.FIELDS)
        return 0
    return _render_table_or_empty(
        corpus_plans,
        plans,
        args,
        lambda on_color, short_ids: tree_module.render_grouped(
            plans,
            on_color,
            key=key,
            reverse=reverse,
            short_ids=short_ids,
            root_id=root_id,
        ),
    )


def _display_path(path: Path) -> str:
    """Renders path with $HOME collapsed to ~, else the plain string."""
    if path.is_relative_to(Path.home()):
        return f"~/{path.relative_to(Path.home())}"
    return str(path)


FIELD_GUTTER = 3

_HEADER_GROUPS = (
    ("identity", ("id",)),
    ("location", ("path",)),
    ("state", ("status", "intent", "tags")),
    ("lineage", ("parent", "project")),
    ("provenance", ("created", "source", "modified")),
)


_FIELD_CODES = {"status": style.STATUS_CODES, "intent": style.INTENT_CODES}


def _header_values(target) -> dict[str, str]:
    """Frontmatter with the effective `status`, `intent`, `created`, and `tags`."""
    values = dict(target.fields)
    values.pop("tags", None)
    values.update(
        id=target.id,
        path=_display_path(target.path),
        status=target.status,
        intent=target.intent,
        source=target.source,
        modified=times_module.local_stamp(target.modified),
    )
    if target.created:
        values["created"] = target.created
    if target.tags:
        values["tags"] = tags_module.render(target.tags)
    return values


def _show_field_groups(target):
    """Lists of (key, value, codes) per semantic group, skipping empty groups."""
    values = _header_values(target)
    grouped_keys = {key for _, keys in _HEADER_GROUPS for key in keys}
    key_groups = [[key for key in keys if key in values] for _, keys in _HEADER_GROUPS]
    key_groups.append([key for key in values if key not in grouped_keys])
    return [
        [(key, values[key], _FIELD_CODES.get(key, {}).get(values[key], ())) for key in keys]
        for keys in key_groups
        if keys
    ]


def _flow_pairs(pairs: list[tuple[str, str]], width: int) -> list[str]:
    """Greedy-pack (plain, painted) `pairs` from one group onto lines.

    Pairs are joined by `FIELD_GUTTER` spaces. A pair wider than `width` gets
    its own line and is never truncated -- the `id` and `parent` values must
    stay copy-pasteable.
    """
    lines: list[str] = []
    line_painted: list[str] = []
    line_width = 0
    gutter = " " * FIELD_GUTTER
    for plain, painted in pairs:
        cell_width = style.display_width(plain)
        if line_painted and line_width + FIELD_GUTTER + cell_width > width:
            lines.append(gutter.join(line_painted))
            line_painted, line_width = [], 0
        if line_painted:
            line_width += FIELD_GUTTER
        line_painted.append(painted)
        line_width += cell_width
    if line_painted:
        lines.append(gutter.join(line_painted))
    return lines


def _show_header(target, width: int, *, on_color: bool) -> list[str]:
    lines = [style.paint(f"# {target.title}", style.BOLD, on=on_color), ""]
    for group in _show_field_groups(target):
        pairs = [
            style.render_cells([(f"{key}:", (style.DIM,)), (value, codes)], " ", on_color=on_color)
            for key, value, codes in group
        ]
        lines.extend(_flow_pairs(pairs, width))
    lines.append("")
    return lines


def _paint_leading(lines: list[str], length: int, *codes: str, on_color: bool) -> list[str]:
    """Paint the first `length` characters of `lines`, which may span several."""
    painted = []
    for line in lines:
        count = min(length, len(line))
        length -= count
        painted.append(style.paint(line[:count], *codes, on=on_color) + line[count:])
    return painted


def _show_findings(found, width: int, on_color: bool) -> list[str]:
    lines = []
    for finding in found:
        wrapped = style.wrap(f"{finding.code}: {finding.message}", width)
        lines.extend(_paint_leading(wrapped, len(finding.code), style.RED, on_color=on_color))
        hint = style.wrap(check_module.show_hint(finding.code), width - len(table.STACK_INDENT))
        lines.extend(style.paint(table.STACK_INDENT + h, style.DIM, on=on_color) for h in hint)
    if lines:
        lines.append("")
    return lines


def _should_page(args, line_count: int) -> bool:
    return (
        args.full
        and not args.no_pager
        and sys.stdout.isatty()
        and line_count > style.terminal_height()
    )


def cmd_show(args) -> int:
    plans = corpus.load_all()
    target = corpus.by_id(plans, args.id)
    if target is None:
        _report(_no_such_plan(plans, args.id))
        return 1
    found = _attach_findings(plans).get(target.id, [])
    if args.format != formats.TABLE:
        record = {**record_module.as_dict(target), "body": target.body}
        formats.emit([record], args.format, sys.stdout, (*record_module.FIELDS, "body"))
        return 0

    on_color = style.enabled(sys.stdout, args.color)
    width = min(style.terminal_width() or markdown.MAX_WIDTH, markdown.MAX_WIDTH)

    header = _show_header(target, width, on_color=on_color) + _show_findings(found, width, on_color)
    body_text = plan_module.body_below_title(target.body)
    body = markdown.render(body_text, on_color=on_color, width=width)
    if _should_page(args, len(header) + len(body)):
        pager.page(header + body)
        return 0

    limit = None
    if sys.stdout.isatty() and not args.full:
        limit = max(style.terminal_height() - len(header) - 2, markdown.MIN_BODY_LINES)
    hint = f"pentimento show {args.id} --full"
    body = markdown.clip(body, limit, hint, on_color=on_color)
    for line in header + body:
        print(line)
    return 0


def _apply_tag_edit(target, args) -> None:
    """Apply --clear-tags, --remove-tag, --add-tag in order.

    Existing tags are normalized on any edit, so a hand-written `Auth`
    self-heals the next time `set` touches tags.
    """
    if not (args.clear_tags or args.remove_tag or args.add_tag):
        return
    current = set() if args.clear_tags else tags_module.normalized(target.tags)
    current -= set(args.remove_tag or ())
    current |= set(args.add_tag or ())
    if current:
        target.fields["tags"] = tags_module.render(sorted(current))
    else:
        target.fields.pop("tags", None)


def _describe_field_changes(before: dict, after: dict) -> list[str]:
    changes = []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        if old is None:
            changes.append(f"{key}: set to {new}")
        elif new is None:
            changes.append(f"{key}: cleared")
        else:
            changes.append(f"{key}: {old} -> {new}")
    return changes


def _require_set_changes(args) -> None:
    if args.clear_tags and (args.add_tag or args.remove_tag):
        raise UsageError("--clear-tags cannot be combined with --add-tag or --remove-tag")
    both = sorted(set(args.add_tag or ()) & set(args.remove_tag or ()))
    if both:
        raise UsageError(f"tag '{both[0]}' is in both --add-tag and --remove-tag")
    requested = (
        args.status,
        args.unpin,
        args.intent,
        args.parent,
        args.clear_parent,
        args.project,
        args.clear_project,
        args.add_tag,
        args.remove_tag,
        args.clear_tags,
    )
    if all(value in (None, False) for value in requested):
        raise UsageError("nothing to set; name a field flag such as --status or --add-tag")


def _apply_project_edit(target, args) -> None:
    if args.clear_project:
        target.fields.pop("project", None)
    elif args.project is not None:
        resolved = _resolve_project(args.project)
        if not frontmatter.is_valid_value(resolved):
            raise UsageError(f"invalid project: '{resolved}' -- {_PROJECT_FORM}")
        target.fields["project"] = resolved


def _apply_parent_edit(targets, plans, args) -> int | None:
    """Exit code when the edit is refused, else `None`. Cycles are checked
    with every target's new parent in place at once."""
    if args.clear_parent:
        for target in targets:
            target.fields.pop("parent", None)
    elif args.parent is not None:
        parent_plan = corpus.by_id(plans, args.parent)
        if parent_plan is None:
            _report(_no_such_plan(plans, args.parent))
            return 1
        parent_of = {p.id: p.fields.get("parent") for p in plans}
        parent_of.update({target.id: parent_plan.id for target in targets})
        if any(lineage.in_cycle(target.id, parent_of) for target in targets):
            raise UsageError(f"--parent {parent_plan.id} would create a cycle")
        for target in targets:
            target.fields["parent"] = parent_plan.id
    return None


def _apply_status_edit(target, args) -> None:
    for field in ("status", "intent"):
        value = getattr(args, field, None)
        if value is not None:
            target.fields[field] = value
    if args.status is not None:
        target.fields["pinned"] = "true"
    if args.unpin:
        target.fields.pop("pinned", None)


def _resolve_targets(plans, values):
    """The distinct plans `values` name, in order, and the `_no_such_plan`
    message for the first value that resolves to none."""
    targets = {}
    for value in values:
        target = corpus.by_id(plans, value)
        if target is None:
            return [], _no_such_plan(plans, value)
        targets.setdefault(target.id, target)
    return list(targets.values()), None


def _print_set_changes(changed, short_ids, args) -> None:
    """One `field: change` line each; with several plans, each block is
    headed by the plan's short id."""
    suffix = " (dry run)" if args.dry_run else ""
    headed = len(args.ids) > 1
    for target, changes in changed:
        if headed:
            print(short_ids.get(target.id, target.id))
        for change in changes:
            print(f"{'  ' if headed else ''}{change}{suffix}")


def cmd_set(args) -> int:
    _require_set_changes(args)
    plans = corpus.load_all()
    targets, error = _resolve_targets(plans, args.ids)
    if error is not None:
        _report(error)
        return 1

    before = {target.id: dict(target.fields) for target in targets}
    for target in targets:
        _apply_project_edit(target, args)
        _apply_tag_edit(target, args)
        _apply_status_edit(target, args)
    refused = _apply_parent_edit(targets, plans, args)
    if refused is not None:
        return refused

    changed = [
        (target, changes)
        for target in targets
        if (changes := _describe_field_changes(before[target.id], target.fields))
    ]
    if not changed:
        print("no changes")
        return 0
    _print_set_changes(changed, shortid.shorten(p.id for p in plans), args)
    if not args.dry_run:
        for target, _ in changed:
            plan_module.save(target, keep_mtime=True)
    return 0


def _backfill(
    *,
    dry_run: bool = False,
    rederive: bool = False,
    recreate: bool = False,
    max_status: str | None = None,
    only=None,
    sessions=None,
    plans=None,
    details=None,
) -> list[str]:
    if sessions is None:
        sessions = sessions_module.load()
    if plans is None:
        plans = corpus.load_all(sessions=sessions)
    return backfill_module.run(
        plans,
        sessions,
        dry_run=dry_run,
        rederive=rederive,
        recreate=recreate,
        max_status=max_status,
        only=only,
        details=details,
    )


def cmd_hook(_args) -> int:
    # PostToolUse treats exit 2 as blocking and surfaces other non-zero exits, so a
    # crash here would visibly interrupt every session -- fail open and silent instead.
    try:
        path = hook_module.touched_plan_path(sys.stdin.read())
        if path is None:
            return 0
        sessions = sessions_module.load()
        plans = corpus.load_all(sessions=sessions)
        target = corpus.by_id(plans, path.name)
        if target is None:
            return 0
        changed = _backfill(
            only={target.id}, max_status=vocabulary.PARTIAL, sessions=sessions, plans=plans
        )
        for plan_id in changed:
            print(plan_id)
    except Exception:
        if os.environ.get("PENTIMENTO_DEBUG"):
            traceback.print_exc(file=sys.stderr)
    return 0


def cmd_backfill(args) -> int:
    sessions = sessions_module.load()
    plans = corpus.load_all(sessions=sessions)
    _report_if_empty(plans)
    duplicates = sorted({p.id for p in check_module.duplicate_ids(plans)})
    if duplicates:
        _report(
            f"duplicate plan id(s): {', '.join(duplicates)} -- "
            "run `pentimento check` and resolve before backfilling"
        )
        return 1

    only = None
    if args.only:
        targets, error = _resolve_targets(plans, args.only)
        if error is not None:
            _report(error)
            return 1
        only = {target.id for target in targets}

    details = {}
    changed = _backfill(
        dry_run=args.dry_run,
        rederive=args.rederive,
        recreate=args.recreate,
        only=only,
        sessions=sessions,
        plans=plans,
        details=details,
    )
    if not args.quiet:
        for plan_id in changed:
            print(plan_id)
            for change in _describe_field_changes(*details[plan_id]):
                print(f"  {change}")
        if not changed:
            print("no changes")
        elif args.dry_run:
            print(f"{counts.plural(len(changed), 'plan')} would change (dry run)")
        else:
            print(f"{counts.plural(len(changed), 'plan')} updated")
    return 0


def cmd_index(_args) -> int:
    plans = corpus.load_all()
    _report_if_empty(plans)
    index_module.write(plans, corpus.plans_directory())
    print(f"{counts.plural(len(plans), 'plan')} indexed")
    return 0


def _render_check_table(findings, plans, *, on_color: bool) -> str:
    columns = (
        table.Column("CODE"),
        table.Column("PLAN"),
        table.Column("MESSAGE", fit=table.WRAP, floor=20),
    )
    short = shortid.shorten(p.id for p in plans)
    rows = [
        ((f.code, (style.RED,)), (short.get(f.id, f.id), ()), (f.message, ())) for f in findings
    ]
    return table.render(columns, rows, on_color=on_color, width=style.terminal_width())


def _print_check_table(findings, plans, args) -> None:
    on_color = style.enabled(sys.stdout, args.color)
    if findings:
        print(_render_check_table(findings, plans, on_color=on_color))
        print()
    plan_count = counts.plural(len(plans), "plan")
    finding_count = counts.plural(len(findings), "finding")
    print(style.paint(f"{plan_count} checked, {finding_count}", style.DIM, on=on_color))
    for code in sorted({f.code for f in findings}):
        print(style.paint(f"{code}: {check_module.HINTS[code]}", style.DIM, on=on_color))
    if findings:
        print(style.paint("narrow with: pentimento list --finding <code>", style.DIM, on=on_color))


def cmd_check(args) -> int:
    sessions = sessions_module.load()
    touches = touches_module.load()
    skips = []
    plans = corpus.load_all(sessions=sessions, skips=skips)
    _report_if_empty(plans)
    findings = check_module.run(plans, sessions, touches, skips=skips)
    if args.format == formats.TABLE:
        _print_check_table(findings, plans, args)
    else:
        columns = tuple(f.name for f in dataclasses.fields(check_module.Finding))
        formats.emit([dataclasses.asdict(f) for f in findings], args.format, sys.stdout, columns)
    return 1 if findings else 0


def cmd_history(args) -> int:
    plans = corpus.load_all()
    target = corpus.by_id(plans, args.id)
    if target is None:
        _report(_no_such_plan(plans, args.id))
        return 1

    plan_touches = touches_module.load().get(target.id, [])
    if args.format != formats.TABLE:
        formats.emit(
            history_module.as_records(target.id, plan_touches),
            args.format,
            sys.stdout,
            history_module.FIELDS,
        )
        return 0
    if not plan_touches:
        _report(
            history_module.EMPTY_MESSAGE.format(
                plan_id=target.id, directory=sessions_module.sessions_directory()
            )
        )
        return 0
    on_color = style.enabled(sys.stdout, args.color)
    print(history_module.render(target.id, plan_touches, on_color))
    return 0


def cmd_completion(args) -> int:
    sys.stdout.write(completion.script(args.shell))
    return 0


COMMANDS = {
    "list": cmd_list,
    "tree": cmd_tree,
    "show": cmd_show,
    "set": cmd_set,
    "backfill": cmd_backfill,
    "hook": cmd_hook,
    "index": cmd_index,
    "check": cmd_check,
    "history": cmd_history,
    "completion": cmd_completion,
}


def _silence_stdout() -> None:
    """Point stdout at devnull so the interpreter's exit-time flush of a broken pipe stays quiet."""
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, sys.stdout.fileno())
    os.close(devnull)


def _dispatch(argv) -> int:
    if argv and argv[0] == "__complete":
        code = completion.complete(argv[1:])
    else:
        parser = build_parser()
        args = parser.parse_args(argv)
        try:
            code = COMMANDS[args.command](args)
        except (UsageError, columns_module.EmptySelectionError) as exc:
            args.command_parser.error(str(exc))
    sys.stdout.flush()
    return code


def _describe_os_error(exc: OSError) -> str:
    if exc.filename and exc.strerror:
        return f"{exc.filename}: {exc.strerror}"
    return str(exc)


def _replace_unencodable_output() -> None:
    """Print `?` for characters the stdout encoding lacks instead of raising."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="replace")


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    _replace_unencodable_output()
    try:
        return _dispatch(argv)
    except BrokenPipeError:
        _silence_stdout()
        return 141
    except OSError as exc:
        _report(_describe_os_error(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
