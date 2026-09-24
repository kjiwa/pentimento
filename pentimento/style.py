"""Color policy and ANSI primitives. No other module touches escape codes.

Widths must be computed on unpainted strings -- pad first, then paint, so
SGR bytes never enter a column width.
"""

from __future__ import annotations

import os
import shutil
import sys
import unicodedata

from pentimento import vocabulary as vocabulary_module

GUTTER = 2
ELLIPSIS = "..."


def _require_matching_keys(mapping: dict, expected, what: str) -> None:
    if set(mapping) != set(expected):
        raise ValueError(f"{what} out of sync with its keys")


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
_require_matching_keys(STATUS_CODES, vocabulary_module.STATUS_ORDER, "STATUS_CODES")

INTENT_CODES = {
    vocabulary_module.ACTIVE: (BOLD, MAGENTA),
    vocabulary_module.QUEUED: (CYAN,),
    vocabulary_module.SOMEDAY: (DIM,),
    vocabulary_module.ABANDONED: (DIM,),
    vocabulary_module.UNSET: (DIM,),
}
_require_matching_keys(INTENT_CODES, vocabulary_module.INTENT_VALUES, "INTENT_CODES")

SOURCE_CODES = {
    "claude": (CYAN,),
    "cursor": (MAGENTA,),
}


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


def terminal_width() -> int | None:
    """`COLUMNS` if set, else the tty width on a tty, else `None` (unbounded)."""
    columns = os.environ.get("COLUMNS", "")
    if columns.isdigit() and int(columns) > 0:
        return int(columns)
    if sys.stdout.isatty():
        return shutil.get_terminal_size().columns
    return None


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


def truncate(text: str, width: int) -> str:
    """Truncate `text` to `width` display columns, appending an ellipsis."""
    ellipsis_width = display_width(ELLIPSIS)
    if width <= 0 or display_width(text) <= width:
        return text
    if width <= ellipsis_width:
        kept, _ = split_width(text, width)
        return kept

    kept, _ = split_width(text, width - ellipsis_width)
    return kept.rstrip() + ELLIPSIS


def render_cells(cells: list[Cell], separator: str, *, on_color: bool) -> tuple[str, str]:
    """Join `cells` with `separator`, returning the (plain, painted) pair."""
    plain = separator.join(text for text, _ in cells)
    painted = separator.join(paint(text, *codes, on=on_color) for text, codes in cells)
    return plain, painted


def _chunks(text: str, width: int) -> list[str]:
    """Hard-wrap `text` into pieces of at most `width` display columns."""
    pieces = []
    while text:
        piece, text = split_width(text, width)
        if not piece:
            piece, text = text[:1], text[1:]
        pieces.append(piece)
    return pieces


def wrap(text: str, width: int) -> list[str]:
    """Wrap `text` at spaces to `width` display columns; a word wider than
    `width` hard-wraps."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if display_width(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        *full, current = _chunks(word, width)
        lines.extend(full)
    if current:
        lines.append(current)
    return lines or [""]


def wrap_fields(
    cells: list[Cell], separator: str, width: int | None, indent: str, *, on_color: bool
) -> list[str]:
    """Pack `cells` onto lines of at most `width` columns, each starting with
    `indent`. A line breaks only between cells; a cell wider than the line
    hard-wraps. Painting happens last, on the unpainted pieces.
    """
    room = None if width is None else max(1, width - display_width(indent))
    sep_width = display_width(separator)
    lines: list[list[str]] = [[]]
    used = 0
    for text, codes in cells:
        pieces = [text] if room is None else _chunks(text, room)
        for index, piece in enumerate(pieces):
            gap = sep_width if lines[-1] and not index else 0
            piece_width = display_width(piece)
            if lines[-1] and (index or (room is not None and used + gap + piece_width > room)):
                lines.append([])
                used, gap = 0, 0
            if gap:
                lines[-1].append(separator)
            lines[-1].append(paint(piece, *codes, on=on_color))
            used += gap + piece_width
    return [indent + "".join(parts) for parts in lines if parts]


GLYPHS = {
    "branch": "|-- ",
    "last": "`-- ",
    "vertical": "|   ",
    "space": "    ",
}
