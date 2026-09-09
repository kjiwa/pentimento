"""Flat scalar frontmatter: no PyYAML, zero runtime dependencies.

A frontmatter block is recognized only when the file's first three bytes are
literally "---\n" -- never a "---" line anywhere else in the body. Plan
bodies use "---" as a Markdown horizontal rule; treating any mid-body match
as a delimiter would silently corrupt those files.
"""

from __future__ import annotations

DELIMITER = "---"

NAMESPACE = "pentimento"
INDENT = "  "

# Canonical field order for serialization; the reader accepts any order.
FIELD_ORDER = ("status", "intent", "parent", "project", "created")


def parse(text: str) -> tuple[dict[str, str], str]:
    """Split text into (frontmatter fields, body).

    Returns an empty dict and the whole text unchanged if text does not
    begin with a frontmatter block at byte 0.
    """
    if not text.startswith(DELIMITER + "\n"):
        return {}, text

    lines = text.split("\n")
    closing_index = _find_closing_delimiter(lines)
    if closing_index is None:
        return {}, text

    fields = _parse_fields(lines[1:closing_index])
    body = "\n".join(lines[closing_index + 1 :])
    return fields, body


def _find_closing_delimiter(lines: list[str]) -> int | None:
    for index, line in enumerate(lines[1:], start=1):
        if line == DELIMITER:
            return index
    return None


def _parse_fields(lines: list[str]) -> dict[str, str]:
    fields = {}
    in_namespace = False
    for line in lines:
        if not line.strip() or ":" not in line:
            continue
        indented = line[:1] in (" ", "\t")
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not indented and key == NAMESPACE and not value:
            in_namespace = True
            continue
        if not indented:
            in_namespace = False
        if indented and not in_namespace:
            continue
        fields[key] = value
    return fields


def serialize(fields: dict[str, str], body: str) -> str:
    """Render fields plus body back into text, in FIELD_ORDER.

    Known fields (`FIELD_ORDER`) are emitted nested under a `pentimento:`
    opener, indented, in canonical order. Fields absent from `fields` are
    omitted. Unknown keys are emitted unindented after the block, outside
    the namespace, so parse reads them back as top-level fields. Body bytes
    are never touched.
    """
    if not fields:
        return body

    known = set(FIELD_ORDER)
    namespaced = [key for key in FIELD_ORDER if key in fields]
    unknown = [key for key in fields if key not in known]

    lines = [DELIMITER]
    if namespaced:
        lines.append(f"{NAMESPACE}:")
        for key in namespaced:
            lines.append(f"{INDENT}{key}: {fields[key]}")
    for key in unknown:
        lines.append(f"{key}: {fields[key]}")
    lines.append(DELIMITER)
    return "\n".join(lines) + "\n" + body
