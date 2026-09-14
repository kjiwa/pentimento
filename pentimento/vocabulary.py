"""Corpus vocabulary: the fixed value sets for status and intent."""

from __future__ import annotations

NOT_STARTED = "not-started"
PARTIAL = "partial"
COMPLETE = "complete"
SUPERSEDED = "superseded"
UNKNOWN = "unknown"

ACTIVE = "active"
QUEUED = "queued"
SOMEDAY = "someday"
ABANDONED = "abandoned"
UNSET = "unset"

# Display order: superseded/unknown sort above complete.
STATUS_ORDER = (NOT_STARTED, PARTIAL, COMPLETE, SUPERSEDED, UNKNOWN)
# The monotonic subset derivation may advance a plan's status along.
PROGRESS_ORDER = (NOT_STARTED, PARTIAL, COMPLETE)
INTENT_VALUES = (ACTIVE, QUEUED, SOMEDAY, ABANDONED, UNSET)
STARRED_INTENTS = (ACTIVE, QUEUED)
UNWORKED_STATUSES = (NOT_STARTED, UNKNOWN)
DEFAULT_STATUS, DEFAULT_INTENT = UNKNOWN, UNSET
