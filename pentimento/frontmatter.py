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
FIELD_ORDER = ("status", "intent", "tags", "parent", "project", "created")


def parse(text: str) -> tuple[dict[str, str], str]:
    """Split text into (frontmatter fields, body).

    Returns an empty dict and the whole text unchanged if text does not
    begin with a frontmatter block at byte 0.
    """
    if text.startswith(DELIMITER + "\r\n"):
        nl = "\r\n"
    elif text.startswith(DELIMITER + "\n"):
        nl = "\n"
    else:
        return {}, text

    lines = text.split(nl)
    closing_index = _find_closing_delimiter(lines)
    if closing_index is None:
        return {}, text

    fields = _parse_fields(lines[1:closing_index])
    body = nl.join(lines[closing_index + 1 :])
    return fields, body


def _find_closing_delimiter(lines: list[str]) -> int | None:
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == DELIMITER:
            return index
    return None


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
    return value.split("#", 1)[0].strip()


def _parse_fields(lines: list[str]) -> dict[str, str]:
    fields = {}
    in_namespace = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in line:
            continue
        indented = line[:1] in (" ", "\t")
        key, _, raw_value = line.partition(":")
        key = key.strip()
        value = _clean_value(raw_value)
        if not indented and key == NAMESPACE and not value:
            in_namespace = True
            continue
        if not indented:
            in_namespace = False
        if indented and not in_namespace:
            continue
        if value:
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
