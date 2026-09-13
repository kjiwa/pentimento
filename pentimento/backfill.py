"""Derive and write frontmatter for plans that don't have it."""

from __future__ import annotations

from pentimento import frontmatter, lineage, status, times
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

    Each derived field states its gap-fill and its rederive behaviour once:

    - `status`: recomputed every run, plain or `--rederive` alike, and
      written unless the existing value is `superseded` (operator-only,
      never derivable) or the recomputed value is `unknown` while a status
      is already set (an absent or ambiguous signal must never downgrade a
      real status).
    - `intent`: gap-filled if absent; never touched otherwise -- operator-owned.
    - `created`: gap-filled if absent; never touched by `rederive`, only by
      `recreate`, which overwrites it from local time.
    - `parent`: gap-filled if absent; when `rederive`, recomputed and
      overwritten, cleared if re-derivation finds nothing.
    - `project`: gap-filled if absent; when `rederive`, recomputed and
      overwritten, but `_derive_project` falls back to the existing value,
      so unlike `parent`, `rederive` never clears `project`.
    """
    fields = dict(target.fields)
    fields.setdefault("intent", "unset")
    fields.setdefault("created", _created_date(target))
    if recreate:
        fields["created"] = _created_date(target)

    existing_status = fields.get("status")
    derived_status = status.derive_status(target.body)
    if existing_status != "superseded" and not (derived_status == "unknown" and existing_status is not None):
        fields["status"] = derived_status

    if rederive or "project" not in fields:
        project = _derive_project(target, sessions)
        if project:
            fields["project"] = project

    if rederive:
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
        if frontmatter.serialize(new_fields, target.body) == target.text:
            continue
        changed.append(target.id)
        if not dry_run:
            target.fields = new_fields
            plan_module.save(target, keep_mtime=True)
    return changed
