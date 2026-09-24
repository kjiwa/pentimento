"""Operator-owned tags: a flow-style list frontmatter can round-trip as one scalar."""

from __future__ import annotations

import re

from pentimento import style

PATTERN = r"^[a-z0-9][a-z0-9._/-]*$"
_VALID = re.compile(PATTERN)


def parse(raw: str | None) -> list[str]:
    """Parse `[a, b]` or bare `a, b` into a sorted, deduped list.

    Faithful to case: does not normalize, so `check` can flag a hand-written
    `Auth`.
    """
    if not raw:
        return []
    text = raw.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    values = {v.strip() for v in text.split(",")}
    values.discard("")
    return sorted(values)


def render(tags) -> str:
    if not tags:
        return ""
    return "[" + ", ".join(tags) + "]"


def shorten(rendered: str, width: int) -> str:
    """Fit a `render`ed tag list to `width`: whole tags, then `+N` for the rest."""
    if style.display_width(rendered) <= width:
        return rendered
    tags = rendered[1:-1].split(", ")
    for kept in range(len(tags) - 1, -1, -1):
        candidate = render([*tags[:kept], f"+{len(tags) - kept}"])
        if style.display_width(candidate) <= width:
            return candidate
    return style.truncate(rendered, width)


def normalize(tag: str) -> str:
    return tag.strip().lower()


def normalized(tags) -> set[str]:
    return {normalize(t) for t in tags}


def is_valid(tag: str) -> bool:
    return bool(_VALID.match(tag))
