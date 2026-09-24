"""Render a plan's session-touch history: who touched it, and when.

Groups the `touches.Touch` list for a single plan by session. A session
whose id equals the plan's own id authored it; any other session that later
read, edited, or delegated work on it worked it. Absence of any group is
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

EMPTY_MESSAGE = "no session history for {plan_id}; searched: {directory}"


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
    groups: dict[str, Group] = {}
    order: list[str] = []
    for touch in plan_touches:
        existing = groups.get(touch.session)
        if existing is None:
            what = "authored" if touch.session == plan_id else "worked"
            groups[touch.session] = Group(
                session=touch.session, what=what, when=touch.at, touches=1
            )
            order.append(touch.session)
        else:
            existing.touches += 1
    return [groups[session] for session in order]


def as_records(plan_id: str, plan_touches: list[touches_module.Touch]) -> list[dict]:
    return [
        {**dataclasses.asdict(g), "when": times.utc_stamp(times.parse_iso(g.when)) or g.when}
        for g in group(plan_id, plan_touches)
    ]


def render(plan_id: str, plan_touches: list[touches_module.Touch], on_color: bool) -> str:
    rows = []
    for g in group(plan_id, plan_touches):
        when = times.local_stamp(times.parse_iso(g.when)) or g.when
        rows.append(((when, ()), (g.what, ()), (g.session, ()), (str(g.touches), ())))
    width = style.terminal_width()
    return table.render(COLUMNS, rows, on_color=on_color, width=width)
