"""Regression guard: no machine-local path should ever land in the repo.

Walks `git ls-files` rather than the working tree, so an untracked scratch
file never trips this, and covers everything `demo/capture.sh`'s
`$FIXTURE_DIR` `sed` normalization does not.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

_LEAK_RE = re.compile(r"/(?:Users|home)/([A-Za-z0-9_.-]+)")
_ALLOWED_USER = "user"


def _tracked_files() -> list[Path]:
    repo_root = Path(__file__).parent.parent
    output = subprocess.run(
        ["git", "ls-files"], cwd=repo_root, check=True, capture_output=True, text=True
    ).stdout
    return [repo_root / line for line in output.splitlines() if line]


def _is_binary(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:8000]
    except OSError:
        return True
    return b"\x00" in chunk


class NoLocalPathLeaksTests(unittest.TestCase):
    def test_no_tracked_text_file_names_a_real_home_directory(self):
        offenders = []
        for path in _tracked_files():
            if _is_binary(path):
                continue
            text = path.read_text(errors="ignore")
            for match in _LEAK_RE.finditer(text):
                if match.group(1) != _ALLOWED_USER:
                    offenders.append(f"{path}: {match.group(0)}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
