"""Timezone-aware parsing and formatting. The only module that touches tz.

Session timestamps and `Plan.started` are always UTC ISO-8601. Everything
shown to a human -- `created`, `modified`, relative times -- converts to the
local zone at render time.
"""

from __future__ import annotations

import datetime


def parse_iso(text: str) -> datetime.datetime | None:
    """Parse a UTC ISO-8601 timestamp, normalizing a trailing `Z`.

    `datetime.fromisoformat` only accepts `Z` from Python 3.11; this project
    supports 3.9, so `Z` is swapped for `+00:00` first.
    """
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def local_date(dt: datetime.datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone().strftime("%Y-%m-%d")


def local_stamp(dt: datetime.datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def relative(dt: datetime.datetime, now: datetime.datetime | None = None) -> str:
    """A short relative age: `just now`, `14m`, `2h`, `3d`, `5w`, `1y`."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    delta = (now - dt).total_seconds()
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m"
    if delta < 86400:
        return f"{int(delta // 3600)}h"
    if delta < 604800:
        return f"{int(delta // 86400)}d"
    if delta < 31536000:
        return f"{int(delta // 604800)}w"
    return f"{int(delta // 31536000)}y"
