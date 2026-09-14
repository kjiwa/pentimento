"""Shortest-unique trailing-segment ids for the human tables.

Plan ids are hyphen-segmented (`is-it-possible-to-abundant-rabbit`). The
generated ids put the discriminating `adjective-noun` at the end, so the
shortest unique *suffix* run of segments is both short and stable -- unlike
a shortest-unique-prefix scheme, which yields stubs like `a-co`. Machine
formats and `show`'s `id:` line always use the full id; this module only
feeds the display tables (`list`, `check`, `tree`).
"""

from __future__ import annotations

import collections

MIN_SEGMENTS = 2


def _candidates(plan_id: str) -> list[str]:
    """Trailing segment runs from shortest to longest, full id last."""
    segments = plan_id.split("-")
    candidates = [
        "-".join(segments[-count:]) for count in range(MIN_SEGMENTS, len(segments))
    ]
    candidates.append(plan_id)
    return candidates


def shorten(ids) -> dict[str, str]:
    """Shortest unique trailing-segment run per id, falling back to the full id."""
    ids = list(ids)
    per_id_candidates = [(plan_id, _candidates(plan_id)) for plan_id in ids]

    counts: collections.Counter[str] = collections.Counter()
    for _, candidates in per_id_candidates:
        counts.update(set(candidates))

    result = {}
    for plan_id, candidates in per_id_candidates:
        result[plan_id] = next((c for c in candidates if counts[c] == 1), plan_id)
    return result


def matches(ids, wanted: str) -> list[str]:
    """Full ids whose trailing segment run equals `wanted`, segment-aligned."""
    return [plan_id for plan_id in ids if plan_id == wanted or plan_id.endswith("-" + wanted)]
