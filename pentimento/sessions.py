"""Read harness session logs into a slug-keyed index.

Each Claude Code session is recorded as `~/.claude/projects/<encoded-dir>/
<uuid>.jsonl`, one line per event. Lines carry a `slug` (identical to the
plan filename stem this session produced, when it produced one), a `cwd`,
and, for user lines, the prompt text. Absent or unreadable directories yield
an empty index -- pentimento must stay usable without a harness.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

HOME_PROJECT_NAME = "home"


@dataclasses.dataclass
class Session:
    slug: str
    project: str
    started: str
    prompt: str
    ended: str = ""


def sessions_directory() -> Path:
    return Path(os.environ.get("AGENT_SESSIONS_DIR", str(Path.home() / ".claude" / "projects")))


def load(directory: Path | None = None) -> dict[str, Session]:
    directory = directory or sessions_directory()
    if not directory.is_dir():
        return {}

    sessions: dict[str, Session] = {}
    for project_dir in sorted(p for p in directory.iterdir() if p.is_dir()):
        sessions.update(_load_project(project_dir))
    return sessions


def _load_project(project_dir: Path) -> dict[str, Session]:
    by_slug: dict[str, dict] = {}
    for log_path in sorted(project_dir.glob("*.jsonl")):
        for record in _read_records(log_path):
            slug = record.get("slug")
            if not slug:
                continue
            entry = by_slug.setdefault(
                slug, {"cwds": [], "started": None, "ended": None, "prompt": None, "prompt_ts": None}
            )
            cwd = record.get("cwd")
            if cwd:
                entry["cwds"].append(cwd)
            timestamp = record.get("timestamp")
            if timestamp and (entry["started"] is None or timestamp < entry["started"]):
                entry["started"] = timestamp
            if timestamp and (entry["ended"] is None or timestamp > entry["ended"]):
                entry["ended"] = timestamp
            if timestamp and record.get("type") == "user" and (
                entry["prompt_ts"] is None or timestamp < entry["prompt_ts"]
            ):
                text = _prompt_text(record)
                if text is not None:
                    entry["prompt"] = text
                    entry["prompt_ts"] = timestamp

    project = _project_name(cwd for entry in by_slug.values() for cwd in entry["cwds"])
    return {
        slug: Session(
            slug=slug,
            project=project,
            started=entry["started"] or "",
            prompt=entry["prompt"] or "",
            ended=entry["ended"] or "",
        )
        for slug, entry in by_slug.items()
    }


def _read_records(log_path: Path):
    with log_path.open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _prompt_text(record: dict) -> str | None:
    content = record.get("message", {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        blocks = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(blocks)
    return None


def _project_name(cwds) -> str:
    cwds = list(cwds)
    if not cwds:
        return ""
    common = os.path.commonpath(cwds)
    if common == str(Path.home()):
        return HOME_PROJECT_NAME
    return os.path.basename(common)
