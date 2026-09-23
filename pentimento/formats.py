"""Machine-readable output: `json` and `tsv`."""

from __future__ import annotations

import json
import sys


def _scrub(text: str) -> str:
    return text.replace("\t", " ").replace("\n", " ").replace("\r", " ")


def _sanitize_tsv(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ",".join(_scrub(str(v)) for v in value)
    return _scrub(str(value))


def _emit_json(records, stream, columns) -> None:
    json.dump(records, stream, indent=2)
    stream.write("\n")


def _emit_tsv(records, stream, columns) -> None:
    if columns:
        stream.write("\t".join(columns) + "\n")
    for r in records:
        stream.write("\t".join(_sanitize_tsv(r.get(col)) for col in columns) + "\n")


FORMATS = {
    "json": _emit_json,
    "tsv": _emit_tsv,
}

TABLE = "table"  # the human format `emit` does not handle
CHOICES = (TABLE, *FORMATS)


def emit(records, fmt: str, stream=sys.stdout, columns: tuple = ()) -> None:
    """Emit `records` in `fmt`.

    `columns` names the record's scalar keys, in order, for `tsv`; a nested
    field like a tree node's `children` is left out by the caller rather
    than sniffed from the data, so it's dropped from the header and every
    row rather than silently truncated.
    """
    FORMATS[fmt](records, stream, columns)
