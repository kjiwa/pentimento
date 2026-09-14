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

COLUMNS = (
    table.Column("STATUS", drop=7),
    table.Column("INTENT", drop=6),
    table.Column("PROJECT", drop=4),
    table.Column("SOURCE", drop=3),
    table.Column("PLAN", drop=5),
    table.Column("TITLE", flex=1, comfort=32, floor=16),
    table.Column("TAGS", drop=2),
    table.Column("CREATED", drop=1),
    table.Column("UPDATED", align="right"),
)


def render(plans, on_color: bool, unicode_ok: bool = True, *, short_ids=None) -> str:
    """Render `plans` as a table.

    `short_ids`, when given, must be a corpus-wide `shortid.shorten` mapping
    -- a mapping built from a filtered subset could print an id that is
    ambiguous corpus-wide. When omitted, ids are shortened over `plans`
    itself.
    """
    if short_ids is None:
        short_ids = shortid.shorten(p.id for p in plans)
    show_project = len({p.project for p in plans}) > 1
    show_source = len({p.source for p in plans}) > 1
    show_tags = any(p.tags for p in plans)
    show_created = any(p.fields.get("created") for p in plans)

    shown = {
        "STATUS": True,
        "INTENT": True,
        "PROJECT": show_project,
        "SOURCE": show_source,
        "PLAN": True,
        "TITLE": True,
        "TAGS": show_tags,
        "CREATED": show_created,
        "UPDATED": True,
    }
    columns = tuple(c for c in COLUMNS if shown[c.header])

    rows = []
    for p in plans:
        title = p.title if p.has_title else ""
        cells = {
            "STATUS": (p.status, style.STATUS_CODES.get(p.status, ())),
            "INTENT": (p.intent, style.INTENT_CODES.get(p.intent, ())),
            "PROJECT": (p.project or "", ()),
            "SOURCE": (p.source, style.SOURCE_CODES.get(p.source, ())),
            "PLAN": (short_ids[p.id], ()),
            "TITLE": (title, ()),
            "TAGS": (", ".join(p.tags), ()),
            "CREATED": (p.fields.get("created", ""), (style.DIM,)),
            "UPDATED": (times.relative(p.modified), (style.DIM,)),
        }
        rows.append(tuple(cells[c.header] for c in columns))

    width = style.terminal_width()
    return table.render(columns, rows, on_color=on_color, unicode_ok=unicode_ok, width=width)
