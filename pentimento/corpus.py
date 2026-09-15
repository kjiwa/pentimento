"""Load and resolve the plan directory."""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

from pentimento import plan as plan_module
from pentimento import sessions as sessions_module
from pentimento import shortid
from pentimento import sources as sources_module


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


def by_id(plans: list[plan_module.Plan], plan_id: str) -> plan_module.Plan | None:
    for candidate in plans:
        if candidate.id == plan_id:
            return candidate

    target = plan_id
    if target.endswith(plan_module.CURSOR_SUFFIX):
        target = target[: -len(plan_module.CURSOR_SUFFIX)]
    elif target.endswith(plan_module.PLAN_SUFFIX):
        target = target[: -len(plan_module.PLAN_SUFFIX)]
    target_stem = Path(target).stem

    for candidate in plans:
        if candidate.id in (target, target_stem) or candidate.path.name == plan_id:
            return candidate

    found = shortid.matches([p.id for p in plans], plan_id)
    if len(found) == 1:
        for candidate in plans:
            if candidate.id == found[0]:
                return candidate
    return None


def ambiguous(plans: list[plan_module.Plan], wanted: str) -> list[str]:
    """Full ids when `wanted` is a short id that matched more than one plan."""
    found = shortid.matches([p.id for p in plans], wanted)
    return found if len(found) > 1 else []


def suggest(plans: list[plan_module.Plan], wanted: str) -> list[str]:
    """Close-match ids for a `wanted` id that didn't resolve, for a hint."""
    return difflib.get_close_matches(wanted, [p.id for p in plans])
