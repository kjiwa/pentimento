"""The field set shared by every output format."""

from __future__ import annotations

from pentimento import plan as plan_module

FIELDS = (
    "id",
    "title",
    "status",
    "intent",
    "tags",
    "parent",
    "project",
    "source",
    "created",
    "started",
    "modified",
    "path",
)


def as_dict(plan: plan_module.Plan) -> dict:
    return {
        "id": plan.id,
        "title": plan.title,
        "status": plan.status,
        "intent": plan.intent,
        "tags": plan.tags,
        "parent": plan.parent,
        "project": plan.project,
        "source": plan.source,
        "created": plan.fields.get("created"),
        "started": plan.started,
        "modified": plan.modified.astimezone().isoformat(),
        "path": str(plan.path),
    }
