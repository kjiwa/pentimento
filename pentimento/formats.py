"""Machine-readable output: `json` and `tsv`."""

from __future__ import annotations

import json
import sys


def _sanitize_tsv(value) -> str:
    if value is None:
        return ""
    return str(value).replace("\t", " ").replace("\n", " ")


def _tsv_columns(records) -> tuple:
    """Scalar keys of the first record, in insertion order.

    Non-scalar fields (e.g. a tree node's `children`) can't round-trip
    through TSV, so they're dropped rather than silently truncated per row.
    """
    if not records:
        return ()
    return tuple(k for k, v in records[0].items() if not isinstance(v, (list, dict)))


def _emit_json(records, stream) -> None:
    json.dump(records, stream, indent=2)
    stream.write("\n")


def _emit_tsv(records, stream) -> None:
    columns = _tsv_columns(records)
    if columns:
        stream.write("\t".join(columns) + "\n")
    for r in records:
        stream.write("\t".join(_sanitize_tsv(r.get(col)) for col in columns) + "\n")


FORMATS = {
    "json": _emit_json,
    "tsv": _emit_tsv,
}


def emit(records, fmt: str, stream=sys.stdout) -> None:
    FORMATS[fmt](records, stream)
