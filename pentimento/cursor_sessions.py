"""Read Cursor agent transcripts into per-plan sessions.

Cursor records each chat as `~/.cursor/projects/<slug>/agent-transcripts/
<uuid>/<uuid>.jsonl`. A transcript carries no plan id; its `CreatePlan` tool
call carries the plan's `name`, which is also the plan file's frontmatter
`name`. A plan gets a session only when that name pairs it with exactly one
transcript and no other plan -- a wrong project is worse than none. The
slug is the workspace path with every non-alphanumeric turned into `-`, so
the workspace root is the ancestor of a tool-call path that encodes to it.
"""

from __future__ import annotations

import collections
import os
import re
from pathlib import Path

from pentimento import cache as cache_module
from pentimento import frontmatter, sessions

_PATH_KEYS = ("path", "target_directory", "file_path")
_QUERY = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL)


def transcripts_directory() -> Path:
    return Path(os.environ.get("CURSOR_SESSIONS_DIR", str(Path.home() / ".cursor" / "projects")))


def load(plans, directory: Path | None = None) -> dict[str, sessions.Session]:
    directory = directory or transcripts_directory()
    if not directory.is_dir():
        return {}

    cached = cache_module.read("cursor_sessions")
    fresh: dict[str, dict] = {}
    by_name: dict[str, list[dict]] = collections.defaultdict(list)
    for log_path in sorted(directory.glob("*/agent-transcripts/*/*.jsonl")):
        try:
            cache_key = cache_module.key(log_path)
        except OSError:
            continue
        parsed = cached.get(cache_key)
        if parsed is None:
            parsed = _parse_transcript(log_path)
        fresh[cache_key] = parsed
        for name in set(parsed["names"]):
            by_name[name].append(parsed)
    cache_module.write("cursor_sessions", fresh)

    plans = [p for p in plans if p.source == "cursor"]
    claimed = collections.Counter(_plan_name(p) for p in plans)
    return {
        plan.id: sessions.Session(
            slug=plan.id,
            project=by_name[name][0]["project"],
            started=plan.started,
            prompt=by_name[name][0]["prompt"],
            ended=plan.ended,
        )
        for plan in plans
        if (name := _plan_name(plan)) and claimed[name] == 1 and len(by_name.get(name, [])) == 1
    }


def _plan_name(plan) -> str:
    line = plan.extras.unknown_lines.get("name", "") if plan.extras else ""
    return frontmatter.clean_value(line.partition(":")[2])


def _parse_transcript(log_path: Path) -> dict:
    names: list[str] = []
    paths: list[str] = []
    prompt = None
    for record in sessions.read_records(log_path):
        if prompt is None and record.get("role") == "user":
            prompt = _query_text(record)
        names.extend(_created_plan_names(record))
        paths.extend(_tool_paths(record))
    return {
        "names": names,
        "prompt": prompt or "",
        "project": _workspace_name(log_path.parent.parent.parent.name, paths),
    }


def _tool_calls(record: dict):
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    for block in content if isinstance(content, list) else []:
        if (
            isinstance(block, dict)
            and block.get("type") == "tool_use"
            and isinstance(block.get("input"), dict)
        ):
            yield block.get("name"), block["input"]


def _created_plan_names(record: dict) -> list[str]:
    return [
        tool_input["name"]
        for name, tool_input in _tool_calls(record)
        if name == "CreatePlan" and isinstance(tool_input.get("name"), str)
    ]


def _tool_paths(record: dict) -> list[str]:
    return [
        tool_input[key]
        for _, tool_input in _tool_calls(record)
        for key in _PATH_KEYS
        if isinstance(tool_input.get(key), str)
    ]


def _query_text(record: dict) -> str | None:
    text = sessions.prompt_text(record)
    match = _QUERY.search(text) if text is not None else None
    return match.group(1) if match else text


def _encode(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", path).lstrip("-")


def _workspace_name(slug: str, paths: list[str]) -> str:
    roots = {
        candidate
        for path in paths
        for candidate in (Path(path), *Path(path).parents)
        if _encode(str(candidate)) == slug
    }
    return roots.pop().name if len(roots) == 1 else ""
