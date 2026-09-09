"""Load and resolve the plan directory."""

from __future__ import annotations

import os
from pathlib import Path

from pentimento import plan as plan_module
from pentimento import sessions as sessions_module
from pentimento import sources as sources_module


def plans_directory() -> Path:
    return Path(os.environ.get("AGENT_PLANS_DIR", str(Path.home() / ".claude" / "plans")))


def load_all(directory: Path | None = None, sessions: dict | None = None) -> list[plan_module.Plan]:
    """Load every plan across all sources.

    `directory`, when given, overrides discovery entirely with a single
    Claude-style directory -- the shape callers and tests relied on before
    Cursor discovery existed.
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
    stem = Path(plan_id).stem
    for candidate in plans:
        if candidate.id == stem:
            return candidate
    return None
