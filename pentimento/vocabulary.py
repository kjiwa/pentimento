"""Corpus vocabulary: the fixed value sets for status and intent."""

from __future__ import annotations

STATUS_ORDER = ("not-started", "partial", "complete", "superseded", "unknown")
INTENT_VALUES = ("active", "queued", "someday", "abandoned", "unset")
