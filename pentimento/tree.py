"""Render plan lineage as an ASCII tree, grouped by project.

Glyphs are plain ASCII (`+-`, `|`, `` `- ``) -- the working agreement bars
Unicode in non-web UIs.
"""

from __future__ import annotations


def _children_by_parent(plans):
    children = {}
    for p in plans:
        if p.parent:
            children.setdefault(p.parent, []).append(p)
    for kids in children.values():
        kids.sort(key=lambda p: p.id)
    return children


def _roots(plans):
    ids = {p.id for p in plans}
    return sorted((p for p in plans if not p.parent or p.parent not in ids), key=lambda p: p.id)


def _render_node(plan, children_by_parent, prefix, is_last, lines, visited):
    connector = "`- " if is_last else "+- "
    lines.append(f"{prefix}{connector}{plan.id} ({plan.title})")
    if plan.id in visited:
        return
    visited.add(plan.id)

    child_prefix = prefix + ("   " if is_last else "|  ")
    kids = children_by_parent.get(plan.id, [])
    for index, child in enumerate(kids):
        _render_node(child, children_by_parent, child_prefix, index == len(kids) - 1, lines, visited)


def render(plans) -> str:
    """ASCII tree for one project's worth of plans (roots and descendants)."""
    children_by_parent = _children_by_parent(plans)
    roots = _roots(plans)
    lines = []
    visited = set()
    for index, root in enumerate(roots):
        _render_node(root, children_by_parent, "", index == len(roots) - 1, lines, visited)
    return "\n".join(lines)


def render_grouped(plans) -> str:
    """Group plans by project, then render each group's tree."""
    groups: dict[str, list] = {}
    for p in plans:
        groups.setdefault(p.project or "(no project)", []).append(p)

    sections = []
    for project in sorted(groups):
        sections.append(f"{project}:")
        sections.append(render(groups[project]))
    return "\n".join(sections)
