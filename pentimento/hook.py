"""Pure parsing for the `pentimento hook` PostToolUse entry point.

No corpus or session loading here -- everything that touches the filesystem
belongs in `cli.cmd_hook`, so this module stays trivially testable.
"""

from __future__ import annotations

import json
from pathlib import Path

from pentimento import sources as sources_module


def touched_plan_path(text: str) -> Path | None:
    """The plan file a PostToolUse payload wrote, or None."""
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None

    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str):
        return None

    path = Path(file_path).expanduser()
    for source in sources_module.all_sources():
        if sources_module.contains(source, path):
            return path
    return None
