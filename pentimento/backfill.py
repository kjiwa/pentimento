"""Derive and write frontmatter for plans that don't have it."""

from __future__ import annotations

import datetime
from pathlib import Path

from pentimento import lineage, status
from pentimento import plan as plan_module


def _created_date(path: Path) -> str:
    stat = path.stat()
    ts = getattr(stat, "st_birthtime", stat.st_mtime)
    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).date().isoformat()


def derive_fields(target, candidates) -> dict[str, str]:
    """Fields to backfill for `target`, never overwriting existing ones."""
    fields = dict(target.fields)
    fields.setdefault("status", status.derive_status(target.body))
    fields.setdefault("intent", "unset")
    fields.setdefault("created", _created_date(target.path))

    if "parent" not in fields:
        parent_id, conflict = lineage.derive_parent(target, candidates)
        if parent_id and not conflict:
            fields["parent"] = parent_id
    return fields


def run(plans, *, dry_run: bool = False) -> list[str]:
    """Backfill frontmatter across `plans`. Returns ids that were changed."""
    changed = []
    for target in plans:
        new_fields = derive_fields(target, plans)
        if new_fields == target.fields:
            continue
        changed.append(target.id)
        if not dry_run:
            target.fields = new_fields
            plan_module.save(target)
    return changed
