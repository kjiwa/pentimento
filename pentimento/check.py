"""Validate the plan corpus for lineage and vocabulary defects."""

from __future__ import annotations

import dataclasses

from pentimento import index as index_module

INTENT_VALUES = ("active", "queued", "someday", "abandoned", "unset")


@dataclasses.dataclass
class Finding:
    plan_id: str
    code: str
    message: str


def _dangling_parents(plans, by_id):
    return [p for p in plans if p.parent and p.parent not in by_id]


def _self_parents(plans):
    return [p for p in plans if p.parent == p.id]


def _cross_project_parents(plans, by_id):
    findings = []
    for p in plans:
        if not p.parent:
            continue
        parent = by_id.get(p.parent)
        if parent is None:
            continue
        if parent.project != p.project:
            findings.append(p)
    return findings


def _in_cycle(plan, by_id):
    seen = set()
    current = plan
    while current is not None and current.parent:
        if current.id in seen:
            return True
        seen.add(current.id)
        current = by_id.get(current.parent)
    return False


def _cycle_members(plans, by_id):
    return [p for p in plans if p.parent and _in_cycle(p, by_id)]


def _duplicate_ids(plans):
    seen = set()
    duplicates = []
    for p in plans:
        if p.id in seen:
            duplicates.append(p)
        else:
            seen.add(p.id)
    return duplicates


def _off_vocabulary_status(plans):
    return [p for p in plans if p.status not in index_module.STATUS_ORDER]


def _off_vocabulary_intent(plans):
    return [p for p in plans if p.intent not in INTENT_VALUES]


def run(plans) -> list[Finding]:
    """Return structured findings; an empty list means a clean corpus."""
    by_id = {p.id: p for p in plans}
    findings = []

    for p in _dangling_parents(plans, by_id):
        message = f"{p.id}: parent {p.parent!r} does not resolve to a plan"
        findings.append(Finding(p.id, "dangling-parent", message))
    for p in _self_parents(plans):
        findings.append(Finding(p.id, "self-parent", f"{p.id}: parent is itself"))
    for p in _cross_project_parents(plans, by_id):
        message = f"{p.id}: parent {p.parent!r} is in a different project"
        findings.append(Finding(p.id, "cross-project-parent", message))
    for p in _cycle_members(plans, by_id):
        message = f"{p.id}: parent chain cycles back to itself"
        findings.append(Finding(p.id, "cycle", message))
    for p in _duplicate_ids(plans):
        message = f"{p.id}: duplicate id across sources (second occurrence from {p.source})"
        findings.append(Finding(p.id, "duplicate-id", message))
    for p in _off_vocabulary_status(plans):
        message = f"{p.id}: status {p.status!r} is outside {index_module.STATUS_ORDER}"
        findings.append(Finding(p.id, "off-vocabulary-status", message))
    for p in _off_vocabulary_intent(plans):
        message = f"{p.id}: intent {p.intent!r} is outside {INTENT_VALUES}"
        findings.append(Finding(p.id, "off-vocabulary-intent", message))

    return findings
