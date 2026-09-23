"""Flat scalar frontmatter: no PyYAML, zero runtime dependencies.

A frontmatter block is recognized only when the file's first three bytes are
literally "---\n" -- never a "---" line anywhere else in the body. Plan
bodies use "---" as a Markdown horizontal rule; treating any mid-body match
as a delimiter would silently corrupt those files.
"""

from __future__ import annotations

import dataclasses
import re

DELIMITER = "---"

NAMESPACE = "pentimento"
INDENT = "  "

# Canonical field order for serialization; the reader accepts any order.
FIELD_ORDER = ("status", "pinned", "intent", "tags", "parent", "project", "created")

# Sentinel marking, within `Extras.lines`, where the pentimento block goes.
# Everything else in `Extras.lines` is foreign raw text re-emitted verbatim.
_MARKER = "\x00pentimento-block\x00"


@dataclasses.dataclass
class Extras:
    """Everything in a frontmatter block that isn't a pentimento field.

    `lines` holds the block's raw lines -- foreign top-level blocks (with
    their indented children), comments, and blank lines -- in their original
    order, with `_MARKER` standing in for where the pentimento block goes.
    `newline` is the line ending the source file used, so re-emitting it
    doesn't silently normalize CRLF to LF (or the reverse). `unknown_lines`
    maps each unrecognized top-level key to its original line, re-emitted
    as written so a value that could not be rebuilt from its parsed form
    (`name: Plan: the sequel`) survives.
    """

    lines: list[str]
    newline: str = "\n"
    unknown_lines: dict[str, str] = dataclasses.field(default_factory=dict)


def is_valid_value(value: str) -> bool:
    """A value survives round-tripping through a `key: value` line.

    Leading/trailing whitespace, `#` (starts a comment), `: ` (looks like a
    nested key), and newlines would all corrupt a re-emitted line or let a
    hand-edited value inject one. Same shape of guard as `tags.is_valid`.
    """
    if value != value.strip():
        return False
    return not any(bad in value for bad in ("\n", "\r", "#", ": "))


def _validate_values(fields: dict[str, str], skip=()) -> None:
    for key, value in fields.items():
        if key not in skip and not is_valid_value(value):
            raise ValueError(f"invalid frontmatter value for {key!r}: {value!r}")


def parse(text: str) -> tuple[dict[str, str], str, Extras | None]:
    """Split text into (frontmatter fields, body, extras).

    Returns an empty dict, the whole text unchanged, and no extras if text
    does not begin with a frontmatter block at byte 0.
    """
    if text.startswith(DELIMITER + "\r\n"):
        nl = "\r\n"
    elif text.startswith(DELIMITER + "\n"):
        nl = "\n"
    else:
        return {}, text, None

    lines = text.split(nl)
    closing_index = _find_closing_delimiter(lines)
    if closing_index is None:
        return {}, text, None

    fields, raw_lines, unknown_lines = _parse_block(lines[1:closing_index])
    body = nl.join(lines[closing_index + 1 :])
    return fields, body, Extras(lines=raw_lines, newline=nl, unknown_lines=unknown_lines)


def _find_closing_delimiter(lines: list[str]) -> int | None:
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == DELIMITER:
            return index
    return None


# A `#` starts a comment only at the value's start or after whitespace, so
# `url: http://x/#a` keeps its fragment.
_COMMENT = re.compile(r"(?:^|\s)#")


def _clean_value(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    if value.startswith('"'):
        end = value.find('"', 1)
        if end != -1:
            return value[1:end]
        return value[1:].strip()
    if value.startswith("'"):
        end = value.find("'", 1)
        if end != -1:
            return value[1:end]
        return value[1:].strip()
    return _COMMENT.split(value, maxsplit=1)[0].strip()


def _parse_block(lines: list[str]) -> tuple[dict[str, str], list[str], dict[str, str]]:
    """Parse pentimento fields while capturing everything else verbatim.

    A comment or blank line inside the pentimento block is dropped (there is
    nowhere to re-anchor it once fields are re-emitted in canonical order).
    Everywhere else -- outside the block, or inside a foreign sibling block
    -- comments, blank lines, and unrecognized content are preserved in
    `extras` so they survive a re-emit unchanged.
    """
    fields: dict[str, str] = {}
    extras: list[str] = []
    unknown_lines: dict[str, str] = {}
    in_namespace = False
    marker_inserted = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if not in_namespace:
                extras.append(line)
            continue
        if ":" not in line:
            if not in_namespace:
                extras.append(line)
            continue
        indented = line[:1] in (" ", "\t")
        key, _, raw_value = line.partition(":")
        key = key.strip()
        value = _clean_value(raw_value)
        if not indented and key == NAMESPACE and not value:
            in_namespace = True
            if not marker_inserted:
                extras.append(_MARKER)
                marker_inserted = True
            continue
        if not indented:
            in_namespace = False
        if indented and not in_namespace:
            extras.append(line)
            continue
        if indented and in_namespace:
            if value:
                fields[key] = value
            continue
        if value:
            fields[key] = value
            if key not in FIELD_ORDER:
                unknown_lines[key] = line
        else:
            extras.append(line)
    if not marker_inserted:
        extras.insert(0, _MARKER)
    return fields, extras, unknown_lines


def serialize(fields: dict[str, str], body: str, extras: Extras | None = None) -> str:
    """Render fields plus body back into text, in FIELD_ORDER.

    Known fields (`FIELD_ORDER`) are emitted nested under a `pentimento:`
    opener, indented, in canonical order. Fields absent from `fields` are
    omitted. Unknown keys are emitted unindented after the block, outside
    the namespace, so parse reads them back as top-level fields. Body bytes
    are never touched. `extras`, when given, restores foreign blocks,
    comments, and blank lines to their original position, and the source
    file's line ending.
    """
    if not fields:
        return body

    unknown_lines = extras.unknown_lines if extras is not None else {}
    _validate_values(fields, skip=unknown_lines)

    known = set(FIELD_ORDER)
    namespaced = [key for key in FIELD_ORDER if key in fields]
    unknown = [key for key in fields if key not in known]

    pentimento_block: list[str] = []
    if namespaced:
        pentimento_block.append(f"{NAMESPACE}:")
        for key in namespaced:
            pentimento_block.append(f"{INDENT}{key}: {fields[key]}")
    for key in unknown:
        pentimento_block.append(unknown_lines.get(key) or f"{key}: {fields[key]}")

    raw_lines = list(extras.lines) if extras is not None else [_MARKER]
    if _MARKER not in raw_lines:
        raw_lines = [_MARKER, *raw_lines]

    lines = [DELIMITER]
    for raw_line in raw_lines:
        if raw_line == _MARKER:
            lines.extend(pentimento_block)
        else:
            lines.append(raw_line)
    lines.append(DELIMITER)

    nl = extras.newline if extras is not None else "\n"
    return nl.join(lines) + nl + body
