"""Where plan files live, per harness.

Two harnesses are discovered: Claude Code (`~/.claude/plans/*.md`) and
Cursor (`~/.cursor/plans/*.plan.md`, plus its legacy pre-migration location).
A directory that does not exist contributes nothing -- pentimento must stay
usable without a harness, mirroring `sessions.py`.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

from pentimento import plan as plan_module

SOURCE_NAMES = ("claude", "cursor")


@dataclasses.dataclass
class Source:
    name: str
    directories: list[Path]
    suffix: str
    strip_suffix: str


def directory_source(directory: Path) -> Source:
    """A single Claude-style directory, overriding discovery entirely."""
    return Source(name="claude", directories=[directory], suffix=plan_module.PLAN_SUFFIX, strip_suffix=plan_module.PLAN_SUFFIX)


def claude_source() -> Source:
    directory = Path(os.environ.get("AGENT_PLANS_DIR", str(Path.home() / ".claude" / "plans")))
    return directory_source(directory)


def cursor_source() -> Source:
    env = os.environ.get("CURSOR_PLANS_DIR")
    if env:
        directories = [Path(p) for p in env.split(os.pathsep)]
    else:
        directories = [
            Path.home() / ".cursor" / "plans",
            Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "plans",
        ]
    return Source(name="cursor", directories=directories, suffix=plan_module.CURSOR_SUFFIX, strip_suffix=plan_module.CURSOR_SUFFIX)


def all_sources() -> tuple[Source, ...]:
    return (claude_source(), cursor_source())


def _name_matches(source: Source, path: Path) -> bool:
    if source.name == "claude":
        return plan_module.is_plan_file(path) and path.name.endswith(source.suffix)
    return path.name.endswith(source.suffix)


def files(source: Source) -> list[Path]:
    found = []
    for directory in source.directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob(f"*{source.suffix}")):
            if _name_matches(source, path):
                found.append(path)
    return found


def contains(source: Source, path: Path) -> bool:
    """Whether `path` would be discovered by `source`, without requiring it to exist."""
    if not _name_matches(source, path):
        return False
    resolved_parent = path.parent.resolve()
    return any(resolved_parent == directory.resolve() for directory in source.directories)


def discover() -> list[tuple[str, Path]]:
    """`(source_name, path)` pairs across every configured source."""
    pairs = []
    for source in all_sources():
        pairs.extend((source.name, path) for path in files(source))
    return pairs
