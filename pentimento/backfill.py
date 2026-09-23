"""Derive and write frontmatter for plans that don't have it."""

from __future__ import annotations

from pentimento import frontmatter, lineage, status, times, vocabulary
from pentimento import plan as plan_module

_PROGRESS_RANK = {s: i for i, s in enumerate(vocabulary.PROGRESS_ORDER)}


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


def derive_fields(
    target,
    candidates,
    sessions,
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
    derived_status = status.derive_status(target.body)
    if max_status and _PROGRESS_RANK.get(derived_status, -1) > _PROGRESS_RANK[max_status]:
        derived_status = max_status
    if existing_status is None:
        fields["status"] = derived_status
    elif existing_status != vocabulary.SUPERSEDED and fields.get("pinned") != "true":
        if rederive:
            fields["status"] = derived_status
        else:
            existing_rank = _PROGRESS_RANK.get(existing_status, -1)
            derived_rank = _PROGRESS_RANK.get(derived_status, -1)
            if derived_rank > existing_rank:
                fields["status"] = derived_status

    if rederive or "project" not in fields:
        project = _derive_project(target, sessions)
        if project:
            fields["project"] = project

    if rederive:
        parent_id = lineage.derive_parent(
            target, candidates, sessions, project=fields.get("project")
        )
        if parent_id:
            fields["parent"] = parent_id
        else:
            fields.pop("parent", None)
    elif "parent" not in fields:
        parent_id = lineage.derive_parent(
            target, candidates, sessions, project=fields.get("project")
        )
        if parent_id:
            fields["parent"] = parent_id

    return fields


def run(
    plans,
    sessions=None,
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

    `only`, when given, restricts writes to those ids; derivation still spans
    `plans` entire, because `lineage.derive_parent` resolves against the whole
    corpus and `_resolves_to_cycle` needs every plan's new fields.
    """
    sessions = sessions or {}
    new_fields_by_path = {
        target.path: derive_fields(
            target,
            plans,
            sessions,
            rederive=rederive,
            recreate=recreate,
            max_status=max_status,
        )
        for target in plans
    }
    # Cycle traversal walks `parent` id references, so it needs an id-keyed view.
    # A shared id makes the choice of which plan's fields represent that id
    # arbitrary here, but that ambiguity is inherent to duplicate ids, not
    # introduced by this map -- it does not affect which plan's fields get
    # written, which is keyed by path above.
    new_fields_by_id = {target.id: new_fields_by_path[target.path] for target in plans}

    for target in plans:
        new_fields = new_fields_by_path[target.path]
        parent_id = new_fields.get("parent")
        if parent_id and _resolves_to_cycle(target.id, parent_id, new_fields_by_id):
            new_fields.pop("parent", None)

    changed = []
    for target in plans:
        if only is not None and target.id not in only:
            continue
        new_fields = new_fields_by_path[target.path]
        if frontmatter.serialize(new_fields, target.body, target.extras) == target.text:
            continue
        changed.append(target.id)
        if details is not None:
            details[target.id] = (dict(target.fields), new_fields)
        if not dry_run:
            target.fields = new_fields
            plan_module.save(target, keep_mtime=True)
    return changed
