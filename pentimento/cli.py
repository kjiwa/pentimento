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

# The `list`/`tree` column each `--sort` key is about, so its column is
# never dropped -- an order the row nearest the prompt doesn't show is
# unverifiable.
SORT_COLUMNS = {
    "created": "created",
    "status": "status",
    "title": "title",
    "id": "plan",
    "modified": "updated",
}

_ORDER_ASC, _ORDER_DESC = "asc", "desc"
ORDER_CHOICES = (_ORDER_ASC, _ORDER_DESC)


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"limit must not be negative: {value}")
    return parsed


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
        "--tag", action="append", help="filter by tag; repeatable, every given tag must be present"
    )
    group.add_argument(
        "--grep",
        metavar="PATTERN",
        help="filter by a case-insensitive regex over title and body",
    )


def _add_sort_args(parser):
    group = parser.add_argument_group("sorting")
    group.add_argument(
        "--sort", choices=SORT_CHOICES, default="modified", help="sort order (default: modified)"
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
        help="colour policy (default: auto)",
    )
    group.add_argument(
        "--ascii",
        action="store_true",
        help="force ASCII box-drawing glyphs, even on a UTF-8 terminal",
    )
    return group


def _resolve_project(value: str) -> str:
    """`.` resolves to the current directory's name -- exactly how `backfill`
    derives `project` from a session's `cwd`."""
    return Path.cwd().name if value == "." else value


def _apply_filters(plans, args):
    if args.status:
        plans = [p for p in plans if p.status == args.status]
    if args.intent:
        plans = [p for p in plans if p.intent == args.intent]
    if args.project:
        project = _resolve_project(args.project)
        plans = [p for p in plans if p.project == project]
    if args.source:
        plans = [p for p in plans if p.source == args.source]
    if args.starred:
        plans = [p for p in plans if p.intent in STARRED_INTENTS]
    if args.tag:
        wanted = {tags_module.normalize(t) for t in args.tag}
        plans = [p for p in plans if wanted <= {tags_module.normalize(t) for t in p.tags}]
    if args.grep:
        try:
            pattern = re.compile(args.grep, re.IGNORECASE)
        except re.error as exc:
            print(str(exc), file=sys.stderr)
            return None
        plans = [p for p in plans if pattern.search(p.title + p.body)]
    return plans


