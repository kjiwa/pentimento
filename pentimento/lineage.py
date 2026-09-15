"""Derive a plan's parent from explicit references, never guessed.

Two signals, tried in order:
1. Session prompt -- plan ids referenced as `<id>.md` in the originating
   session's first user prompt.
2. Plan preamble -- the same reference scan over the body above the first
   `##` heading, so a parent's `## Progress` notes about executed children
   can no longer make those children its parents.

Both are filtered by the same guards -- not the plan itself, same project,
same source, strictly earlier `started` -- and the newest surviving
candidate wins.
"""

from __future__ import annotations


def _preamble(body: str) -> str:
    lines = body.split("\n")
    for index, line in enumerate(lines):
        if line.startswith("## "):
            return "\n".join(lines[:index])
    return body


def _referenced_ids(text: str, candidates) -> set[str]:
    return {
        candidate.id
        for candidate in candidates
        if candidate.id + ".md" in text or candidate.id + ".plan.md" in text
    }


def _eligible(plan, candidate_ids, by_id, project):
    eligible = []
    for candidate_id in candidate_ids:
        candidate = by_id.get(candidate_id)
        if candidate is None or candidate.id == plan.id:
            continue
        if candidate.project != project:
            continue
        if candidate.source != plan.source:
            continue
        if not (candidate.started and plan.started and candidate.started < plan.started):
            continue
        eligible.append(candidate)
    return eligible


def derive_parent(plan, candidates, sessions, *, project=None) -> str | None:
    """`project` overrides `plan.project` for callers deriving it in the same pass."""
    if project is None:
        project = plan.project
    session = sessions.get(plan.id)
    prompt_ids = _referenced_ids(session.prompt, candidates) if session else set()
    preamble_ids = _referenced_ids(_preamble(plan.body), candidates)
    by_id = {c.id: c for c in candidates}

    for reference_ids in (prompt_ids, preamble_ids):
        eligible = _eligible(plan, reference_ids, by_id, project)
        if eligible:
            return max(eligible, key=lambda c: c.started).id
    return None
