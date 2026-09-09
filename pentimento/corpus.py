"""Load and resolve the plan directory."""

from __future__ import annotations

import os
from pathlib import Path

from pentimento import plan as plan_module
from pentimento import sessions as sessions_module


def plans_directory() -> Path:
    return Path(os.environ.get("AGENT_PLANS_DIR", str(Path.home() / ".claude" / "plans")))


def load_all(directory: Path | None = None, sessions: dict | None = None) -> list[plan_module.Plan]:
    directory = directory or plans_directory()
    if sessions is None:
        sessions = sessions_module.load()
    paths = sorted(p for p in directory.glob("*.md") if plan_module.is_plan_file(p))
    return [plan_module.load(p, sessions) for p in paths]


def by_id(plans: list[plan_module.Plan], plan_id: str) -> plan_module.Plan | None:
    stem = Path(plan_id).stem
    for candidate in plans:
        if candidate.id == stem:
            return candidate
    return None
