"""No GitHub Actions expression is interpolated into a `run:` script; event
fields reach scripts through `env:` so the shell never parses them.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_RUN = re.compile(r"^(\s*)(?:- )?run:\s*(.*)$")


def _workflows() -> list[str]:
    output = subprocess.run(
        ["git", "ls-files", ".github/workflows"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line for line in output.splitlines() if line.endswith((".yml", ".yaml"))]


def _interpolated_run_lines(text: str) -> list[str]:
    hits = []
    block_indent = None
    for line in text.splitlines():
        if block_indent is not None:
            indent = len(line) - len(line.lstrip())
            if line.strip() and indent <= block_indent:
                block_indent = None
            elif "${{" in line:
                hits.append(line.strip())
                continue
        match = _RUN.match(line)
        if match is None:
            continue
        if match.group(2) in ("|", ">", "|-", ">-"):
            block_indent = len(match.group(1)) + (2 if line.lstrip().startswith("- ") else 0)
        elif "${{" in match.group(2):
            hits.append(line.strip())
    return hits


class WorkflowTests(unittest.TestCase):
    def test_run_scripts_do_not_interpolate_expressions(self):
        paths = _workflows()
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(path=path):
                text = (_REPO_ROOT / path).read_text(encoding="utf-8")
                self.assertEqual([], _interpolated_run_lines(text))
