"""Print one instant, `DAYS_AGO` days before the base, in three formats.

Lines: a `touch -t` stamp, the local created date, and the UTC session
timestamp, so a plan's mtime and its authoring session's timestamp agree
exactly. Time-of-day is pinned (only the date moves): capture.sh commits its
output literally and CI's readme-samples job regenerates and diffs it, so a real
wall-clock time-of-day would drift the sample on every rerun. The base instant
honours `PENTIMENTO_NOW` so capture.sh can pin it for reproducible samples.
"""

from __future__ import annotations

import datetime
import os
import sys


def _base_utc() -> datetime.datetime:
    override = os.environ.get("PENTIMENTO_NOW")
    if not override:
        pinned_local = datetime.datetime.now().replace(hour=12, minute=30, second=0, microsecond=0)
        return pinned_local.astimezone(datetime.timezone.utc)
    normalized = override[:-1] + "+00:00" if override.endswith("Z") else override
    base = datetime.datetime.fromisoformat(normalized)
    if base.tzinfo is None:
        base = base.replace(tzinfo=datetime.timezone.utc)
    return base


def main() -> None:
    utc = _base_utc() - datetime.timedelta(days=int(sys.argv[1]))
    local = utc.astimezone()
    print(local.strftime("%Y%m%d%H%M.%S"))
    print(local.strftime("%Y-%m-%d"))
    print(utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"))


if __name__ == "__main__":
    main()