def _version() -> str:
    try:
        return importlib.metadata.version("pentimento")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _add_command(sub, name, help, description=None, epilog=None):
    return sub.add_parser(
        name,
        help=help,
        description=description or help,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pentimento",
        description="Status, intent, and lineage over agent plan files.",
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
            "One line per plan; the row nearest the prompt is the most recent. TAGS "
            "and CREATED appear only when the corpus has them; as the terminal "
            "narrows, columns drop in this order: CREATED, TAGS, SOURCE, PROJECT, "
            "INTENT, STATUS, then PLAN -- TITLE and UPDATED never drop. --columns "
            "overrides both rules, and the --sort key's column never drops."
        ),
        epilog=(
            "Examples:\n"
            "  pentimento list --starred\n"
            "  pentimento list --project . --status partial\n"
            "  pentimento list --grep auth -n 3\n"
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
            "default set; or 'all'. Table format only; defaults to PENTIMENTO_COLUMNS"
        ),
    )
    sort_group = _add_sort_args(p_list)
    sort_group.add_argument(
        "-n",
        "--limit",
        type=_non_negative_int,
        help="keep only the N rows nearest the prompt (before rendering or emitting); 0 means none",
    )

    p_tree = _add_command(
        sub,
        "tree",
        "lineage tree, grouped by project",
        description="Plans nested under their parents, grouped by project.",
        epilog=("Examples:\n  pentimento tree --project .\n  pentimento tree --starred --ascii"),
    )
    _add_filter_args(p_tree)
    _add_format_args(p_tree)
    _add_sort_args(p_tree)

    p_show = _add_command(
        sub,
        "show",
        "H1, frontmatter, and the rendered body",
        description=(
            "One plan's H1, frontmatter, and body. On a tty the body clips to the "
            "terminal height; --full prints it whole, through $PAGER if it is longer "
            "than the terminal."
        ),
        epilog=(
            "Examples:\n  pentimento show api-auth-rollout --full\n"
            "  pentimento show api-auth-rollout --full --no-pager"
        ),
    )
    p_show.add_argument("id", help="plan id (filename stem)")
    p_show.add_argument("--full", action="store_true", help="print the whole body, unclipped")
    p_show.add_argument("--no-pager", action="store_true", help="with --full, never use a pager")
    _add_format_args(p_show)

    p_set = _add_command(
        sub,
        "set",
        "rewrite frontmatter in place",
        description=("Rewrite one plan's frontmatter in place. Only the fields you name change."),
        epilog=(
            "Examples:\n"
            "  pentimento set api-auth-rollout --intent active\n"
            "  pentimento set api-auth-rollout --status complete --add-tag auth\n"
            "  pentimento set api-auth-rollout --clear-parent"
        ),
    )
    p_set.add_argument("id", help="plan id (filename stem)")
    p_set.add_argument(
        "--status",
        choices=vocabulary_module.STATUS_ORDER,
        help="new status; pins it against derivation",
    )
    p_set.add_argument(
        "--unpin", action="store_true", help="release a pinned status back to derivation"
    )
    p_set.add_argument("--intent", choices=vocabulary_module.INTENT_VALUES, help="new intent")
    p_set.add_argument(
        "--parent", metavar="ID", help="new parent plan id; rejected if it would create a cycle"
    )
    p_set.add_argument("--clear-parent", action="store_true", help="clear parent plan id")
    p_set.add_argument(
        "--project", help="new project; '.' resolves to the current directory's name"
    )
    p_set.add_argument("--clear-project", action="store_true", help="clear project")
    p_set.add_argument("--add-tag", metavar="TAG", action="append", help="add a tag; repeatable")
    p_set.add_argument(
        "--remove-tag", metavar="TAG", action="append", help="remove a tag; repeatable"
    )
    p_set.add_argument("--clear-tags", action="store_true", help="remove all tags")
    p_set.add_argument(
        "--dry-run", action="store_true", help="report what would change, without writing"
    )

    p_backfill = _add_command(
        sub,
        "backfill",
        "derive and write missing frontmatter",
        description=(
            "Derive status, intent, created, parent, and project for plans missing "
            "them, and write the frontmatter block. To fix one plan, use --only or "
            "`pentimento set`; --rederive recomputes derived fields across the whole "
            "corpus and cannot change a pinned status."
        ),
        epilog="Examples:\n  pentimento backfill --dry-run",
    )
    p_backfill.add_argument("--dry-run", action="store_true", help="report without writing")
    p_backfill.add_argument("--quiet", action="store_true", help="suppress changed-id output")
    p_backfill.add_argument(
        "--only",
        metavar="ID",
        action="append",
        help="restrict writes to this plan id; repeatable",
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
            "Read a Claude Code PostToolUse payload on stdin and backfill frontmatter "
            "for the plan just written, deriving status capped at partial. Wiring is "
            "in docs/integrations.md."
        ),
    )

    _add_command(
        sub,
        "index",
        "write INDEX.md into the plans directory",
        description=(
            "Write INDEX.md into the plans directory: one linked row per plan, grouped by status."
        ),
    )

    p_check = _add_command(
        sub,
        "check",
        "validate lineage and vocabulary; exits 1 on any finding",
        description=(
            "Validate lineage and vocabulary across the corpus. Exits 1 when "
            "anything is found; finding codes are in docs/troubleshooting.md."
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
    p_history.add_argument("id", help="plan id (filename stem)")
    _add_format_args(p_history)

    p_completion = _add_command(
        sub,
        "completion",
        "print a shell integration script",
        description=(
            "Print an integration script for SHELL to stdout. Source it, or eval its "
            "output, to get tab completion for subcommands, flags, and plan ids."
        ),
        epilog=("Examples:\n  pentimento completion bash\n  pentimento completion zsh"),
    )
    p_completion.add_argument("shell", choices=completion.SHELLS, help="bash, zsh, or fish")

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


def _apply_limit(plans, args):
    """Keep the N rows nearest the prompt: the tail under `--order asc`, the head under `desc`."""
    if args.limit is None:
        return plans
    if args.limit == 0:
        return []
    return plans[: args.limit] if _sort_descending(args) else plans[-args.limit :]


def _render_table_or_empty(corpus_plans, plans, args, render):
    """Shared `list`/`tree` table-format tail: empty-corpus hint, empty-filter
    summary, or `render(on_color, unicode_ok, short_ids)` followed by the
    filtered/total summary line."""
    if not corpus_plans:
        print(_empty_corpus_hint(), file=sys.stderr)
        return 0
    if not plans:
        on_color = style.enabled(sys.stdout, args.color)
        print(style.paint(counts.summary(0, len(corpus_plans)), style.DIM, on=on_color))
        return 0
    on_color = style.enabled(sys.stdout, args.color)
    unicode_ok = style.unicode_enabled(sys.stdout, args.ascii)
    short_ids = shortid.shorten(p.id for p in corpus_plans)
    print(render(on_color, unicode_ok, short_ids))
    print()
    print(style.paint(counts.summary(len(plans), len(corpus_plans)), style.DIM, on=on_color))
    return 0


def _columns_selection(args):
    """The `--columns` selection, or `PENTIMENTO_COLUMNS` when the flag is
    absent. Returns `(selection, error)`; `error` is a ready-to-print message
    when the flag or the environment variable is invalid."""
    if args.columns is not None:
        return args.columns, None
    env_value = os.environ.get("PENTIMENTO_COLUMNS")
    if not env_value:
        return None, None
    try:
        return _column_spec(env_value), None
    except argparse.ArgumentTypeError as exc:
        return None, f"PENTIMENTO_COLUMNS: {exc}"


def cmd_list(args) -> int:
    if args.columns is not None and args.format != formats.TABLE:
        print("--columns only applies to --format table", file=sys.stderr)
        return 1

    corpus_plans = corpus.load_all()
    plans = _apply_filters(corpus_plans, args)
    if plans is None:
        return 1
    plans = sorted(plans, key=_sort_key(args), reverse=_sort_descending(args))
    plans = _apply_limit(plans, args)
    if args.format != formats.TABLE:
        formats.emit(
            [record_module.as_dict(p) for p in plans], args.format, sys.stdout, record_module.FIELDS
        )
        return 0

    selection, error = _columns_selection(args)
    if error is not None:
        print(error, file=sys.stderr)
        return 1
    pin = (SORT_COLUMNS[args.sort],)
    return _render_table_or_empty(
        corpus_plans,
        plans,
        args,
        lambda on_color, unicode_ok, short_ids: listing.render(
            plans, on_color, unicode_ok, short_ids=short_ids, selection=selection, pin=pin
        ),
    )


def cmd_tree(args) -> int:
    corpus_plans = corpus.load_all()
    plans = _apply_filters(corpus_plans, args)
    if plans is None:
        return 1
    key, reverse = _sort_key(args), _sort_descending(args)
    if args.format != formats.TABLE:
        records = tree_module.as_records(plans, key=key, reverse=reverse)
        formats.emit(records, args.format, sys.stdout, record_module.FIELDS)
        return 0
    return _render_table_or_empty(
        corpus_plans,
        plans,
        args,
        lambda on_color, unicode_ok, short_ids: tree_module.render_grouped(
            plans,
            on_color,
            key=key,
            reverse=reverse,
            glyphs=style.glyphs(unicode_ok),
            unicode_ok=unicode_ok,
            short_ids=short_ids,
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


def _show_field_groups(target):
    """Lists of (key, value, codes) per semantic group, skipping empty groups."""
    values = dict(target.fields)
    values["id"] = target.id
    values["path"] = _display_path(target.path)
    values["source"] = target.source
    values["modified"] = times_module.local_stamp(target.modified)
    grouped_keys = {key for _, keys in _HEADER_GROUPS for key in keys}
    for _, keys in _HEADER_GROUPS:
        group = []
        for key in keys:
            if key not in values:
                continue
            value = values[key]
            if key == "status":
                codes = style.STATUS_CODES.get(value, ())
            elif key == "intent":
                codes = style.INTENT_CODES.get(value, ())
            else:
                codes = ()
            group.append((key, value, codes))
        if group:
            yield group
    extra = [key for key in target.fields if key not in grouped_keys]
    if extra:
        yield [(key, values[key], ()) for key in extra]


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
        print(_no_such_plan(plans, args.id), file=sys.stderr)
        return 1
    if args.format != formats.TABLE:
        formats.emit([record_module.as_dict(target)], args.format, sys.stdout, record_module.FIELDS)
        return 0

    on_color = style.enabled(sys.stdout, args.color)
    unicode_ok = style.unicode_enabled(sys.stdout, args.ascii)
    width = min(style.terminal_width(), markdown.MAX_WIDTH)

    header = _show_header(target, width, on_color=on_color)
    body_text = plan_module.body_below_title(target.body)
    body = markdown.render(body_text, on_color=on_color, unicode_ok=unicode_ok, width=width)
    if _should_page(args, len(header) + len(body)):
        pager.page(header + body)
        return 0

    limit = None
    if sys.stdout.isatty() and not args.full:
        limit = max(style.terminal_height() - len(header) - 2, markdown.MIN_BODY_LINES)
    hint = f"pentimento show {args.id} --full"
    body = markdown.clip(body, limit, hint, on_color=on_color, unicode_ok=unicode_ok)
    for line in header + body:
        print(line)
    return 0


def _apply_tag_edits(target, args) -> str | None:
    """Apply --clear-tags, --remove-tag, --add-tag in order.

    Existing tags are normalized on any edit, so a hand-written `Auth`
    self-heals the next time `set` touches tags. Each `--add-tag` value must
    already pass `tags.is_valid` as given -- normalize only lowercases, it
    doesn't fix a malformed tag -- so this mutates `target.fields["tags"]`
    on success, or returns the offending value without mutating anything.
    """
    current = {tags_module.normalize(t) for t in target.tags}
    if args.clear_tags:
        current = set()
    for tag in args.remove_tag or ():
        current.discard(tags_module.normalize(tag))
    for tag in args.add_tag or ():
        if not tags_module.is_valid(tag):
            return tag
        current.add(tags_module.normalize(tag))
    if current:
        target.fields["tags"] = tags_module.render(sorted(current))
    else:
        target.fields.pop("tags", None)
    return None


def _describe_field_changes(before: dict, after: dict) -> list[str]:
    changes = []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        if old is None:
            changes.append(f"{key}: set to {new!r}")
        elif new is None:
            changes.append(f"{key}: cleared (was {old!r})")
        else:
            changes.append(f"{key}: {old!r} -> {new!r}")
    return changes


def cmd_set(args) -> int:
    plans = corpus.load_all()
    target = corpus.by_id(plans, args.id)
    if target is None:
        print(_no_such_plan(plans, args.id), file=sys.stderr)
        return 1

    before_fields = dict(target.fields)

    if args.clear_project:
        target.fields.pop("project", None)
    elif args.project is not None:
        resolved = _resolve_project(args.project)
        if not frontmatter.is_valid_value(resolved):
            print(f"invalid project: {resolved!r}", file=sys.stderr)
            return 1
        target.fields["project"] = resolved

    if args.clear_parent:
        target.fields.pop("parent", None)
    elif args.parent is not None:
        parent_plan = corpus.by_id(plans, args.parent)
        if parent_plan is None:
            print(_no_such_plan(plans, args.parent), file=sys.stderr)
            return 1
        fields_by_id = {p.id: p.fields for p in plans}
        fields_by_id[target.id] = {**target.fields, "parent": parent_plan.id}
        if backfill_module._resolves_to_cycle(target.id, parent_plan.id, fields_by_id):
            print(f"pentimento: --parent {parent_plan.id} would create a cycle", file=sys.stderr)
            return 1
        target.fields["parent"] = parent_plan.id

    if args.clear_tags or args.remove_tag or args.add_tag:
        invalid = _apply_tag_edits(target, args)
        if invalid is not None:
            print(f"invalid tag: {invalid!r}", file=sys.stderr)
            return 1

    for field in ("status", "intent"):
        value = getattr(args, field, None)
        if value is not None:
            target.fields[field] = value

    if args.status is not None:
        target.fields["pinned"] = "true"
    if args.unpin:
        target.fields.pop("pinned", None)

    changes = _describe_field_changes(before_fields, target.fields)
    if not changes:
        print("no changes")
        return 0
    suffix = " (dry run)" if args.dry_run else ""
    for change in changes:
        print(f"{change}{suffix}")
    if args.dry_run:
        return 0
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
    )


def cmd_hook(_args) -> int:
    # PostToolUse treats exit 2 as blocking and surfaces other non-zero exits, so a
    # crash here would visibly interrupt every session -- fail closed instead.
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
    duplicates = sorted({p.id for p in check_module.duplicate_ids(plans)})
    if duplicates:
        print(
            f"pentimento: duplicate plan id(s): {', '.join(duplicates)} -- "
            "run `pentimento check` and resolve before backfilling",
            file=sys.stderr,
        )
        return 1

    changed = _backfill(
        dry_run=args.dry_run,
        rederive=args.rederive,
        recreate=args.recreate,
        only=set(args.only) if args.only else None,
        sessions=sessions,
        plans=plans,
    )
    if not args.quiet:
        for plan_id in changed:
            print(plan_id)
        if not changed:
            print("no changes")
        elif args.dry_run:
            print(f"{counts.plural(len(changed), 'plan')} would change (dry run)")
        else:
            print(f"{counts.plural(len(changed), 'plan')} updated")
    return 0


def cmd_index(_args) -> int:
    plans = corpus.load_all()
    index_module.write(plans, corpus.plans_directory())
    print(f"{counts.plural(len(plans), 'plan')} indexed")
    return 0


def cmd_check(args) -> int:
    sessions = sessions_module.load()
    touches = touches_module.load()
    skips = []
    plans = corpus.load_all(sessions=sessions, skips=skips)
    findings = check_module.run(plans, sessions, touches, skips=skips)
    if args.format == formats.TABLE:
        on_color = style.enabled(sys.stdout, args.color)
        unicode_ok = style.unicode_enabled(sys.stdout, args.ascii)
        if findings:
            columns = (
                table.Column("CODE", drop=1),
                table.Column("PLAN"),
                table.Column("MESSAGE", flex=2, comfort=40, floor=20),
            )
            short = shortid.shorten(p.id for p in plans)
            rows = [
                ((f.code, (style.RED,)), (short.get(f.plan_id, f.plan_id), ()), (f.message, ()))
                for f in findings
            ]
            width = style.terminal_width()
            print(
                table.render(columns, rows, on_color=on_color, unicode_ok=unicode_ok, width=width)
            )
        plan_count = counts.plural(len(plans), "plan")
        finding_count = counts.plural(len(findings), "finding")
        print(f"{plan_count} checked, {finding_count}")
    else:
        columns = tuple(f.name for f in dataclasses.fields(check_module.Finding))
        formats.emit([dataclasses.asdict(f) for f in findings], args.format, sys.stdout, columns)
    return 1 if findings else 0


def cmd_history(args) -> int:
    plans = corpus.load_all()
    target = corpus.by_id(plans, args.id)
    if target is None:
        print(_no_such_plan(plans, args.id), file=sys.stderr)
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
        print(history_module.EMPTY_MESSAGE.format(plan_id=target.id))
        return 0
    on_color = style.enabled(sys.stdout, args.color)
    unicode_ok = style.unicode_enabled(sys.stdout, args.ascii)
    print(history_module.render(target.id, plan_touches, on_color, unicode_ok))
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


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "__complete":
        return completion.complete(argv[1:])
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"pentimento: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
