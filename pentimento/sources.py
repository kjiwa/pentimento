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


def claude_source() -> Source:
    directory = Path(os.environ.get("AGENT_PLANS_DIR", str(Path.home() / ".claude" / "plans")))
    return Source(name="claude", directories=[directory], suffix=".md", strip_suffix=".md")


def cursor_source() -> Source:
    env = os.environ.get("CURSOR_PLANS_DIR")
    if env:
        directories = [Path(p) for p in env.split(os.pathsep)]
    else:
        directories = [
            Path.home() / ".cursor" / "plans",
            Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "plans",
        ]
    return Source(name="cursor", directories=directories, suffix=".plan.md", strip_suffix=".plan.md")


def files(source: Source) -> list[Path]:
    found = []
    for directory in source.directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob(f"*{source.suffix}")):
            if source.name == "claude" and not plan_module.is_plan_file(path):
                continue
            found.append(path)
    return found


def discover() -> list[tuple[str, Path]]:
    """`(source_name, path)` pairs across every configured source."""
    pairs = []
    for source in (claude_source(), cursor_source()):
        pairs.extend((source.name, path) for path in files(source))
    return pairs
