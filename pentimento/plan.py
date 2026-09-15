"""A single plan file: id, title, frontmatter fields, and body."""

from __future__ import annotations

import dataclasses
import datetime
import os
import tempfile
from pathlib import Path

from pentimento import frontmatter, tags, times
from pentimento import vocabulary as vocabulary_module

EXCLUDED_FILENAMES = {"README.md", "INDEX.md"}

CURSOR_SUFFIX = ".plan.md"
PLAN_SUFFIX = ".md"


@dataclasses.dataclass
class Plan:
    id: str
    path: Path
    fields: dict[str, str]
    body: str
    mtime: float
    started: str
    source: str = "claude"
    text: str = ""
    ended: str = ""
    extras: frontmatter.Extras | None = None

    @property
    def modified(self) -> datetime.datetime:
        """The later of the session's end and the file's own mtime.

        A session end alone goes stale the moment a *later* session (or a
        hand edit) touches the file without also touching a session tied to
        it -- writes already use `keep_mtime=True`, so mtime only moves on a
        real edit.
        """
        mtime = datetime.datetime.fromtimestamp(self.mtime, tz=datetime.timezone.utc)
        ended = times.parse_iso(self.ended)
        if ended is not None:
            return max(ended, mtime)
        return mtime

    @property
    def created_at(self) -> datetime.datetime | None:
        return times.parse_iso(self.started)

    @property
    def created_date(self) -> datetime.date | None:
        """The `created` field, or the date `backfill` would have written."""
        return times.parse_date(self.fields.get("created", "")) or times.local_day(self.created_at)

    @property
    def title(self) -> str:
        return _first_h1(self.body) or self.id

    @property
    def has_title(self) -> bool:
        return _first_h1(self.body) is not None

    @property
    def status(self) -> str:
        return self.fields.get("status", vocabulary_module.DEFAULT_STATUS)

    @property
    def intent(self) -> str:
        return self.fields.get("intent", vocabulary_module.DEFAULT_INTENT)

    @property
    def tags(self) -> list[str]:
        return tags.parse(self.fields.get("tags"))

    @property
    def parent(self) -> str | None:
        return self.fields.get("parent")

    @property
    def project(self) -> str | None:
        return self.fields.get("project")


def _first_h1(body: str) -> str | None:
    for line in body.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return None


def body_below_title(body: str) -> str:
    """Drop a leading H1 and the blank lines around it."""
    lines = body.split("\n")
    while lines and lines[0].strip() == "":
        lines.pop(0)
    if not lines or not lines[0].startswith("# "):
        return body
    lines.pop(0)
    while lines and lines[0].strip() == "":
        lines.pop(0)
    return "\n".join(lines)


def _id_for(path: Path) -> str:
    if path.name.endswith(CURSOR_SUFFIX):
        return path.name[: -len(CURSOR_SUFFIX)]
    return path.stem


def load(path: Path, sessions: dict | None = None, source: str = "claude") -> Plan:
    text = path.read_text(encoding="utf-8", errors="replace")
    fields, body, extras = frontmatter.parse(text)
    plan_id = _id_for(path)
    session = (sessions or {}).get(plan_id)
    started = session.started if session else _file_started(path)
    ended = session.ended if session else ""
    return Plan(
        id=plan_id,
        path=path,
        fields=fields,
        body=body,
        mtime=path.stat().st_mtime,
        started=started,
        source=source,
        text=text,
        ended=ended,
        extras=extras,
    )


def _file_started(path: Path) -> str:
    stat = path.stat()
    ts = getattr(stat, "st_birthtime", stat.st_mtime)
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def atomic_write(path: Path, text: str, *, keep_mtime: bool = False) -> None:
    """Write `text` to `path` via same-directory tmp file + `os.replace`.

    Resolves symlinks first, so a `*.md` symlink's target is written
    explicitly rather than silently followed. Preserves the original file's
    permission bits, since `os.replace` otherwise carries over `mkstemp`'s
    0600, and uses a unique tmp name so concurrent writers cannot collide.
    """
    target = path.resolve()
    try:
        stat = target.stat()
    except FileNotFoundError:
        stat = None
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        if stat is not None:
            os.chmod(tmp_name, stat.st_mode)
        os.replace(tmp_name, target)
    except BaseException:
        os.unlink(tmp_name)
        raise
    if keep_mtime and stat is not None:
        os.utime(target, (stat.st_atime, stat.st_mtime))


def save(plan: Plan, *, keep_mtime: bool = False) -> None:
    text = frontmatter.serialize(plan.fields, plan.body, plan.extras)
    plan.text = text
    atomic_write(plan.path, text, keep_mtime=keep_mtime)


def is_plan_file(path: Path) -> bool:
    return path.suffix == PLAN_SUFFIX and path.name not in EXCLUDED_FILENAMES
