"""Pure parsing for the `pentimento hook` PostToolUse entry point.

Claude Code names the written file in `tool_input.file_path`; Antigravity in
`toolCall.args.TargetFile`, and requires the hook to answer with a JSON object.

No corpus or session loading here -- everything that touches the filesystem
belongs in `cli.cmd_hook`, so this module stays trivially testable.
"""

from __future__ import annotations

import json
from pathlib import Path

from pentimento import sources as sources_module


def _payload(text: str) -> dict | None:
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def is_antigravity(text: str) -> bool:
    """Whether `text` is an Antigravity hook payload, which must be answered with JSON."""
    payload = _payload(text)
    return payload is not None and any(
        key in payload for key in ("artifactDirectoryPath", "conversationId", "toolCall")
    )


def _written_file(payload: dict):
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict) and "file_path" in tool_input:
        return tool_input["file_path"]
    tool_call = payload.get("toolCall")
    args = tool_call.get("args") if isinstance(tool_call, dict) else None
    return args.get("TargetFile") if isinstance(args, dict) else None


def touched_plan_path(text: str) -> Path | None:
    """The plan file a PostToolUse payload wrote, or None."""
    payload = _payload(text)
    if payload is None:
        return None

    file_path = _written_file(payload)
    if not isinstance(file_path, str):
        return None

    path = Path(file_path).expanduser()
    for source in sources_module.all_sources():
        if sources_module.contains(source, path):
            return path
    return None
