"""Colour policy and ANSI primitives. No other module touches escape codes.

Widths must be computed on unpainted strings -- pad first, then paint, so
SGR bytes never enter a column width.
"""

from __future__ import annotations

import os
import shutil
import unicodedata

from pentimento import sources as sources_module
from pentimento import vocabulary as vocabulary_module

GUTTER = 2

Cell = tuple[str, tuple[str, ...]]

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

BLACK = "\033[30m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"

STATUS_CODES = {
    vocabulary_module.COMPLETE: (GREEN,),
    vocabulary_module.PARTIAL: (YELLOW,),
    vocabulary_module.NOT_STARTED: (BLUE,),
    vocabulary_module.SUPERSEDED: (DIM,),
    vocabulary_module.UNKNOWN: (DIM,),
}
assert set(STATUS_CODES) == set(vocabulary_module.STATUS_ORDER)

INTENT_CODES = {
    vocabulary_module.ACTIVE: (BOLD, MAGENTA),
    vocabulary_module.QUEUED: (CYAN,),
    vocabulary_module.SOMEDAY: (DIM,),
    vocabulary_module.ABANDONED: (DIM,),
    vocabulary_module.UNSET: (DIM,),
}
assert set(INTENT_CODES) == set(vocabulary_module.INTENT_VALUES)

SOURCE_CODES = {
    "claude": (CYAN,),
    "cursor": (MAGENTA,),
}
assert set(SOURCE_CODES) == set(sources_module.SOURCE_NAMES)


_COLOR_AUTO, _COLOR_ALWAYS, _COLOR_NEVER = "auto", "always", "never"
COLOR_CHOICES = (_COLOR_AUTO, _COLOR_ALWAYS, _COLOR_NEVER)


def enabled(stream, choice: str) -> bool:
    """Resolve a `--color` choice (`COLOR_CHOICES`) against a stream."""
    if choice == _COLOR_ALWAYS:
        return True
    if choice == _COLOR_NEVER:
        return False
    if not stream.isatty():
        return False
    if os.environ.get("NO_COLOR"):
        return False
    return os.environ.get("TERM") != "dumb"


def paint(text: str, *codes: str, on: bool) -> str:
    if not on or not codes:
        return text
    return "".join(codes) + text + RESET


def terminal_width() -> int:
    return shutil.get_terminal_size().columns


def terminal_height() -> int:
    return shutil.get_terminal_size().lines


def display_width(text: str) -> int:
    """Terminal column width: East Asian wide/fullwidth count 2, combining marks 0."""
    total = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return total


def split_width(text: str, width: int) -> tuple[str, str]:
    """Split `text` into the longest prefix fitting `width` display columns and the remainder.

    A combining mark rides along with the character it follows, same as
    every other display-width accumulation in this module.
    """
    used = 0
    for index, ch in enumerate(text):
        if unicodedata.combining(ch):
            continue
        char_width = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if used + char_width > width:
            return text[:index], text[index:]
        used += char_width
    return text, ""


def truncate(text: str, width: int, *, unicode_ok: bool) -> str:
    """Truncate `text` to `width` display columns, appending an ellipsis glyph."""
    ellipsis = "…" if unicode_ok else "..."
    ellipsis_width = display_width(ellipsis)
    if width <= 0 or display_width(text) <= width:
        return text
    if width <= ellipsis_width:
        kept, _ = split_width(text, width)
        return kept

    kept, _ = split_width(text, width - ellipsis_width)
    return kept.rstrip() + ellipsis


def render_cells(cells: list[Cell], separator: str, *, on_color: bool) -> tuple[str, str]:
    """Join `cells` with `separator`, returning the (plain, painted) pair."""
    plain = separator.join(text for text, _ in cells)
    painted = separator.join(paint(text, *codes, on=on_color) for text, codes in cells)
    return plain, painted


def truncate_cells(cells: list[Cell], separator: str, width: int, *, unicode_ok: bool, on_color: bool) -> str:
    """Join `cells` under a `width` column budget.

    Only the cell that straddles the limit is truncated, and its unpainted
    text is what gets truncated -- painting happens last, same invariant
    as everywhere else in this module.
    """
    sep_width = display_width(separator)
    parts = []
    used = 0
    for index, (text, codes) in enumerate(cells):
        gap = sep_width if index else 0
        text_width = display_width(text)
        if used + gap + text_width <= width:
            if gap:
                parts.append(separator)
            parts.append(paint(text, *codes, on=on_color))
            used += gap + text_width
            continue
        remaining = width - used - gap
        if remaining > 0:
            if gap:
                parts.append(separator)
            parts.append(paint(truncate(text, remaining, unicode_ok=unicode_ok), *codes, on=on_color))
        break
    return "".join(parts)


GLYPHS_UNICODE = {
    "branch": "├─ ",
    "last": "└─ ",
    "vertical": "│  ",
    "space": "   ",
    "ellipsis": "…",
}

GLYPHS_ASCII = {
    "branch": "+- ",
    "last": "`- ",
    "vertical": "|  ",
    "space": "   ",
    "ellipsis": "...",
}


def glyphs(unicode_ok: bool) -> dict:
    return GLYPHS_UNICODE if unicode_ok else GLYPHS_ASCII


def unicode_enabled(stream, ascii_flag: bool) -> bool:
    """Resolve whether Unicode glyphs are safe to emit on `stream`."""
    if ascii_flag:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return (stream.encoding or "").lower().startswith("utf")
