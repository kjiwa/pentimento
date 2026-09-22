"""`--columns`/`PENTIMENTO_COLUMNS` spec parsing and resolution.

Pure parsing, no dependency on `listing` -- the caller passes the valid
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


def _unknown_error(bad: set[str], valid: tuple[str, ...]) -> ValueError:
    return ValueError(
        f"unknown column: {', '.join(sorted(bad))} -- valid columns: {', '.join(valid)}"
    )


def parse(spec: str, valid: tuple[str, ...]) -> Selection:
    """Parses a comma-separated `SPEC`: absolute names, `+`/`-` relative
    modifiers, or `all`. Raises `ValueError` on an empty, mixed, duplicate,
    or unknown-name spec, ending with `valid columns: ...`."""
    segments = [segment.strip() for segment in spec.split(",") if segment.strip()]
    if not segments:
        raise ValueError(f"empty column spec -- valid columns: {', '.join(valid)}")

    if segments == [ALL]:
        return Selection(absolute=valid, add=frozenset(), remove=frozenset())

    relative = [segment for segment in segments if segment[0] in "+-"]
    absolute = [segment for segment in segments if segment[0] not in "+-"]
    if relative and absolute:
        raise ValueError(
            f"cannot mix absolute and relative columns: {spec} -- valid columns: {', '.join(valid)}"
        )

    if absolute:
        unknown = {name for name in absolute if name not in valid}
        if unknown:
            raise _unknown_error(unknown, valid)
        duplicates = {name for name in absolute if absolute.count(name) > 1}
        if duplicates:
            raise ValueError(
                f"duplicate column: {', '.join(sorted(duplicates))} -- "
                f"valid columns: {', '.join(valid)}"
            )
        return Selection(absolute=tuple(absolute), add=frozenset(), remove=frozenset())

    add = {segment[1:] for segment in relative if segment[0] == "+"}
    remove = {segment[1:] for segment in relative if segment[0] == "-"}
    unknown = {name for name in add | remove if name not in valid}
    if unknown:
        raise _unknown_error(unknown, valid)
    return Selection(absolute=None, add=frozenset(add), remove=frozenset(remove))


def resolve(
    selection: Selection, default_names: tuple[str, ...], pin: tuple[str, ...]
) -> tuple[list[str], set[str]]:
    """Returns the ordered names to render and the set that must never drop.

    `default_names` is the content-derived default set, in canonical order.
    An absolute selection is the final word: it keeps the given order and
    every name in it is pinned; the sort key's pin does not extend it. A
    relative selection keeps canonical order, applies `add`/`remove` on top
    of the default set, and pins every explicitly added name plus `pin`.
    """
    if selection.absolute is not None:
        names = list(selection.absolute)
        return names, set(names)

    names = [name for name in default_names if name not in selection.remove]
    extra = sorted(name for name in selection.add if name not in names)
    names.extend(extra)
    never_drop = set(selection.add) | set(pin)
    return names, never_drop
