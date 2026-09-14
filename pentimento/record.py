"""The field set shared by every output format."""

from __future__ import annotations

from pentimento import plan as plan_module

_ACCESSORS = {
    "id": lambda p: p.id,
    "title": lambda p: p.title,
    "status": lambda p: p.status,
    "intent": lambda p: p.intent,
    "tags": lambda p: p.tags,
    "parent": lambda p: p.parent,
    "project": lambda p: p.project,
    "source": lambda p: p.source,
    "created": lambda p: p.fields.get("created"),
    "started": lambda p: p.started,
    "modified": lambda p: p.modified.astimezone().isoformat(),
    "path": lambda p: str(p.path),
}

FIELDS = tuple(_ACCESSORS)


def as_dict(plan: plan_module.Plan) -> dict:
    return {field: accessor(plan) for field, accessor in _ACCESSORS.items()}
