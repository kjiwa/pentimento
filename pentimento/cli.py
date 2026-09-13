"""Argument parsing and command dispatch."""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import importlib.metadata
import sys

from pentimento import backfill as backfill_module
from pentimento import check as check_module
from pentimento import corpus, counts, formats, frontmatter, listing, style
from pentimento import index as index_module
from pentimento import plan as plan_module
from pentimento import record as record_module
from pentimento import sessions as sessions_module
from pentimento import sources as sources_module
from pentimento import tags as tags_module
from pentimento import times as times_module
from pentimento import tree as tree_module
from pentimento import vocabulary as vocabulary_module

STARRED_INTENTS = ("active", "queued")
SORT_CHOICES = ("modified", "created", "id", "status", "title")
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


def _add_filter_args(parser):
    parser.add_argument("--status", choices=vocabulary_module.STATUS_ORDER, help="filter by status")
    parser.add_argument("--intent", choices=vocabulary_module.INTENT_VALUES, help="filter by intent")
    parser.add_argument("--project", help="filter by project")
    parser.add_argument("--source", choices=sources_module.SOURCE_NAMES, help="filter by source")
    parser.add_argument("--starred", action="store_true", help="only active/queued intent")
    parser.add_argument(
        "--tag", action="append", help="filter by tag; repeatable, every given tag must be present"
    )


def _add_sort_args(parser):
    parser.add_argument("--sort", choices=SORT_CHOICES, default="modified", help="sort order (default: modified)")
    parser.add_argument("--order", choices=("asc", "desc"), default="asc", help="sort direction (default: asc)")


def _sort_key(args):
    return SORT_KEYS[args.sort]


def _sort_descending(args) -> bool:
    return args.order == "desc"


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
    parser.add_argument(
        "--ascii",
        action="store_true",
        help="force ASCII box-drawing glyphs, even on a UTF-8 terminal",
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
    if args.tag:
        wanted = {tags_module.normalize(t) for t in args.tag}
        plans = [p for p in plans if wanted <= {tags_module.normalize(t) for t in p.tags}]
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

    p_tree = sub.add_parser("tree", help="lineage tree, grouped by project")
    _add_filter_args(p_tree)
    _add_format_args(p_tree)
    _add_sort_args(p_tree)

    p_show = sub.add_parser("show", help="H1, frontmatter, and Progress block")
    p_show.add_argument("id", help="plan id (filename stem)")
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
    p_backfill.add_argument("--recreate", action="store_true", help="recompute created from local time too")

    sub.add_parser("index", help="write INDEX.md into the plans directory")

    p_check = sub.add_parser("check", help="validate lineage and vocabulary; exits 1 on any finding")
    _add_format_args(p_check)

    return parser


def _no_such_plan(plans, wanted: str) -> str:
    message = f"no such plan: {wanted}"
    close = corpus.suggest(plans, wanted)
    if close:
        message += f" -- did you mean: {', '.join(close)}?"
    return message


def _empty_corpus_hint() -> str:
    directories = []
    for source in (sources_module.claude_source(), sources_module.cursor_source()):
        directories.extend(str(d) for d in source.directories)
    return "no plans found; searched: " + ", ".join(directories)


def cmd_list(args) -> int:
    corpus_plans = corpus.load_all()
    plans = sorted(_apply_filters(corpus_plans, args), key=_sort_key(args), reverse=_sort_descending(args))
    if args.format != "table":
        formats.emit([record_module.as_dict(p) for p in plans], args.format, sys.stdout, record_module.FIELDS)
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
    print(listing.render(plans, on_color, unicode_ok))
    print()
    print(style.paint(counts.summary(len(plans), len(corpus_plans)), style.DIM, on=on_color))
    return 0


def cmd_tree(args) -> int:
    corpus_plans = corpus.load_all()
    plans = _apply_filters(corpus_plans, args)
    key, reverse = _sort_key(args), _sort_descending(args)
    if args.format != "table":
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
    print(tree_module.render_grouped(plans, on_color, key=key, reverse=reverse, glyphs=glyphs, unicode_ok=unicode_ok))
    print()
    print(style.paint(counts.summary(len(plans), len(corpus_plans)), style.DIM, on=on_color))
    return 0


def cmd_show(args) -> int:
    plans = corpus.load_all()
    target = corpus.by_id(plans, args.id)
    if target is None:
        print(_no_such_plan(plans, args.id), file=sys.stderr)
        return 1
    if args.format == "table":
        on_color = style.enabled(sys.stdout, args.color)
        print(style.paint(f"# {target.title}", style.BOLD, on=on_color))
        print()
        ordered = [k for k in frontmatter.FIELD_ORDER if k in target.fields]
        remaining = [k for k in target.fields if k not in frontmatter.FIELD_ORDER]
        for key in ordered + remaining:
            value = target.fields[key]
            if key == "status":
                value = style.paint(value, *style.STATUS_CODES.get(value, ()), on=on_color)
            elif key == "intent":
                value = style.paint(value, *style.INTENT_CODES.get(value, ()), on=on_color)
            print(f"{style.paint(f'{key}:', style.DIM, on=on_color)} {value}")
        print(f"{style.paint('source:', style.DIM, on=on_color)} {target.source}")
        print(f"{style.paint('modified:', style.DIM, on=on_color)} {times_module.local_stamp(target.modified)}")
        print()
        section = _progress_block(target.body)
        if section:
            print(section)
    else:
        formats.emit([record_module.as_dict(target)], args.format, sys.stdout, record_module.FIELDS)
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
            else:
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
    plans = corpus.load_all(sessions=sessions)
    findings = check_module.run(plans, sessions)
    if args.format == "table":
        on_color = style.enabled(sys.stdout, args.color)
        unicode_ok = style.unicode_enabled(sys.stdout, args.ascii)
        if findings:
            code_width = max(style.display_width(f.code) for f in findings)
            width = style.terminal_width()
            for finding in findings:
                code = style.paint(finding.code.ljust(code_width), style.RED, on=on_color)
                message_width = max(width - code_width - 1, 1)
                message = style.truncate(finding.message, message_width, unicode_ok=unicode_ok)
                print(f"{code} {message}")
        print(f"{counts.plural(len(plans), 'plan')} checked, {counts.plural(len(findings), 'finding')}")
    else:
        columns = tuple(f.name for f in dataclasses.fields(check_module.Finding))
        formats.emit([dataclasses.asdict(f) for f in findings], args.format, sys.stdout, columns)
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
