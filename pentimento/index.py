"""Render INDEX.md: one row per plan, grouped by status."""

from __future__ import annotations

from pentimento import plan as plan_module

STATUS_ORDER = ("not-started", "partial", "complete", "superseded", "unknown")


def render(plans: list[plan_module.Plan]) -> str:
    lines = ["# Plan index", ""]
    by_status: dict[str, list[plan_module.Plan]] = {}
    for p in plans:
        by_status.setdefault(p.status, []).append(p)

    remaining = sorted(status for status in by_status if status not in STATUS_ORDER)
    for status in (*STATUS_ORDER, *remaining):
        group = sorted(by_status.get(status, []), key=lambda p: p.id)
        if not group:
            continue
        lines.append(f"## {status}")
        lines.append("")
        for p in group:
            lines.append(f"- [{p.title}]({p.path.name}) (`{p.id}`)")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write(plans: list[plan_module.Plan], directory) -> None:
    (directory / "INDEX.md").write_text(render(plans))
