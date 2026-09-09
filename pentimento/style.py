"""Colour policy and ANSI primitives. No other module touches escape codes.

Widths must be computed on unpainted strings -- pad first, then paint, so
SGR bytes never enter a column width.
"""

from __future__ import annotations

import os
import shutil

from pentimento import check
from pentimento import index as index_module

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
    "complete": (GREEN,),
    "partial": (YELLOW,),
    "not-started": (BLUE,),
    "superseded": (DIM,),
    "unknown": (DIM,),
}
assert set(STATUS_CODES) == set(index_module.STATUS_ORDER)

INTENT_CODES = {
    "active": (BOLD, MAGENTA),
    "queued": (CYAN,),
    "someday": (DIM,),
    "abandoned": (DIM,),
    "unset": (DIM,),
}
assert set(INTENT_CODES) == set(check.INTENT_VALUES)


def enabled(stream, choice: str) -> bool:
    """Resolve a `--color {auto,always,never}` choice against a stream."""
    if choice == "always":
        return True
    if choice == "never":
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
