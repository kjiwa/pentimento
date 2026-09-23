"""Timezone-aware parsing and formatting. The only module that touches tz.

Session timestamps and `Plan.started` are always UTC ISO-8601. Everything
shown to a human -- `created`, `modified`, relative times -- converts to the
local zone at render time.
"""

from __future__ import annotations

import datetime
import os
import re


def _wall_clock() -> datetime.datetime:
    override = parse_iso(os.environ.get("PENTIMENTO_NOW", ""))
    if override is not None:
        return override
    return datetime.datetime.now(datetime.timezone.utc)


def now() -> datetime.datetime:
    """Wall clock, overridable by `PENTIMENTO_NOW` (ISO-8601, UTC)."""
    return _wall_clock()


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


def parse_date(text: str) -> datetime.date | None:
    """Parse a `YYYY-MM-DD` date, returning `None` for empty or invalid text."""
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


_AGE_SECONDS = {"m": 60, "h": 3600, "d": 86400, "w": 604800, "y": 31536000}
_AGE = re.compile(r"(\d+)([mhdwy])")


def parse_when(text: str) -> datetime.date | None:
    """Parse a `YYYY-MM-DD` date or an age in `relative`'s units (`14m`, `5h`,
    `3d`, `2w`, `1y`) into a local day, or `None` for anything else. An age
    counts back from `now()`."""
    day = parse_date(text)
    if day is not None:
        return day
    match = _AGE.fullmatch(text)
    if match is None:
        return None
    seconds = int(match.group(1)) * _AGE_SECONDS[match.group(2)]
    try:
        return local_day(now() - datetime.timedelta(seconds=seconds))
    except OverflowError:
        return None


def local_day(dt: datetime.datetime | None) -> datetime.date | None:
    if dt is None:
        return None
    return dt.astimezone().date()


def local_date(dt: datetime.datetime | None) -> str | None:
    day = local_day(dt)
    if day is None:
        return None
    return day.strftime("%Y-%m-%d")


def utc_stamp(dt: datetime.datetime | None) -> str | None:
    """The machine-format instant: UTC, whole seconds, trailing `Z`."""
    if dt is None:
        return None
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def local_stamp(dt: datetime.datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def relative(dt: datetime.datetime, now: datetime.datetime | None = None) -> str:
    """A short relative age: `just now`, `14m`, `2h`, `3d`, `5w`, `1y`."""
    if now is None:
        now = _wall_clock()
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
