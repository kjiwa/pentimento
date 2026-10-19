"""Read Antigravity conversation transcripts into per-plan sessions.

Antigravity keeps each conversation in `<brain>/<uuid>/`, with the plan next
to a `.system_generated/logs/transcript.jsonl` that records one step per line.
A plan therefore names its own transcript -- no matching is needed. Steps
carry `created_at`; the first `USER_INPUT` holds the prompt inside
`<USER_REQUEST>`; tool calls carry JSON-encoded string args (`Cwd`,
`TargetFile`, `AbsolutePath`), and the first working directory outside
Antigravity's own `~/.gemini` tree is the project.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from pentimento import cache as cache_module
from pentimento import sessions

TRANSCRIPT = Path(".system_generated") / "logs" / "transcript.jsonl"

_REQUEST = re.compile(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", re.DOTALL)
_PATH_KEYS = ("TargetFile", "AbsolutePath")


def load(plans) -> dict[str, sessions.Session]:
    plans = [p for p in plans if p.source == "antigravity"]
    if not plans:
        return {}

    cached = cache_module.read("antigravity_sessions")
    fresh: dict[str, dict] = {}
    parsed_by_plan: dict[str, dict] = {}
    for plan in plans:
        log_path = plan.path.parent / TRANSCRIPT
        try:
            cache_key = cache_module.key(log_path)
        except OSError:
            continue
        parsed = cached.get(cache_key)
        if parsed is None:
            parsed = _parse_transcript(log_path)
        fresh[cache_key] = parsed
        parsed_by_plan[plan.id] = parsed
    cache_module.write("antigravity_sessions", fresh)

    roots = sessions._launch_roots(parsed_by_plan.values())
    return {
        plan_id: sessions.Session(
            slug=plan_id,
            project=sessions._project_name(parsed["launch"], parsed["paths"], roots),
            started=parsed["started"],
            prompt=parsed["prompt"],
            ended=parsed["ended"],
        )
        for plan_id, parsed in parsed_by_plan.items()
    }


def _parse_transcript(log_path: Path) -> dict:
    started = ended = ""
    prompt = None
    launch = None
    paths: list[str] = []
    for record in sessions.read_records(log_path):
        timestamp = record.get("created_at")
        if isinstance(timestamp, str) and timestamp:
            started = min(started or timestamp, timestamp)
            ended = max(ended, timestamp)
        if prompt is None and record.get("type") == "USER_INPUT":
            prompt = _request_text(record.get("content"))
        for args in _tool_args(record):
            cwd = _decode(args.get("Cwd"))
            if launch is None and cwd and not _is_agent_tree(cwd):
                launch = cwd
            paths.extend(
                path
                for key in _PATH_KEYS
                if (path := _decode(args.get(key))) and _is_home_path(path)
            )
    return {
        "started": started,
        "ended": ended,
        "prompt": prompt or "",
        "launch": launch,
        "paths": paths,
    }


def _tool_args(record: dict):
    for call in record.get("tool_calls") or []:
        args = call.get("args") if isinstance(call, dict) else None
        if isinstance(args, dict):
            yield args


def _decode(value) -> str | None:
    """Antigravity JSON-encodes string args; keep the raw value when it is not."""
    if not isinstance(value, str):
        return None
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return value
    return decoded if isinstance(decoded, str) else value


def _request_text(content) -> str | None:
    if not isinstance(content, str):
        return None
    match = _REQUEST.search(content)
    return match.group(1) if match else content


def _is_agent_tree(path: str) -> bool:
    agent_root = str(Path.home() / ".gemini")
    return path == agent_root or path.startswith(agent_root + os.sep)


def _is_home_path(path: str) -> bool:
    return os.path.isabs(path) and sessions._contains(str(Path.home()), path)
