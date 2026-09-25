"""Derive `status` from a plan's `## Progress` section, Cursor todos, or checkboxes.

Three signals, in order:
1. The `## Progress` section. Checkbox ratio (`- [x]` vs `- [ ]`): all-checked
   is complete, all-unchecked is not-started, mixed is partial. A section with
   no checkboxes falls back to prose such as "Nothing started" or "Planning
   only".
2. The `todos:` frontmatter block that Cursor writes: all `pending` is
   not-started, all `completed` is complete, any other mix of `pending`,
   `in_progress`, and `completed` is partial.
3. The checkbox ratio over the whole body, only when there is no `## Progress`
   heading.

Everything else stays `unknown` -- guessing "complete" on a stale plan is
the one failure mode that loses work, so an absent or ambiguous signal must
never be upgraded to a real status.
"""

from __future__ import annotations

import re

from pentimento import frontmatter, vocabulary

CHECKBOX_RE = re.compile(r"^\s*-\s*\[([ xX])\]", re.MULTILINE)

TODO_ITEM_RE = re.compile(r"^\s*-(\s+)")
TODO_STATUS_RE = re.compile(r"^status:(.*)$")
TODO_STATUSES = ("pending", "in_progress", "completed")

PROGRESS = "'## Progress'"
TODOS = "todos"
CHECKBOXES = "body checkboxes"

NOT_STARTED_PHRASES = (
    "nothing started",
    "planning only",
    "not started",
    "no progress",
)


def progress_section(body: str) -> str | None:
    lines = body.split("\n")
    start = None
    for index, line in enumerate(lines):
        if line.strip().lower() == "## progress":
            start = index + 1
            break
    if start is None:
        return None

    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end])


def _from_checkboxes(section: str) -> str | None:
    marks = CHECKBOX_RE.findall(section)
    if not marks:
        return None
    checked = sum(1 for m in marks if m.lower() == "x")
    if checked == len(marks):
        return vocabulary.COMPLETE
    if checked == 0:
        return vocabulary.NOT_STARTED
    return vocabulary.PARTIAL


def _from_prose(section: str) -> str | None:
    lowered = section.lower()
    if any(phrase in lowered for phrase in NOT_STARTED_PHRASES):
        return vocabulary.NOT_STARTED
    return None


def rank(status: str) -> int:
    """Position in `PROGRESS_ORDER`, or -1 for a status derivation can't produce."""
    order = vocabulary.PROGRESS_ORDER
    return order.index(status) if status in order else -1


def _todo_block(extras: frontmatter.Extras) -> list[str]:
    """Lines of the top-level `todos:` block, up to the next top-level key."""
    block: list[str] = []
    in_todos = False
    for line in extras.lines:
        if not line.strip():
            continue
        if line[:1] not in (" ", "\t") and not line.startswith("- "):
            in_todos = line.strip() == "todos:"
        elif in_todos:
            block.append(line)
    return block


def has_todos(extras: frontmatter.Extras) -> bool:
    return bool(_todo_block(extras))


def todo_statuses(extras: frontmatter.Extras) -> list[str]:
    """Each todo item's `status:` value, read on the item's own `- ` line or key column."""
    values: list[str] = []
    item_indent: int | None = None
    key_indent = -1
    for line in _todo_block(extras):
        indent = len(line) - len(line.lstrip())
        item = TODO_ITEM_RE.match(line)
        if item and item_indent in (None, indent):
            item_indent = indent
            key_indent = item.end(1)
            line = line[key_indent:]
            indent = key_indent
        if indent == key_indent and (m := TODO_STATUS_RE.match(line.strip())):
            values.append(frontmatter.clean_value(m.group(1)))
    return values


def _from_todos(extras: frontmatter.Extras | None) -> str | None:
    if extras is None:
        return None
    values = todo_statuses(extras)
    if not values or any(v not in TODO_STATUSES for v in values):
        return None
    if all(v == "pending" for v in values):
        return vocabulary.NOT_STARTED
    if all(v == "completed" for v in values):
        return vocabulary.COMPLETE
    return vocabulary.PARTIAL


def _from_progress(body: str) -> str | None:
    section = progress_section(body)
    if section is None:
        return None
    return _from_checkboxes(section) or _from_prose(section)


def derive(body: str, extras: frontmatter.Extras | None = None) -> tuple[str, str | None]:
    """The derived status and the signal that produced it, or `("unknown", None)`."""
    if found := _from_progress(body):
        return found, PROGRESS
    if found := _from_todos(extras):
        return found, TODOS
    if progress_section(body) is None and (found := _from_checkboxes(body)):
        return found, CHECKBOXES
    return vocabulary.UNKNOWN, None


def derive_status(body: str, extras: frontmatter.Extras | None = None) -> str:
    return derive(body, extras)[0]
