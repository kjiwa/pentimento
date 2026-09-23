"""Human-facing `list` rendering: one greppable line per plan."""

from __future__ import annotations

import dataclasses

from pentimento import columns as columns_module
from pentimento import shortid, style, table, times

# (name, Column, include(plans) -> bool, cell(plan, short_ids) -> table.Cell), one
# spelling per column; `name` is the lowercase token `--columns` and
# `PENTIMENTO_COLUMNS` accept.
_SPECS = (
    (
        "status",
        table.Column("STATUS", drop=6),
        lambda plans: True,
        lambda p, short_ids: (p.status, style.STATUS_CODES.get(p.status, ())),
    ),
    (
        "intent",
        table.Column("INTENT", drop=5),
        lambda plans: True,
        lambda p, short_ids: (p.intent, style.INTENT_CODES.get(p.intent, ())),
    ),
    (
        "project",
        table.Column("PROJECT", drop=4),
        lambda plans: True,
        lambda p, short_ids: (p.project or "", ()),
    ),
    (
        "source",
        table.Column("SOURCE", drop=3),
        lambda plans: True,
        lambda p, short_ids: (p.source, style.SOURCE_CODES.get(p.source, ())),
    ),
    (
        "id",
        table.Column("PLAN", drop=7),
        lambda plans: True,
        lambda p, short_ids: (short_ids[p.id], ()),
    ),
    (
        "title",
        table.Column("TITLE", flex=1, comfort=32, floor=16),
        lambda plans: True,
        lambda p, short_ids: (p.title if p.has_title else "", ()),
    ),
    (
        "tags",
        table.Column("TAGS", drop=2),
        lambda plans: any(p.tags for p in plans),
        lambda p, short_ids: (", ".join(p.tags), ()),
    ),
    (
        "created",
        table.Column("CREATED", drop=1),
        lambda plans: any(p.created_date for p in plans),
        lambda p, short_ids: (
            p.created_date.isoformat() if p.created_date else "",
            (style.DIM,),
        ),
    ),
    (
        "modified",
        table.Column("UPDATED", align="right"),
        lambda plans: True,
        lambda p, short_ids: (times.relative(p.modified), (style.DIM,)),
    ),
)

NAMES = tuple(name for name, _, _, _ in _SPECS)
COLUMNS = tuple(spec[1] for spec in _SPECS)


def render(
    plans, on_color: bool, unicode_ok: bool = True, *, short_ids=None, selection=None, pin=()
) -> str:
    """Render `plans` as a table.

    `short_ids`, when given, must be a corpus-wide `shortid.shorten` mapping
    -- a mapping built from a filtered subset could print an id that is
    ambiguous corpus-wide. When omitted, ids are shortened over `plans`
    itself.

    `selection`, a `columns.Selection`, and `pin`, the sort key's column
    name(s), together decide which columns render and which never drop; see
    `columns.resolve`.
    """
    if short_ids is None:
        short_ids = shortid.shorten(p.id for p in plans)

    by_name = {name: (column, cell) for name, column, include, cell in _SPECS}
    default_names = tuple(name for name, _, include, _ in _SPECS if include(plans))

    if selection is None:
        names, never_drop = default_names, set(pin)
    else:
        names, never_drop = columns_module.resolve(selection, default_names, tuple(pin))

    names = [name for name in names if name in by_name]
    columns = tuple(
        dataclasses.replace(by_name[name][0], drop=0) if name in never_drop else by_name[name][0]
        for name in names
    )
    rows = [tuple(by_name[name][1](p, short_ids) for name in names) for p in plans]

    width = style.terminal_width()
    return table.render(columns, rows, on_color=on_color, unicode_ok=unicode_ok, width=width)
