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
    "status-behind-history": (
        "tick the plan's '## Progress', or pentimento history <id> "
        "then pentimento set <id> --status <value> (pins)"
    ),
    "status-behind-progress": f"pentimento backfill, or {_SET_STATUS}",
    "pin-behind-progress": f"{_SET_STATUS}, or pentimento set <id> --unpin",
    "unadopted-reference": "pentimento backfill, or leave it if the omission was deliberate",
    "unadopted-tag": "pentimento set <id> --add-tag <tag>",
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


def _skipped_files(skips):
    return [
        Finding("unreadable-file", path.name, f"could not read {path}: {exc}")
        for _source, path, exc in skips
    ]


def _dangling_parents(plans, by_id):
    return [
        Finding("dangling-parent", p.id, f"parent {p.parent!r} does not resolve to a plan")
        for p in plans
        if p.parent and p.parent not in by_id
    ]


def _self_parents(plans):
    return [Finding("self-parent", p.id, "parent is itself") for p in plans if p.parent == p.id]


def _cross_project_parents(plans, by_id):
    findings = []
    for p in plans:
        parent = by_id.get(p.parent)
        if parent is not None and parent.project != p.project:
            message = f"parent {p.parent!r} is in a different project"
            findings.append(Finding("cross-project-parent", p.id, message))
    return findings


def _cycle_members(plans):
    parent_of = {p.id: p.parent for p in plans}
    return [
        Finding("cycle", p.id, "parent chain cycles back to itself")
        for p in plans
        if p.parent and p.parent != p.id and lineage.in_cycle(p.id, parent_of)
    ]


def duplicate_ids(plans):
    seen = set()
    duplicates = []
    for p in plans:
        if p.id in seen:
            duplicates.append(p)
        else:
            seen.add(p.id)
    return duplicates


def _duplicate_ids(plans):
    return [
        Finding(
            "duplicate-id",
            p.id,
            f"duplicate id across sources (second occurrence from {p.source})",
        )
        for p in duplicate_ids(plans)
    ]


def _off_vocabulary_status(plans):
    allowed = ", ".join(vocabulary_module.STATUS_ORDER)
    return [
        Finding("off-vocabulary-status", p.id, f"status {p.status!r} is not one of {allowed}")
        for p in plans
        if p.status not in vocabulary_module.STATUS_ORDER
    ]


def _off_vocabulary_intent(plans):
    allowed = ", ".join(vocabulary_module.INTENT_VALUES)
    return [
        Finding("off-vocabulary-intent", p.id, f"intent {p.intent!r} is not one of {allowed}")
        for p in plans
        if p.intent not in vocabulary_module.INTENT_VALUES
    ]


def _missing_title(plans):
    return [
        Finding("missing-title", p.id, "body has no H1 title; falling back to the plan id")
        for p in plans
        if not p.has_title
    ]


def _malformed_tags(plans):
    findings = []
    for p in plans:
        bad = [t for t in p.tags if not tags_module.is_valid(t)]
        if bad:
            message = f"malformed tags {tags_module.render(bad)}"
            findings.append(Finding("malformed-tag", p.id, message))
    return findings


def _underived_project(plans, sessions, touches):
    findings = []
    for p in plans:
        session = sessions.get(touches_module.author(touches.get(p.id, []), p.id))
        if not p.project and session and session.project:
            message = f"session supplies project {session.project!r} but frontmatter has none"
            findings.append(Finding("underived-project", p.id, message))
    return findings


def _explicit(p):
    return p.pinned or p.status == vocabulary_module.SUPERSEDED


def _underivable_status(plans):
    findings = []
    for p in plans:
        if _explicit(p) or p.status != vocabulary_module.UNKNOWN:
            continue
        if status_module.derive_status(p.body, p.extras) != vocabulary_module.UNKNOWN:
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
    derived = status_module.derive_status(p.body, p.extras)
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


def _thread_tags(parent, tagged_siblings):
    shared = tags_module.normalized(parent.tags)
    for sibling in tagged_siblings:
        shared &= tags_module.normalized(sibling.tags)
    return sorted(shared)


def _unadopted_tags(plans, by_id):
    tagged_children = {}
    for p in plans:
        if p.tags and p.parent in by_id:
            tagged_children.setdefault(p.parent, []).append(p)
    findings = []
    for p in plans:
        parent = by_id.get(p.parent)
        siblings = tagged_children.get(p.parent)
        if p.tags or parent is None or not parent.tags or not siblings:
            continue
        shared = _thread_tags(parent, siblings)
        if shared:
            message = f"no tags, but its thread carries {tags_module.render(shared)}"
            findings.append(Finding("unadopted-tag", p.id, message))
    return findings


def run(plans, sessions=None, touches=None, skips=None) -> list[Finding]:
    """Return structured findings; an empty list means a clean corpus.

    `sessions`, when given, enables the `underived-project` finding; it
    stays silent by default so plans without a session, where an empty
    `project` is a legitimate state, are not flagged. `touches`,
    when given, enables `status-behind-history` the same way. `skips`, when
    given, is the `(source, path, error)` list `corpus.load_all` collected
    for files it could not read; each becomes an `unreadable-file` finding.
    `unadopted-tag` needs no input: an untagged plan whose tagged parent and
    tagged siblings share tags is the evidence.
    """
    sessions = sessions or {}
    touches = touches or {}
    by_id = {p.id: p for p in plans}
    return [
        *_skipped_files(skips or []),
        *_dangling_parents(plans, by_id),
        *_self_parents(plans),
        *_cross_project_parents(plans, by_id),
        *_cycle_members(plans),
        *_duplicate_ids(plans),
        *_off_vocabulary_status(plans),
        *_off_vocabulary_intent(plans),
        *_missing_title(plans),
        *_malformed_tags(plans),
        *_underivable_status(plans),
        *_underived_project(plans, sessions, touches),
        *_status_behind_history(plans, touches),
        *_status_behind_progress(plans),
        *_pin_behind_progress(plans),
        *_unadopted_reference(plans, sessions),
        *_unadopted_tags(plans, by_id),
    ]
