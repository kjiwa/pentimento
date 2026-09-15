"""Render a plan body as terminal-styled markdown.

Not a markdown library: exactly the block types the plan corpus contains
(headings, fenced/indented code, tables, checklists, bullets, blockquotes,
rules, and prose paragraphs). Anything else passes through as a paragraph.

Same width discipline as `style.py`: widths are measured on unpainted text,
then paint is applied last. Inline spans (`**bold**`, `` `code` ``) are
tokenized before wrapping, so a bold run split across two lines paints
correctly on both.
"""

from __future__ import annotations

import re

from pentimento import style

MAX_WIDTH = 100
MIN_BODY_LINES = 5

Token = tuple[str, tuple[str, ...], bool]

_FENCE_RE = re.compile(r"^(```|~~~)")
_CHECKBOX_RE = re.compile(r"^(\s*)-\s*\[([ xX])\]\s*(.*)$")
_BULLET_RE = re.compile(r"^(\s*)(?:[-*]|\d+\.)\s+(.*)$")
_INLINE_RE = re.compile(
    r"\*\*(?P<bold>.+?)\*\*|`(?P<code>.+?)`|(?<!!)\[(?P<link>[^\]]+)\]\([^)]*\)"
)
_RULES = ("---", "***")

GLYPHS_UNICODE = {
    "bullet": "•",
    "checked": "✓",
    "unchecked": "☐",
    "rule": "─",
    "ellipsis": "…",
    "dash": "—",
}
GLYPHS_ASCII = {
    "bullet": "-",
    "checked": "[x]",
    "unchecked": "[ ]",
    "rule": "-",
    "ellipsis": "...",
    "dash": "--",
}


def _glyphs(unicode_ok: bool) -> dict:
    return GLYPHS_UNICODE if unicode_ok else GLYPHS_ASCII


_Span = tuple[str, tuple[str, ...], int, int]  # (word, codes, start, end) in the scanned text


def _plain_spans(text: str, start: int, end: int) -> list[_Span]:
    return [
        (m.group(0), (), start + m.start(), start + m.end())
        for m in re.finditer(r"\S+", text[start:end])
    ]


def _tokenize_spans(text: str) -> list[_Span]:
    """Marker-stripped (word, codes, start, end) spans, positioned in `text`.

    A marker is found by scanning for its matching closer over the raw text
    first -- regex, not whitespace splitting -- so a code span containing
    internal spaces (`` `sh -n` ``) is never torn apart mid-scan; wrapping
    may still break it into per-word spans (each carrying the marker's
    style), same as it would a multi-word bold run.
    """
    spans: list[_Span] = []
    pos = 0
    for match in _INLINE_RE.finditer(text):
        if match.start() > pos:
            spans.extend(_plain_spans(text, pos, match.start()))
        if match.group("bold") is not None:
            offset = match.start("bold")
            inner = [
                (word, (style.BOLD,) + codes, offset + start, offset + end)
                for word, codes, start, end in _tokenize_spans(match.group("bold"))
            ]
        elif match.group("code") is not None:
            inner = [
                (word, (style.CYAN,), start, end)
                for word, _, start, end in _plain_spans(text, *match.span("code"))
            ]
        else:
            offset = match.start("link")
            inner = []
            for word, codes, start, end in _tokenize_spans(match.group("link")):
                codes = codes if style.CYAN in codes else (style.CYAN,) + codes
                inner.append((word, codes, offset + start, offset + end))
        if inner:
            # Adjacency against text outside the marker is decided by the
            # marker's own start/end (backticks and all), not the named
            # group's -- otherwise a token glued right up against the
            # closing `` ` `` looks one character short of touching.
            word, codes, _, end = inner[0]
            inner[0] = (word, codes, match.start(), end)
            word, codes, start, _ = inner[-1]
            inner[-1] = (word, codes, start, match.end())
        spans.extend(inner)
        pos = match.end()
    if pos < len(text):
        spans.extend(_plain_spans(text, pos, len(text)))
    return spans


def _inline(text: str) -> list[Token]:
    """Tokenize a paragraph, stripping `**bold**`/`` `code` `` markers.

    A marker run with no matching closer inside `text` never matches the
    regex, so it stays literal in the plain-text fallthrough. A token is
    "glued" -- rendered with no leading space -- when its source span
    touches the previous token's with no whitespace between them, e.g. two
    code spans butted against a bare `/`.
    """
    tokens: list[Token] = []
    prev_end = None
    for word, codes, start, end in _tokenize_spans(text):
        tokens.append((word, codes, prev_end == start))
        prev_end = end
    return tokens


