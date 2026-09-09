"""Derive and write frontmatter for plans that don't have it."""

from __future__ import annotations

from pentimento import lineage, status, times
from pentimento import plan as plan_module


def _created_date(target) -> str:
    return times.local_date(target.created_at) or target.started[:10]


def _derive_project(target, sessions) -> str | None:
    session = sessions.get(target.id)
    if session and session.project:
        return session.project
    return target.fields.get("project")


def _resolves_to_cycle(plan_id: str, parent_id: str, fields_by_id: dict[str, dict]) -> bool:
    seen = {plan_id}
    current = parent_id
    while current is not None:
        if current in seen:
            return True
        seen.add(current)
        current = fields_by_id.get(current, {}).get("parent")
    return False


def derive_fields(target, candidates, sessions, *, rederive: bool = False, recreate: bool = False) -> dict[str, str]:
    """Fields to backfill for `target`.

    When `rederive` is false, only fills fields absent from `target.fields`.
    When true, `status`, `parent`, and `project` are recomputed and
    overwritten; `intent` and `created` are never touched. `recreate`
    overwrites `created` too -- the opt-in fix for the day-late bug, kept
    separate so plain `backfill` and `--rederive` never touch it.
    """
    fields = dict(target.fields)
    fields.setdefault("status", status.derive_status(target.body))
    fields.setdefault("intent", "unset")
    fields.setdefault("created", _created_date(target))
    if recreate:
        fields["created"] = _created_date(target)

    if rederive:
        fields["status"] = status.derive_status(target.body)
        project = _derive_project(target, sessions)
        if project:
            fields["project"] = project
        parent_id = lineage.derive_parent(target, candidates, sessions)
        if parent_id:
            fields["parent"] = parent_id
        else:
            fields.pop("parent", None)
    elif "parent" not in fields:
        parent_id = lineage.derive_parent(target, candidates, sessions)
        if parent_id:
            fields["parent"] = parent_id

    return fields


def run(plans, sessions=None, *, dry_run: bool = False, rederive: bool = False, recreate: bool = False) -> list[str]:
    """Backfill frontmatter across `plans`. Returns ids that were changed."""
    sessions = sessions or {}
    new_fields_by_id = {
        target.id: derive_fields(target, plans, sessions, rederive=rederive, recreate=recreate) for target in plans
    }

    for target in plans:
        new_fields = new_fields_by_id[target.id]
        parent_id = new_fields.get("parent")
        if parent_id and _resolves_to_cycle(target.id, parent_id, new_fields_by_id):
            new_fields.pop("parent", None)

    changed = []
    for target in plans:
        new_fields = new_fields_by_id[target.id]
        if new_fields == target.fields:
            continue
        changed.append(target.id)
        if not dry_run:
            target.fields = new_fields
            plan_module.save(target)
    return changed
