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
from pentimento import (
    corpus,
    counts,
    formats,
    frontmatter,
    listing,
    markdown,
    shortid,
    style,
    table,
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
_UNRANKED_STATUS = len(vocabulary_module.STATUS_ORDER)


def _status_rank(status: str) -> int:
    try:
        return vocabulary_module.STATUS_ORDER.index(status)
    except ValueError:
        return _UNRANKED_STATUS


SORT_KEYS = {
    "modified": lambda p: p.modified,
    "created": lambda p: p.created_at or _MIN_INSTANT,
    "id": lambda p: p.id,
    "status": lambda p: _status_rank(p.status),
    "title": lambda p: p.title,
}
SORT_CHOICES = tuple(SORT_KEYS)

_ORDER_ASC, _ORDER_DESC = "asc", "desc"
ORDER_CHOICES = (_ORDER_ASC, _ORDER_DESC)


def _add_filter_args(parser):
    parser.add_argument("--status", choices=vocabulary_module.STATUS_ORDER, help="filter by status")
    parser.add_argument(
        "--intent", choices=vocabulary_module.INTENT_VALUES, help="filter by intent"
    )
    parser.add_argument(
        "--project", help="filter by project; '.' resolves to the current directory's name"
    )
    parser.add_argument("--source", choices=sources_module.SOURCE_NAMES, help="filter by source")
    parser.add_argument("--starred", action="store_true", help="only active/queued intent")
    parser.add_argument(
        "--tag", action="append", help="filter by tag; repeatable, every given tag must be present"
    )
    parser.add_argument("--grep", help="filter by a case-insensitive regex over title and body")


def _add_sort_args(parser):
    parser.add_argument(
        "--sort", choices=SORT_CHOICES, default="modified", help="sort order (default: modified)"
    )
    parser.add_argument(
        "--order",
        choices=ORDER_CHOICES,
        default=_ORDER_ASC,
        help=f"sort direction (default: {_ORDER_ASC})",
    )


def _sort_key(args):
    return SORT_KEYS[args.sort]


def _sort_descending(args) -> bool:
    return args.order == _ORDER_DESC


def _add_format_args(parser):
    parser.add_argument(
        "--format",
        choices=formats.CHOICES,
        default=formats.TABLE,
        help=f"output format (default: {formats.TABLE})",
    )
    parser.add_argument(
        "--color",
        choices=style.COLOR_CHOICES,
        default="auto",
        help="colour policy (default: auto)",
    )
    parser.add_argument(
        "--ascii",
        action="store_true",
        help="force ASCII box-drawing glyphs, even on a UTF-8 terminal",
    )


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
            sys.exit(1)
        plans = [p for p in plans if pattern.search(p.title + p.body)]
    return plans


def _version() -> str:
    try:
        return importlib.metadata.version("pentimento")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pentimento")
    parser.add_argument("--version", action="version", version=f"pentimento {_version()}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="flat table of plans")
    _add_filter_args(p_list)
    _add_format_args(p_list)
    _add_sort_args(p_list)
    p_list.add_argument(
        "-n",
        "--limit",
        type=int,
        help="keep only the N rows nearest the prompt (before rendering or emitting)",
    )

    p_tree = sub.add_parser("tree", help="lineage tree, grouped by project")
    _add_filter_args(p_tree)
    _add_format_args(p_tree)
    _add_sort_args(p_tree)

    p_show = sub.add_parser("show", help="H1, frontmatter, and the rendered body")
    p_show.add_argument("id", help="plan id (filename stem)")
    p_show.add_argument("--full", action="store_true", help="print the whole body, unclipped")
    _add_format_args(p_show)

    p_set = sub.add_parser("set", help="rewrite frontmatter in place")
    p_set.add_argument("id", help="plan id (filename stem)")
    p_set.add_argument("--status", choices=vocabulary_module.STATUS_ORDER, help="new status")
    p_set.add_argument("--intent", choices=vocabulary_module.INTENT_VALUES, help="new intent")
    p_set.add_argument("--parent", help="new parent plan id")
    p_set.add_argument("--clear-parent", action="store_true", help="clear parent plan id")
    p_set.add_argument("--project", help="new project")
    p_set.add_argument("--add-tag", action="append", help="add a tag; repeatable")
    p_set.add_argument("--remove-tag", action="append", help="remove a tag; repeatable")
    p_set.add_argument("--clear-tags", action="store_true", help="remove all tags")

    p_backfill = sub.add_parser("backfill", help="derive and write missing frontmatter")
    p_backfill.add_argument("--dry-run", action="store_true", help="report without writing")
    p_backfill.add_argument("--quiet", action="store_true", help="suppress changed-id output")
    p_backfill.add_argument("--rederive", action="store_true", help="recompute derived fields")
    p_backfill.add_argument(
        "--recreate", action="store_true", help="recompute created from local time too"
    )

    sub.add_parser("hook", help="run as a Claude Code PostToolUse hook; reads the payload on stdin")

    sub.add_parser("index", help="write INDEX.md into the plans directory")

    p_check = sub.add_parser(
        "check", help="validate lineage and vocabulary; exits 1 on any finding"
    )
    _add_format_args(p_check)

    p_history = sub.add_parser("history", help="session-touch history for a plan")
    p_history.add_argument("id", help="plan id (filename stem)")
    _add_format_args(p_history)

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
    return plans[: args.limit] if _sort_descending(args) else plans[-args.limit :]


def cmd_list(args) -> int:
    corpus_plans = corpus.load_all()
    plans = sorted(
        _apply_filters(corpus_plans, args), key=_sort_key(args), reverse=_sort_descending(args)
    )
    plans = _apply_limit(plans, args)
    if args.format != formats.TABLE:
        formats.emit(
            [record_module.as_dict(p) for p in plans], args.format, sys.stdout, record_module.FIELDS
        )
        return 0
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
    print(listing.render(plans, on_color, unicode_ok, short_ids=short_ids))
    print()
    print(style.paint(counts.summary(len(plans), len(corpus_plans)), style.DIM, on=on_color))
    return 0


def cmd_tree(args) -> int:
    corpus_plans = corpus.load_all()
    plans = _apply_filters(corpus_plans, args)
    key, reverse = _sort_key(args), _sort_descending(args)
    if args.format != formats.TABLE:
        records = tree_module.as_records(plans, key=key, reverse=reverse)
        formats.emit(records, args.format, sys.stdout, record_module.FIELDS)
        return 0
    if not corpus_plans:
        print(_empty_corpus_hint(), file=sys.stderr)
        return 0
    if not plans:
        on_color = style.enabled(sys.stdout, args.color)
        print(style.paint(counts.summary(0, len(corpus_plans)), style.DIM, on=on_color))
        return 0
    on_color = style.enabled(sys.stdout, args.color)
    unicode_ok = style.unicode_enabled(sys.stdout, args.ascii)
    glyphs = style.glyphs(unicode_ok)
    short_ids = shortid.shorten(p.id for p in corpus_plans)
    print(
        tree_module.render_grouped(
            plans,
            on_color,
            key=key,
            reverse=reverse,
            glyphs=glyphs,
            unicode_ok=unicode_ok,
            short_ids=short_ids,
        )
    )
    print()
    print(style.paint(counts.summary(len(plans), len(corpus_plans)), style.DIM, on=on_color))
    return 0


FIELD_GUTTER = 3

_HEADER_GROUPS = (
    ("identity", ("id",)),
    ("state", ("status", "intent", "tags")),
    ("lineage", ("parent", "project")),
    ("provenance", ("created", "source", "modified")),
)


def _show_field_groups(target):
    """Lists of (key, value, codes) per semantic group, skipping empty groups."""
    values = dict(target.fields)
    values["id"] = target.id
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


def cmd_show(args) -> int:
    plans = corpus.load_all()
    target = corpus.by_id(plans, args.id)
    if target is None:
        print(_no_such_plan(plans, args.id), file=sys.stderr)
        return 1
    if args.format == formats.TABLE:
        on_color = style.enabled(sys.stdout, args.color)
        unicode_ok = style.unicode_enabled(sys.stdout, args.ascii)
        header_lines = 0

        def emit(text: str = "") -> None:
            nonlocal header_lines
            print(text)
            header_lines += 1

        width = min(style.terminal_width(), markdown.MAX_WIDTH)

        emit(style.paint(f"# {target.title}", style.BOLD, on=on_color))
        emit()
        for group in _show_field_groups(target):
            pairs = [
                style.render_cells(
                    [(f"{key}:", (style.DIM,)), (value, codes)], " ", on_color=on_color
                )
                for key, value, codes in group
            ]
            for line in _flow_pairs(pairs, width):
                emit(line)
        emit()

        body = plan_module.body_below_title(target.body)
        lines = markdown.render(body, on_color=on_color, unicode_ok=unicode_ok, width=width)
        limit = None
        if sys.stdout.isatty() and not args.full:
            limit = max(style.terminal_height() - header_lines - 2, markdown.MIN_BODY_LINES)
        hint = f"pentimento show {args.id} --full"
        for line in markdown.clip(lines, limit, hint, on_color=on_color, unicode_ok=unicode_ok):
            print(line)
    else:
        formats.emit([record_module.as_dict(target)], args.format, sys.stdout, record_module.FIELDS)
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


def cmd_set(args) -> int:
    plans = corpus.load_all()
    target = corpus.by_id(plans, args.id)
    if target is None:
        print(_no_such_plan(plans, args.id), file=sys.stderr)
        return 1

    if args.clear_parent or args.parent in ("", "none", "None"):
        target.fields.pop("parent", None)
    elif args.parent is not None:
        parent_plan = corpus.by_id(plans, args.parent)
        if parent_plan is None:
            print(_no_such_plan(plans, args.parent), file=sys.stderr)
            return 1
        target.fields["parent"] = parent_plan.id

    if args.clear_tags or args.remove_tag or args.add_tag:
        invalid = _apply_tag_edits(target, args)
        if invalid is not None:
            print(f"invalid tag: {invalid!r}", file=sys.stderr)
            return 1

    for field in ("status", "intent", "project"):
        value = getattr(args, field, None)
        if value is not None:
            if value == "" and field == "project":
                target.fields.pop(field, None)
            elif field == "project":
                target.fields[field] = _resolve_project(value)
            else:
                target.fields[field] = value

    if frontmatter.serialize(target.fields, target.body) == target.text:
        return 0
    plan_module.save(target, keep_mtime=True)
    return 0


def _backfill(
    *,
    dry_run: bool = False,
    rederive: bool = False,
    recreate: bool = False,
    derive_status: bool = True,
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
        derive_status=derive_status,
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
        changed = _backfill(only={target.id}, derive_status=False, sessions=sessions, plans=plans)
        for plan_id in changed:
            print(plan_id)
    except Exception:
        if os.environ.get("PENTIMENTO_DEBUG"):
            traceback.print_exc(file=sys.stderr)
    return 0


def cmd_backfill(args) -> int:
    changed = _backfill(dry_run=args.dry_run, rederive=args.rederive, recreate=args.recreate)
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
    plans = corpus.load_all(sessions=sessions)
    findings = check_module.run(plans, sessions, touches)
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
}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
