"""Render a plan's session-touch history: who touched it, and when.

Groups the `touches.Touch` list for a single plan by session. A session
that wrote the plan (`touches.author`) authored it; any other session that later
edited or delegated work on it worked it, and one that only read it is `read`.
Absence of any group is
never rendered as evidence the plan wasn't worked -- see `touches.py`.
"""

from __future__ import annotations

import dataclasses

from pentimento import style, table, times
from pentimento import touches as touches_module

FIELDS = ("when", "what", "session", "touches")

COLUMNS = (
    table.Column("WHEN"),
    table.Column("WHAT"),
    table.Column("SESSION", fit=table.TRUNCATE, floor=16),
    table.Column("TOUCHES", align="right", stack_label="touches"),
)

EMPTY_MESSAGE = "no session history for '{plan_id}'; searched: {directory}"


@dataclasses.dataclass
class Group:
    session: str
    what: str
    when: str
    touches: int


def group(plan_id: str, plan_touches: list[touches_module.Touch]) -> list[Group]:
    """One `Group` per distinct session, in the order it first appears.

    `plan_touches` is expected already sorted by `at`, as `touches.load`
    returns it, so the first appearance of a session is its earliest touch.
    """
    writer = touches_module.author(plan_touches, plan_id)
    worked_sessions = {t.session for t in touches_module.worked(plan_touches, plan_id)}
    groups: dict[str, Group] = {}
    for touch in plan_touches:
        existing = groups.get(touch.session)
        if existing is None:
            groups[touch.session] = Group(
                session=touch.session,
                what=_what(touch.session, writer, worked_sessions),
                when=touch.at,
                touches=1,
            )
        else:
            existing.touches += 1
    return list(groups.values())


def _what(session: str, writer: str, worked_sessions: set[str]) -> str:
    if session == writer:
        return "authored"
    return "worked" if session in worked_sessions else "read"


def as_records(plan_id: str, plan_touches: list[touches_module.Touch]) -> list[dict]:
    records = []
    for g in group(plan_id, plan_touches):
        fields = {
            **dataclasses.asdict(g),
            "when": times.utc_stamp(times.parse_iso(g.when)) or g.when,
        }
        records.append({name: fields[name] for name in FIELDS})
    return records


def render(
    plan_id: str, plan_touches: list[touches_module.Touch], on_color: bool, short_ids: dict
) -> str:
    rows = []
    for g in group(plan_id, plan_touches):
        when = times.local_stamp(times.parse_iso(g.when)) or g.when
        session = short_ids.get(g.session, g.session)
        rows.append(((when, ()), (g.what, ()), (session, ()), (str(g.touches), ())))
    width = style.terminal_width()
    return table.render(COLUMNS, rows, on_color=on_color, width=width)
