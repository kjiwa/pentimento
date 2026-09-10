"""Render INDEX.md: one row per plan, grouped by status."""

from __future__ import annotations

import os
from pathlib import Path

from pentimento import plan as plan_module
from pentimento import vocabulary as vocabulary_module


def _link_target(plan_path: Path, base_dir: Path | None) -> str:
    if base_dir is None:
        return plan_path.name
    try:
        return os.path.relpath(plan_path, base_dir)
    except ValueError:
        return str(plan_path)


def render(plans: list[plan_module.Plan], base_dir: Path | None = None) -> str:
    lines = ["# Plan index", ""]
    by_status: dict[str, list[plan_module.Plan]] = {}
    for p in plans:
        by_status.setdefault(p.status, []).append(p)

    remaining = sorted(status for status in by_status if status not in vocabulary_module.STATUS_ORDER)
    for status in (*vocabulary_module.STATUS_ORDER, *remaining):
        group = sorted(by_status.get(status, []), key=lambda p: p.id)
        if not group:
            continue
        lines.append(f"## {status}")
        lines.append("")
        for p in group:
            target = _link_target(p.path, base_dir)
            lines.append(f"- [{p.title}]({target}) (`{p.id}`)")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write(plans: list[plan_module.Plan], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "INDEX.md").write_text(render(plans, base_dir=directory), encoding="utf-8")
