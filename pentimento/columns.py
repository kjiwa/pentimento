"""`--columns`/`PENTIMENTO_COLUMNS` spec parsing and resolution.

Pure parsing, no dependency on `listing`; the caller passes the valid
column names, avoiding an import cycle.
"""

from __future__ import annotations

import dataclasses

ALL = "all"


@dataclasses.dataclass(frozen=True)
class Selection:
    absolute: tuple[str, ...] | None
    add: frozenset[str]
    remove: frozenset[str]


class EmptySelectionError(ValueError):
    """A relative selection removed every column."""


def _quoted(names) -> str:
    return ", ".join(f"'{name}'" for name in names)


def _error(message: str, valid: tuple[str, ...]) -> ValueError:
    return ValueError(f"{message}; valid columns: {', '.join(valid)}")


def _unknown_error(bad: set[str], valid: tuple[str, ...]) -> ValueError:
    return _error(f"unknown column: {_quoted(sorted(bad))}", valid)


def parse(spec: str, valid: tuple[str, ...]) -> Selection:
    """Parses a comma-separated `SPEC`: absolute names, `+`/`-` relative
    modifiers, or `all`. Raises `ValueError` on an empty, mixed, duplicate,
    or unknown-name spec, ending with `valid columns: ...`."""
    segments = [segment.strip() for segment in spec.split(",") if segment.strip()]
    if not segments:
        raise _error("empty column spec", valid)

    if segments == [ALL]:
        return Selection(absolute=valid, add=frozenset(), remove=frozenset())

    relative = [segment for segment in segments if segment[0] in "+-"]
    absolute = [segment for segment in segments if segment[0] not in "+-"]
    if relative and absolute:
        raise _error(f"cannot mix absolute and relative columns: '{spec}'", valid)

    if absolute:
        unknown = {name for name in absolute if name not in valid}
        if unknown:
            raise _unknown_error(unknown, valid)
        duplicates = {name for name in absolute if absolute.count(name) > 1}
        if duplicates:
            raise _error(f"duplicate column: {_quoted(sorted(duplicates))}", valid)
        return Selection(absolute=tuple(absolute), add=frozenset(), remove=frozenset())

    if any(len(segment) == 1 for segment in relative):
        raise _error(f"missing column name after +/-: '{spec}'", valid)

    add = {segment[1:] for segment in relative if segment[0] == "+"}
    remove = {segment[1:] for segment in relative if segment[0] == "-"}
    unknown = {name for name in add | remove if name not in valid}
    if unknown:
        raise _unknown_error(unknown, valid)
    return Selection(absolute=None, add=frozenset(add), remove=frozenset(remove))


def resolve(selection: Selection, default_names: tuple[str, ...]) -> list[str]:
    """Returns the ordered names to render.

    `default_names` is the content-derived default set, in canonical order.
    An absolute selection is the final word and keeps the given order. A
    relative selection removes `remove` from the default set, then appends
    the `add` names, sorted. Raises `EmptySelectionError` when nothing is left.
    """
    if selection.absolute is not None:
        return list(selection.absolute)

    names = [name for name in default_names if name not in selection.remove]
    names.extend(sorted(name for name in selection.add if name not in names))
    if not names:
        raise EmptySelectionError("--columns removes every column; keep at least one")
    return names
