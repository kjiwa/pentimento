"""Where plan files live, per harness.

Three harnesses are discovered: Claude Code (`~/.claude/plans/*.md`), Cursor
(`.plan.md` files under `~/.cursor/plans` and its Application Support
directory), and Antigravity (`~/.gemini/antigravity/brain/<conversation>/
<name>.md`, each with a `<name>.md.metadata.json` sidecar).
A directory that does not exist contributes nothing.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

from pentimento import plan as plan_module

SOURCE_NAMES = ("claude", "cursor", "antigravity")

# Antigravity also writes these artifacts next to a plan; they are not plans.
_ANTIGRAVITY_EXCLUDED = {"task.md", "walkthrough.md"}
_ANTIGRAVITY_SIDECAR = ".metadata.json"


@dataclasses.dataclass
class Source:
    name: str
    directories: list[Path]
    suffix: str
    nested: bool = False


def directory_source(directory: Path) -> Source:
    """A single Claude-style directory, overriding discovery entirely."""
    return Source(
        name="claude",
        directories=[directory],
        suffix=plan_module.PLAN_SUFFIX,
    )


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
    return Source(
        name="cursor",
        directories=directories,
        suffix=plan_module.CURSOR_SUFFIX,
    )


def antigravity_source() -> Source:
    directory = Path(
        os.environ.get(
            "ANTIGRAVITY_BRAIN_DIR", str(Path.home() / ".gemini" / "antigravity" / "brain")
        )
    )
    return Source(
        name="antigravity",
        directories=[directory],
        suffix=plan_module.PLAN_SUFFIX,
        nested=True,
    )


def all_sources() -> tuple[Source, ...]:
    return (claude_source(), cursor_source(), antigravity_source())


def _name_matches(source: Source, path: Path) -> bool:
    if source.name == "claude":
        return plan_module.is_plan_file(path) and path.name.endswith(source.suffix)
    if source.name == "antigravity":
        return path.name.endswith(source.suffix) and path.name not in _ANTIGRAVITY_EXCLUDED
    return path.name.endswith(source.suffix)


def _pattern(source: Source) -> str:
    return ("*/" if source.nested else "") + f"*{source.suffix}"


def _root(source: Source, path: Path) -> Path:
    """The directory a source's files sit directly in."""
    return path.parent.parent if source.nested else path.parent


def files(source: Source) -> list[Path]:
    found = []
    for directory in source.directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob(_pattern(source))):
            if _name_matches(source, path) and _has_sidecar(source, path):
                found.append(path)
    return found


def _has_sidecar(source: Source, path: Path) -> bool:
    """Antigravity writes a sidecar for every plan artifact; a stray `.md` has none."""
    if source.name != "antigravity":
        return True
    return path.with_name(path.name + _ANTIGRAVITY_SIDECAR).is_file()


def contains(source: Source, path: Path) -> bool:
    """Whether `path` would be discovered by `source`, without requiring it to exist."""
    if not _name_matches(source, path):
        return False
    root = _root(source, path).resolve()
    return any(root == directory.resolve() for directory in source.directories)


def discover() -> list[tuple[str, Path]]:
    """`(source_name, path)` pairs across every configured source."""
    pairs = []
    for source in all_sources():
        pairs.extend((source.name, path) for path in files(source))
    return pairs
