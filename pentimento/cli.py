"""Argument parsing and command dispatch."""

from __future__ import annotations

import argparse
import sys

from pentimento import backfill as backfill_module
from pentimento import corpus
from pentimento import index as index_module
from pentimento import plan as plan_module
from pentimento import tree as tree_module

STARRED_INTENTS = ("active", "queued")


def _add_filter_args(parser):
    parser.add_argument("--status")
    parser.add_argument("--intent")
    parser.add_argument("--project")
    parser.add_argument("--starred", action="store_true")


def _apply_filters(plans, args):
    if args.status:
        plans = [p for p in plans if p.status == args.status]
    if args.intent:
        plans = [p for p in plans if p.intent == args.intent]
    if args.project:
        plans = [p for p in plans if p.project == args.project]
    if args.starred:
        plans = [p for p in plans if p.intent in STARRED_INTENTS]
    return plans


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pentimento")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="flat table of plans")
    _add_filter_args(p_list)

    p_tree = sub.add_parser("tree", help="lineage tree, grouped by project")
    _add_filter_args(p_tree)

    p_show = sub.add_parser("show", help="H1, frontmatter, and Progress block")
    p_show.add_argument("id")

    p_set = sub.add_parser("set", help="rewrite frontmatter in place")
    p_set.add_argument("id")
    p_set.add_argument("--status")
    p_set.add_argument("--intent")
    p_set.add_argument("--parent")
    p_set.add_argument("--project")

    p_backfill = sub.add_parser("backfill", help="derive and write missing frontmatter")
    p_backfill.add_argument("--dry-run", action="store_true")
    p_backfill.add_argument("--quiet", action="store_true")

    sub.add_parser("index", help="write INDEX.md into the plans directory")

    return parser


def cmd_list(args) -> int:
    plans = _apply_filters(corpus.load_all(), args)
    for p in sorted(plans, key=lambda p: p.id):
        print(f"{p.id}\t{p.status}\t{p.intent}\t{p.project or ''}\t{p.title}")
    return 0


def cmd_tree(args) -> int:
    plans = _apply_filters(corpus.load_all(), args)
    print(tree_module.render_grouped(plans))
    return 0


def cmd_show(args) -> int:
    plans = corpus.load_all()
    target = corpus.by_id(plans, args.id)
    if target is None:
        print(f"no such plan: {args.id}", file=sys.stderr)
        return 1
    print(f"# {target.title}")
    print()
    for key, value in target.fields.items():
        print(f"{key}: {value}")
    print()
    section = _progress_block(target.body)
    if section:
        print(section)
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
    plans = corpus.load_all()
    changed = backfill_module.run(plans, dry_run=args.dry_run)
    if not args.quiet:
        for plan_id in changed:
            print(plan_id)
    return 0


def cmd_index(_args) -> int:
    plans = corpus.load_all()
    index_module.write(plans, corpus.plans_directory())
    return 0


COMMANDS = {
    "list": cmd_list,
    "tree": cmd_tree,
    "show": cmd_show,
    "set": cmd_set,
    "backfill": cmd_backfill,
    "index": cmd_index,
}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
