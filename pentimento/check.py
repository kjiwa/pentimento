"""Validate the plan corpus for lineage and vocabulary defects."""

from __future__ import annotations

import dataclasses

from pentimento import counts, lineage
from pentimento import status as status_module
from pentimento import tags as tags_module
from pentimento import touches as touches_module
from pentimento import vocabulary as vocabulary_module

_HISTORY_ELIGIBLE_STATUSES = vocabulary_module.UNWORKED_STATUSES


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


def duplicate_ids(plans):
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


def _status_behind_history(plans, touches):
    findings = []
    for p in plans:
        if p.status not in _HISTORY_ELIGIBLE_STATUSES:
            continue
        worked = touches_module.worked(touches.get(p.id, []), p.id)
        if not worked:
            continue
        sessions_worked = len({t.session for t in worked})
        message = (
            f"status {p.status!r} but "
            f"{counts.plural(sessions_worked, 'later session')} worked this plan; "
            f"see `pentimento history {p.id}`"
        )
        findings.append(Finding(p.id, "status-behind-history", message))
    return findings


_PROGRESS_RANK = {s: i for i, s in enumerate(vocabulary_module.PROGRESS_ORDER)}


def _status_behind_progress(plans):
    findings = []
    for p in plans:
        if p.pinned:
            continue
        if p.status not in _PROGRESS_RANK:
            continue
        derived = status_module.derive_status(p.body)
        if derived not in _PROGRESS_RANK:
            continue
        if _PROGRESS_RANK[derived] <= _PROGRESS_RANK[p.status]:
            continue
        message = (
            f"status {p.status!r} but '## Progress' derives {derived!r}; run pentimento backfill"
        )
        findings.append(Finding(p.id, "status-behind-progress", message))
    return findings


def _pin_diverged(plans):
    findings = []
    for p in plans:
        if not p.pinned:
            continue
        derived = status_module.derive_status(p.body)
        if derived == p.status:
            continue
        message = f"pinned status {p.status!r} disagrees with derived {derived!r}"
        findings.append(Finding(p.id, "pin-diverged", message))
    return findings


def _unadopted_reference(plans, sessions):
    findings = []
    for p in plans:
        if p.parent:
            continue
        ids = lineage.references(p, plans, sessions)
        if not ids:
            continue
        message = f"no parent, but {ids[0]!r} is an eligible reference; run pentimento backfill"
        findings.append(Finding(p.id, "unadopted-reference", message))
    return findings


def run(plans, sessions=None, touches=None, skips=None) -> list[Finding]:
    """Return structured findings; an empty list means a clean corpus.

    `sessions`, when given, enables the `underived-project` finding; it
    stays silent by default so Cursor plans and session-less plans, where
    an empty `project` is a legitimate state, are not flagged. `touches`,
    when given, enables `status-behind-history` the same way. `skips`, when
    given, is the `(source, path, error)` list `corpus.load_all` collected
    for files it could not read; each becomes an `unreadable-file` finding.
    """
    sessions = sessions or {}
    touches = touches or {}
    skips = skips or []
    by_id = {p.id: p for p in plans}
    findings = []

    for _source, path, exc in skips:
        message = f"could not read {path}: {exc}"
        findings.append(Finding(path.name, "unreadable-file", message))

    for p in _dangling_parents(plans, by_id):
        message = f"parent {p.parent!r} does not resolve to a plan"
        findings.append(Finding(p.id, "dangling-parent", message))
    for p in _self_parents(plans):
        findings.append(Finding(p.id, "self-parent", "parent is itself"))
    for p in _cross_project_parents(plans, by_id):
        message = f"parent {p.parent!r} is in a different project"
        findings.append(Finding(p.id, "cross-project-parent", message))
    for p in _cycle_members(plans, by_id):
        message = "parent chain cycles back to itself"
        findings.append(Finding(p.id, "cycle", message))
    for p in duplicate_ids(plans):
        message = f"duplicate id across sources (second occurrence from {p.source})"
        findings.append(Finding(p.id, "duplicate-id", message))
    for p in _off_vocabulary_status(plans):
        message = f"status {p.status!r} is outside {vocabulary_module.STATUS_ORDER}"
        findings.append(Finding(p.id, "off-vocabulary-status", message))
    for p in _off_vocabulary_intent(plans):
        message = f"intent {p.intent!r} is outside {vocabulary_module.INTENT_VALUES}"
        findings.append(Finding(p.id, "off-vocabulary-intent", message))
    for p in _missing_title(plans):
        message = "body has no H1 title; falling back to the plan id"
        findings.append(Finding(p.id, "missing-title", message))
    for p in _malformed_tags(plans):
        bad = [t for t in p.tags if not tags_module.is_valid(t)]
        message = f"malformed tag(s) {bad!r}"
        findings.append(Finding(p.id, "malformed-tag", message))
    for p in _missing_progress(plans):
        message = "body has no '## Progress' heading; status can't be derived"
        findings.append(Finding(p.id, "missing-progress", message))
    for p in _underived_project(plans, sessions):
        message = f"session supplies project {sessions[p.id].project!r} but frontmatter has none"
        findings.append(Finding(p.id, "underived-project", message))
    findings.extend(_status_behind_history(plans, touches))
    findings.extend(_status_behind_progress(plans))
    findings.extend(_pin_diverged(plans))
    findings.extend(_unadopted_reference(plans, sessions))

    return findings
