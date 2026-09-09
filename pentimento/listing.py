"""Human-facing `list` rendering: bold header, two-line records."""

from __future__ import annotations

from pentimento import style

GUTTER = 2


def _column_width(header: str, values: list[str]) -> int:
    return max(len(header), *(len(v) for v in values)) if values else len(header)


def render(plans, on_color: bool) -> str:
    plans = sorted(plans, key=lambda p: p.id)
    show_project = len({p.project for p in plans}) > 1

    status_width = _column_width("STATUS", [p.status for p in plans])
    intent_width = _column_width("INTENT", [p.intent for p in plans])
    project_width = _column_width("PROJECT", [p.project or "" for p in plans]) if show_project else 0

    header_cells = ["STATUS".ljust(status_width), "INTENT".ljust(intent_width)]
    if show_project:
        header_cells.append("PROJECT".ljust(project_width))
    header_cells.append("PLAN")
    header = style.paint((" " * GUTTER).join(header_cells), style.BOLD, on=on_color)

    indent = status_width + GUTTER + intent_width + GUTTER
    if show_project:
        indent += project_width + GUTTER

    lines = [header]
    for p in plans:
        cells = [
            style.paint(p.status.ljust(status_width), *style.STATUS_CODES.get(p.status, ()), on=on_color),
            style.paint(p.intent.ljust(intent_width), *style.INTENT_CODES.get(p.intent, ()), on=on_color),
        ]
        if show_project:
            cells.append((p.project or "").ljust(project_width))
        cells.append(p.title)
        lines.append((" " * GUTTER).join(cells))
        lines.append(" " * indent + style.paint(p.id, style.DIM, on=on_color))

    return "\n".join(lines)
