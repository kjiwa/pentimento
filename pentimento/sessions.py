"""Read harness session transcripts into a slug-keyed index.

Each Claude Code session is recorded as `~/.claude/projects/<encoded-dir>/
<uuid>.jsonl`, one line per event. Lines carry a `slug` (identical to the
plan filename stem this session produced, when it produced one), a `cwd`,
and, for user lines, the prompt text. Absent or unreadable directories yield
an empty index -- pentimento must stay usable without a harness.
"""

from __future__ import annotations

import collections
import dataclasses
import json
import os
import re
from pathlib import Path

from pentimento import cache as cache_module


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

    cached = cache_module.read("sessions")
    fresh: dict[str, dict] = {}
    by_slug: dict[str, dict] = {}
    for project_dir in sorted(p for p in directory.iterdir() if p.is_dir()):
        _load_project(project_dir, cached, fresh, by_slug)
    cache_module.write("sessions", fresh)

    roots = _launch_roots(by_slug.values())
    return {
        slug: Session(
            slug=slug,
            project=_project_name(entry["cwds"], entry["paths"], roots),
            started=entry["started"] or "",
            prompt=entry["prompt"] or "",
            ended=entry["ended"] or "",
        )
        for slug, entry in by_slug.items()
    }


def _load_project(project_dir: Path, cached: dict, fresh: dict, by_slug: dict[str, dict]) -> None:
    for log_path in sorted(project_dir.glob("*.jsonl")):
        cache_key = cache_module.key(log_path)
        partials = cached.get(cache_key)
        if partials is None:
            partials = _parse_log(log_path)
        fresh[cache_key] = partials
        for slug, partial in partials.items():
            _merge_slug(by_slug, slug, partial)


def _parse_log(log_path: Path) -> dict[str, dict]:
    partials: dict[str, dict] = {}
    for record in read_records(log_path):
        slug = record.get("slug")
        if not slug:
            continue
        entry = partials.setdefault(slug, _empty_entry())
        cwd = record.get("cwd")
        if cwd:
            entry["cwds"].append(cwd)
            entry["launch"] = entry["launch"] or cwd
        timestamp = record.get("timestamp")
        if timestamp and (entry["started"] is None or timestamp < entry["started"]):
            entry["started"] = timestamp
        if timestamp and (entry["ended"] is None or timestamp > entry["ended"]):
            entry["ended"] = timestamp
        if (
            timestamp
            and record.get("type") == "user"
            and (entry["prompt_ts"] is None or timestamp < entry["prompt_ts"])
        ):
            text = prompt_text(record)
            if text is not None:
                entry["prompt"] = text
                entry["prompt_ts"] = timestamp
        entry["paths"].extend(home_paths(record))
    for entry in partials.values():
        if not _is_home_rooted(entry["cwds"]):
            entry["paths"] = []
    return partials


def _merge_slug(by_slug: dict[str, dict], slug: str, partial: dict) -> None:
    entry = by_slug.setdefault(slug, _empty_entry())
    entry["cwds"].extend(partial["cwds"])
    entry["paths"].extend(partial["paths"])
    if partial["launch"] and (
        entry["launch"] is None
        or (partial["started"] and entry["started"] and partial["started"] < entry["started"])
    ):
        entry["launch"] = partial["launch"]
    if partial["started"] and (entry["started"] is None or partial["started"] < entry["started"]):
        entry["started"] = partial["started"]
    if partial["ended"] and (entry["ended"] is None or partial["ended"] > entry["ended"]):
        entry["ended"] = partial["ended"]
    if partial["prompt_ts"] and (
        entry["prompt_ts"] is None or partial["prompt_ts"] < entry["prompt_ts"]
    ):
        entry["prompt"] = partial["prompt"]
        entry["prompt_ts"] = partial["prompt_ts"]


def read_records(log_path: Path):
    try:
        with log_path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    yield record
    except OSError:
        return


def prompt_text(record: dict) -> str | None:
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        blocks = [
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        ]
        return "\n".join(blocks)
    return None


def _empty_entry() -> dict:
    return {
        "cwds": [],
        "paths": [],
        "launch": None,
        "started": None,
        "ended": None,
        "prompt": None,
        "prompt_ts": None,
    }


def _is_home_rooted(cwds) -> bool:
    cwds = [c for c in cwds if os.path.isabs(c)]
    return bool(cwds) and os.path.commonpath(cwds) == str(Path.home())


def home_paths(record: dict) -> list[str]:
    """Absolute paths under home named in a record's tool calls."""
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    pattern = re.escape(str(Path.home())) + r"/[^\s\"'\\,;:)`>*]+"
    return [
        path.rstrip(".")
        for block in content
        if isinstance(block, dict) and block.get("type") == "tool_use"
        for path in re.findall(pattern, json.dumps(block.get("input", {})))
    ]


def _launch_roots(entries) -> set[str]:
    home = Path.home()
    return {
        e["launch"]
        for e in entries
        if e["launch"] and _contains(str(home), e["launch"]) and e["launch"] != str(home)
    }


def _contains(root: str, path: str) -> bool:
    return path == root or path.startswith(root + os.sep)


def _project_name(cwds, paths, roots) -> str:
    cwds = [c for c in cwds if os.path.isabs(c)]
    if not cwds:
        return ""
    common = os.path.commonpath(cwds)
    if common == str(Path.home()):
        return _launch_root_name(cwds + paths, roots)
    return os.path.basename(common)


def _launch_root_name(evidence, roots) -> str:
    """Home is where every terminal opens, so a session rooted there says
    nothing about intent; the launch directory its work lands in does."""
    votes = collections.Counter()
    for path in evidence:
        containing = [r for r in roots if _contains(r, path)]
        if containing:
            votes[min(containing, key=len)] += 1
    top = votes.most_common(2)
    if top and (len(top) == 1 or top[0][1] > top[1][1]):
        return os.path.basename(top[0][0])
    return Path.home().name
