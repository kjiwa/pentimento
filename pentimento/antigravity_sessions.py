"""Read Antigravity conversation transcripts into per-plan sessions.

Antigravity keeps each conversation in `<brain>/<uuid>/`, with the plan next
to a `.system_generated/logs/transcript.jsonl` that records one step per line.
A plan therefore names its own transcript -- no matching is needed. Steps
carry `created_at`; the first `USER_INPUT` holds the prompt inside
`<USER_REQUEST>`; tool calls carry JSON-encoded string args (`Cwd`, `Path`,
`TargetFile`, `AbsolutePath`). `project` comes from the first working directory
outside Antigravity's own `~/.gemini` tree, or, when a transcript has no `Cwd`,
from voting touched non-agent paths against known launch roots and enclosing
`.git` directories.
"""

from __future__ import annotations

import collections
import json
import os
from pathlib import Path

from pentimento import cache as cache_module
from pentimento import sessions

TRANSCRIPT = Path(".system_generated") / "logs" / "transcript.jsonl"

_PATH_KEYS = ("Path", "TargetFile", "AbsolutePath")


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
            project=_project_for(parsed, roots),
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
            prompt = sessions.tagged_text(record.get("content"), "USER_REQUEST")
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


def _is_agent_tree(path: str) -> bool:
    return sessions._contains(str(Path.home() / ".gemini"), path)


def _is_home_path(path: str) -> bool:
    return os.path.isabs(path) and sessions._contains(str(Path.home()), path)


def _is_home_dot_tree(path: str) -> bool:
    try:
        rel = Path(path).relative_to(Path.home())
    except ValueError:
        return False
    return bool(rel.parts) and rel.parts[0].startswith(".")


def _project_for(parsed: dict, roots: set[str]) -> str:
    if parsed["launch"]:
        return sessions._project_name(parsed["launch"], parsed["paths"], roots)
    paths = [p for p in parsed["paths"] if not _is_home_dot_tree(p)]
    if not paths:
        return ""
    return _root_vote(paths, roots) or _git_root_vote(paths)


def _root_vote(paths: list[str], roots: set[str]) -> str:
    if not roots:
        return ""
    votes: collections.Counter[str] = collections.Counter()
    for path in paths:
        containing = [r for r in roots if sessions._contains(r, path)]
        if containing:
            votes[min(containing, key=len)] += 1
    return _winning_basename(votes)


def _git_root(path: str) -> str | None:
    home = Path.home()
    current = Path(path)
    for candidate in (current, *current.parents):
        if candidate == home or not sessions._contains(str(home), str(candidate)):
            return None
        try:
            if (candidate / ".git").exists():
                return str(candidate)
        except OSError:
            return None
    return None


def _git_root_vote(paths: list[str]) -> str:
    votes: collections.Counter[str] = collections.Counter()
    for path in paths:
        root = _git_root(path)
        if root:
            votes[root] += 1
    return _winning_basename(votes)


def _winning_basename(votes: collections.Counter[str]) -> str:
    top = votes.most_common(2)
    if top and (len(top) == 1 or top[0][1] > top[1][1]):
        return os.path.basename(top[0][0])
    return ""
