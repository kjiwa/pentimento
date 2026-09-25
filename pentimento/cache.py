"""Memoize per-file derived data across `pentimento` invocations.

A cache miss, a corrupt file, or an unwritable cache directory all degrade
to a full parse rather than an error.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

VERSION = 3


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
        fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=f".{namespace}.", suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"version": VERSION, "entries": entries}))
            os.replace(tmp_name, directory / f"{namespace}.json")
        except OSError:
            os.unlink(tmp_name)
            raise
    except OSError:
        pass
