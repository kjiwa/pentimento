"""A single plan file: id, title, frontmatter fields, and body."""

from __future__ import annotations

import dataclasses
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


def load(path: Path) -> Plan:
    text = path.read_text()
    fields, body = frontmatter.parse(text)
    return Plan(id=path.stem, path=path, fields=fields, body=body, mtime=path.stat().st_mtime)


def save(plan: Plan) -> None:
    text = frontmatter.serialize(plan.fields, plan.body)
    plan.path.write_text(text)


def is_plan_file(path: Path) -> bool:
    return path.suffix == ".md" and path.name not in EXCLUDED_FILENAMES
