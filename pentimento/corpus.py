"""Load and resolve the plan directory."""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

from pentimento import backfill, cursor_sessions, shortid
from pentimento import plan as plan_module
from pentimento import sessions as sessions_module
from pentimento import sources as sources_module
from pentimento import touches as touches_module


def plans_directory() -> Path:
    return sources_module.claude_source().directories[0]


def load_all(
    directory: Path | None = None,
    sessions: dict | None = None,
    skips: list | None = None,
) -> list[plan_module.Plan]:
    """Load every plan across all sources.

    `directory`, when given, overrides discovery entirely with a single
    Claude-style directory. A file that raises `OSError` (unreadable,
    dangling symlink, a directory named `*.md`, ...) is skipped rather than
    crashing the whole corpus; one line goes to stderr per skip, and the
    `(source, path, error)` triple is appended to `skips` when given, so
    `pentimento check` can also report it.
    """
    if sessions is None:
        sessions = sessions_module.load()
    if directory is not None:
        source = sources_module.directory_source(directory)
        pairs = [(source.name, p) for p in sources_module.files(source)]
    else:
        pairs = sources_module.discover()
    plans = []
    for name, path in pairs:
        try:
            plans.append(plan_module.load(path, sessions, source=name))
        except OSError as exc:
            print(f"pentimento: skipping unreadable plan {path}: {exc}", file=sys.stderr)
            if skips is not None:
                skips.append((name, path, exc))
    return plans


def with_cursor(plans: list[plan_module.Plan], sessions: dict) -> dict:
    """`sessions` plus the Cursor sessions of `plans`, which need the plans loaded first."""
    return {**sessions, **cursor_sessions.load(plans)}


def load_with_sessions(skips: list | None = None) -> tuple[list[plan_module.Plan], dict]:
    """Every plan and the sessions that describe them, Claude Code and Cursor alike."""
    claude_sessions = sessions_module.load()
    plans = load_all(sessions=claude_sessions, skips=skips)
    return plans, with_cursor(plans, claude_sessions)


def load_derived(skips: list | None = None) -> tuple[list[plan_module.Plan], dict, dict]:
    """Every plan with `derived` set to what `backfill` would persist, plus sessions and touches."""
    plans, sessions = load_with_sessions(skips)
    touches = touches_module.load()
    derived = backfill.derive_all(plans, sessions, touches, rederive=False, recreate=False, max_status=None)
    for plan in plans:
        plan.derived = derived[plan.path]
    return plans, sessions, touches


def _only(matched: list[plan_module.Plan]) -> plan_module.Plan | None:
    return matched[0] if len(matched) == 1 else None


def by_id(plans: list[plan_module.Plan], plan_id: str) -> plan_module.Plan | None:
    """The plan `plan_id` names, or `None` when nothing or several plans match.

    Tried in order: full path, exact filename, full id, filename stem, then a
    short id. A tier that matches several plans (the same id in two sources)
    resolves nothing rather than picking one.
    """
    target = plan_id
    if target.endswith(plan_module.CURSOR_SUFFIX):
        target = target[: -len(plan_module.CURSOR_SUFFIX)]
    elif target.endswith(plan_module.PLAN_SUFFIX):
        target = target[: -len(plan_module.PLAN_SUFFIX)]
    stem = Path(target).stem

    tiers = (
        [c for c in plans if str(c.path) == plan_id],
        [c for c in plans if c.path.name == plan_id],
        [c for c in plans if c.id == plan_id],
        [c for c in plans if c.id in (target, stem)],
    )
    for matched in tiers:
        if matched:
            return _only(matched)

    found = shortid.matches([p.id for p in plans], plan_id)
    return _only([c for c in plans if c.id in found])


def ambiguous(plans: list[plan_module.Plan], wanted: str) -> list[str]:
    """Full ids when `wanted` matched more than one plan."""
    ids = [p.id for p in plans]
    found = list(dict.fromkeys(shortid.matches(ids, wanted)))
    if len(found) == 1 and ids.count(found[0]) > 1:
        return [f"{p.id} ({p.path})" for p in plans if p.id == found[0]]
    return found if len(found) > 1 else []


def suggest(plans: list[plan_module.Plan], wanted: str) -> list[str]:
    """Close-match ids for a `wanted` id that didn't resolve, for a hint."""
    ids = list(dict.fromkeys(p.id for p in plans))
    shorts = shortid.shorten(ids)
    close = difflib.get_close_matches(wanted, [*ids, *shorts.values()])
    return list(dict.fromkeys(close))
