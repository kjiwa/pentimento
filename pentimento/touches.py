"""Which sessions touched which plan file.

Reads the same `~/.claude/projects/**/*.jsonl` transcripts as `sessions.py`,
but looks for `tool_use` records that name a plan's *path* rather than for
the `slug` field a session was started with -- a plan's own authoring
session and every later session that reads, edits, or delegates work on it
both leave records here. Restricting to tool_use inputs that name the plan
path (rather than free-text substring matching) keeps this signal clean:
pentimento's own dev sessions and `/plans` listings mention every id, but
rarely as a `Read`/`Edit`/`Write`/`Task` input.

A prescan for the literal `/plans/` before `json.loads` keeps a full sweep
of the transcript corpus fast.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

from pentimento import sessions

_TOOLS = {"Read", "Edit", "Write", "NotebookEdit", "MultiEdit", "Task"}
_PLAN_PATH = re.compile(r"/plans/([^/\"\s]+?)\.(?:plan\.)?md")


@dataclasses.dataclass
class Touch:
    plan_id: str
    session: str
    tool: str
    at: str
    cwd: str


def load(directory: Path | None = None) -> dict[str, list[Touch]]:
    directory = directory or sessions.sessions_directory()
    if not directory.is_dir():
        return {}

    by_plan: dict[str, list[Touch]] = {}
    for log_path in sorted(directory.rglob("*.jsonl")):
        for touch in _touches_in(log_path):
            by_plan.setdefault(touch.plan_id, []).append(touch)

    for plan_touches in by_plan.values():
        plan_touches.sort(key=lambda t: t.at)
    return by_plan


def _touches_in(log_path: Path):
    try:
        with log_path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if "/plans/" not in line:
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                yield from _touches_in_record(record, log_path)
    except OSError:
        return


def _touches_in_record(record: dict, log_path: Path):
    content = record.get("message", {}).get("content")
    if not isinstance(content, list):
        return
    session = record.get("slug") or log_path.stem
    at = record.get("timestamp", "")
    cwd = record.get("cwd", "")
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        tool = block.get("name")
        if tool not in _TOOLS:
            continue
        serialized = json.dumps(block.get("input", {}))
        for plan_id in _PLAN_PATH.findall(serialized):
            yield Touch(plan_id=plan_id, session=session, tool=tool, at=at, cwd=cwd)


def authored(touches: list[Touch], plan_id: str) -> list[Touch]:
    return [t for t in touches if t.session == plan_id]


def worked(touches: list[Touch], plan_id: str) -> list[Touch]:
    return [t for t in touches if t.session != plan_id]
