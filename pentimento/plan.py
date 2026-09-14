"""A single plan file: id, title, frontmatter fields, and body."""

from __future__ import annotations

import dataclasses
import datetime
import os
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

    @property
    def modified(self) -> datetime.datetime:
        ended = times.parse_iso(self.ended)
        if ended is not None:
            return ended
        return datetime.datetime.fromtimestamp(self.mtime, tz=datetime.timezone.utc)

    @property
    def created_at(self) -> datetime.datetime | None:
        return times.parse_iso(self.started)

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
    text = path.read_text(encoding="utf-8")
    fields, body = frontmatter.parse(text)
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
    )


def _file_started(path: Path) -> str:
    stat = path.stat()
    ts = getattr(stat, "st_birthtime", stat.st_mtime)
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def save(plan: Plan, *, keep_mtime: bool = False) -> None:
    text = frontmatter.serialize(plan.fields, plan.body)
    plan.text = text
    if keep_mtime:
        stat = plan.path.stat()
        plan.path.write_text(text, encoding="utf-8")
        os.utime(plan.path, (stat.st_atime, stat.st_mtime))
    else:
        plan.path.write_text(text, encoding="utf-8")


def is_plan_file(path: Path) -> bool:
    return path.suffix == PLAN_SUFFIX and path.name not in EXCLUDED_FILENAMES
