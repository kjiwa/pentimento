"""Human-facing `list` rendering: one greppable line per plan."""

from __future__ import annotations

from pentimento import columns as columns_module
from pentimento import shortid, style, table, times
from pentimento import tags as tags_module

# (name, Column, include(plans) -> bool, cell(plan, short_ids) -> table.Cell);
# `name` is the token `--columns` accepts.
_SPECS = (
    (
        "id",
        table.Column("PLAN"),
        lambda plans: True,
        lambda p, short_ids: (short_ids[p.id], ()),
    ),
    (
        "status",
        table.Column("STATUS"),
        lambda plans: True,
        lambda p, short_ids: (p.status, style.STATUS_CODES.get(p.status, ())),
    ),
    (
        "intent",
        table.Column("INTENT"),
        lambda plans: True,
        lambda p, short_ids: (p.intent, style.INTENT_CODES.get(p.intent, ())),
    ),
    (
        "project",
        table.Column("PROJECT", fit=table.TRUNCATE, floor=10, comfort=16),
        lambda plans: True,
        lambda p, short_ids: (p.project or "", ()),
    ),
    (
        "source",
        table.Column("SOURCE"),
        lambda plans: True,
        lambda p, short_ids: (p.source, style.SOURCE_CODES.get(p.source, ())),
    ),
    (
        "title",
        table.Column("TITLE", fit=table.TRUNCATE, floor=30, comfort=50),
        lambda plans: True,
        lambda p, short_ids: (p.title if p.has_title else "", ()),
    ),
    (
        "finding",
        table.Column("FINDING"),
        lambda plans: any(p.findings for p in plans),
        lambda p, short_ids: (", ".join(p.findings), (style.RED,)),
    ),
    (
        "tags",
        table.Column("TAGS", fit=table.TRUNCATE, floor=14, comfort=30, shorten=tags_module.shorten),
        lambda plans: any(p.tags for p in plans),
        lambda p, short_ids: (tags_module.render(p.tags), ()),
    ),
    (
        "created",
        table.Column("CREATED"),
        lambda plans: any(p.created for p in plans),
        lambda p, short_ids: (p.created or "", (style.DIM,)),
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


def render(plans, on_color: bool, *, short_ids=None, selection=None) -> str:
    """Render `plans` as a table, or stacked records when the table does not fit.

    `short_ids`, when given, must be a corpus-wide `shortid.shorten` mapping
    -- a mapping built from a filtered subset could print an id that is
    ambiguous corpus-wide. When omitted, ids are shortened over `plans`
    itself.

    `selection`, a `columns.Selection`, decides which columns render; see
    `columns.resolve`.
    """
    if short_ids is None:
        short_ids = shortid.shorten(p.id for p in plans)

    by_name = {name: (column, cell) for name, column, include, cell in _SPECS}
    default_names = tuple(name for name, _, include, _ in _SPECS if include(plans))
    names = default_names if selection is None else columns_module.resolve(selection, default_names)

    columns = tuple(by_name[name][0] for name in names)
    rows = [tuple(by_name[name][1](p, short_ids) for name in names) for p in plans]
    return table.render(columns, rows, on_color=on_color, width=style.terminal_width())
