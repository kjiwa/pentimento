"""Shortest-unique trailing-segment ids for the human tables.

Plan ids are hyphen-segmented, with the discriminating `adjective-noun` at
the end — or directly before a trailing `-of-<uuid>` session suffix — so the
shortest unique trailing run of segments is short and stable. Machine formats
and `show`'s `id:` line always use the full id.
"""

from __future__ import annotations

import collections
import re

MIN_SEGMENTS = 2

_UUID_SUFFIX = re.compile(r"-of-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _strip_uuid_suffix(plan_id: str) -> str:
    return _UUID_SUFFIX.sub("", plan_id)


def _trailing_runs(text: str) -> list[str]:
    segments = text.split("-")
    return ["-".join(segments[-count:]) for count in range(MIN_SEGMENTS, len(segments) + 1)]


def _candidates(plan_id: str) -> list[str]:
    """Trailing segment runs from shortest to longest, full id last."""
    base = _strip_uuid_suffix(plan_id)
    candidates = _trailing_runs(base) if base != plan_id else []
    candidates.extend(_trailing_runs(plan_id))
    if not candidates or candidates[-1] != plan_id:
        candidates.append(plan_id)
    return list(dict.fromkeys(candidates))


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


def _has_suffix(text: str, wanted: str) -> bool:
    return text == wanted or text.endswith("-" + wanted)


def _matches_id(plan_id: str, wanted: str) -> bool:
    if _has_suffix(plan_id, wanted):
        return True
    base = _strip_uuid_suffix(plan_id)
    return base != plan_id and _has_suffix(base, wanted)


def matches(ids, wanted: str) -> list[str]:
    """Full ids whose trailing segment run equals `wanted`, segment-aligned."""
    return [plan_id for plan_id in ids if _matches_id(plan_id, wanted)]
