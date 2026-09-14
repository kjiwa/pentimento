"""Memoize per-file derived data across `pentimento` invocations.

Transcripts only grow by appending lines, so a cache keyed on file identity
(`key`) never goes stale: any edit changes `st_size`. A cache miss, a
corrupt file, or an unwritable cache directory all degrade to a full parse
rather than an error -- the same "a missing harness is a normal state"
stance `sessions.py` already takes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

VERSION = 1


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path.home() / ".cache"
    return root / "pentimento"


def key(path: Path) -> str:
    stat = path.stat()
    return f"{path}:{stat.st_size}:{stat.st_mtime_ns}"


def read(namespace: str) -> dict:
    try:
        data = json.loads((cache_dir() / f"{namespace}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}

    if data.get("version") != VERSION:
        return {}

    entries = data.get("entries")
    return entries if isinstance(entries, dict) else {}


def write(namespace: str, entries: dict) -> None:
    directory = cache_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        tmp_path = directory / f".{namespace}.json.tmp"
        tmp_path.write_text(json.dumps({"version": VERSION, "entries": entries}), encoding="utf-8")
        os.replace(tmp_path, directory / f"{namespace}.json")
    except OSError:
        pass
