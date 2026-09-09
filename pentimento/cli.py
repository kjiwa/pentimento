"""Argument parsing and command dispatch."""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import sys

from pentimento import backfill as backfill_module
from pentimento import check as check_module
from pentimento import corpus, formats, listing, style
from pentimento import index as index_module
from pentimento import plan as plan_module
from pentimento import record as record_module
from pentimento import sessions as sessions_module
from pentimento import sources as sources_module
from pentimento import times as times_module
from pentimento import tree as tree_module

STARRED_INTENTS = ("active", "queued")
SORT_CHOICES = ("modified", "created", "id", "status", "title")
DATE_SORTS = ("modified", "created")
_MIN_INSTANT = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)

SORT_KEYS = {
    "modified": lambda p: p.modified,
    "created": lambda p: p.created_at or _MIN_INSTANT,
    "id": lambda p: p.id,
    "status": lambda p: p.status,
    "title": lambda p: p.title,
}


def _add_filter_args(parser):
    parser.add_argument("--status", choices=index_module.STATUS_ORDER, help="filter by status")
    parser.add_argument("--intent", choices=check_module.INTENT_VALUES, help="filter by intent")
    parser.add_argument("--project", help="filter by project")
    parser.add_argument("--source", choices=sources_module.SOURCE_NAMES, help="filter by source")
    parser.add_argument("--starred", action="store_true", help="only active/queued intent")


def _add_sort_args(parser):
    parser.add_argument("--sort", choices=SORT_CHOICES, default="modified", help="sort order (default: modified)")
    parser.add_argument("--reverse", action="store_true", help="reverse the sort order")


def _sort_key(args):
    return SORT_KEYS[args.sort]


def _sort_reverse(args) -> bool:
    default_reverse = args.sort in DATE_SORTS
    return not default_reverse if args.reverse else default_reverse


def _add_format_args(parser):
    parser.add_argument(
        "--format",
        choices=("table", "json", "tsv"),
        default="table",
        help="output format (default: table)",
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="colour policy (default: auto)",
    )


def _apply_filters(plans, args):
    if args.status:
        plans = [p for p in plans if p.status == args.status]
    if args.intent:
        plans = [p for p in plans if p.intent == args.intent]
    if args.project:
        plans = [p for p in plans if p.project == args.project]
    if args.source:
        plans = [p for p in plans if p.source == args.source]
    if args.starred:
        plans = [p for p in plans if p.intent in STARRED_INTENTS]
    return plans


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pentimento")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="flat table of plans")
    _add_filter_args(p_list)
    _add_format_args(p_list)
    _add_sort_args(p_list)

    p_tree = sub.add_parser("tree", help="lineage tree, grouped by project")
    _add_filter_args(p_tree)
    _add_format_args(p_tree)
    _add_sort_args(p_tree)

    p_show = sub.add_parser("show", help="H1, frontmatter, and Progress block")
    p_show.add_argument("id", help="plan id (filename stem)")
    _add_format_args(p_show)

    p_set = sub.add_parser("set", help="rewrite frontmatter in place")
    p_set.add_argument("id", help="plan id (filename stem)")
    p_set.add_argument("--status", choices=index_module.STATUS_ORDER, help="new status")
    p_set.add_argument("--intent", choices=check_module.INTENT_VALUES, help="new intent")
    p_set.add_argument("--parent", help="new parent plan id")
    p_set.add_argument("--project", help="new project")

    p_backfill = sub.add_parser("backfill", help="derive and write missing frontmatter")
    p_backfill.add_argument("--dry-run", action="store_true", help="report without writing")
    p_backfill.add_argument("--quiet", action="store_true", help="suppress changed-id output")
    p_backfill.add_argument("--rederive", action="store_true", help="recompute derived fields")
    p_backfill.add_argument("--recreate", action="store_true", help="recompute created from local time too")

    sub.add_parser("index", help="write INDEX.md into the plans directory")

    p_check = sub.add_parser("check", help="validate lineage and vocabulary; exits 1 on any finding")
    _add_format_args(p_check)

    return parser


def cmd_list(args) -> int:
    plans = sorted(_apply_filters(corpus.load_all(), args), key=_sort_key(args), reverse=_sort_reverse(args))
    if args.format == "table":
        on_color = style.enabled(sys.stdout, args.color)
        print(listing.render(plans, on_color))
    else:
        formats.emit([record_module.as_dict(p) for p in plans], args.format, sys.stdout)
    return 0


def cmd_tree(args) -> int:
    plans = _apply_filters(corpus.load_all(), args)
    key, reverse = _sort_key(args), _sort_reverse(args)
    if args.format == "table":
        on_color = style.enabled(sys.stdout, args.color)
        print(tree_module.render_grouped(plans, on_color, key=key, reverse=reverse))
    else:
        formats.emit(tree_module.as_records(plans, key=key, reverse=reverse), args.format, sys.stdout)
    return 0


def cmd_show(args) -> int:
    plans = corpus.load_all()
    target = corpus.by_id(plans, args.id)
    if target is None:
        print(f"no such plan: {args.id}", file=sys.stderr)
        return 1
    if args.format == "table":
        print(f"# {target.title}")
        print()
        for key, value in target.fields.items():
            print(f"{key}: {value}")
        print(f"source: {target.source}")
        print(f"modified: {times_module.local_stamp(target.modified)}")
        print()
        section = _progress_block(target.body)
        if section:
            print(section)
    else:
        formats.emit([record_module.as_dict(target)], args.format, sys.stdout)
    return 0


def _progress_block(body: str) -> str | None:
    lines = body.split("\n")
    start = None
    for index, line in enumerate(lines):
        if line.strip().lower() == "## progress":
            start = index
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end]).rstrip()


def cmd_set(args) -> int:
    plans = corpus.load_all()
    target = corpus.by_id(plans, args.id)
    if target is None:
        print(f"no such plan: {args.id}", file=sys.stderr)
        return 1

    if args.parent is not None and corpus.by_id(plans, args.parent) is None:
        print(f"no such plan: {args.parent}", file=sys.stderr)
        return 1

    for field in ("status", "intent", "parent", "project"):
        value = getattr(args, field)
        if value is not None:
            target.fields[field] = value
    plan_module.save(target)
    return 0


def cmd_backfill(args) -> int:
    sessions = sessions_module.load()
    plans = corpus.load_all(sessions=sessions)
    changed = backfill_module.run(
        plans, sessions, dry_run=args.dry_run, rederive=args.rederive, recreate=args.recreate
    )
    if not args.quiet:
        for plan_id in changed:
            print(plan_id)
    return 0


def cmd_index(_args) -> int:
    plans = corpus.load_all()
    index_module.write(plans, corpus.plans_directory())
    return 0


def cmd_check(args) -> int:
    plans = corpus.load_all()
    findings = check_module.run(plans)
    if args.format == "table":
        for finding in findings:
            print(finding.message)
    else:
        formats.emit([dataclasses.asdict(f) for f in findings], args.format, sys.stdout)
    return 1 if findings else 0


COMMANDS = {
    "list": cmd_list,
    "tree": cmd_tree,
    "show": cmd_show,
    "set": cmd_set,
    "backfill": cmd_backfill,
    "index": cmd_index,
    "check": cmd_check,
}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
