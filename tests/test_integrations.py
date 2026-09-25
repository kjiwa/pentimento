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


class CursorHooksTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(CURSOR_HOOKS.read_text())
        self.command = self.config["hooks"]["stop"][0]["command"]

    def test_config_shape(self):
        self.assertEqual(self.config["version"], 1)
        self.assertEqual(list(self.config["hooks"]), ["stop"])
        self.assertEqual(len(self.config["hooks"]["stop"]), 1)

    def test_command_form(self):
        self.assertTrue(self.command.startswith("pentimento backfill --quiet"))
        self.assertTrue(self.command.endswith("echo '{}'"))

    def test_command_prints_only_json_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, PYTHONPATH=str(ROOT),
                       AGENT_PLANS_DIR=tmp, CURSOR_PLANS_DIR=tmp,
                       AGENT_SESSIONS_DIR=tmp)
            command = self.command.replace(
                "pentimento", f"{sys.executable} -m pentimento", 1)
            result = subprocess.run(
                ["sh", "-c", command], input=STOP_PAYLOAD.read_text(),
                capture_output=True, text=True, env=env, cwd=ROOT)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "{}\n")


if __name__ == "__main__":
    unittest.main()
