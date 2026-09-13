"""Human-facing `list` rendering: bold header, two-line records.

Sort order is decided by the caller (`cli.py`); this module renders plans
in the order given.
"""

from __future__ import annotations

from pentimento import style, times
from pentimento import tags as tags_module

GUTTER = 2
ELLIPSIS = "..."


def _column_width(header: str, values: list[str]) -> int:
    return max(len(header), *(len(v) for v in values)) if values else len(header)


def _truncate(text: str, width: int) -> str:
    if width <= 0 or len(text) <= width:
        return text
    if width <= len(ELLIPSIS):
        return text[:width]
    return text[: width - len(ELLIPSIS)].rstrip() + ELLIPSIS


def render(plans, on_color: bool) -> str:
    show_project = len({p.project for p in plans}) > 1
    show_source = len({p.source for p in plans}) > 1

    status_width = _column_width("STATUS", [p.status for p in plans])
    intent_width = _column_width("INTENT", [p.intent for p in plans])
    project_width = _column_width("PROJECT", [p.project or "" for p in plans]) if show_project else 0
    source_width = _column_width("SOURCE", [p.source for p in plans]) if show_source else 0
    relative_width = _column_width("", [times.relative(p.modified) for p in plans])

    header_cells = ["STATUS".ljust(status_width), "INTENT".ljust(intent_width)]
    if show_project:
        header_cells.append("PROJECT".ljust(project_width))
    if show_source:
        header_cells.append("SOURCE".ljust(source_width))
    header_cells.append("PLAN")
    header_row = (" " * GUTTER).join(header_cells)
    header = style.paint(header_row, style.BOLD, on=on_color)

    indent = status_width + GUTTER + intent_width + GUTTER
    if show_project:
        indent += project_width + GUTTER
    if show_source:
        indent += source_width + GUTTER

    prefix_width = len(header_row) - len("PLAN")
    title_width = max(style.terminal_width() - prefix_width - GUTTER - relative_width, 1)

    lines = [header]
    for p in plans:
        cells = [
            style.paint(p.status.ljust(status_width), *style.STATUS_CODES.get(p.status, ()), on=on_color),
            style.paint(p.intent.ljust(intent_width), *style.INTENT_CODES.get(p.intent, ()), on=on_color),
        ]
        if show_project:
            cells.append((p.project or "").ljust(project_width))
        if show_source:
            source_codes = style.SOURCE_CODES.get(p.source, ())
            cells.append(style.paint(p.source.ljust(source_width), *source_codes, on=on_color))
        title = _truncate(p.title, title_width).ljust(title_width)
        relative_field = style.paint(times.relative(p.modified).rjust(relative_width), style.DIM, on=on_color)
        cells.append(title)
        lines.append((" " * GUTTER).join(cells) + (" " * GUTTER) + relative_field)

        stamp = times.local_stamp(p.modified)
        meta = f"{p.id}  {stamp}"
        if p.tags:
            meta += f"  {tags_module.render(p.tags)}"
        lines.append(" " * indent + style.paint(meta, style.DIM, on=on_color))

    return "\n".join(lines)
