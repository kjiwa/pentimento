"""Gap-fill intent, created, project, and parent in plan frontmatter, and advance status."""

from __future__ import annotations

from pentimento import frontmatter, lineage, status, times, vocabulary
from pentimento import plan as plan_module
from pentimento import touches as touches_module


def _created_date(target) -> str:
    return times.local_date(target.created_at) or target.started[:10]


def _derive_project(target, sessions, touches) -> str | None:
    session = sessions.get(touches_module.author(touches.get(target.id, []), target.id))
    if session and session.project:
        return session.project
    return target.fields.get("project")


def derive_fields(
    target,
    candidates,
    sessions,
    touches,
    *,
    rederive: bool = False,
    recreate: bool = False,
    max_status: str | None = None,
) -> dict[str, str]:
    """Fields to backfill for `target`."""
    fields = dict(target.fields)
    fields.setdefault("intent", vocabulary.DEFAULT_INTENT)
    fields.setdefault("created", _created_date(target))
    if recreate:
        fields["created"] = _created_date(target)

    existing_status = fields.get("status")
    derived_status = status.derive_status(target.body, target.extras)
    if max_status and status.rank(derived_status) > status.rank(max_status):
        derived_status = max_status
    if existing_status is None:
        fields["status"] = derived_status
    elif existing_status != vocabulary.SUPERSEDED and fields.get("pinned") != "true":
        if rederive:
            fields["status"] = derived_status
        else:
            existing_rank = status.rank(existing_status)
            derived_rank = status.rank(derived_status)
            if derived_rank > existing_rank:
                fields["status"] = derived_status

    if rederive or "project" not in fields:
        project = _derive_project(target, sessions, touches)
        if project and frontmatter.is_valid_value(project):
            fields["project"] = project

    if rederive or "parent" not in fields:
        parent_id = lineage.derive_parent(
            target, candidates, sessions, project=fields.get("project")
        )
        if parent_id:
            fields["parent"] = parent_id
        elif rederive:
            fields.pop("parent", None)

    return fields


def run(
    plans,
    sessions=None,
    touches=None,
    *,
    dry_run: bool = False,
    rederive: bool = False,
    recreate: bool = False,
    max_status: str | None = None,
    only=None,
    details: dict | None = None,
) -> list[str]:
    """Backfill frontmatter across `plans`. Returns ids that were changed.

    `details`, when given, receives `id -> (fields before, fields after)` for
    each changed plan.

    `only`, when given, restricts writes to those ids; derivation still spans all `plans`.
    """
    sessions = sessions or {}
    touches = touches or {}
    new_fields_by_path = {
        target.path: derive_fields(
            target,
            plans,
            sessions,
            touches,
            rederive=rederive,
            recreate=recreate,
            max_status=max_status,
        )
        for target in plans
    }
    parent_of = {target.id: new_fields_by_path[target.path].get("parent") for target in plans}
    for target in plans:
        if parent_of[target.id] and lineage.in_cycle(target.id, parent_of):
            new_fields_by_path[target.path].pop("parent", None)
            parent_of[target.id] = None

    rendered = {
        target.path: frontmatter.serialize(
            new_fields_by_path[target.path], target.body, target.extras
        )
        for target in plans
        if only is None or target.id in only
    }
    changed = []
    for target in plans:
        if target.path not in rendered or rendered[target.path] == target.text:
            continue
        new_fields = new_fields_by_path[target.path]
        changed.append(target.id)
        if details is not None:
            details[target.id] = (dict(target.fields), new_fields)
        if not dry_run:
            target.fields = new_fields
            plan_module.save(target, keep_mtime=True)
    return changed
