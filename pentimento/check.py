"""Validate the plan corpus for lineage and vocabulary defects."""

from __future__ import annotations

import dataclasses

from pentimento import counts, lineage
from pentimento import status as status_module
from pentimento import tags as tags_module
from pentimento import touches as touches_module
from pentimento import vocabulary as vocabulary_module

_HISTORY_ELIGIBLE_STATUSES = vocabulary_module.UNWORKED_STATUSES

_REVIEW_FIRST = "pentimento show <id>, then "
_SET_STATUS = f"{_REVIEW_FIRST}pentimento set <id> --status <value>"

HINTS = {
    "unreadable-file": "check the file's permissions and encoding",
    "dangling-parent": "pentimento set <id> --parent <id>, or --clear-parent",
    "self-parent": "pentimento set <id> --clear-parent",
    "cross-project-parent": "pentimento set <id> --project <name> on whichever plan is wrong",
    "cycle": "pentimento set <id> --parent <id>, or --clear-parent, on one plan in the chain",
    "duplicate-id": "rename one of the files",
    "off-vocabulary-status": "pentimento set <id> --status <value>",
    "off-vocabulary-intent": "pentimento set <id> --intent <value>",
    "missing-title": "add a '# Title' line to the plan body",
    "malformed-tag": "pentimento set <id> --remove-tag <bad> --add-tag <fixed>",
    "underived-project": "pentimento backfill",
    "underivable-status": f"add a checklist to '## Progress', or {_SET_STATUS}",
    "status-behind-history": "pentimento history <id>, then pentimento set <id> --status <value>",
    "status-behind-progress": f"pentimento backfill, or {_SET_STATUS}",
    "pin-behind-progress": f"{_SET_STATUS}, or pentimento set <id> --unpin",
    "unadopted-reference": "pentimento backfill, or leave it if the omission was deliberate",
}


def show_hint(code: str) -> str:
    """`HINTS[code]` for a reader already in `pentimento show`."""
    return HINTS[code].replace(_REVIEW_FIRST, "")


@dataclasses.dataclass
class Finding:
    code: str
    id: str
    message: str
    hint: str = dataclasses.field(init=False)

    def __post_init__(self):
        self.hint = HINTS[self.code]


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


def _underived_project(plans, sessions):
    findings = []
    for p in plans:
        if p.project:
            continue
        session = sessions.get(p.id)
        if session and session.project:
            findings.append(p)
    return findings


def _explicit(p):
    return p.pinned or p.status == vocabulary_module.SUPERSEDED


def _underivable_status(plans):
    findings = []
    for p in plans:
        if _explicit(p) or p.status != vocabulary_module.UNKNOWN:
            continue
        if status_module.derive_status(p.body) != vocabulary_module.UNKNOWN:
            continue
        if status_module.progress_section(p.body) is None:
            message = "no '## Progress' heading and no checkboxes in the body"
        else:
            message = "'## Progress' has no checkboxes or recognized phrase"
        findings.append(Finding("underivable-status", p.id, message))
    return findings


def _status_behind_history(plans, touches):
    findings = []
    for p in plans:
        if _explicit(p) or p.status not in _HISTORY_ELIGIBLE_STATUSES:
            continue
        worked = touches_module.worked(touches.get(p.id, []), p.id)
        if not worked:
            continue
        sessions_worked = len({t.session for t in worked})
        message = (
            f"status {p.status!r} but "
            f"{counts.plural(sessions_worked, 'later session')} worked this plan"
        )
        findings.append(Finding("status-behind-history", p.id, message))
    return findings


def _behind_progress(p):
    derived = status_module.derive_status(p.body)
    if status_module.rank(derived) > status_module.rank(p.status):
        return derived
    return None


def _status_behind_progress(plans):
    findings = []
    for p in plans:
        if _explicit(p):
            continue
        derived = _behind_progress(p)
        if derived:
            message = f"status {p.status!r} but '## Progress' derives {derived!r}"
            findings.append(Finding("status-behind-progress", p.id, message))
    return findings


def _pin_behind_progress(plans):
    findings = []
    for p in plans:
        if not p.pinned or p.status == vocabulary_module.SUPERSEDED:
            continue
        derived = _behind_progress(p)
        if derived:
            message = f"pinned status {p.status!r} but '## Progress' derives {derived!r}"
            findings.append(Finding("pin-behind-progress", p.id, message))
    return findings


def _unadopted_reference(plans, sessions):
    findings = []
    for p in plans:
        if p.parent:
            continue
        ids = lineage.references(p, plans, sessions)
        if not ids:
            continue
        message = f"no parent, but {ids[0]!r} is an eligible reference"
        findings.append(Finding("unadopted-reference", p.id, message))
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
        findings.append(Finding("unreadable-file", path.name, message))

    for p in _dangling_parents(plans, by_id):
        message = f"parent {p.parent!r} does not resolve to a plan"
        findings.append(Finding("dangling-parent", p.id, message))
    for p in _self_parents(plans):
        findings.append(Finding("self-parent", p.id, "parent is itself"))
    for p in _cross_project_parents(plans, by_id):
        message = f"parent {p.parent!r} is in a different project"
        findings.append(Finding("cross-project-parent", p.id, message))
    for p in _cycle_members(plans, by_id):
        message = "parent chain cycles back to itself"
        findings.append(Finding("cycle", p.id, message))
    for p in duplicate_ids(plans):
        message = f"duplicate id across sources (second occurrence from {p.source})"
        findings.append(Finding("duplicate-id", p.id, message))
    for p in _off_vocabulary_status(plans):
        message = f"status {p.status!r} is outside {vocabulary_module.STATUS_ORDER}"
        findings.append(Finding("off-vocabulary-status", p.id, message))
    for p in _off_vocabulary_intent(plans):
        message = f"intent {p.intent!r} is outside {vocabulary_module.INTENT_VALUES}"
        findings.append(Finding("off-vocabulary-intent", p.id, message))
    for p in _missing_title(plans):
        message = "body has no H1 title; falling back to the plan id"
        findings.append(Finding("missing-title", p.id, message))
    for p in _malformed_tags(plans):
        bad = [t for t in p.tags if not tags_module.is_valid(t)]
        message = f"malformed tag(s) {bad!r}"
        findings.append(Finding("malformed-tag", p.id, message))
    findings.extend(_underivable_status(plans))
    for p in _underived_project(plans, sessions):
        message = f"session supplies project {sessions[p.id].project!r} but frontmatter has none"
        findings.append(Finding("underived-project", p.id, message))
    findings.extend(_status_behind_history(plans, touches))
    findings.extend(_status_behind_progress(plans))
    findings.extend(_pin_behind_progress(plans))
    findings.extend(_unadopted_reference(plans, sessions))

    return findings
