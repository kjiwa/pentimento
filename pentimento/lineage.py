"""Derive a plan's parent from body references and filename-slug containment.

Auto-generated plan filenames are `<slugified-prompt>-<adjective>-<noun>`.
When a plan resumes an earlier one, the prompt (and therefore the slug)
embeds a truncated prefix of the parent's own slug body -- see the design
plan's example: `resume-planning-ses` inside a child's filename is a prefix
of the parent's `resume-planning-session-users-kjiwa-clau`.

Two signals, never guessed when they disagree:
1. Body reference to another plan's `<id>.md`; nearest preceding by mtime
   wins among several matches.
2. Filename slug containment: the longest prefix of another candidate's
   slug body that appears verbatim inside this plan's id.
"""

from __future__ import annotations

import re

MIN_SLUG_PREFIX = 12


def slug_body(plan_id: str) -> str:
    """Plan id with its trailing <adjective>-<noun> suffix stripped."""
    tokens = plan_id.split("-")
    if len(tokens) > 2:
        return "-".join(tokens[:-2])
    return plan_id


def _body_reference_matches(plan, candidates):
    matches = []
    for candidate in candidates:
        if candidate.id == plan.id:
            continue
        if re.search(re.escape(candidate.id) + r"\.md", plan.body):
            matches.append(candidate)
    return matches


def _nearest_preceding(plan, matches):
    preceding = [c for c in matches if c.mtime < plan.mtime]
    pool = preceding or matches
    return min(pool, key=lambda c: abs(plan.mtime - c.mtime))


def _slug_containment_match(plan, candidates):
    best = None
    best_length = 0
    for candidate in candidates:
        if candidate.id == plan.id:
            continue
        body = slug_body(candidate.id)
        for length in range(len(body), MIN_SLUG_PREFIX - 1, -1):
            if body[:length] in plan.id:
                if length > best_length:
                    best = candidate
                    best_length = length
                break
    return best


def derive_parent(plan, candidates) -> tuple[str | None, bool]:
    """Returns (parent_id or None, conflict).

    conflict is True when both signals fire but disagree; parent is then
    left unset rather than guessed.
    """
    body_matches = _body_reference_matches(plan, candidates)
    body_parent = _nearest_preceding(plan, body_matches).id if body_matches else None
    slug_match = _slug_containment_match(plan, candidates)
    slug_parent = slug_match.id if slug_match else None

    if body_parent and slug_parent:
        if body_parent == slug_parent:
            return body_parent, False
        return None, True
    return body_parent or slug_parent, False
