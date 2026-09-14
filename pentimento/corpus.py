"""Load and resolve the plan directory."""

from __future__ import annotations

import difflib
import os
from pathlib import Path

from pentimento import plan as plan_module
from pentimento import sessions as sessions_module
from pentimento import shortid
from pentimento import sources as sources_module


def plans_directory() -> Path:
    return Path(os.environ.get("AGENT_PLANS_DIR", str(Path.home() / ".claude" / "plans")))


def load_all(directory: Path | None = None, sessions: dict | None = None) -> list[plan_module.Plan]:
    """Load every plan across all sources.

    `directory`, when given, overrides discovery entirely with a single
    Claude-style directory.
    """
    if sessions is None:
        sessions = sessions_module.load()
    if directory is not None:
        source = sources_module.Source(name="claude", directories=[directory], suffix=".md", strip_suffix=".md")
        pairs = [(source.name, p) for p in sources_module.files(source)]
    else:
        pairs = sources_module.discover()
    return [plan_module.load(path, sessions, source=name) for name, path in pairs]


def by_id(plans: list[plan_module.Plan], plan_id: str) -> plan_module.Plan | None:
    for candidate in plans:
        if candidate.id == plan_id:
            return candidate

    target = plan_id
    if target.endswith(".plan.md"):
        target = target[: -len(".plan.md")]
    elif target.endswith(".md"):
        target = target[: -len(".md")]
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