def _paint_tokens(tokens: list[Token], *, on_color: bool) -> str:
    parts = []
    for index, (text, codes, glued) in enumerate(tokens):
        if index and not glued:
            parts.append(" ")
        parts.append(style.paint(text, *codes, on=on_color))
    return "".join(parts)


def _pack(tokens: list[Token], first_width: int, rest_width: int) -> list[list[Token]]:
    rows: list[list[Token]] = []
    row: list[Token] = []
    row_width = 0
    limit = max(first_width, 1)

    def break_row():
        nonlocal row, row_width, limit
        rows.append(row)
        row, row_width = [], 0
        limit = max(rest_width, 1)

    for text, codes, glued in tokens:
        token_width = style.display_width(text)
        space = 1 if row and not glued else 0
        if row and row_width + space + token_width > limit:
            break_row()

        while token_width > limit:
            head, text = style.split_width(text, limit)
            if not head:
                break
            row.append((head, codes, glued))
            break_row()
            glued = True
            token_width = style.display_width(text)

        if text:
            space = 1 if row and not glued else 0
            row.append((text, codes, glued))
            row_width += space + token_width
    if row:
        rows.append(row)
    return rows


def _wrap(
    tokens: list[Token], width: int, indent: int, hanging: int, *, on_color: bool
) -> list[str]:
    if not tokens:
        return []
    rows = _pack(tokens, width - indent, width - hanging)
    lines = []
    for index, row in enumerate(rows):
        pad = indent if index == 0 else hanging
        lines.append(" " * pad + _paint_tokens(row, on_color=on_color))
    return lines


def _verbatim(line: str, width: int, *, unicode_ok: bool) -> str:
    return style.truncate("    " + line, width, unicode_ok=unicode_ok)


def _heading(text: str, level: int, width: int, *, on_color: bool) -> list[str]:
    indent = max(level - 2, 0) * 2
    tokens = [(word, (style.BOLD,) + codes, glued) for word, codes, glued in _inline(text)]
    return [""] + _wrap(tokens, width, indent, indent, on_color=on_color)


def _starts_a_block(stripped: str) -> bool:
    """Whether `stripped` opens a block type other than a plain prose line.

    A nested fence, heading, table row, blockquote, or rule ends a list
    item's hard-wrapped continuation the same as a new bullet does --
    otherwise its markers get folded into the item's prose and re-tokenized
    as (broken) inline spans.
    """
    return bool(
        _FENCE_RE.match(stripped)
        or re.match(r"^#{2,6}\s+", stripped)
        or stripped.startswith(("|", ">"))
        or stripped in _RULES
        or _BULLET_RE.match(stripped)
        or _CHECKBOX_RE.match(stripped)
    )


def _continuation(lines: list[str], index: int, count: int, indent: int) -> tuple[str, int]:
    """Fold hard-wrapped continuation lines of a list item back into one flow.

    A line indented past the item's own marker and not itself the start of
    another block is prose the author wrapped by hand; a line at or below
    the marker's indent, or one that starts a new block, ends the item.
    """
    parts = []
    while index < count:
        candidate = lines[index]
        if candidate.strip() == "":
            break
        candidate_indent = len(candidate) - len(candidate.lstrip(" "))
        if candidate_indent <= indent:
            break
        if _starts_a_block(candidate.strip()):
            break
        parts.append(candidate.strip())
        index += 1
    return " ".join(parts), index


_PIPE_RE = re.compile(r"(?<!\\)\|")
_DELIM_CELL_RE = re.compile(r"^:?-+:?$")
_MIN_COLUMN = 4


def _table_row(line: str) -> list[str]:
    parts = _PIPE_RE.split(line.strip())
    if parts and parts[0] == "":
        parts = parts[1:]
    if parts and parts[-1] == "":
        parts = parts[:-1]
    return [part.strip().replace("\\|", "|") for part in parts]


