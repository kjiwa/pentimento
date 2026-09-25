"""Every shell file in the repo parses under its own shell, and `.sh` and
`.bash` files pass shellcheck. A tool that is not installed skips its test.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent


def _files(*suffixes: str) -> list[str]:
    output = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line for line in output.splitlines() if line.endswith(suffixes)]


def _failures(command: list[str], paths: list[str]) -> list[str]:
    failures = []
    for path in paths:
        result = subprocess.run(
            [*command, path], cwd=_REPO_ROOT, capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            failures.append(f"{path}:\n{result.stdout}{result.stderr}")
    return failures


class ShellFileTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("shellcheck"), "shellcheck is not installed")
    def test_sh_and_bash_files_pass_shellcheck(self):
        paths = _files(".sh", ".bash")
        self.assertTrue(paths)
        self.assertEqual([], _failures(["shellcheck"], paths))

    @unittest.skipUnless(shutil.which("zsh"), "zsh is not installed")
    def test_zsh_files_parse(self):
        paths = _files(".zsh")
        self.assertTrue(paths)
        self.assertEqual([], _failures(["zsh", "-n"], paths))

    @unittest.skipUnless(shutil.which("fish"), "fish is not installed")
    def test_fish_files_parse(self):
        paths = _files(".fish")
        self.assertTrue(paths)
        self.assertEqual([], _failures(["fish", "--no-execute"], paths))


if __name__ == "__main__":
    unittest.main()
