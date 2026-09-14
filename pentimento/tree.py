"""Render plan lineage as a tree, grouped by project."""

from __future__ import annotations

from pentimento import record as record_module
from pentimento import shortid, style, times
from pentimento import tags as tags_module


def _id_key(plan):
    return plan.id


def _children_by_parent(plans, key=_id_key, reverse=False):
    children = {}
    for p in plans:
        if p.parent:
            children.setdefault(p.parent, []).append(p)
    for kids in children.values():
        kids.sort(key=key, reverse=reverse)
    return children


def _reachable_ids(root, children_by_parent):
    reachable = {root.id}
    stack = list(children_by_parent.get(root.id, []))
    while stack:
        node = stack.pop()
        if node.id in reachable:
            continue
        reachable.add(node.id)
        stack.extend(children_by_parent.get(node.id, []))
    return reachable


def _roots(plans, children_by_parent, key=_id_key, reverse=False):
    ids = {p.id for p in plans}
    genuine = sorted((p for p in plans if not p.parent or p.parent not in ids), key=key, reverse=reverse)

    reachable: set[str] = set()
    for root in genuine:
        reachable |= _reachable_ids(root, children_by_parent)

    roots = list(genuine)
    for plan in sorted(plans, key=key, reverse=reverse):
        if plan.id in reachable:
            continue
        roots.append(plan)
        reachable |= _reachable_ids(plan, children_by_parent)
    return roots


def _render_node(
    plan, children_by_parent, prefix, is_last, lines, visited, on_color, glyphs, unicode_ok, width, short_ids,
    root_annotation=None,
):
    connector = glyphs["last"] if is_last else glyphs["branch"]
    annotation_text = f"({root_annotation})" if root_annotation else ""
    title_line = f"{prefix}{connector}{plan.title}"
    if annotation_text:
        title_line += f" {annotation_text}"
    title_line = style.truncate(title_line, width, unicode_ok=unicode_ok)
    if annotation_text and title_line.endswith(annotation_text):
        title_line = title_line[: -len(annotation_text)] + style.paint(annotation_text, style.DIM, on=on_color)
    lines.append(title_line)

    child_prefix = prefix + (glyphs["space"] if is_last else glyphs["vertical"])
    is_repeat = plan.id in visited
    status_text = style.paint(plan.status, *style.STATUS_CODES.get(plan.status, ()), on=on_color)
    intent_text = style.paint(plan.intent, *style.INTENT_CODES.get(plan.intent, ()), on=on_color)
    meta = f"{short_ids[plan.id]}  {status_text}  {intent_text}"
    if plan.tags:
        meta += f"  {tags_module.render(plan.tags)}"
    created = plan.fields.get("created")
    if created:
        meta += f"  {style.paint(created, style.DIM, on=on_color)}"
    meta += f"  {style.paint(times.relative(plan.modified), style.DIM, on=on_color)}"
    if is_repeat:
        meta += "  (cycle)"
    meta_line = style.truncate(f"{child_prefix}  {meta}", width, unicode_ok=unicode_ok)
    lines.append(meta_line)

    if is_repeat:
        return
    visited.add(plan.id)
    kids = children_by_parent.get(plan.id, [])
    for index, child in enumerate(kids):
        _render_node(
            child, children_by_parent, child_prefix, index == len(kids) - 1, lines, visited, on_color, glyphs,
            unicode_ok, width, short_ids,
        )


def render(
    plans, on_color: bool = False, key=_id_key, reverse: bool = False, glyphs=None, unicode_ok: bool = False,
    short_ids=None,
) -> str:
    """Tree for one project's worth of plans (roots and descendants)."""
    glyphs = glyphs or style.GLYPHS_ASCII
    width = style.terminal_width()
    if short_ids is None:
        short_ids = shortid.shorten(p.id for p in plans)
    children_by_parent = _children_by_parent(plans, key, reverse)
    roots = _roots(plans, children_by_parent, key, reverse)
    ids = {p.id for p in plans}
    lines = []
    visited = set()
    for index, root in enumerate(roots):
        annotation = f"parent elided: {root.parent}" if root.parent and root.parent not in ids else None
        _render_node(
            root, children_by_parent, "", index == len(roots) - 1, lines, visited, on_color, glyphs, unicode_ok,
            width, short_ids, annotation,
        )
    return "\n".join(lines)


def render_grouped(
    plans, on_color: bool = False, key=_id_key, reverse: bool = False, glyphs=None, unicode_ok: bool = False,
    short_ids=None,
) -> str:
    """Group plans by project, then render each group's tree."""
    if short_ids is None:
        short_ids = shortid.shorten(p.id for p in plans)
    groups: dict[str, list] = {}
    for p in plans:
        groups.setdefault(p.project or "(no project)", []).append(p)

    blocks = []
    for project in sorted(groups):
        heading = style.paint(project, style.BOLD, on=on_color)
        blocks.append(
            heading + "\n" + render(groups[project], on_color, key, reverse, glyphs, unicode_ok, short_ids)
        )
    return "\n\n".join(blocks)


def as_records(plans, key=_id_key, reverse: bool = False) -> list[dict]:
    """Nested {record, children} tree for `formats.emit`, mirroring `render`."""
    children_by_parent = _children_by_parent(plans, key, reverse)
    roots = _roots(plans, children_by_parent, key, reverse)
    visited: set[str] = set()

    def build(plan):
        rec = record_module.as_dict(plan)
        if plan.id in visited:
            rec["children"] = []
            return rec
        visited.add(plan.id)
        rec["children"] = [build(child) for child in children_by_parent.get(plan.id, [])]
        return rec

    return [build(root) for root in roots]
