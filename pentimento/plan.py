"""A single plan file: id, title, frontmatter fields, and body."""

from __future__ import annotations

import dataclasses
import datetime
from pathlib import Path

from pentimento import frontmatter

EXCLUDED_FILENAMES = {"README.md", "INDEX.md"}


@dataclasses.dataclass
class Plan:
    id: str
    path: Path
    fields: dict[str, str]
    body: str
    mtime: float
    started: str

    @property
    def title(self) -> str:
        return _first_h1(self.body) or self.id

    @property
    def status(self) -> str:
        return self.fields.get("status", "unknown")

    @property
    def intent(self) -> str:
        return self.fields.get("intent", "unset")

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


def load(path: Path, sessions: dict | None = None) -> Plan:
    text = path.read_text()
    fields, body = frontmatter.parse(text)
    session = (sessions or {}).get(path.stem)
    started = session.started if session else _file_started(path)
    return Plan(id=path.stem, path=path, fields=fields, body=body, mtime=path.stat().st_mtime, started=started)


def _file_started(path: Path) -> str:
    stat = path.stat()
    ts = getattr(stat, "st_birthtime", stat.st_mtime)
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def save(plan: Plan) -> None:
    text = frontmatter.serialize(plan.fields, plan.body)
    plan.path.write_text(text)


def is_plan_file(path: Path) -> bool:
    return path.suffix == ".md" and path.name not in EXCLUDED_FILENAMES
