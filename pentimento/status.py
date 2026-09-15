"""Derive `status` from a plan's `## Progress` section.

Two signals, in order:
1. Checkbox ratio (`- [x]` vs `- [ ]`): all-checked is complete, all-unchecked
   is not-started, mixed is partial.
2. Prose fallback for sections with no checkboxes at all, e.g. "Nothing
   started" or "Planning only".

A body with no `## Progress` heading at all -- e.g. a Cursor plan, which has
no such convention -- falls back to the checkbox ratio over the whole body.

Everything else stays `unknown` -- guessing "complete" on a stale plan is
the one failure mode that loses work, so an absent or ambiguous signal must
never be upgraded to a real status.
"""

from __future__ import annotations

import re

from pentimento import vocabulary

CHECKBOX_RE = re.compile(r"^\s*-\s*\[([ xX])\]", re.MULTILINE)

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


def derive_status(body: str) -> str:
    section = progress_section(body)
    if section is None:
        return _from_checkboxes(body) or vocabulary.UNKNOWN
    return _from_checkboxes(section) or _from_prose(section) or vocabulary.UNKNOWN
