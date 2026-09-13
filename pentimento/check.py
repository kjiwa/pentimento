"""Validate the plan corpus for lineage and vocabulary defects."""

from __future__ import annotations

import dataclasses

from pentimento import status as status_module
from pentimento import tags as tags_module
from pentimento import vocabulary as vocabulary_module


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
    if plan.parent == plan.id:
        return False
    seen = set()
    current = plan
    while current is not None and current.parent:
        if current.id in seen:
            return current.id == plan.id
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
    return [p for p in plans if p.status not in vocabulary_module.STATUS_ORDER]


def _off_vocabulary_intent(plans):
    return [p for p in plans if p.intent not in vocabulary_module.INTENT_VALUES]


def _missing_title(plans):
    return [p for p in plans if not p.has_title]


def _malformed_tags(plans):
    return [p for p in plans if any(not tags_module.is_valid(t) for t in p.tags)]


def _missing_progress(plans):
    return [p for p in plans if status_module.progress_section(p.body) is None]


def _underived_project(plans, sessions):
    findings = []
    for p in plans:
        if p.project:
            continue
        session = sessions.get(p.id)
        if session and session.project:
            findings.append(p)
    return findings


def run(plans, sessions=None) -> list[Finding]:
    """Return structured findings; an empty list means a clean corpus.

    `sessions`, when given, enables the `underived-project` finding; it
    stays silent by default so Cursor plans and session-less plans, where
    an empty `project` is a legitimate state, are not flagged.
    """
    sessions = sessions or {}
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
        message = f"{p.id}: status {p.status!r} is outside {vocabulary_module.STATUS_ORDER}"
        findings.append(Finding(p.id, "off-vocabulary-status", message))
    for p in _off_vocabulary_intent(plans):
        message = f"{p.id}: intent {p.intent!r} is outside {vocabulary_module.INTENT_VALUES}"
        findings.append(Finding(p.id, "off-vocabulary-intent", message))
    for p in _missing_title(plans):
        message = f"{p.id}: body has no H1 title; falling back to the plan id"
        findings.append(Finding(p.id, "missing-title", message))
    for p in _malformed_tags(plans):
        bad = [t for t in p.tags if not tags_module.is_valid(t)]
        message = f"{p.id}: malformed tag(s) {bad!r}"
        findings.append(Finding(p.id, "malformed-tag", message))
    for p in _missing_progress(plans):
        message = f"{p.id}: body has no '## Progress' heading; status can't be derived"
        findings.append(Finding(p.id, "missing-progress", message))
    for p in _underived_project(plans, sessions):
        message = f"{p.id}: session supplies project {sessions[p.id].project!r} but frontmatter has none"
        findings.append(Finding(p.id, "underived-project", message))

    return findings