def _column_widths(rows: list[list[str]], width: int) -> list[int]:
    ncols = len(rows[0]) if rows else 0
    if ncols == 0:
        return []
    natural = [
        max(style.display_width(_paint_tokens(_inline(row[c]), on_color=False)) for row in rows)
        for c in range(ncols)
    ]
    total = sum(natural) + style.GUTTER * (ncols - 1)
    if total <= width:
        return natural

    available = width - style.GUTTER * (ncols - 1)
    floor = max(min(_MIN_COLUMN, available // ncols), 1)
    sum_natural = sum(natural) or 1
    widths = [max(floor, round(n * available / sum_natural)) for n in natural]
    overflow = sum(widths) - available
    while overflow > 0:
        widest = max(range(ncols), key=lambda i: widths[i])
        if widths[widest] <= floor:
            break
        take = min(overflow, widths[widest] - floor)
        widths[widest] -= take
        overflow -= take
    return widths


def _table_cell_lines(
    text: str, col_width: int, *, bold: bool, on_color: bool
) -> list[tuple[str, str]]:
    """(plain, painted) physical lines for one cell, wrapped to `col_width`."""
    tokens = _inline(text)
    if bold:
        tokens = [(word, (style.BOLD,) + codes, glued) for word, codes, glued in tokens]
    rows = _pack(tokens, col_width, col_width)
    return [
        (_paint_tokens(row, on_color=False), _paint_tokens(row, on_color=on_color)) for row in rows
    ]


def _table_row_lines(
    cells: list[str], widths: list[int], aligns: list[str], *, bold: bool, on_color: bool
) -> list[str]:
    columns = [
        _table_cell_lines(cell, w, bold=bold, on_color=on_color) for cell, w in zip(cells, widths)
    ]
    height = max((len(column) for column in columns), default=0) or 1
    gutter = " " * style.GUTTER
    lines = []
    for row_index in range(height):
        parts = []
        for col_index, (column, col_width, align) in enumerate(zip(columns, widths, aligns)):
            plain, painted = column[row_index] if row_index < len(column) else ("", "")
            pad = " " * max(col_width - style.display_width(plain), 0)
            is_last = col_index == len(columns) - 1
            if align == "right":
                parts.append(pad + painted)
            elif is_last:
                parts.append(painted)
            else:
                parts.append(painted + pad)
        lines.append(gutter.join(parts))
    return lines


def _table(
    lines: list[str], index: int, count: int, width: int, *, on_color: bool
) -> tuple[list[str], int]:
    """Render the run of `|`-prefixed `lines` starting at `index`."""
    raw_rows = []
    while index < count and lines[index].strip().startswith("|"):
        raw_rows.append(_table_row(lines[index]))
        index += 1

    header = None
    body = raw_rows
    delimiter = raw_rows[1] if len(raw_rows) >= 2 else None
    if delimiter and all(_DELIM_CELL_RE.match(cell) for cell in delimiter):
        header = raw_rows[0]
        body = raw_rows[2:]
    else:
        delimiter = None

    ncols = max((len(row) for row in ([header] if header else []) + body), default=0)
    if header is not None:
        header = header + [""] * (ncols - len(header))
    body = [row + [""] * (ncols - len(row)) for row in body]

    aligns = ["left"] * ncols
    if delimiter:
        for i, cell in enumerate(delimiter[:ncols]):
            if cell.endswith(":") and not cell.startswith(":"):
                aligns[i] = "right"

    widths = _column_widths(([header] if header else []) + body, width)

    out = []
    if header is not None:
        out.extend(_table_row_lines(header, widths, aligns, bold=True, on_color=on_color))
    for row in body:
        out.extend(_table_row_lines(row, widths, aligns, bold=False, on_color=on_color))
    return out, index


def _squeeze(lines: list[str]) -> list[str]:
    """Drop leading/trailing blank lines and collapse interior runs to one."""
    out: list[str] = []
    for line in lines:
        if line == "" and out and out[-1] == "":
            continue
        out.append(line)
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()
    return out


def render(body: str, *, on_color: bool, unicode_ok: bool, width: int) -> list[str]:
    glyphs = _glyphs(unicode_ok)
    lines = body.split("\n")
    out: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph():
        if not paragraph:
            return
        text = " ".join(line.strip() for line in paragraph)
        paragraph.clear()
        out.extend(_wrap(_inline(text), width, 0, 0, on_color=on_color))

    index = 0
    count = len(lines)
    while index < count:
        line = lines[index]
        stripped = line.strip()

        if stripped == "":
            flush_paragraph()
            out.append("")
            index += 1
            continue

        fence = _FENCE_RE.match(stripped)
        if fence:
            flush_paragraph()
            marker = fence.group(1)
            index += 1
            while index < count and lines[index].strip() != marker:
                out.append(_verbatim(lines[index], width, unicode_ok=unicode_ok))
                index += 1
            index += 1
            continue

        if line.startswith("    "):
            flush_paragraph()
            while index < count and lines[index].startswith("    "):
                out.append(_verbatim(lines[index][4:], width, unicode_ok=unicode_ok))
                index += 1
            continue

        heading_match = re.match(r"^(#{2,6})\s+(.*)$", stripped)
        if heading_match:
            flush_paragraph()
            marks = heading_match.group(1)
            out.extend(_heading(heading_match.group(2), len(marks), width, on_color=on_color))
            index += 1
            continue

        if stripped.startswith("|"):
            flush_paragraph()
            table_lines, index = _table(lines, index, count, width, on_color=on_color)
            out.extend(table_lines)
            continue

        checkbox_match = _CHECKBOX_RE.match(line)
        if checkbox_match:
            flush_paragraph()
            spaces, mark, text = checkbox_match.groups()
            checked = mark.lower() == "x"
            glyph = glyphs["checked"] if checked else glyphs["unchecked"]
            codes = (style.GREEN,) if checked else ()
            plain_prefix = " " * len(spaces) + glyph + " "
            painted_prefix = " " * len(spaces) + style.paint(glyph, *codes, on=on_color) + " "
            prefix_width = style.display_width(plain_prefix)
            extra, index = _continuation(lines, index + 1, count, len(spaces))
            text = f"{text} {extra}" if extra else text
            out.extend(
                _wrap_with_prefix(text, width, painted_prefix, prefix_width, on_color=on_color)
            )
            continue

        bullet_match = _BULLET_RE.match(line)
        if bullet_match:
            flush_paragraph()
            spaces, text = bullet_match.groups()
            prefix = " " * len(spaces) + glyphs["bullet"] + " "
            extra, index = _continuation(lines, index + 1, count, len(spaces))
            text = f"{text} {extra}" if extra else text
            out.extend(
                _wrap_with_prefix(
                    text, width, prefix, style.display_width(prefix), on_color=on_color
                )
            )
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote_lines = [stripped[1:].strip()]
            index += 1
            while index < count and lines[index].strip().startswith(">"):
                quote_lines.append(lines[index].strip()[1:].strip())
                index += 1
            text = " ".join(quote_lines)
            plain_tokens = [(word, (), glued) for word, _, glued in _inline(text)]
            for wrapped in _wrap(plain_tokens, width, 2, 2, on_color=False):
                out.append(style.paint(wrapped, style.DIM, on=on_color))
            continue

        if stripped in _RULES:
            flush_paragraph()
            rule = glyphs["rule"] * width
            out.append(style.paint(rule, style.DIM, on=on_color))
            index += 1
            continue

        paragraph.append(line)
        index += 1

    flush_paragraph()
    return _squeeze(out)


def _wrap_with_prefix(
    text: str, width: int, prefix: str, prefix_width: int, *, on_color: bool
) -> list[str]:
    """Wrap `text` with `prefix` (already painted) on the first line only.

    Continuation lines are indented to align under the text that follows
    the prefix, not under the prefix's raw character count -- callers pass
    the unpainted display width separately since ANSI bytes must never
    enter a column measurement.
    """
    tokens = _inline(text)
    if not tokens:
        return [prefix.rstrip(" ")] if prefix.strip() else []
    lines = _wrap(tokens, width, prefix_width, prefix_width, on_color=on_color)
    lines[0] = prefix + lines[0][prefix_width:]
    return lines


def clip(
    lines: list[str], limit: int | None, hint: str, *, on_color: bool, unicode_ok: bool
) -> list[str]:
    if limit is None or len(lines) <= limit:
        return lines
    limit = max(limit, MIN_BODY_LINES)
    if len(lines) <= limit:
        return lines
    kept = lines[:limit]
    while kept and kept[-1] == "":
        kept.pop()
    remaining = len(lines) - len(kept)
    glyphs = _glyphs(unicode_ok)
    message = f"{glyphs['ellipsis']} {remaining} more lines {glyphs['dash']} {hint}"
    kept.append(style.paint(message, style.DIM, on=on_color))
    return kept
