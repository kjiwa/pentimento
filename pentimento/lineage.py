"""Derive a plan's parent from explicit references, never guessed.

Two signals, tried in order:
1. Session prompt -- plan ids referenced in the originating session's first
   user prompt, either as `<id>.md` / `<id>.plan.md` or by a trailing
   codename (a hyphen-aligned suffix, e.g. `wobbly-willow` for
   `...-wobbly-willow`). Underscore ids (Cursor) match only exactly.
2. Plan preamble -- the same reference scan over the body above the first
   `##` heading, so a parent's `## Progress` notes about executed children
   are not read as references.

Both are filtered by the same guards -- not the plan itself, same project,
same source, strictly earlier `started`. Within a tier, an exact `<id>.md`
reference outranks a codename reference, and within a group the earliest
mention wins; `max(started)` is only a fallback for a genuine positional
tie.
"""

from __future__ import annotations

import datetime
import re

from pentimento import shortid

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)+")

_EARLIEST = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)


def _preamble(body: str) -> str:
    lines = body.split("\n")
    for index, line in enumerate(lines):
        if line.startswith("## "):
            return "\n".join(lines[:index])
    return body


def _scan(text: str, candidate_ids):
    """Ordered `(position, id, exact)` for tokens that resolve to exactly one id."""
    hits = []
    for match in _TOKEN_RE.finditer(text):
        rest = text[match.end() :]
        exact = rest.startswith(".plan.md") or rest.startswith(".md")
        resolved = shortid.matches(candidate_ids, match.group())
        if len(resolved) != 1:
            continue
        hits.append((match.start(), resolved[0], exact))
    return hits


def _order(hits, by_id):
    """Ids best-first: exact before codename, then earliest mention, then newest `started`."""
    best = {}
    for position, candidate_id, exact in hits:
        key = (not exact, position)
        if candidate_id not in best or key < best[candidate_id]:
            best[candidate_id] = key
    ids = sorted(best, key=lambda cid: by_id[cid].created_at or _EARLIEST, reverse=True)
    ids.sort(key=lambda cid: best[cid])
    return ids


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
        if not (
            candidate.created_at and plan.created_at and candidate.created_at < plan.created_at
        ):
            continue
        eligible.append(candidate)
    return eligible


def references(plan, candidates, sessions, *, project=None) -> list[str]:
    """Ordered eligible reference ids, best first; empty when there is no signal."""
    if project is None:
        project = plan.project
    session = sessions.get(plan.id)
    by_id = {c.id: c for c in candidates}
    candidate_ids = list(by_id)

    prompt_hits = _scan(session.prompt, candidate_ids) if session else []
    preamble_hits = _scan(_preamble(plan.body), candidate_ids)

    for hits in (prompt_hits, preamble_hits):
        ordered_ids = _order(hits, by_id)
        eligible = _eligible(plan, ordered_ids, by_id, project)
        if eligible:
            return [c.id for c in eligible]
    return []


def derive_parent(plan, candidates, sessions, *, project=None) -> str | None:
    """`project` overrides `plan.project` for callers deriving it in the same pass."""
    ids = references(plan, candidates, sessions, project=project)
    return ids[0] if ids else None


def in_cycle(plan_id: str, parent_of: dict) -> bool:
    """True when following `parent_of` from `plan_id` returns to `plan_id`.

    A chain that runs into some other plan's cycle is not itself cyclic.
    """
    seen = set()
    current = parent_of.get(plan_id)
    while current is not None and current not in seen:
        if current == plan_id:
            return True
        seen.add(current)
        current = parent_of.get(current)
    return False
