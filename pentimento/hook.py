"""Pure parsing for the `pentimento hook` PostToolUse entry point.

Claude Code names the written file in `tool_input.file_path`; Antigravity in
`toolCall.args.Path` (or legacy `toolCall.args.TargetFile`), and requires the
hook to answer with a JSON object.

No corpus or session loading here -- everything that touches the filesystem
belongs in `cli.cmd_hook`, so this module stays trivially testable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pentimento import sessions
from pentimento import sources as sources_module


def _payload(text: str) -> dict | None:
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _is_antigravity_payload(payload: dict | None) -> bool:
    return payload is not None and any(
        key in payload for key in ("artifactDirectoryPath", "conversationId", "toolCall")
    )


def is_antigravity(text: str) -> bool:
    """Whether `text` is an Antigravity hook payload, which must be answered with JSON."""
    return _is_antigravity_payload(_payload(text))


def _is_usable_workspace(path: object) -> bool:
    if not isinstance(path, str) or not os.path.isabs(path):
        return False
    normalized = os.path.normpath(path)
    home = str(Path.home())
    if normalized == home:
        return False
    return not sessions._contains(str(Path.home() / ".gemini"), normalized)


def antigravity_workspace(text: str) -> str | None:
    """Workspace directory from an Antigravity hook payload, or None."""
    payload = _payload(text)
    if not _is_antigravity_payload(payload):
        return None
    candidates = [payload.get("cwd")]
    workspace_paths = payload.get("workspacePaths")
    if isinstance(workspace_paths, list):
        candidates.extend(workspace_paths)
    for candidate in candidates:
        if _is_usable_workspace(candidate):
            return os.path.normpath(candidate)
    return None


def _written_file(payload: dict):
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict) and "file_path" in tool_input:
        return tool_input["file_path"]
    tool_call = payload.get("toolCall")
    args = tool_call.get("args") if isinstance(tool_call, dict) else None
    if not isinstance(args, dict):
        return None
    return args.get("Path") or args.get("TargetFile")


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
