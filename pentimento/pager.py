"""Pipe rendered lines through the user's pager.

Colour and width are resolved against the real stdout before this module is
reached, so the pager receives exactly what a tty would have shown.
"""

from __future__ import annotations

import os
import shlex
import subprocess

_DEFAULT_PAGER = ["less"]
_LESS_DEFAULT = "FRX"


def command() -> list[str] | None:
    """The pager argv from `PAGER`, `less` if unset, None if empty or unparseable."""
    raw = os.environ.get("PAGER")
    if raw is None:
        return list(_DEFAULT_PAGER)
    try:
        return shlex.split(raw) or None
    except ValueError:
        return None


def _environment(argv: list[str]) -> dict[str, str]:
    """`LESS=FRX` when the pager is `less` and the operator has not set `LESS`.

    -R keeps ANSI colour, -F exits at once for one-screen output, -X leaves
    the text on screen after quitting.
    """
    env = dict(os.environ)
    if os.path.basename(argv[0]) == "less":
        env.setdefault("LESS", _LESS_DEFAULT)
    return env


def page(lines: list[str]) -> None:
    """Show `lines` in the pager, or print them if none can be started."""
    argv = command()
    if argv is None:
        _print(lines)
        return
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, env=_environment(argv), text=True)
    except OSError:
        _print(lines)
        return
    try:
        with proc.stdin:
            proc.stdin.write("\n".join(lines) + "\n")
    except BrokenPipeError:
        pass
    _wait(proc)


def _wait(proc: subprocess.Popen) -> None:
    """Wait out the pager, leaving Ctrl-C to it as `git` does."""
    while True:
        try:
            proc.wait()
            return
        except KeyboardInterrupt:
            continue


def _print(lines: list[str]) -> None:
    for line in lines:
        print(line)
