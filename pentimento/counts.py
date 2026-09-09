"""Pluralized counts for table-format command footers."""

from __future__ import annotations


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def summary(shown: int, total: int) -> str:
    if shown == total:
        return plural(total, "plan")
    return f"{shown} of {plural(total, 'plan')}"
