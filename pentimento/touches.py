"""Which sessions touched which plan file.

Reads the same `~/.claude/projects/**/*.jsonl` transcripts as `sessions.py`,
but looks for `tool_use` records that name a plan's *path* rather than for
the `slug` field a session was started with -- a plan's authoring
session (see `author`) and every later session that reads, edits, or delegates work on it
both leave records here; only edits, writes, and delegation count as work.
A tool call names a plan only through its target path (`file_path`,
`notebook_path`, `path`); file content or an edit's new text that merely
mentions a plan does not. `Task` is the exception: a delegation prompt naming
a plan is the signal, so its whole input is scanned. pentimento's own dev
sessions and `/plans` listings mention every id, but rarely as a tool target.

A prescan for the literal `/plans/` before `json.loads` keeps a full sweep
of the transcript corpus fast.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

from pentimento import cache as cache_module
from pentimento import sessions

_WORK_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "Task"}
_TOOLS = _WORK_TOOLS | {"Read"}
_PATH_KEYS = ("file_path", "notebook_path", "path")
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

    cached = cache_module.read("touches")
    fresh: dict[str, list[dict]] = {}
    by_plan: dict[str, list[Touch]] = {}
    for log_path in sorted(directory.rglob("*.jsonl")):
        try:
            cache_key = cache_module.key(log_path)
        except OSError:
            continue
        serialized = cached.get(cache_key)
        if serialized is None:
            serialized = [dataclasses.asdict(t) for t in _touches_in(log_path)]
        fresh[cache_key] = serialized
        for record in serialized:
            touch = Touch(**record)
            by_plan.setdefault(touch.plan_id, []).append(touch)
    cache_module.write("touches", fresh)

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
                if isinstance(record, dict):
                    yield from _touches_in_record(record, log_path)
    except OSError:
        return


def _touches_in_record(record: dict, log_path: Path):
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
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
        for plan_id in _PLAN_PATH.findall(_scanned_text(tool, block.get("input", {}))):
            yield Touch(plan_id=plan_id, session=session, tool=tool, at=at, cwd=cwd)


def _scanned_text(tool: str, tool_input) -> str:
    if tool == "Task" or not isinstance(tool_input, dict):
        return json.dumps(tool_input)
    return "\n".join(tool_input[key] for key in _PATH_KEYS if isinstance(tool_input.get(key), str))


def author(touches: list[Touch], plan_id: str) -> str:
    """The session that wrote the plan: the same-slug session if it touched the plan,
    else the session whose `Write` is the plan's first touch, else the plan id."""
    if any(t.session == plan_id for t in touches):
        return plan_id
    if touches and touches[0].tool == "Write":
        return touches[0].session
    return plan_id


def worked(touches: list[Touch], plan_id: str) -> list[Touch]:
    writer = author(touches, plan_id)
    return [t for t in touches if t.session != writer and t.tool in _WORK_TOOLS]
