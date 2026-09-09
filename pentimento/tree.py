"""Render plan lineage as an ASCII tree, grouped by project.

Glyphs are plain ASCII (`+-`, `|`, `` `- ``) -- the working agreement bars
Unicode in non-web UIs.
"""

from __future__ import annotations

from pentimento import record as record_module
from pentimento import style


def _children_by_parent(plans):
    children = {}
    for p in plans:
        if p.parent:
            children.setdefault(p.parent, []).append(p)
    for kids in children.values():
        kids.sort(key=lambda p: p.id)
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


def _roots(plans, children_by_parent):
    ids = {p.id for p in plans}
    genuine = sorted((p for p in plans if not p.parent or p.parent not in ids), key=lambda p: p.id)

    reachable: set[str] = set()
    for root in genuine:
        reachable |= _reachable_ids(root, children_by_parent)

    roots = list(genuine)
    for plan in sorted(plans, key=lambda p: p.id):
        if plan.id in reachable:
            continue
        roots.append(plan)
        reachable |= _reachable_ids(plan, children_by_parent)
    return roots


def _render_node(plan, children_by_parent, prefix, is_last, lines, visited, on_color, root_annotation=None):
    connector = "`- " if is_last else "+- "
    title_line = f"{prefix}{connector}{plan.title}"
    if root_annotation:
        title_line += " " + style.paint(f"({root_annotation})", style.DIM, on=on_color)
    lines.append(title_line)

    child_prefix = prefix + ("   " if is_last else "|  ")
    is_repeat = plan.id in visited
    meta = f"{plan.id}  {plan.status}  {plan.intent}"
    if is_repeat:
        meta += "  (cycle)"
    lines.append(f"{child_prefix}  " + style.paint(meta, style.DIM, on=on_color))

    if is_repeat:
        return
    visited.add(plan.id)
    kids = children_by_parent.get(plan.id, [])
    for index, child in enumerate(kids):
        _render_node(child, children_by_parent, child_prefix, index == len(kids) - 1, lines, visited, on_color)


def render(plans, on_color: bool = False) -> str:
    """ASCII tree for one project's worth of plans (roots and descendants)."""
    children_by_parent = _children_by_parent(plans)
    roots = _roots(plans, children_by_parent)
    ids = {p.id for p in plans}
    lines = []
    visited = set()
    for index, root in enumerate(roots):
        annotation = f"parent elided: {root.parent}" if root.parent and root.parent not in ids else None
        _render_node(root, children_by_parent, "", index == len(roots) - 1, lines, visited, on_color, annotation)
    return "\n".join(lines)


def render_grouped(plans, on_color: bool = False) -> str:
    """Group plans by project, then render each group's tree."""
    groups: dict[str, list] = {}
    for p in plans:
        groups.setdefault(p.project or "(no project)", []).append(p)

    blocks = []
    for project in sorted(groups):
        heading = style.paint(project, style.BOLD, on=on_color)
        blocks.append(heading + "\n" + render(groups[project], on_color))
    return "\n\n".join(blocks)


def as_records(plans) -> list[dict]:
    """Nested {record, children} tree for `formats.emit`, mirroring `render`."""
    children_by_parent = _children_by_parent(plans)
    roots = _roots(plans, children_by_parent)
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
