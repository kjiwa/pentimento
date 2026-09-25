"""Column rendering shared by `list`, `check`, and `history`: a table when every
column fits at its floor, otherwise one stacked record per row."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable

from pentimento import style
from pentimento.style import Cell

FIXED, TRUNCATE, WRAP = "fixed", "truncate", "wrap"
MAX_WRAP_LINES = 3
STACK_INDENT = "  "


@dataclasses.dataclass(frozen=True)
class Column:
    header: str
    align: str = "left"  # "left" | "right"
    fit: str = FIXED  # FIXED never shrinks; TRUNCATE cuts to one line; WRAP breaks at spaces
    floor: int = 0  # narrowest width a TRUNCATE or WRAP column keeps in a table
    comfort: int = 0  # width a flexible column reaches before spare width is shared out
    stack_label: str = ""  # prefixes the field in the stacked layout only
    shorten: Callable[[str, int], str] = style.truncate


def _natural_widths(columns: tuple[Column, ...], rows: list[tuple[Cell, ...]]) -> list[int]:
    return [
        max([style.display_width(column.header), *(style.display_width(r[index][0]) for r in rows)])
        for index, column in enumerate(columns)
    ]


def _minimum_widths(columns: tuple[Column, ...], natural: list[int]) -> list[int]:
    return [
        width if column.fit == FIXED else min(column.floor, width)
        for column, width in zip(columns, natural)
    ]


def _table_widths(
    columns: tuple[Column, ...], natural: list[int], width: int | None
) -> list[int] | None:
    """Column widths for a table within `width`, or `None` when the floors do not fit.

    Spare width first grows each flexible column to its comfort, the widest
    comfort first, then goes to the flexible columns narrowest natural width
    first, so short values stay whole and the longest column takes what is left.
    """
    if width is None or _headline(columns) is None:
        return natural
    widths = _minimum_widths(columns, natural)
    spare = width - sum(widths) - style.GUTTER * (len(columns) - 1)
    if spare < 0:
        return None
    flexible = [i for i, column in enumerate(columns) if column.fit != FIXED]
    by_comfort = sorted(flexible, key=lambda i: -columns[i].comfort)
    for index in by_comfort:
        spare = _grow(widths, index, min(columns[index].comfort, natural[index]), spare)
    for index in sorted(flexible, key=lambda i: natural[i]):
        spare = _grow(widths, index, natural[index], spare)
    return widths


def _grow(widths: list[int], index: int, target: int, spare: int) -> int:
    """Widen column `index` toward `target` using `spare`; returns what is left."""
    grow = max(0, min(spare, target - widths[index]))
    widths[index] += grow
    return spare - grow


def _headline(columns: tuple[Column, ...]) -> int | None:
    """The column whose text opens a stacked record: the one with the largest floor."""
    floors = [column.floor for column in columns]
    if not any(floors):
        return None
    return floors.index(max(floors))


def _pad(text: str, width: int, align: str) -> str:
    fill = " " * max(0, width - style.display_width(text))
    return fill + text if align == "right" else text + fill


def _cell_lines(column: Column, text: str, width: int) -> list[str]:
    if column.fit == WRAP:
        return style.wrap(text, width)
    return [column.shorten(text, width) if text else ""]


def _table_row(
    columns: tuple[Column, ...], widths: list[int], row: tuple[Cell, ...], on_color: bool
) -> list[str] | None:
    """The physical lines of one row, or `None` when a wrapped cell needs too many."""
    cell_lines = [
        _cell_lines(column, text, width) for column, (text, _), width in zip(columns, row, widths)
    ]
    height = max(len(lines) for lines in cell_lines)
    if height > MAX_WRAP_LINES:
        return None
    return [
        _join_line(columns, widths, row, [_line_at(lines, n) for lines in cell_lines], on_color)
        for n in range(height)
    ]


def _line_at(lines: list[str], line_number: int) -> str:
    return lines[line_number] if line_number < len(lines) else ""


def _join_line(
    columns: tuple[Column, ...],
    widths: list[int],
    row: tuple[Cell, ...],
    texts: list[str],
    on_color: bool,
) -> str:
    """Pad each cell to its column, drop trailing blank cells, and paint."""
    parts = [
        [_pad(text, width, column.align), codes]
        for column, width, text, (_, codes) in zip(columns, widths, texts, row)
    ]
    while parts and not parts[-1][0].strip():
        parts.pop()
    if parts and columns[len(parts) - 1].align == "left":
        parts[-1][0] = parts[-1][0].rstrip()
    return (" " * style.GUTTER).join(style.paint(t, *codes, on=on_color) for t, codes in parts)


def _table(
    columns: tuple[Column, ...],
    rows: list[tuple[Cell, ...]],
    widths: list[int],
    on_color: bool,
) -> str | None:
    header_cells = tuple((column.header, (style.BOLD,)) for column in columns)
    lines = _table_row(columns, widths, header_cells, on_color)
    for row in rows:
        row_lines = _table_row(columns, widths, row, on_color)
        if row_lines is None:
            return None
        lines.extend(row_lines)
    return "\n".join(lines)


def _stacked_record(
    columns: tuple[Column, ...],
    headline: int,
    row: tuple[Cell, ...],
    width: int,
    on_color: bool,
) -> list[str]:
    text, codes = row[headline]
    if columns[headline].fit == WRAP:
        head = style.wrap(text, width)
    else:
        head = [style.truncate(text, width)]
    lines = [style.paint(line, *codes, on=on_color) for line in head if line]
    fields = [
        _labelled(column, cell)
        for index, (column, cell) in enumerate(zip(columns, row))
        if index != headline and cell[0]
    ]
    return lines + style.wrap_fields(fields, "  ", width, STACK_INDENT, on_color=on_color)


def _labelled(column: Column, cell: Cell) -> Cell:
    text, codes = cell
    return (f"{column.stack_label} {text}" if column.stack_label else text, codes)


def _stacked(
    columns: tuple[Column, ...],
    rows: list[tuple[Cell, ...]],
    width: int,
    on_color: bool,
) -> str:
    headline = _headline(columns)
    lines = []
    for row in rows:
        lines.extend(_stacked_record(columns, headline, row, width, on_color))
    return "\n".join(lines)


def render(
    columns: tuple[Column, ...],
    rows: list[tuple[Cell, ...]],
    *,
    on_color: bool,
    width: int | None,
) -> str:
    natural = _natural_widths(columns, rows)
    widths = _table_widths(columns, natural, width)
    table = None if widths is None else _table(columns, rows, widths, on_color)
    if table is not None:
        return table
    return _stacked(columns, rows, width, on_color)
