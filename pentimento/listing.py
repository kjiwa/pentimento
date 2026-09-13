"""Human-facing `list` rendering: one greppable line per plan.

Sort order is decided by the caller (`cli.py`); this module renders plans
in the order given. The `PLAN` column is a flexible gutter: it absorbs
whatever width the fixed columns don't use, and shrinks -- down to a
12-column floor, truncating with an ellipsis -- when the terminal is too
narrow to hold everything, so every line fits `style.terminal_width()`.
"""

from __future__ import annotations

from pentimento import style, times

GUTTER = 2
PLAN_FLOOR = 12

# Left to right; PLAN is flexible, everything else is fixed-width. Drop
# order when the terminal is too narrow, applied in sequence.
DROP_ORDER = ("TAGS", "SOURCE", "PROJECT", "INTENT", "STATUS")


def _column_width(header: str, values: list[str]) -> int:
    if not values:
        return style.display_width(header)
    return max(style.display_width(header), *(style.display_width(v) for v in values))


def render(plans, on_color: bool, unicode_ok: bool = True) -> str:
    show_project = len({p.project for p in plans}) > 1
    show_source = len({p.source for p in plans}) > 1
    show_tags = any(p.tags for p in plans)

    status_values = [p.status for p in plans]
    intent_values = [p.intent for p in plans]
    project_values = [p.project or "" for p in plans]
    source_values = [p.source for p in plans]
    plan_values = [p.id for p in plans]
    tags_values = [", ".join(p.tags) for p in plans]
    age_values = [times.relative(p.modified) for p in plans]

    widths = {
        "STATUS": _column_width("STATUS", status_values),
        "INTENT": _column_width("INTENT", intent_values),
        "PROJECT": _column_width("PROJECT", project_values),
        "SOURCE": _column_width("SOURCE", source_values),
        "PLAN": _column_width("PLAN", plan_values),
        "TAGS": _column_width("TAGS", tags_values),
        "AGE": _column_width("AGE", age_values),
    }

    shown = {
        "STATUS": True,
        "INTENT": True,
        "PROJECT": show_project,
        "SOURCE": show_source,
        "PLAN": True,
        "TAGS": show_tags,
        "AGE": True,
    }
    active = [c for c in ("STATUS", "INTENT", "PROJECT", "SOURCE", "PLAN", "TAGS", "AGE") if shown[c]]

    term_width = style.terminal_width()
    drop_order = list(DROP_ORDER)

    def others_total() -> int:
        fixed = [c for c in active if c != "PLAN"]
        return sum(widths[c] for c in fixed) + GUTTER * (len(active) - 1)

    while drop_order and (term_width - others_total()) < PLAN_FLOOR:
        candidate = drop_order.pop(0)
        if candidate in active:
            active.remove(candidate)

    widths["PLAN"] = max(term_width - others_total(), PLAN_FLOOR)

    header_cells = []
    for column in active:
        if column == "AGE":
            header_cells.append(column.rjust(widths[column]))
        else:
            header_cells.append(column.ljust(widths[column]))
    header = style.paint((" " * GUTTER).join(header_cells), style.BOLD, on=on_color)

    lines = [header]
    for index, p in enumerate(plans):
        cells = []
        for column in active:
            if column == "STATUS":
                text = status_values[index].ljust(widths[column])
                cells.append(style.paint(text, *style.STATUS_CODES.get(p.status, ()), on=on_color))
            elif column == "INTENT":
                text = intent_values[index].ljust(widths[column])
                cells.append(style.paint(text, *style.INTENT_CODES.get(p.intent, ()), on=on_color))
            elif column == "PROJECT":
                cells.append(project_values[index].ljust(widths[column]))
            elif column == "SOURCE":
                text = source_values[index].ljust(widths[column])
                cells.append(style.paint(text, *style.SOURCE_CODES.get(p.source, ()), on=on_color))
            elif column == "PLAN":
                text = style.truncate(plan_values[index], widths[column], unicode_ok=unicode_ok)
                cells.append(text.ljust(widths[column]))
            elif column == "TAGS":
                cells.append(tags_values[index].ljust(widths[column]))
            elif column == "AGE":
                cells.append(style.paint(age_values[index].rjust(widths[column]), style.DIM, on=on_color))
        lines.append((" " * GUTTER).join(cells))

    return "\n".join(lines)
