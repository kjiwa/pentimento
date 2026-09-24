"""Render plan lineage as a tree, grouped by project, and select a thread by lineage."""

from __future__ import annotations

import dataclasses

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


def subtree(plans, root):
    """`root` plus every plan beneath it."""
    reachable = _reachable_ids(root, _children_by_parent(plans))
    return [p for p in plans if p.id in reachable]


def spine(plans, plan):
    """`plan`'s ancestors, nearest first -- the path down to it with every
    sibling branch left out. Stops at the topmost ancestor, or at a cycle."""
    by_id = {p.id: p for p in plans}
    chain, seen = [], {plan.id}
    current = by_id.get(plan.parent) if plan.parent else None
    while current is not None and current.id not in seen:
        seen.add(current.id)
        chain.append(current)
        current = by_id.get(current.parent) if current.parent else None
    return chain


def _roots(plans, children_by_parent, key=_id_key, reverse=False, first=None):
    """Genuine roots, then one root per cycle. `first` names the plan a cycle
    should be entered at, when it sits in one."""
    ids = {p.id for p in plans}
    genuine = sorted(
        (p for p in plans if not p.parent or p.parent not in ids), key=key, reverse=reverse
    )

    reachable: set[str] = set()
    for root in genuine:
        reachable |= _reachable_ids(root, children_by_parent)

    roots = list(genuine)
    remaining = sorted(plans, key=key, reverse=reverse)
    remaining.sort(key=lambda p: p.id != first)
    for plan in remaining:
        if plan.id in reachable:
            continue
        roots.append(plan)
        reachable |= _reachable_ids(plan, children_by_parent)
    return roots


@dataclasses.dataclass(frozen=True)
class _RenderContext:
    children_by_parent: dict
    lines: list
    visited: set
    on_color: bool
    width: int | None
    short_ids: dict


def _render_node(ctx, plan, prefix, is_last, root_annotation=None):
    connector = style.GLYPHS["last"] if is_last else style.GLYPHS["branch"]
    title_line = f"{prefix}{connector}{plan.title}"
    if ctx.width is not None:
        title_line = style.truncate(title_line, ctx.width)
    ctx.lines.append(title_line)

    child_prefix = prefix + (style.GLYPHS["space"] if is_last else style.GLYPHS["vertical"])
    is_repeat = plan.id in ctx.visited
    cells: list[style.Cell] = [(ctx.short_ids[plan.id], ())]
    cells.append((plan.status, style.STATUS_CODES.get(plan.status, ())))
    cells.append((plan.intent, style.INTENT_CODES.get(plan.intent, ())))
    if plan.tags:
        cells.append((tags_module.render(plan.tags), ()))
    if plan.created:
        cells.append((plan.created, (style.DIM,)))
    cells.append((times.relative(plan.modified), (style.DIM,)))
    if is_repeat:
        cells.append(("(cycle)", ()))
    if root_annotation:
        cells.append((f"({root_annotation})", (style.DIM,)))
    prefix_text = f"{child_prefix}  "
    ctx.lines.extend(style.wrap_fields(cells, "  ", ctx.width, prefix_text, on_color=ctx.on_color))

    if is_repeat:
        return
    ctx.visited.add(plan.id)
    kids = ctx.children_by_parent.get(plan.id, [])
    for index, child in enumerate(kids):
        _render_node(ctx, child, child_prefix, index == len(kids) - 1)


def render(
    plans,
    on_color: bool = False,
    key=_id_key,
    reverse: bool = False,
    short_ids=None,
    root_id=None,
) -> str:
    """Tree for one project's worth of plans (roots and descendants)."""
    width = style.terminal_width()
    if short_ids is None:
        short_ids = shortid.shorten(p.id for p in plans)
    children_by_parent = _children_by_parent(plans, key, reverse)
    roots = _roots(plans, children_by_parent, key, reverse, root_id)
    ids = {p.id for p in plans}
    ctx = _RenderContext(
        children_by_parent=children_by_parent,
        lines=[],
        visited=set(),
        on_color=on_color,
        width=width,
        short_ids=short_ids,
    )
    for index, root in enumerate(roots):
        annotation = (
            f"parent elided: {root.parent}" if root.parent and root.parent not in ids else None
        )
        _render_node(ctx, root, "", index == len(roots) - 1, annotation)
    return "\n".join(ctx.lines)


def render_grouped(
    plans,
    on_color: bool = False,
    key=_id_key,
    reverse: bool = False,
    short_ids=None,
    root_id=None,
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
            heading
            + "\n"
            + render(
                groups[project],
                on_color,
                key,
                reverse,
                short_ids,
                root_id,
            )
        )
    return "\n\n".join(blocks)


def as_records(plans, key=_id_key, reverse: bool = False, root_id=None) -> list[dict]:
    """Nested {record, children} tree for `formats.emit`, mirroring `render`."""
    children_by_parent = _children_by_parent(plans, key, reverse)
    roots = _roots(plans, children_by_parent, key, reverse, root_id)
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
