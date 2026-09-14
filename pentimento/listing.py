"""Human-facing `list` rendering: one greppable line per plan.

Sort order is decided by the caller (`cli.py`); this module renders plans
in the order given. Columns are sized to their content -- `table.render`
never stretches a column to fill the terminal -- and shrink, then drop, in
a documented order when the terminal is too narrow to hold everything, so
every line fits `style.terminal_width()`. `PLAN` holds the short id
(`pentimento/shortid.py`) and is never truncated -- it only drops -- so
`TITLE` is the sole column that shrinks.
"""

from __future__ import annotations

from pentimento import shortid, style, table, times

# (Column, include(plans) -> bool, cell(plan, short_ids) -> table.Cell), one spelling per column.
_SPECS = (
    (
        table.Column("STATUS", drop=6),
        lambda plans: len({p.status for p in plans}) > 1,
        lambda p, short_ids: (p.status, style.STATUS_CODES.get(p.status, ())),
    ),
    (
        table.Column("INTENT", drop=5),
        lambda plans: len({p.intent for p in plans}) > 1,
        lambda p, short_ids: (p.intent, style.INTENT_CODES.get(p.intent, ())),
    ),
    (
        table.Column("PROJECT", drop=4),
        lambda plans: len({p.project for p in plans}) > 1,
        lambda p, short_ids: (p.project or "", ()),
    ),
    (
        table.Column("SOURCE", drop=3),
        lambda plans: len({p.source for p in plans}) > 1,
        lambda p, short_ids: (p.source, style.SOURCE_CODES.get(p.source, ())),
    ),
    (
        table.Column("PLAN", drop=7),
        lambda plans: True,
        lambda p, short_ids: (short_ids[p.id], ()),
    ),
    (
        table.Column("TITLE", flex=1, comfort=32, floor=16),
        lambda plans: True,
        lambda p, short_ids: (p.title if p.has_title else "", ()),
    ),
    (
        table.Column("TAGS", drop=2),
        lambda plans: any(p.tags for p in plans),
        lambda p, short_ids: (", ".join(p.tags), ()),
    ),
    (
        table.Column("CREATED", drop=1),
        lambda plans: any(p.fields.get("created") for p in plans),
        lambda p, short_ids: (p.fields.get("created", ""), (style.DIM,)),
    ),
    (
        table.Column("UPDATED", align="right"),
        lambda plans: True,
        lambda p, short_ids: (times.relative(p.modified), (style.DIM,)),
    ),
)

COLUMNS = tuple(spec[0] for spec in _SPECS)


def render(plans, on_color: bool, unicode_ok: bool = True, *, short_ids=None) -> str:
    """Render `plans` as a table.

    `short_ids`, when given, must be a corpus-wide `shortid.shorten` mapping
    -- a mapping built from a filtered subset could print an id that is
    ambiguous corpus-wide. When omitted, ids are shortened over `plans`
    itself.
    """
    if short_ids is None:
        short_ids = shortid.shorten(p.id for p in plans)

    active = [(column, cell) for column, include, cell in _SPECS if include(plans)]
    columns = tuple(column for column, _ in active)
    rows = [tuple(cell(p, short_ids) for _, cell in active) for p in plans]

    width = style.terminal_width()
    return table.render(columns, rows, on_color=on_color, unicode_ok=unicode_ok, width=width)
