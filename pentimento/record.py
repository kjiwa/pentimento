"""The field set shared by every output format."""

from __future__ import annotations

from pentimento import plan as plan_module


def as_dict(plan: plan_module.Plan) -> dict:
    return {
        "id": plan.id,
        "title": plan.title,
        "status": plan.status,
        "intent": plan.intent,
        "parent": plan.parent,
        "project": plan.project,
        "created": plan.fields.get("created"),
        "started": plan.started,
        "path": str(plan.path),
    }
