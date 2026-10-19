from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
CURSOR_HOOKS = ROOT / "integrations" / "cursor" / "hooks.json"
STOP_PAYLOAD = ROOT / "tests" / "fixtures" / "cursor" / "stop-completed.json"


ANTIGRAVITY_HOOKS = ROOT / "integrations" / "antigravity" / "hooks.json"
ANTIGRAVITY_FIXTURES = ROOT / "tests" / "fixtures" / "antigravity"


class AntigravityHooksTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(ANTIGRAVITY_HOOKS.read_text())
        (self.group,) = self.config["pentimento"]["PostToolUse"]

    def test_config_shape(self):
        self.assertEqual(list(self.config), ["pentimento"])
        self.assertEqual(list(self.config["pentimento"]), ["PostToolUse"])
        self.assertEqual(self.group["hooks"], [{"command": "pentimento hook"}])

    def test_matcher_covers_the_plan_write_tools_seen_in_payloads(self):
        names = set()
        for path in ANTIGRAVITY_FIXTURES.glob("post-tool-use-write*.json"):
            names.add(json.loads(path.read_text())["toolCall"]["name"])
        self.assertTrue(names)
        for name in names:
            self.assertRegex(name, f"^(?:{self.group['matcher']})$")


class CursorHooksTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(CURSOR_HOOKS.read_text())
        self.command = self.config["hooks"]["stop"][0]["command"]

    def test_config_shape(self):
        self.assertEqual(self.config["version"], 1)
        self.assertEqual(list(self.config["hooks"]), ["stop"])
        self.assertEqual(len(self.config["hooks"]["stop"]), 1)

    def test_command_form(self):
        self.assertIn("pentimento backfill --quiet", self.command)
        self.assertIn("echo '{}'", self.command)

    def _run(self, tmp: str, command: str, **env_overrides: str) -> subprocess.CompletedProcess:
        env = dict(
            os.environ,
            **env_overrides,
            PYTHONPATH=str(ROOT),
            AGENT_PLANS_DIR=tmp,
            CURSOR_PLANS_DIR=tmp,
            ANTIGRAVITY_BRAIN_DIR=str(Path(tmp) / "no-such-brain-dir"),
            CURSOR_SESSIONS_DIR=tmp,
            AGENT_SESSIONS_DIR=tmp,
            XDG_CACHE_HOME=str(Path(tmp) / "cache"),
        )
        return subprocess.run(
            ["/bin/sh", "-c", command],
            input=STOP_PAYLOAD.read_text(),
            capture_output=True,
            text=True,
            env=env,
            cwd=ROOT,
        )

    def test_command_prints_only_json_and_exits_zero(self):
        command = self.command.replace("pentimento", f"{sys.executable} -m pentimento", 1)
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(tmp, command)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "{}\n")

    def test_missing_pentimento_exits_one_with_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(tmp, self.command, PATH=tmp)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertNotEqual(result.stderr, "")

    def test_bare_backfill_with_stop_payload_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(tmp, f"{sys.executable} -m pentimento backfill --quiet")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
