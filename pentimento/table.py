"""Content-width column rendering shared by `list` and `check`."""

from __future__ import annotations

import dataclasses

from pentimento import style
from pentimento.style import Cell


@dataclasses.dataclass(frozen=True)
class Column:
    header: str
    align: str = "left"  # "left" | "right"
    flex: int = 0  # 0 fixed; 1 shrinks first, 2 next
    comfort: int = 0  # mild-truncation floor
    floor: int = 0  # hard floor
    drop: int = 0  # 0 never dropped; low positive numbers drop first


def _natural_widths(columns: tuple[Column, ...], rows: list[tuple[Cell, ...]]) -> dict[Column, int]:
    widths = {}
    for index, column in enumerate(columns):
        values = [row[index][0] for row in rows]
        widths[column] = (
            max(style.display_width(column.header), *(style.display_width(v) for v in values))
            if values
            else style.display_width(column.header)
        )
    return widths


def _total(widths: dict[Column, int], active: list[Column]) -> int:
    if not active:
        return 0
    return sum(widths[c] for c in active) + style.GUTTER * (len(active) - 1)


def _shrink(
    widths: dict[Column, int], active: list[Column], attr: str, width: int
) -> tuple[dict[Column, int], bool]:
    widths = dict(widths)
    for column in sorted((c for c in active if c.flex > 0), key=lambda c: c.flex):
        excess = _total(widths, active) - width
        if excess <= 0:
            break
        widths[column] = max(getattr(column, attr), widths[column] - excess)
    return widths, _total(widths, active) <= width


def _fit(
    columns: tuple[Column, ...], natural: dict[Column, int], width: int
) -> tuple[list[Column], dict[Column, int]]:
    active = list(columns)
    while True:
        widths = {c: natural[c] for c in active}
        if _total(widths, active) <= width:
            return active, widths

        widths, fits = _shrink(widths, active, "comfort", width)
        if fits:
            return active, widths

        droppable = [c for c in active if c.drop > 0]
        if droppable:
            victim = min(droppable, key=lambda c: c.drop)
            active = [c for c in active if c is not victim]
            continue

        widths, _fits = _shrink(widths, active, "floor", width)
        return active, widths


def _pad(text: str, width: int, align: str) -> str:
    return text.rjust(width) if align == "right" else text.ljust(width)


def _render_row(
    active: list[Column],
    widths: dict[Column, int],
    cells: list[Cell],
    width: int,
    unicode_ok: bool,
    on_color: bool,
) -> str:
    parts = []
    used = 0
    for index, column in enumerate(active):
        text, codes = cells[index]
        is_last = index == len(active) - 1
        gutter = style.GUTTER if parts else 0
        remaining = width - used - gutter
        if remaining <= 0:
            break
        col_width = min(widths[column], remaining)
        cell_text = style.truncate(text, col_width, unicode_ok=unicode_ok)
        if column.align == "right" or not is_last:
            cell_text = _pad(cell_text, col_width, column.align)
        parts.append(style.paint(cell_text, *codes, on=on_color))
        used += gutter + col_width
    return (" " * style.GUTTER).join(parts)


def render(
    columns: tuple[Column, ...],
    rows: list[tuple[Cell, ...]],
    *,
    on_color: bool,
    unicode_ok: bool,
    width: int,
) -> str:
    natural = _natural_widths(columns, rows)
    active, widths = _fit(columns, natural, width)
    index_by_column = {c: i for i, c in enumerate(columns)}

    header_cells = [(c.header, ()) for c in active]
    header_line = _render_row(active, widths, header_cells, width, unicode_ok, on_color=False)
    header = style.paint(header_line, style.BOLD, on=on_color)

    lines = [header]
    for row in rows:
        active_cells = [row[index_by_column[c]] for c in active]
        lines.append(_render_row(active, widths, active_cells, width, unicode_ok, on_color))
    return "\n".join(lines)
